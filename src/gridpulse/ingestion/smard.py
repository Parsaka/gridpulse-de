"""SMARD (Bundesnetzagentur) chart_data client. No authentication required.

URL scheme: /app/chart_data/{filter}/{region}/index_{resolution}.json lists chunk start
timestamps (ms); each chunk lives at {filter}_{region}_{resolution}_{ts}.json.
Data is published under CC BY 4.0 ("Bundesnetzagentur | SMARD.de").
"""

from datetime import UTC, datetime

import httpx
import pandas as pd

from gridpulse.ingestion.http import get_json

BASE_URL = "https://www.smard.de/app/chart_data"

# dataset name -> (filter id, region)
DATASETS: dict[str, tuple[int, str]] = {
    "generation_lignite": (1223, "DE"),
    "generation_nuclear": (1224, "DE"),
    "generation_wind_offshore": (1225, "DE"),
    "generation_hydro": (1226, "DE"),
    "generation_other_conventional": (1227, "DE"),
    "generation_other_renewable": (1228, "DE"),
    "generation_biomass": (4066, "DE"),
    "generation_wind_onshore": (4067, "DE"),
    "generation_solar": (4068, "DE"),
    "generation_hard_coal": (4069, "DE"),
    "generation_pumped_storage": (4070, "DE"),
    "generation_gas": (4071, "DE"),
    "load_total": (410, "DE"),
    "load_residual": (4359, "DE"),
    "price_day_ahead": (4169, "DE-LU"),
}


def _to_ms(dt: datetime) -> int:
    return int(dt.astimezone(UTC).timestamp() * 1000)


def fetch_dataset(
    client: httpx.Client,
    dataset: str,
    start: datetime,
    end: datetime,
    resolution: str = "hour",
) -> pd.DataFrame:
    """Return tidy rows (timestamp UTC, value, dataset) within [start, end)."""
    filter_id, region = DATASETS[dataset]
    index = get_json(client, f"{BASE_URL}/{filter_id}/{region}/index_{resolution}.json")
    chunk_starts = sorted(index["timestamps"])
    s_ms, e_ms = _to_ms(start), _to_ms(end)

    # a chunk covers [its start, next chunk start); keep those overlapping the window
    wanted = [
        ts
        for i, ts in enumerate(chunk_starts)
        if ts < e_ms and (i + 1 == len(chunk_starts) or chunk_starts[i + 1] > s_ms)
    ]
    rows: list[tuple[int, float]] = []
    for ts in wanted:
        url = f"{BASE_URL}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{ts}.json"
        for t, v in get_json(client, url)["series"]:
            if v is not None and s_ms <= t < e_ms:
                rows.append((t, v))

    df = pd.DataFrame(rows, columns=["ts_ms", "value"])
    df["timestamp"] = pd.to_datetime(df.pop("ts_ms"), unit="ms", utc=True)
    df["dataset"] = dataset
    df["region"] = region
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
