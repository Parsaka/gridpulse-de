import numpy as np
import pandas as pd
import pytest

from gridpulse.analysis import stats
from gridpulse.analysis.arbitrage import Battery, backtest, plan_day, realised_profit, summarise
from gridpulse.analysis.data import prepare


def _market(days=120, seed=0, price_shift=0.0, start="2025-01-01"):
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=days * 24, freq="h", tz="UTC")
    hour = ts.tz_convert("Europe/Berlin").hour.to_numpy()
    residual = 30 + 15 * np.sin((hour - 7) / 24 * 2 * np.pi) + rng.normal(0, 4, len(ts))
    price = 40 + 3.0 * residual + price_shift + rng.normal(0, 8, len(ts))
    df = pd.DataFrame(
        {
            "ts_utc": ts,
            "price_eur_mwh": price,
            "load_mwh": 55000.0,
            "residual_load_mwh": residual * 1000,
            "renewable_share": 0.5,
            "gen_wind_onshore_mwh": 10000.0,
            "gen_wind_offshore_mwh": 2000.0,
            "gen_solar_mwh": 6000.0,
            "gen_gas_mwh": 4000.0,
        }
    )
    return prepare(df)


# ----------------------------------------------------------------------------- price formation


def test_premium_recovers_a_known_shift_and_slope():
    a = _market(seed=1)
    b = _market(seed=2, price_shift=25.0, start="2025-06-01")
    res = stats.premium_at_equal_conditions(a, b, n_boot=300)
    assert res["premium_eur_mwh"] == pytest.approx(25.0, abs=2.5)
    lo, hi = res["premium_ci"]
    assert 0 < lo < res["premium_eur_mwh"] < hi  # clearly positive, interval around the estimate
    assert hi - lo < 8  # and tight enough to be informative
    assert res["eur_per_gw_residual"] == pytest.approx(3.0, abs=0.3)


def test_no_shift_means_interval_contains_zero():
    a, b = _market(seed=3), _market(seed=4, start="2025-06-01")
    lo, hi = stats.premium_at_equal_conditions(a, b, n_boot=300)["premium_ci"]
    assert lo < 0 < hi


def test_binned_curve_uses_shared_bins():
    a, b = _market(seed=5), _market(seed=6, price_shift=30.0, start="2025-06-01")
    curve = stats.binned_price_curve(a, b, bins=8)
    assert len(curve) >= 6
    shifted = [c for c in curve if c["n_a"] > 20 and c["n_b"] > 20]
    assert all(c["median_b"] > c["median_a"] for c in shifted)


# ----------------------------------------------------------------------------- negatives / spikes


def test_wilson_interval_is_sane():
    lo, hi = stats.wilson(5, 100)
    assert 0.0 < lo < 0.05 < hi < 0.15
    assert all(np.isnan(stats.wilson(0, 0)))


def test_negative_probability_compares_two_periods():
    a, b = _market(seed=7, price_shift=-60.0), _market(seed=8, price_shift=40.0, start="2025-06-01")
    res = stats.negative_probability_when_residual_low(a, b, residual_max_gw=25)
    assert res["a"]["p"] > res["b"]["p"]


def test_spikes_and_negative_summaries_count_hours():
    df = _market(seed=9)
    df.loc[df.index[:5], "price_eur_mwh"] = [-10, -5, 400, 500, 350]
    assert stats.negative_prices(df)["hours"] >= 2
    assert stats.spikes(df, 300)["hours"] >= 3


# ----------------------------------------------------------------------------- battery


def test_plan_charges_cheap_and_discharges_expensive():
    prices = np.array([100.0] * 6 + [20.0, 20.0] + [100.0] * 8 + [200.0, 200.0] + [100.0] * 6)
    actions = plan_day(prices)
    assert actions[6:8].tolist() == [1, 1]
    assert actions[16:18].tolist() == [-1, -1]
    assert actions.sum() == 0  # ends empty


def test_flat_prices_mean_no_trading_and_losses_are_not_free():
    prices = np.full(24, 80.0)
    assert (plan_day(prices) == 0).all()
    # a forced round trip at flat prices loses money (efficiency and degradation)
    forced = np.zeros(24, dtype=int)
    forced[0], forced[1] = 1, -1
    assert realised_profit(forced, prices) < 0


