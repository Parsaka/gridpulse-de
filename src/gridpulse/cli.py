from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pandas as pd
import structlog
import typer

from gridpulse.config import get_settings
from gridpulse.ingestion import brightsky, entsoe, smard
from gridpulse.storage import BronzeStore

app = typer.Typer(help="GridPulse DE ingestion CLI", no_args_is_help=True)
log = structlog.get_logger()

Start = Annotated[datetime, typer.Option(help="Window start (UTC), e.g. 2025-01-01")]
End = Annotated[datetime, typer.Option(help="Window end, exclusive (UTC)")]


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _store() -> BronzeStore:
    return BronzeStore(get_settings().bronze_dir)


@app.command("smard")
def ingest_smard(
    start: Start,
    end: End,
    dataset: Annotated[list[str] | None, typer.Option(help="Default: all")] = None,
):
    """Backfill / incremental load of SMARD generation, load and price series."""
    store = _store()
    start, end = _utc(start), _utc(end)
    with httpx.Client() as client:
        for name in dataset or smard.DATASETS:
            df = smard.fetch_dataset(client, name, start, end)
            n = store.write(df, "smard", name)
            log.info("smard.ingested", dataset=name, rows=n)


@app.command("weather")
def ingest_weather(start: Start, end: End):
    """Hourly DWD weather (via Bright Sky) for the configured regions."""
    store = _store()
    start_d, end_d = _utc(start).date(), (_utc(end) - timedelta(seconds=1)).date()
    with httpx.Client() as client:
        for loc in brightsky.LOCATIONS:
            df = brightsky.fetch_weather(client, loc, start_d, end_d)
            n = store.write(df, "dwd", f"weather_{loc}")
            log.info("weather.ingested", location=loc, rows=n)


@app.command("entsoe-prices")
def ingest_entsoe_prices(start: Start, end: End):
    """Day-ahead prices for DE-LU from ENTSO-E (requires ENTSOE_API_KEY)."""
    df = entsoe.fetch_day_ahead_prices(
        get_settings().entsoe_api_key, pd.Timestamp(_utc(start)), pd.Timestamp(_utc(end))
    )
    n = _store().write(df, "entsoe", "price_day_ahead")
    log.info("entsoe.ingested", rows=n)


@app.command("daily")
def daily(days_back: int = 3):
    """Incremental run used by the scheduler: re-load the last N days (idempotent)."""
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=days_back + 1)
    ingest_smard(start, end, None)
    ingest_weather(start, end)


if __name__ == "__main__":
    app()
