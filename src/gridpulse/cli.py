from datetime import datetime
from typing import Annotated

import pandas as pd
import structlog
import typer

from gridpulse import pipeline
from gridpulse.config import get_settings, make_store
from gridpulse.ingestion import brightsky, entsoe, smard

app = typer.Typer(help="GridPulse DE ingestion CLI", no_args_is_help=True)
log = structlog.get_logger()

Start = Annotated[datetime, typer.Option(help="Window start (UTC), e.g. 2025-01-01")]
End = Annotated[datetime, typer.Option(help="Window end, exclusive (UTC)")]


@app.command("smard")
def ingest_smard(
    start: Start,
    end: End,
    dataset: Annotated[list[str] | None, typer.Option(help="Default: all")] = None,
):
    """Backfill / incremental load of SMARD generation, load and price series."""
    for name in dataset or smard.DATASETS:
        pipeline.load_smard_dataset(name, start, end)


@app.command("weather")
def ingest_weather(start: Start, end: End):
    """Hourly DWD weather (via Bright Sky) for the configured regions."""
    for loc in brightsky.LOCATIONS:
        pipeline.load_weather_location(loc, start, end)


@app.command("entsoe-prices")
def ingest_entsoe_prices(start: Start, end: End):
    """Day-ahead prices for DE-LU from ENTSO-E (requires ENTSOE_API_KEY)."""
    settings = get_settings()
    df = entsoe.fetch_day_ahead_prices(
        settings.entsoe_api_key,
        pd.Timestamp(pipeline.as_utc(start)),
        pd.Timestamp(pipeline.as_utc(end)),
    )
    n = make_store(settings).write(df, "entsoe", "price_day_ahead")
    log.info("entsoe.ingested", rows=n)


@app.command("daily")
def daily(days_back: int = 3):
    """Incremental run: re-load the last N days (idempotent)."""
    start, end = pipeline.daily_window(days_back)
    ingest_smard(start, end, None)
    ingest_weather(start, end)


if __name__ == "__main__":
    app()
