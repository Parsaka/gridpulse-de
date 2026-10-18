import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("holidays")

from gridpulse.ml.features import CALENDAR, FEATURE_SETS, LAGS, TARGET, build_features  # noqa: E402
from gridpulse.ml.train import train_and_evaluate  # noqa: E402


def _frame(days: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-01-01", periods=days * 24, freq="h", tz="UTC")
    hour = ts.hour.to_numpy()
    wind = rng.gamma(2.0, 6.0, len(ts))
    price = 100 + 30 * np.sin((hour - 6) / 24 * 2 * np.pi) - 1.5 * wind + rng.normal(0, 8, len(ts))
    return pd.DataFrame(
        {
            "ts_utc": ts,
            TARGET: price,
            "load_mwh": 55000 + 5000 * np.sin(hour / 24 * 2 * np.pi),
            "renewable_share": rng.uniform(0.2, 0.9, len(ts)),
            "temperature_c": rng.normal(10, 5, len(ts)),
            "wind_speed_kmh": wind,
            "cloud_cover_pct": rng.uniform(0, 100, len(ts)),
            "solar_kwh_m2": rng.uniform(0, 1, len(ts)),
            "precipitation_mm": rng.exponential(0.1, len(ts)),
        }
    )


def test_all_lag_features_look_at_least_24h_back():
    """Leakage guard: perturbing the price at hour t must not change any feature at hour t."""
    df = _frame(30)
    base = build_features(df).set_index("ts_utc")
    t = df["ts_utc"].iloc[400]
    changed = df.copy()
    changed.loc[changed["ts_utc"] == t, [TARGET, "load_mwh", "renewable_share"]] *= 10
    alt = build_features(changed).set_index("ts_utc")
    cols = LAGS + CALENDAR
    pd.testing.assert_series_equal(base.loc[t, cols], alt.loc[t, cols])
    # and the change must show up exactly 24h later, proving the lags are wired correctly
    later = t + pd.Timedelta(hours=24)
    assert alt.loc[later, "price_lag_24"] == pytest.approx(
        changed.loc[changed["ts_utc"] == t, TARGET].iloc[0]
    )


def test_calendar_features_use_berlin_time():
    df = _frame(5)
    out = build_features(df).set_index("ts_utc")
    t = pd.Timestamp("2025-01-02 12:00", tz="UTC")  # winter: Berlin = UTC+1
    assert out.loc[t, "hour_local"] == 13


def test_train_and_evaluate_smoke_beats_naive_on_learnable_signal():
    results, backtest = train_and_evaluate(_frame(240), test_days=30, params={"n_estimators": 200})
    by = {r.name: r for r in results}
    assert set(by) == {"naive_24h", "naive_168h", *[f"lgbm_{k}" for k in FEATURE_SETS]}
    assert by["lgbm_with_weather"].metrics["mae"] < by["naive_24h"].metrics["mae"]
    assert len(backtest) == 30 * 24
    assert {"actual", "pred_naive_24h", "pred_lgbm_with_weather"} <= set(backtest.columns)
