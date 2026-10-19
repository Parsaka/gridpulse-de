from datetime import UTC, date, datetime

import httpx
import pandas as pd

from gridpulse.ingestion import brightsky, smard
from gridpulse.storage import BronzeStore

HOUR = 3_600_000
T0 = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)


def _smard_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("index_hour.json"):
        return httpx.Response(200, json={"timestamps": [T0 - 24 * HOUR, T0, T0 + 24 * HOUR]})
    if path.endswith(f"_{T0}.json"):
        return httpx.Response(200, json={"series": [[T0 + i * HOUR, 10.0 + i] for i in range(24)]})
    return httpx.Response(200, json={"series": [[T0 - HOUR, 1.0], [T0 + 24 * HOUR, None]]})


def test_smard_fetch_filters_window_and_nulls():
    client = httpx.Client(transport=httpx.MockTransport(_smard_handler))
    df = smard.fetch_dataset(
        client,
        "price_day_ahead",
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 2, tzinfo=UTC),
    )
    assert len(df) == 24
    assert df["timestamp"].is_monotonic_increasing
    assert df["timestamp"].iloc[0] == pd.Timestamp("2025-01-01", tz="UTC")
    assert set(df["dataset"]) == {"price_day_ahead"}


def test_bronze_write_is_idempotent(tmp_path):
    store = BronzeStore(tmp_path)
    ts = pd.date_range("2025-01-01", periods=48, freq="h", tz="UTC")
    df = pd.DataFrame({"timestamp": ts, "value": range(48)})
    assert store.write(df, "smard", "x") == 48
    assert store.write(df, "smard", "x") == 48  # re-run replaces, never duplicates
    out = store.read("smard", "x")
    assert len(out) == 48
    assert out["timestamp"].is_unique
    assert len(list((tmp_path / "smard" / "x").glob("date=*"))) == 2


def test_weather_fetch_parses_payload():
    payload = {
        "weather": [
            {"timestamp": "2025-01-01T00:00:00+00:00", "temperature": 3.1, "wind_speed": 12.0},
            {"timestamp": "2025-01-01T01:00:00+00:00", "temperature": 2.9, "wind_speed": 14.5},
        ]
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    )
    df = brightsky.fetch_weather(client, "nrw", date(2025, 1, 1), date(2025, 1, 1))
    assert len(df) == 2
    assert list(df.columns[:2]) == ["timestamp", "temperature"]
    assert (df["location"] == "nrw").all()


def test_bronze_read_since_filters_partitions(tmp_path):
    store = BronzeStore(tmp_path)
    ts = pd.date_range("2025-01-01", periods=72, freq="h", tz="UTC")
    store.write(pd.DataFrame({"timestamp": ts, "value": range(72)}), "smard", "x")
    assert len(store.read("smard", "x")) == 72
    assert len(store.read("smard", "x", since=date(2025, 1, 2))) == 48
    assert store.read("smard", "x", since=date(2025, 2, 1)).empty
