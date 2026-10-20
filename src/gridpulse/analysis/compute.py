"""Run every analysis and return one JSON-serialisable results dict (the single source of numbers
for the figures, the dashboard and docs/analysis.md)."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from gridpulse.analysis import extras, factors, stats
from gridpulse.analysis.arbitrage import DEFAULT_BATTERY, backtest, summarise
from gridpulse.ml.uncertainty import day_block_bootstrap

QUESTION = (
    "Is a one-day-ahead price forecast built from public data good enough, compared with the naive "
    "'same hour yesterday', to matter economically for a battery operator, and which market "
    "conditions decide where it wins or fails?"
)

# Same calendar months a year apart, so seasonality cancels.
PERIOD_A = ("2025-08-01", "2025-10-19")
PERIOD_B = ("2026-08-01", "2026-10-19")
SUMMER_A = ("2025-04-01", "2025-10-01")
SUMMER_B = ("2026-04-01", "2026-10-01")
YEAR_A = ("2024-10-19", "2025-10-19")
YEAR_B = ("2025-10-19", "2026-10-19")


def _round(obj, nd=4):
    if isinstance(obj, dict):
        return {str(k): _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_round(v, nd) for v in obj]
    if isinstance(obj, float | np.floating):
        return None if np.isnan(obj) else round(float(obj), nd)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def noise_sensitivity(wf: pd.DataFrame, n_boot: int = 2000) -> list[dict]:
    cols = [("0", "lgbm_weather")] + [
        (c.removeprefix("lgbm_weather_noise"), c)
        for c in wf.columns
        if c.startswith("lgbm_weather_noise")
    ]
    out = []
    for level, col in sorted(cols, key=lambda x: int(x[0])):
        res = day_block_bootstrap(wf, [col], "naive_24h", n_boot=n_boot)["models"][col]
        out.append(
            {
                "noise_pct_of_std": int(level),
                "mae": res["mae"],
                "gain": res["skill_vs_baseline"],
                "gain_ci": res["skill_ci"],
            }
        )
    cal = day_block_bootstrap(wf, ["lgbm_calendar"], "naive_24h", n_boot=n_boot)["models"]
    out.append(
        {
            "noise_pct_of_std": None,
            "label": "no weather at all",
            "mae": cal["lgbm_calendar"]["mae"],
            "gain": cal["lgbm_calendar"]["skill_vs_baseline"],
            "gain_ci": cal["lgbm_calendar"]["skill_ci"],
        }
    )
    return out


def compute(df: pd.DataFrame, wf: pd.DataFrame, n_boot: int = 2000) -> dict:
    wf = stats.with_regime(extras.add_profile_forecast(wf, df))
    if wf["profile_28d"].isna().any():
        raise ValueError("profile forecast needs 28 days of history before the first test day")
    a, b = stats.window(df, *PERIOD_A), stats.window(df, *PERIOD_B)

    monthly_premium = []
    for m in ("04", "05", "06", "07", "08", "09"):
        ma, mb = df[df["month"] == f"2025-{m}"], df[df["month"] == f"2026-{m}"]
        r = stats.premium_at_equal_conditions(ma, mb, n_boot=400)
        monthly_premium.append({"month": m, "premium": r["premium_eur_mwh"], "ci": r["premium_ci"]})

    sa, sb = stats.window(df, *SUMMER_A), stats.window(df, *SUMMER_B)
    neg_prob = {
        f"le_{t}_gw": stats.negative_probability_when_residual_low(sa, sb, t) for t in (8, 12, 16)
    }

    strategies = {"perfect": "actual", "naive_24h": "naive_24h", "lgbm_calendar": "lgbm_calendar"}
    strategies["profile_28d"] = "profile_28d"
    strategies["lgbm_weather"] = "lgbm_weather"
    for c in wf.columns:
        if c.startswith("lgbm_weather_noise"):
            strategies[c] = c
    daily = backtest(wf, strategies)
    battery = summarise(daily, n_boot=n_boot)
    d = (daily["profile_28d"] - daily["lgbm_weather"]).to_numpy(float)
    battery["differences_per_year"]["profile_28d_minus_lgbm_weather"] = {
        "mean": float(d.mean() * 365),
        "ci": [x * 365 for x in extras._boot_mean(d, n_boot)],
    }
    battery["ranking"] = extras.ranking_quality(
        wf, ("naive_24h", "profile_28d", "lgbm_calendar", "lgbm_weather")
    )
    battery["sizes"] = extras.size_sensitivity(wf, n_boot=min(n_boot, 1000))
    battery["day_types"] = extras.day_types(daily, wf, n_boot=n_boot)
    battery["concentration"] = extras.concentration(daily)
    battery["cumulative"] = extras.cumulative(daily)
    battery["parameters"] = {
        "power_mw": DEFAULT_BATTERY.power_mw,
        "capacity_mwh": DEFAULT_BATTERY.capacity_mwh,
        "round_trip_efficiency": DEFAULT_BATTERY.round_trip_eff,
        "throughput_cost_eur_per_mwh": DEFAULT_BATTERY.throughput_cost,
    }

    ff = factors.feature_frame(wf, df)
    factor_results = {
        "error_by_factor": factors.error_by_factor(ff, n_boot=min(n_boot, 400)),
        "weather_effects": factors.weather_effects(df, n_boot=min(n_boot, 300)),
        "scenarios": factors.scenarios(ff, df),
        "capture_rates": factors.capture_rates(df),
        "consumer_shift": factors.consumer_shift(df),
        "battery_by_factor": factors.battery_by_factor(daily, ff),
        "anomalies": factors.anomalies(ff, df),
    }

    res = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "market_hours": int(len(df)),
            "market_from": str(df["ts_utc"].min()),
            "market_to": str(df["ts_utc"].max()),
            "walk_forward_hours": int(len(wf)),
            "walk_forward_from": str(wf["ts_utc"].min()),
            "walk_forward_to": str(wf["ts_utc"].max()),
        },
        "question": QUESTION,
        "price_level": {
            "aug_oct_2026_vs_2025": stats.premium_at_equal_conditions(a, b, n_boot=n_boot),
            "year_vs_year": stats.premium_at_equal_conditions(
                stats.window(df, *YEAR_A), stats.window(df, *YEAR_B), n_boot=1000
            ),
            "monthly_premium": monthly_premium,
            "curve": stats.binned_price_curve(a, b, bins=15),
            "periods": {"a": PERIOD_A, "b": PERIOD_B},
        },
        "negative": {
            "summary": stats.negative_prices(df),
            "probability_when_residual_low": neg_prob,
            "periods": {"a": SUMMER_A, "b": SUMMER_B},
        },
        "spikes": stats.spikes(df, 300.0),
        "forecast": {
            "skill": stats.skill(wf, n_boot=n_boot),
            "monthly": stats.monthly_skill(wf),
            "interval": stats.interval_report(wf),
            "by_hour": stats.mae_table(wf, "hour_local"),
            "by_regime": stats.mae_table(wf, "regime"),
            "by_wind": stats.wind_terciles(wf, df),
            "noise": noise_sensitivity(wf, n_boot=n_boot) if "lgbm_weather_noise25" in wf else [],
        },
        "battery": battery,
        "factors": factor_results,
    }
    return _round(res)
