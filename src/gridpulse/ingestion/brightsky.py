"""Bright Sky client: JSON API over open DWD data (observations + MOSMIX forecasts).

DWD open data is free to use with attribution ("Quelle: Deutscher Wetterdienst").
"""

from datetime import date

import httpx
import pandas as pd

from gridpulse.ingestion.http import get_json

BASE_URL = "https://api.brightsky.dev/weather"

# Representative locations for wind/solar-heavy regions of Germany.
LOCATIONS: dict[str, tuple[float, float]] = {
    "north_sea_coast": (53.55, 8.58),  # Cuxhaven (offshore/onshore wind)
    "schleswig_holstein": (54.32, 9.70),
    "lower_saxony": (52.37, 9.73),  # Hannover
    "brandenburg": (52.40, 13.07),
    "saxony_anhalt": (51.48, 11.97),
    "nrw": (51.23, 6.78),  # Duesseldorf
    "hesse": (50.11, 8.68),  # Frankfurt
    "bavaria_south": (48.14, 11.58),  # Munich (solar)
    "baden_wuerttemberg": (48.78, 9.18),
}

COLUMNS = [
    "timestamp",
    "temperature",
    "wind_speed",
    "wind_direction",
    "cloud_cover",
    "sunshine",
    "solar",
    "precipitation",
    "pressure_msl",
]


def fetch_weather(client: httpx.Client, location: str, start: date, end: date) -> pd.DataFrame:
    """Hourly weather for a named location, inclusive of both dates."""
    lat, lon = LOCATIONS[location]
    payload = get_json(
        client,
        BASE_URL,
        params={"lat": lat, "lon": lon, "date": start.isoformat(), "last_date": end.isoformat()},
    )
    df = pd.DataFrame(payload["weather"])
    if df.empty:
        return pd.DataFrame(columns=[*COLUMNS, "location"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.reindex(columns=COLUMNS)
    df["location"] = location
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