def test_perfect_foresight_is_an_upper_bound_and_noise_lowers_value():
    rng = np.random.default_rng(0)
    ts = pd.date_range("2026-01-01", periods=24 * 40, freq="h", tz="Europe/Berlin").tz_convert(
        "UTC"
    )
    hour = ts.tz_convert("Europe/Berlin").hour.to_numpy()
    actual = 80 + 50 * np.sin((hour - 14) / 24 * 2 * np.pi) + rng.normal(0, 5, len(ts))
    wf = pd.DataFrame(
        {
            "ts_utc": ts,
            "actual": actual,
            "good": actual + rng.normal(0, 5, len(ts)),
            "bad": rng.normal(80, 50, len(ts)),  # unrelated to the real price
        }
    )
    daily = backtest(wf, {"perfect": "actual", "good": "good", "naive_24h": "bad"})
    res = summarise(daily, n_boot=300)["strategies"]
    assert res["perfect"]["capture_of_perfect"] == pytest.approx(1.0)
    assert (
        res["perfect"]["eur_per_day"]
        >= res["good"]["eur_per_day"]
        >= res["naive_24h"]["eur_per_day"]
    )
    assert 0.5 < res["good"]["capture_of_perfect"] <= 1.0


def test_battery_capacity_limits_the_cycle():
    bat = Battery(power_mw=1.0, capacity_mwh=2.0)
    prices = np.r_[np.full(4, 10.0), np.full(4, 300.0), np.full(16, 100.0)]
    actions = plan_day(prices, bat)
    soc = np.cumsum(actions)
    assert soc.max() <= 2 and soc.min() >= 0


# ----------------------------------------------------------------------------- forecast errors


def _wf(n_days=60, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=n_days * 24, freq="h", tz="UTC")
    actual = 100 + rng.normal(0, 30, len(ts))
    wf = pd.DataFrame(
        {
            "ts_utc": ts,
            "actual": actual,
            "naive_24h": actual + rng.normal(0, 30, len(ts)),
            "naive_168h": actual + rng.normal(0, 40, len(ts)),
            "lgbm_calendar": actual + rng.normal(0, 28, len(ts)),
            "lgbm_weather": actual + rng.normal(0, 15, len(ts)),
        }
    )
    wf["q10"] = wf["lgbm_weather"] - 20
    wf["q90"] = wf["lgbm_weather"] + 20
    return stats.with_regime(wf)


def test_skill_and_interval_report():
    wf = _wf()
    res = stats.skill(wf, n_boot=300)
    assert res["models"]["lgbm_weather"]["mae_diff_ci"][1] < 0
    assert "rmse" in res["baseline"]
    cov = stats.interval_report(wf)
    assert 0.0 < cov["coverage"] < 1.0 and cov["mean_width"] == pytest.approx(40.0)
    assert {r["regime"] for r in cov["by_regime"]} <= {
        "negative",
        "low 0-60",
        "mid 60-150",
        "high 150-300",
        "spike >300",
    }


def test_error_tables_cover_all_rows():
    wf = _wf(n_days=58)  # January and February in Berlin time
    by_hour = stats.mae_table(wf, "hour_local")
    assert sum(r["n"] for r in by_hour) == len(wf) and len(by_hour) == 24
    monthly = stats.monthly_skill(wf, n_boot=200)
    assert {m["month"] for m in monthly} == {"2026-01", "2026-02"}


# ----------------------------------------------------------------------------- report


def test_committed_report_matches_committed_results():
    """docs/analysis.md must be regenerated whenever results.json changes."""
    import json
    from pathlib import Path

    from gridpulse.analysis.report import render

    root = Path(__file__).resolve().parents[1] / "docs"
    res = json.loads((root / "analysis" / "results.json").read_text(encoding="utf-8"))
    text = render(res)
    committed = (root / "analysis.md").read_text(encoding="utf-8")
    assert text == committed
    d = res["battery"]["differences_per_year"]["lgbm_weather_minus_naive_24h"]
    assert d["ci"][0] < 0 < d["ci"][1]  # the headline claim "no economic difference" holds


def test_bi_tables_have_the_columns_the_power_bi_model_expects():
    import json
    import re
    from pathlib import Path

    from gridpulse.analysis.report import bi_tables

    root = Path(__file__).resolve().parents[1]
    res = json.loads((root / "docs/analysis/results.json").read_text(encoding="utf-8"))
    for name, frame in bi_tables(res).items():
        tmdl = (root / f"powerbi/GridPulse.SemanticModel/definition/tables/{name}.tmdl").read_text(
            encoding="utf-8"
        )
        assert set(re.findall(r"^\tcolumn (\w+)", tmdl, re.M)) == set(frame.columns), name
        assert len(frame) > 0
