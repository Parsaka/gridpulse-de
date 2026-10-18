"""Unit-of-work functions shared by the CLI and the Airflow DAGs.

Each function loads one dataset/location for a [start, end) window and is idempotent, so
Airflow can retry or backfill it freely.
"""

from datetime import UTC, datetime, timedelta

import httpx
import structlog

from gridpulse.config import get_settings
from gridpulse.ingestion import brightsky, smard
from gridpulse.storage import BronzeStore

log = structlog.get_logger()


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _store() -> BronzeStore:
    return BronzeStore(get_settings().bronze_dir)


def load_smard_dataset(dataset: str, start: datetime, end: datetime) -> int:
    start, end = as_utc(start), as_utc(end)
    with httpx.Client() as client:
        df = smard.fetch_dataset(client, dataset, start, end)
    rows = _store().write(df, "smard", dataset)
    log.info("smard.ingested", dataset=dataset, rows=rows)
    return rows


def load_weather_location(location: str, start: datetime, end: datetime) -> int:
    start, end = as_utc(start), as_utc(end)
    last_day = (end - timedelta(seconds=1)).date()
    with httpx.Client() as client:
        df = brightsky.fetch_weather(client, location, start.date(), last_day)
    rows = _store().write(df, "dwd", f"weather_{location}")
    log.info("weather.ingested", location=location, rows=rows)
    return rows


def daily_window(days_back: int = 3, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Re-load the last N full days plus today (late revisions are common in SMARD)."""
    now = as_utc(now or datetime.now(UTC))
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return end - timedelta(days=days_back + 1), end
