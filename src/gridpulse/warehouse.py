"""Load bronze Parquet into PostgreSQL (schema `bronze`). dbt takes over from there.

Loads are idempotent upserts keyed on (dataset|location, ts), so re-running never duplicates.
"""

import pandas as pd
import structlog
from sqlalchemy import Engine, create_engine, text

from gridpulse.ingestion import brightsky, smard

log = structlog.get_logger()

DDL = [
    "CREATE SCHEMA IF NOT EXISTS bronze",
    """CREATE TABLE IF NOT EXISTS bronze.smard_series (
        dataset text NOT NULL, region text NOT NULL, ts timestamptz NOT NULL,
        value double precision, ingested_at timestamptz NOT NULL,
        PRIMARY KEY (dataset, ts))""",
    """CREATE TABLE IF NOT EXISTS bronze.dwd_weather (
        location text NOT NULL, ts timestamptz NOT NULL,
        temperature double precision, wind_speed double precision,
        wind_direction double precision, cloud_cover double precision,
        sunshine double precision, solar double precision,
        precipitation double precision, pressure_msl double precision,
        ingested_at timestamptz NOT NULL, PRIMARY KEY (location, ts))""",
]

SMARD_COLS = ["dataset", "region", "ts", "value", "ingested_at"]
WEATHER_COLS = [
    "location",
    "ts",
    "temperature",
    "wind_speed",
    "wind_direction",
    "cloud_cover",
    "sunshine",
    "solar",
    "precipitation",
    "pressure_msl",
    "ingested_at",
]


def get_engine(url: str) -> Engine:
    return create_engine(url)


def init_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))


def _upsert(engine: Engine, df: pd.DataFrame, table: str, key: list[str], cols: list[str]) -> int:
    if df.empty:
        return 0
    stage = f"_stage_{table.split('.')[-1]}"
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
    with engine.begin() as conn:
        df[cols].to_sql(stage, conn, schema="bronze", if_exists="replace", index=False)
        conn.execute(
            text(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"SELECT {', '.join(cols)} FROM bronze.{stage} "
                f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
            )
        )
        conn.execute(text(f"DROP TABLE bronze.{stage}"))
    return len(df)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"timestamp": "ts", "_ingested_at": "ingested_at"})
    return df.drop_duplicates(subset=[c for c in df.columns if c in ("dataset", "location", "ts")])


def load_smard(engine: Engine, store, since=None) -> int:
    total = 0
    for name in smard.DATASETS:
        df = store.read("smard", name, since)
        if not df.empty:
            total += _upsert(
                engine, _prepare(df), "bronze.smard_series", ["dataset", "ts"], SMARD_COLS
            )
    log.info("warehouse.smard_loaded", rows=total)
    return total


def load_weather(engine: Engine, store, since=None) -> int:
    total = 0
    for loc in brightsky.LOCATIONS:
        df = store.read("dwd", f"weather_{loc}", since)
        if not df.empty:
            total += _upsert(
                engine, _prepare(df), "bronze.dwd_weather", ["location", "ts"], WEATHER_COLS
            )
    log.info("warehouse.weather_loaded", rows=total)
    return total
