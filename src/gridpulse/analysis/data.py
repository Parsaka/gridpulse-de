"""Hourly analysis frame: market, generation mix and national weather, with Berlin-time fields."""

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from sqlalchemy import Engine

QUERY = """
select m.*, w.temperature_c, w.wind_speed_kmh, w.cloud_cover_pct, w.solar_kwh_m2
from gold.fct_market_hourly m
left join gold.mart_weather_national_hourly w using (ts_utc)
order by m.ts_utc
"""


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Add convenience columns. Expects fct_market_hourly columns."""
    df = df.copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    local = df["ts_utc"].dt.tz_convert("Europe/Berlin")
    df["date_local"] = local.dt.date
    df["hour_local"] = local.dt.hour
    df["weekday"] = local.dt.dayofweek  # 0 = Monday
    df["is_weekend"] = df["weekday"] >= 5
    df["month"] = local.dt.strftime("%Y-%m")
    df["wind_gw"] = (df["gen_wind_onshore_mwh"] + df["gen_wind_offshore_mwh"]) / 1000
    df["solar_gw"] = df["gen_solar_mwh"] / 1000
    df["residual_gw"] = df["residual_load_mwh"] / 1000
    df["load_gw"] = df["load_mwh"] / 1000
    df["gas_gw"] = df["gen_gas_mwh"] / 1000
    return df


def load_hourly(engine: "Engine") -> pd.DataFrame:
    return prepare(pd.read_sql(QUERY, engine))
