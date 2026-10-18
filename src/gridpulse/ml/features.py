"""Feature engineering for the day-ahead price model.

Leakage rules (the point of this module):
- The day-ahead auction for day D clears around noon on D-1, so for a target hour t the model
  may only use prices/loads at or before t-24h (every lag below is >= 24).
- Weather columns are the OBSERVED values at the target hour. In production a weather *forecast*
  (e.g. DWD MOSMIX) would be used instead, so the "with_weather" feature set is an optimistic
  upper bound and is labelled that way everywhere. The "calendar_lags" set has no such proxy.
"""

import numpy as np
import pandas as pd

TARGET = "price_eur_mwh"

CALENDAR = [
    "hour_local",
    "iso_weekday",
    "month_local",
    "is_weekend",
    "is_holiday",
    "doy_sin",
    "doy_cos",
]
LAGS = [
    "price_lag_24",
    "price_lag_48",
    "price_lag_168",
    "price_mean_24h_lag24",
    "price_mean_7d_lag24",
    "load_lag_24",
    "load_lag_168",
    "ren_share_lag_24",
]
WEATHER = [
    "temperature_c",
    "wind_speed_kmh",
    "cloud_cover_pct",
    "solar_kwh_m2",
    "precipitation_mm",
]

FEATURE_SETS = {
    "calendar_lags": CALENDAR + LAGS,
    "with_weather": CALENDAR + LAGS + WEATHER,
}


def _german_holidays(years: range) -> set:
    import holidays

    return set(holidays.Germany(years=years).keys())


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """df: one row per UTC hour (price, load, renewable share, weather) -> features + target."""
    df = df.copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("ts_utc").sort_index()
    # full hourly grid so that shift(24) always means "24 hours earlier"
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="h", tz="UTC"))
    df.index.name = "ts_utc"

    local = df.index.tz_convert("Europe/Berlin")
    df["hour_local"] = local.hour
    df["iso_weekday"] = local.isocalendar().day.to_numpy().astype(int)
    df["month_local"] = local.month
    df["is_weekend"] = (df["iso_weekday"] >= 6).astype(int)
    hol = _german_holidays(range(local.year.min(), local.year.max() + 1))
    df["is_holiday"] = pd.Index(local.date).isin(hol).astype(int)
    doy = local.dayofyear.to_numpy()
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    price = df[TARGET]
    df["price_lag_24"] = price.shift(24)
    df["price_lag_48"] = price.shift(48)
    df["price_lag_168"] = price.shift(168)
    df["price_mean_24h_lag24"] = price.shift(24).rolling(24, min_periods=12).mean()
    df["price_mean_7d_lag24"] = price.shift(24).rolling(168, min_periods=84).mean()
    df["load_lag_24"] = df["load_mwh"].shift(24)
    df["load_lag_168"] = df["load_mwh"].shift(168)
    df["ren_share_lag_24"] = df["renewable_share"].shift(24)
    return df.reset_index()
