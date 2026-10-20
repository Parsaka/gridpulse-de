"""Open-Meteo Previous Runs API: the weather forecast that was issued one day before each hour.

This is what a day-ahead forecaster could really have known, unlike observed weather. Open-Meteo
data is CC BY 4.0 and free for non-commercial use (https://open-meteo.com/en/license).
"""

from datetime import date

import httpx
import pandas as pd

from gridpulse.ingestion.brightsky import LOCATIONS
from gridpulse.ingestion.http import get_json

BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LIVE_VARIABLES = {
    "temperature_2m": "temperature_c",
    "wind_speed_10m": "wind_speed_kmh",
    "cloud_cover": "cloud_cover_pct",
    "shortwave_radiation": "shortwave_wm2",
    "precipitation": "precipitation_mm",
}
VARIABLES = {
    "temperature_2m_previous_day1": "temperature_c",
    "wind_speed_10m_previous_day1": "wind_speed_kmh",
    "cloud_cover_previous_day1": "cloud_cover_pct",
    "shortwave_radiation_previous_day1": "shortwave_wm2",
    "precipitation_previous_day1": "precipitation_mm",
}


def fetch_previous_day_forecast(
    client: httpx.Client, location: str, start: date, end: date
) -> pd.DataFrame:
    """Hourly forecasts issued the day before, for a named location, inclusive of both dates."""
    lat, lon = LOCATIONS[location]
    payload = get_json(
        client,
        BASE_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(VARIABLES),
            "timezone": "UTC",
        },
    )
    h = payload["hourly"]
    df = pd.DataFrame({"timestamp": pd.to_datetime(h["time"], utc=True)})
    for src, dst in VARIABLES.items():
        df[dst] = h[src]
    df["location"] = location
    return df


def fetch_live_forecast(
    client: httpx.Client, location: str, start: date, end: date
) -> pd.DataFrame:
    """The current best forecast for [start, end] (what is known now, for the next day)."""
    lat, lon = LOCATIONS[location]
    payload = get_json(
        client,
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(LIVE_VARIABLES),
            "timezone": "UTC",
        },
    )
    h = payload["hourly"]
    df = pd.DataFrame({"timestamp": pd.to_datetime(h["time"], utc=True)})
    for src, dst in LIVE_VARIABLES.items():
        df[dst] = h[src]
    df["location"] = location
    return df


def national_mean(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Simple mean across stations per hour, with the columns the model expects."""
    all_ = pd.concat(frames)
    g = all_.groupby("timestamp")[list(VARIABLES.values())].mean().reset_index()
    g = g.rename(columns={"timestamp": "ts_utc"})
    g["solar_kwh_m2"] = g.pop("shortwave_wm2") / 1000.0  # W/m2 averaged over an hour = Wh/m2/1000
    return g
