"""Statistics behind the analysis: price formation, negative prices, spikes, forecast errors.

Everything here is descriptive or a simple regression with day-block bootstrap intervals. No
causal claims: gas and CO2 prices, the main cost drivers, are not in the data (the report says so).
"""

import numpy as np
import pandas as pd

from gridpulse.ml.uncertainty import day_block_bootstrap

REGIMES = [
    ("negative", -np.inf, 0),
    ("low 0-60", 0, 60),
    ("mid 60-150", 60, 150),
    ("high 150-300", 150, 300),
    ("spike >300", 300, np.inf),
]


def window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Rows with start <= local date < end (ISO date strings)."""
    d = pd.to_datetime(df["date_local"])
    return df[(d >= start) & (d < end)]


# ----------------------------------------------------------------------------- price formation


def binned_price_curve(a: pd.DataFrame, b: pd.DataFrame, bins: int = 15) -> list[dict]:
    """Median price (and quartiles) per residual-load bin for two periods, same bin edges."""
    both = pd.concat([a["residual_gw"], b["residual_gw"]])
    edges = np.unique(np.quantile(both.dropna(), np.linspace(0, 1, bins + 1)))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        row = {"residual_gw_mid": float((lo + hi) / 2), "lo": float(lo), "hi": float(hi)}
        for name, d in (("a", a), ("b", b)):
            s = d.loc[(d["residual_gw"] >= lo) & (d["residual_gw"] <= hi), "price_eur_mwh"]
            row[f"n_{name}"] = int(len(s))
            row[f"median_{name}"] = float(s.median()) if len(s) else None
            row[f"p25_{name}"] = float(s.quantile(0.25)) if len(s) else None
            row[f"p75_{name}"] = float(s.quantile(0.75)) if len(s) else None
        out.append(row)
    return out


def _design(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Intercept, residual load (GW), period-b flag, hour-of-day dummies."""
    hours = pd.get_dummies(df["hour_local"].astype(int), prefix="h", drop_first=True).to_numpy(
        float
    )
    x = np.column_stack(
        [np.ones(len(df)), df["residual_gw"].to_numpy(float), df["_b"].to_numpy(float), hours]
    )
    return x, df["price_eur_mwh"].to_numpy(float)


def premium_at_equal_conditions(
    a: pd.DataFrame, b: pd.DataFrame, n_boot: int = 1500, seed: int = 0
) -> dict:
    """Price difference (b minus a) holding residual load and hour of day fixed (OLS), plus the
    price change per GW of residual load. Day-block bootstrap intervals (days are resampled)."""
    df = pd.concat([a.assign(_b=0), b.assign(_b=1)], ignore_index=True)
    df = df.dropna(subset=["residual_gw", "price_eur_mwh"]).reset_index(drop=True)
    x, y = _design(df)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    day_id = pd.factorize(df["date_local"].astype(str) + "|" + df["_b"].astype(str))[0]
    order = np.argsort(day_id, kind="stable")
    bounds = np.r_[0, np.cumsum(np.bincount(day_id))]
    groups = [order[bounds[i] : bounds[i + 1]] for i in range(len(bounds) - 1)]
    rng = np.random.default_rng(seed)
    draws = np.empty((n_boot, 2))
    for k in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        coef = np.linalg.lstsq(x[idx], y[idx], rcond=None)[0]
        draws[k] = coef[1], coef[2]
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    return {
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "premium_eur_mwh": float(beta[2]),
        "premium_ci": [float(lo[1]), float(hi[1])],
        "eur_per_gw_residual": float(beta[1]),
        "eur_per_gw_ci": [float(lo[0]), float(hi[0])],
        "mean_price_a": float(a["price_eur_mwh"].mean()),
        "mean_price_b": float(b["price_eur_mwh"].mean()),
        "mean_residual_a": float(a["residual_gw"].mean()),
        "mean_residual_b": float(b["residual_gw"].mean()),
    }


# ----------------------------------------------------------------------------- negative prices


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return [float(c - h), float(c + h)]


def negative_prices(df: pd.DataFrame) -> dict:
    neg = df["price_eur_mwh"] < 0
    cond = {}
    for col in ("wind_gw", "solar_gw", "load_gw", "residual_gw"):
        cond[col] = {
            "negative_hours_mean": float(df.loc[neg, col].mean()),
            "other_hours_mean": float(df.loc[~neg, col].mean()),
        }
    return {
        "hours": int(neg.sum()),
        "share_of_hours": float(neg.mean()),
        "by_month": df.groupby("month")["price_eur_mwh"]
        .apply(lambda s: int((s < 0).sum()))
        .to_dict(),
        "by_hour": df.groupby("hour_local")["price_eur_mwh"]
        .apply(lambda s: int((s < 0).sum()))
        .to_dict(),
        "weekend_share_of_negative": float(df.loc[neg, "is_weekend"].mean()),
        "weekend_share_of_all": float(df["is_weekend"].mean()),
        "midday_share_of_negative": float(df.loc[neg, "hour_local"].between(10, 16).mean()),
        "conditions": cond,
    }


def negative_probability_when_residual_low(
    a: pd.DataFrame, b: pd.DataFrame, residual_max_gw: float
) -> dict:
    """P(price < 0 | residual load below a threshold) in two periods, with Wilson intervals."""
    out = {"residual_max_gw": residual_max_gw}
    for name, d in (("a", a), ("b", b)):
        low = d[d["residual_gw"] <= residual_max_gw]
        k, n = int((low["price_eur_mwh"] < 0).sum()), int(len(low))
        out[name] = {
            "hours_low_residual": n,
            "negative": k,
            "p": k / n if n else None,
            "ci": wilson(k, n),
        }
    return out


