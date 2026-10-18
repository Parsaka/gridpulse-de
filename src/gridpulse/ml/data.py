import pandas as pd
from sqlalchemy import Engine

QUERY = """
select m.ts_utc, m.price_eur_mwh, m.load_mwh, m.renewable_share,
       w.temperature_c, w.wind_speed_kmh, w.cloud_cover_pct, w.solar_kwh_m2, w.precipitation_mm
from gold.fct_market_hourly m
left join gold.mart_weather_national_hourly w using (ts_utc)
order by m.ts_utc
"""


def load_training_frame(engine: Engine) -> pd.DataFrame:
    return pd.read_sql(QUERY, engine, parse_dates=["ts_utc"])


def write_backtest(engine: Engine, backtest: pd.DataFrame) -> None:
    """Actual vs predicted for the test window; consumed by Power BI."""
    backtest.to_sql(
        "price_forecast_backtest", engine, schema="gold", if_exists="replace", index=False
    )
