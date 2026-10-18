from datetime import datetime
from typing import Annotated

import pandas as pd
import structlog
import typer
from sqlalchemy import create_engine

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


@app.command("load-warehouse")
def load_warehouse():
    """Upsert bronze Parquet into PostgreSQL (schema bronze) for dbt."""
    from gridpulse import warehouse

    settings = get_settings()
    engine = warehouse.get_engine(settings.warehouse_url)
    warehouse.init_schema(engine)
    store = make_store(settings)
    warehouse.load_smard(engine, store)
    warehouse.load_weather(engine, store)


@app.command("sample-data")
def sample_data(start: str = "2026-01-01", days: int = 7):
    """Write deterministic SYNTHETIC bronze data (for CI/offline demos; not real data)."""
    from gridpulse.sample import write_sample_bronze

    write_sample_bronze(make_store(), start, days)
    log.info("sample.written", start=start, days=days)


@app.command("train")
def train(
    test_days: int = 90,
    register: Annotated[str, typer.Option(help="Feature set to register")] = "with_weather",
    no_mlflow: bool = False,
):
    """Train baselines + LightGBM on gold tables, log to MLflow, write backtest to gold."""
    import json

    from gridpulse.ml import data, registry
    from gridpulse.ml import train as ml_train

    settings = get_settings()
    engine = create_engine(settings.warehouse_url)
    df = data.load_training_frame(engine)
    results, backtest = ml_train.train_and_evaluate(df, test_days=test_days)
    data.write_backtest(engine, backtest)
    info = {
        "rows": len(df),
        "first_ts": str(df["ts_utc"].min()),
        "last_ts": str(df["ts_utc"].max()),
        "test_days": test_days,
    }
    from gridpulse.ml import artifacts

    chosen = next(r for r in results if r.feature_set == register and r.model is not None)
    artifacts.save_model(chosen, settings.model_dir, ml_train.ANCHOR, info)
    if not no_mlflow:
        registry.log_run(results, settings.mlflow_tracking_uri, info, register=register)
    summary = {r.name: {k: round(v, 4) for k, v in r.metrics.items()} for r in results}
    typer.echo(json.dumps({"data": info, "metrics": summary}, indent=2))


@app.command("daily")
def daily(days_back: int = 3):
    """Incremental run: re-load the last N days (idempotent)."""
    start, end = pipeline.daily_window(days_back)
    ingest_smard(start, end, None)
    ingest_weather(start, end)


if __name__ == "__main__":
    app()