# ----------------------------------------------------------------------------- spikes


def spikes(df: pd.DataFrame, threshold: float = 300.0) -> dict:
    s = df["price_eur_mwh"] > threshold
    return {
        "threshold": threshold,
        "hours": int(s.sum()),
        "by_hour": df.groupby("hour_local")["price_eur_mwh"]
        .apply(lambda x: int((x > threshold).sum()))
        .to_dict(),
        "by_month": df.groupby("month")["price_eur_mwh"]
        .apply(lambda x: int((x > threshold).sum()))
        .to_dict(),
        "evening_share": float(df.loc[s, "hour_local"].between(17, 21).mean()) if s.any() else None,
        "mean_residual_gw_spike": float(df.loc[s, "residual_gw"].mean()) if s.any() else None,
        "mean_residual_gw_other": float(df.loc[~s, "residual_gw"].mean()),
        "mean_wind_gw_spike": float(df.loc[s, "wind_gw"].mean()) if s.any() else None,
        "mean_wind_gw_other": float(df.loc[~s, "wind_gw"].mean()),
    }


# ----------------------------------------------------------------------------- forecast errors

MODELS = ["naive_24h", "naive_168h", "lgbm_calendar", "lgbm_weather"]


def skill(wf: pd.DataFrame, n_boot: int = 4000) -> dict:
    """MAE, RMSE and day-block bootstrap intervals for every model against naive_24h."""
    preds = [m for m in MODELS if m != "naive_24h"]
    bt = wf.rename(columns={"actual": "actual"})
    res = day_block_bootstrap(bt, preds, "naive_24h", n_boot=n_boot)
    for m in MODELS:
        e = bt["actual"] - bt[m]
        entry = res["baseline"] if m == "naive_24h" else res["models"][m]
        entry["rmse"] = float(np.sqrt((e**2).mean()))
    return res


def with_regime(wf: pd.DataFrame) -> pd.DataFrame:
    out = wf.copy()
    out["ts_utc"] = pd.to_datetime(out["ts_utc"], utc=True)
    local = out["ts_utc"].dt.tz_convert("Europe/Berlin")
    out["hour_local"] = local.dt.hour
    out["month"] = local.dt.strftime("%Y-%m")
    out["is_weekend"] = local.dt.dayofweek >= 5
    out["regime"] = pd.cut(
        out["actual"],
        bins=[-np.inf, 0, 60, 150, 300, np.inf],
        labels=[r[0] for r in REGIMES],
        right=False,
    )
    return out


def mae_table(wf: pd.DataFrame, by: str, models=("naive_24h", "lgbm_weather")) -> list[dict]:
    rows = []
    for key, g in wf.groupby(by, observed=True):
        row = {by: key if not hasattr(key, "item") else key.item(), "n": int(len(g))}
        for m in models:
            row[f"mae_{m}"] = float((g["actual"] - g[m]).abs().mean())
        rows.append(row)
    return rows


def monthly_skill(wf: pd.DataFrame, n_boot: int = 1500) -> list[dict]:
    """Per calendar month: MAE of naive and the weather model, and the bootstrap interval of the
    MAE difference (days are the resampling unit; ~30 days per month, so intervals are wide)."""
    rows = []
    for month, g in wf.groupby("month"):
        res = day_block_bootstrap(g, ["lgbm_weather"], "naive_24h", n_boot=n_boot)
        m = res["models"]["lgbm_weather"]
        rows.append(
            {
                "month": month,
                "n_days": res["n_days"],
                "mae_naive": res["baseline"]["mae"],
                "mae_model": m["mae"],
                "diff": m["mae_diff_vs_baseline"],
                "diff_ci": m["mae_diff_ci"],
                "p_better": m["p_better_than_baseline"],
            }
        )
    return rows


def interval_report(wf: pd.DataFrame) -> dict:
    """Empirical coverage of the 10-90% prediction interval (nominal 80%)."""
    inside = (wf["actual"] >= wf["q10"]) & (wf["actual"] <= wf["q90"])
    width = wf["q90"] - wf["q10"]
    reg = (
        wf.assign(inside=inside)
        .groupby("regime", observed=True)["inside"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "coverage", "count": "n"})
        .reset_index()
        .to_dict("records")
    )
    by_month = wf.assign(inside=inside).groupby("month")["inside"].mean().to_dict()
    return {
        "nominal": 0.8,
        "coverage": float(inside.mean()),
        "mean_width": float(width.mean()),
        "below_q10": float((wf["actual"] < wf["q10"]).mean()),
        "above_q90": float((wf["actual"] > wf["q90"]).mean()),
        "by_regime": reg,
        "by_month": {k: float(v) for k, v in by_month.items()},
    }


def wind_terciles(wf: pd.DataFrame, df: pd.DataFrame) -> list[dict]:
    """Where does the weather model win? MAE by wind-generation tercile (from actual generation)."""
    j = wf.merge(df[["ts_utc", "wind_gw", "solar_gw"]], on="ts_utc", how="left").dropna(
        subset=["wind_gw"]
    )
    j["wind_tercile"] = pd.qcut(j["wind_gw"], 3, labels=["low wind", "mid wind", "high wind"])
    return mae_table(j, "wind_tercile")
