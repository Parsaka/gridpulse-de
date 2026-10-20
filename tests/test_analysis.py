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
    pytest.importorskip("scipy")
    prices = np.array([100.0] * 6 + [20.0, 20.0] + [100.0] * 8 + [200.0, 200.0] + [100.0] * 6)
    charge, discharge = plan_day(prices)
    assert charge[6:8].sum() > 1.5 and discharge[16:18].sum() > 1.5
    assert discharge[:16].sum() < 1e-6  # nothing is sold before the evening peak
    e = Battery().eff_one_way
    assert charge.sum() * e == pytest.approx(discharge.sum() / e)  # ends empty


def test_closed_form_profit_for_one_cycle():
    pytest.importorskip("scipy")
    bat = Battery(power_mw=1.0, capacity_mwh=2.0, round_trip_eff=0.81, throughput_cost=3.0)
    prices = np.r_[
        np.full(2, 10.0), np.full(20, 250.0), np.full(2, 300.0)
    ]  # 250: no profitable trade
    plan = plan_day(prices, bat)
    stored = 2 * 0.9  # two hours at 1 MW grid power, 90% one-way efficiency
    sold = stored * 0.9
    expected = 300 * sold - 10 * 2 - 3 * sold
    assert realised_profit(plan, prices, bat) == pytest.approx(expected, rel=1e-6)


def test_flat_prices_mean_no_trading_and_losses_are_not_free():
    pytest.importorskip("scipy")
    prices = np.full(24, 80.0)
    charge, discharge = plan_day(prices)
    assert charge.sum() + discharge.sum() < 1e-6
    # a forced round trip at flat prices loses money (efficiency and degradation)
    forced = (np.eye(24)[0], np.eye(24)[1] * Battery().eff_one_way ** 2)
    assert realised_profit(forced, prices) < 0


def test_perfect_foresight_is_an_upper_bound_and_noise_lowers_value():
    pytest.importorskip("scipy")
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


def test_battery_respects_power_and_capacity():
    pytest.importorskip("scipy")
    bat = Battery(power_mw=1.0, capacity_mwh=2.0)
    prices = np.r_[np.full(4, 10.0), np.full(4, 300.0), np.full(16, 100.0)]
    charge, discharge = plan_day(prices, bat)
    e = bat.eff_one_way
    soc = np.cumsum(charge * e - discharge / e)
    assert soc.max() <= 2 + 1e-6 and soc.min() >= -1e-6
    assert charge.max() <= 1 + 1e-6 and discharge.max() <= 1 + 1e-6


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


# ----------------------------------------------------------------------------- factors and business


def _market_with_weather(days=60):
    df = _market(days=days, seed=11)
    rng = np.random.default_rng(12)
    df["wind_gw"] = rng.uniform(0, 30, len(df))
    df["solar_gw"] = np.where(df["hour_local"].between(8, 16), rng.uniform(0, 40, len(df)), 0.0)
    df["load_gw"] = 55 + rng.normal(0, 3, len(df))
    df["temperature_c"] = 10 + rng.normal(0, 5, len(df))
    df["wind_speed_kmh"] = 12 + rng.normal(0, 3, len(df))
    df["solar_kwh_m2"] = np.clip(rng.normal(0.15, 0.1, len(df)), 0, None)
    df["cloud_cover_pct"] = rng.uniform(0, 100, len(df))
    df["price_eur_mwh"] = 90 + 3.5 * df["load_gw"] - 3.0 * df["wind_gw"] - 3.3 * df["solar_gw"]
    df["price_eur_mwh"] += rng.normal(0, 5, len(df))
    return df


def test_weather_effects_recover_known_coefficients():
    from gridpulse.analysis.factors import weather_effects

    res = weather_effects(_market_with_weather(), n_boot=40)["effects"]["all"]
    assert res["wind_gw"]["effect"] == pytest.approx(-3.0, abs=0.2)
    assert res["solar_gw"]["effect"] == pytest.approx(-3.3, abs=0.2)
    assert res["load_gw"]["effect"] == pytest.approx(3.5, abs=0.3)


def test_capture_rates_are_below_one_for_a_source_that_sells_when_prices_are_low():
    from gridpulse.analysis.factors import capture_rates

    cr = capture_rates(_market_with_weather())
    assert 0 < cr["solar_capture_all"] < 1.0  # solar output is high exactly when price is low


def test_consumer_shift_saves_money_and_never_costs_more_than_flat():
    from gridpulse.analysis.factors import consumer_shift

    cs = consumer_shift(_market_with_weather(), hours=4)
    assert cs["avg_cheapest_hours"] < cs["avg_flat"]
    assert 0 < cs["saving_share"] < 1
    assert cs["avg_cheapest_hours"] <= cs["avg_cheapest_block"] + 1e-9  # best 4 hours <= best block


def test_error_by_factor_bins_cover_every_hour_once():
    from gridpulse.analysis.factors import error_by_factor, feature_frame

    df = _market_with_weather(days=45)
    ts = df["ts_utc"]
    wf = pd.DataFrame({"ts_utc": ts, "actual": df["price_eur_mwh"]})
    rng = np.random.default_rng(3)
    wf["naive_24h"] = wf["actual"] + rng.normal(0, 30, len(wf))
    wf["lgbm_weather"] = wf["actual"] + rng.normal(0, 15, len(wf))
    ff = feature_frame(wf, df)
    out = error_by_factor(ff, n_boot=30)
    assert sum(b["hours"] for b in out["weekend"]["bins"]) == len(ff)
    assert sum(b["hours"] for b in out["daypart"]["bins"]) == len(ff)
    assert all(b["gain"] > 0 for b in out["daypart"]["bins"])  # model is built to be better


def test_committed_business_page_matches_results():
    import json
    from pathlib import Path

    from gridpulse.analysis.report import render_business

    root = Path(__file__).resolve().parents[1] / "docs"
    res = json.loads((root / "analysis" / "results.json").read_text(encoding="utf-8"))
    assert render_business(res) == (root / "for-business.md").read_text(encoding="utf-8")
