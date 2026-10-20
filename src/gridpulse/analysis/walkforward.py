"""Expanding-window walk-forward evaluation, retraining every calendar month.

Why: a single 90-day test window (the model card) gives wide intervals and one season. Here every
month of the last year is predicted by models trained only on the past, giving ~8,700 out-of-sample
hours. Three LightGBM models per fold: mean, 10% and 90% quantile (a prediction interval), all on
the same target as the main model (change versus the same hour yesterday).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gridpulse.ml.features import FEATURE_SETS, TARGET, WEATHER, build_features
from gridpulse.ml.train import ANCHOR, LGBM_PARAMS

QUANTILES = (0.1, 0.9)
# Test-time noise added to the weather inputs, as a fraction of each feature's training std, to
# mimic an imperfect weather FORECAST. Not calibrated to real forecast errors (none are available
# historically here): it shows how fast the gain decays, not what the real gain will be.
NOISE_LEVELS = (0.25, 0.5, 1.0)


@dataclass
class Fold:
    month: pd.Timestamp
    n_train: int
    n_test: int
    best_iterations: dict


def _fit(lgb, params, X, y, Xv, yv):
    model = lgb.LGBMRegressor(**params)
    model.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(100, verbose=False)])
    return model


def walk_forward(
    df: pd.DataFrame,
    first_test_month: str = "2025-10-01",
    n_months: int = 12,
    val_days: int = 60,
    quantiles: tuple = QUANTILES,
    noise_levels: tuple = NOISE_LEVELS,
    params: dict | None = None,
    extra_features: list[str] | None = None,
    progress=None,
) -> tuple[pd.DataFrame, list[Fold]]:
    """Return one row per out-of-sample hour with every model's prediction, plus fold metadata."""
    import lightgbm as lgb

    feat = build_features(df).dropna(subset=[TARGET, "price_lag_168", ANCHOR])
    base = {**LGBM_PARAMS, **(params or {})}
    cal, wx = (
        FEATURE_SETS["calendar_lags"],
        FEATURE_SETS["with_weather"] + list(extra_features or []),
    )
    weather_cols = [c for c in wx if c in WEATHER]  # noise applies to weather only
    rng = np.random.default_rng(42)
    rows, folds = [], []
    start = pd.Timestamp(first_test_month, tz="UTC")
    for k in range(n_months):
        m0 = start + pd.DateOffset(months=k)
        m1 = start + pd.DateOffset(months=k + 1)
        test = feat[(feat["ts_utc"] >= m0) & (feat["ts_utc"] < m1)]
        past = feat[feat["ts_utc"] < m0]
        if test.empty or len(past) < 24 * (val_days + 120):
            continue
        val_start = m0 - pd.Timedelta(days=val_days)
        tr, va = past[past["ts_utc"] < val_start], past[past["ts_utc"] >= val_start]
        yt, yv = tr[TARGET] - tr[ANCHOR], va[TARGET] - va[ANCHOR]
        out = test[["ts_utc", TARGET, ANCHOR, "price_lag_168"]].rename(
            columns={TARGET: "actual", ANCHOR: "naive_24h", "price_lag_168": "naive_168h"}
        )
        iters = {}
        for name, cols in (("lgbm_calendar", cal), ("lgbm_weather", wx)):
            model = _fit(lgb, base, tr[cols], yt, va[cols], yv)
            out[name] = model.predict(test[cols]) + test[ANCHOR].to_numpy()
            iters[name] = int(model.best_iteration_ or model.n_estimators)
            if name == "lgbm_weather":
                std = tr[weather_cols].std()
                for lvl in noise_levels:
                    noisy = test[cols].copy()
                    noisy[weather_cols] = noisy[weather_cols] + rng.normal(
                        0, 1, (len(test), len(weather_cols))
                    ) * (lvl * std.to_numpy())
                    out[f"lgbm_weather_noise{int(lvl * 100)}"] = (
                        model.predict(noisy) + test[ANCHOR].to_numpy()
                    )
        for q in quantiles:
            qm = _fit(lgb, {**base, "objective": "quantile", "alpha": q}, tr[wx], yt, va[wx], yv)
            out[f"q{int(q * 100)}"] = qm.predict(test[wx]) + test[ANCHOR].to_numpy()
            iters[f"q{int(q * 100)}"] = int(qm.best_iteration_ or qm.n_estimators)
        # keep the quantiles ordered even if two separately fitted models cross
        lo, hi = f"q{int(quantiles[0] * 100)}", f"q{int(quantiles[1] * 100)}"
        out[lo], out[hi] = np.minimum(out[lo], out[hi]), np.maximum(out[lo], out[hi])
        rows.append(out)
        folds.append(Fold(m0, len(tr), len(test), iters))
        if progress:
            progress(m0, len(test))
    if not rows:
        raise ValueError("not enough history for the requested walk-forward window")
    return pd.concat(rows, ignore_index=True), folds
