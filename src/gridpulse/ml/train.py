"""Train, evaluate and (optionally) register the day-ahead price models."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gridpulse.ml.features import FEATURE_SETS, TARGET, build_features

# The model predicts the CHANGE versus the same hour yesterday, not the price level. Trees cannot
# extrapolate beyond the price levels seen in training, and the level drifts with gas/CO2 prices
# (test-period mean was ~48% above the training mean). Chosen on the validation window only.
ANCHOR = "price_lag_24"

LGBM_PARAMS = {
    "objective": "regression",  # best on validation vs regression_l1
    "n_estimators": 2000,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 40,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "verbose": -1,
}


@dataclass
class ModelResult:
    name: str
    feature_set: str
    metrics: dict
    model: object
    features: list[str]
    importance: dict = field(default_factory=dict)


def _metrics(y: pd.Series, pred: pd.Series) -> dict:
    err = (y - pred).to_numpy()
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "n": int(len(y)),
    }


def split_time(feat: pd.DataFrame, test_days: int, val_days: int = 60):
    """Chronological split: train | validation (early stopping) | test (never used in fitting)."""
    last = feat["ts_utc"].max()
    test_start = last.normalize() - pd.Timedelta(days=test_days - 1)
    val_start = test_start - pd.Timedelta(days=val_days)
    train = feat[feat["ts_utc"] < val_start]
    val = feat[(feat["ts_utc"] >= val_start) & (feat["ts_utc"] < test_start)]
    test = feat[feat["ts_utc"] >= test_start]
    return train, val, test


def train_and_evaluate(df: pd.DataFrame, test_days: int = 90, params: dict | None = None):
    """Returns (results, backtest). Baselines are evaluated on exactly the same test rows."""
    import lightgbm as lgb

    feat = build_features(df)
    feat = feat.dropna(subset=[TARGET, "price_lag_168"])  # drop warm-up rows
    train, val, test = split_time(feat, test_days)
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("not enough history for the requested split")

    results: list[ModelResult] = []
    backtest = test[["ts_utc", TARGET]].rename(columns={TARGET: "actual"}).copy()

    # baselines: same hour yesterday / same hour last week (both known at auction time)
    for name, col in [("naive_24h", "price_lag_24"), ("naive_168h", "price_lag_168")]:
        ok = test[col].notna()
        backtest[f"pred_{name}"] = test[col]
        results.append(
            ModelResult(
                name, "baseline", _metrics(test.loc[ok, TARGET], test.loc[ok, col]), None, []
            )
        )

    for set_name, cols in FEATURE_SETS.items():
        tr, va = train.dropna(subset=[ANCHOR]), val.dropna(subset=[ANCHOR])
        model = lgb.LGBMRegressor(**{**LGBM_PARAMS, **(params or {})})
        model.fit(
            tr[cols],
            tr[TARGET] - tr[ANCHOR],
            eval_set=[(va[cols], va[TARGET] - va[ANCHOR])],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        pred = pd.Series(model.predict(test[cols]), index=test.index) + test[ANCHOR]
        backtest[f"pred_lgbm_{set_name}"] = pred
        ok = pred.notna()
        m = _metrics(test.loc[ok, TARGET], pred[ok])
        m["best_iteration"] = int(model.best_iteration_ or model.n_estimators)
        results.append(
            ModelResult(
                f"lgbm_{set_name}",
                set_name,
                m,
                model,
                cols,
                dict(zip(cols, map(float, model.booster_.feature_importance("gain")), strict=True)),
            )
        )

    base = next(r for r in results if r.name == "naive_24h").metrics["mae"]
    for r in results:
        r.metrics["mae_skill_vs_naive_24h"] = 1 - r.metrics["mae"] / base
    return results, backtest.reset_index(drop=True)
