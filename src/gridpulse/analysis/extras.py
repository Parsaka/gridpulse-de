"""Extra comparisons around the battery question: a free no-model forecast, battery size, day types,
how concentrated the revenue is, and revenue over time."""

import numpy as np
import pandas as pd

from gridpulse.analysis.arbitrage import Battery, backtest, summarise

KEY = ("perfect", "naive_24h", "profile_28d", "lgbm_weather")


def add_profile_forecast(wf: pd.DataFrame, df: pd.DataFrame, days: int = 28) -> pd.DataFrame:
    """Forecast = mean price of the same Berlin hour over the previous `days` complete days.

    Uses only days strictly before the target day, so it is available the day before like the other
    forecasts. It is the free alternative a practitioner would try before building a model."""
    p = df.pivot_table(index="date_local", columns="hour_local", values="price_eur_mwh")
    p.index = pd.to_datetime(p.index)
    prof = p.rolling(days, min_periods=days - 3).mean().shift(1)  # skips the target day; DST gaps
    out = wf.copy()
    ts = pd.to_datetime(out["ts_utc"], utc=True).dt.tz_convert("Europe/Berlin")
    day = pd.to_datetime(ts.dt.date)
    hour = ts.dt.hour
    vals = prof.stack()
    vals.index.names = ["d", "h"]
    idx = pd.MultiIndex.from_arrays([day, hour])
    out["profile_28d"] = vals.reindex(idx).to_numpy()
    return out


def size_sensitivity(wf: pd.DataFrame, durations=(1.0, 2.0, 4.0), n_boot: int = 1000) -> list[dict]:
    """Does the forecast matter more for a bigger (longer-duration) battery?"""
    strategies = {"perfect": "actual", "naive_24h": "naive_24h", "lgbm_weather": "lgbm_weather"}
    if "profile_28d" in wf:
        strategies["profile_28d"] = "profile_28d"
    out = []
    for hours in durations:
        bat = Battery(power_mw=1.0, capacity_mwh=hours)
        s = summarise(backtest(wf, strategies, bat), n_boot=n_boot)
        d = s["differences_per_year"]["lgbm_weather_minus_naive_24h"]
        out.append(
            {
                "duration_h": hours,
                "perfect": s["strategies"]["perfect"]["eur_per_mw_year"],
                "naive_24h": s["strategies"]["naive_24h"]["eur_per_mw_year"],
                "lgbm_weather": s["strategies"]["lgbm_weather"]["eur_per_mw_year"],
                "profile_28d": s["strategies"].get("profile_28d", {}).get("eur_per_mw_year"),
                "model_minus_naive": d["mean"],
                "model_minus_naive_ci": d["ci"],
                "naive_capture": s["strategies"]["naive_24h"]["capture_of_perfect"],
            }
        )
    return out


def _boot_mean(x: np.ndarray, n_boot: int, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def day_types(daily: pd.DataFrame, wf: pd.DataFrame, n_boot: int = 2000) -> list[dict]:
    """Daily profit difference weather model minus naive, by kind of day."""
    w = wf.copy()
    w["day"] = pd.to_datetime(w["ts_utc"], utc=True).dt.tz_convert("Europe/Berlin").dt.date
    g = w.groupby("day")["actual"].agg(["min", "max"])
    d = daily.set_index("day").join(g)
    d["diff"] = d["lgbm_weather"] - d["naive_24h"]
    wd = pd.to_datetime(pd.Series(d.index, index=d.index)).dt.dayofweek
    groups = {
        "all days": np.ones(len(d), bool),
        "weekdays": (wd < 5).to_numpy(),
        "weekends": (wd >= 5).to_numpy(),
        "days with a negative price": (d["min"] < 0).to_numpy(),
        "days with a spike above 300": (d["max"] > 300).to_numpy(),
        "days in the top 10% of perfect-foresight profit": (
            d["perfect"] >= d["perfect"].quantile(0.9)
        ).to_numpy(),
    }
    out = []
    for name, mask in groups.items():
        x = d.loc[mask, "diff"].to_numpy(float)
        out.append(
            {
                "group": name,
                "days": int(mask.sum()),
                "mean_diff_eur_per_day": float(x.mean()),
                "ci": _boot_mean(x, n_boot),
                "model_wins_share": float((x > 0).mean()),
            }
        )
    return out


def concentration(daily: pd.DataFrame) -> dict:
    """How much of a year's revenue comes from a few days?"""
    perfect = np.sort(daily["perfect"].to_numpy(float))[::-1]
    k = max(1, int(round(0.1 * len(perfect))))
    diff = (daily["lgbm_weather"] - daily["naive_24h"]).to_numpy(float)
    return {
        "days": int(len(perfect)),
        "top10pct_days": k,
        "top10pct_share_of_perfect_revenue": float(perfect[:k].sum() / perfect.sum()),
        "best_day_eur": float(perfect[0]),
        "median_day_eur": float(np.median(perfect)),
        "model_beats_naive_share_of_days": float((diff > 0).mean()),
        "sum_of_model_gains_eur": float(diff[diff > 0].sum()),
        "sum_of_model_losses_eur": float(diff[diff < 0].sum()),
    }


def cumulative(daily: pd.DataFrame, cols=KEY) -> dict:
    d = daily.sort_values("day")
    return {
        "days": [str(x) for x in d["day"]],
        **{c: [round(float(v), 1) for v in d[c].cumsum()] for c in cols if c in d},
    }


def ranking_quality(wf: pd.DataFrame, cols: tuple[str, ...]) -> dict:
    """Battery dispatch depends on ranking the hours of a day, not on the price level.

    Mean within-day Spearman rank correlation between forecast and actual prices, and the share of
    the day's three most expensive actual hours that the forecast also puts in its own top three."""
    df = wf.copy()
    df["day"] = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("Europe/Berlin").dt.date
    out = {c: {"spearman": [], "top3": []} for c in cols}
    for _, g in df.groupby("day"):
        if len(g) < 23:
            continue
        actual_top = set(g["actual"].nlargest(3).index)
        for c in cols:
            out[c]["spearman"].append(g["actual"].rank().corr(g[c].rank()))
            out[c]["top3"].append(len(actual_top & set(g[c].nlargest(3).index)) / 3)
    return {
        c: {
            "spearman": float(np.nanmean(v["spearman"])),
            "top3_hit_rate": float(np.mean(v["top3"])),
        }
        for c, v in out.items()
    }
