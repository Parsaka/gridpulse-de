"""Load bronze Parquet into PostgreSQL (schema `bronze`). dbt takes over from there.

Loads are idempotent upserts keyed on (dataset|location, ts), so re-running never duplicates.
"""

import io

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

NULL_TOKEN = "__null__"  # CSV marker for missing values in COPY
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
    """Bulk upsert: COPY into a temporary table, then INSERT .. ON CONFLICT DO UPDATE.

    COPY is orders of magnitude faster than row-wise inserts, which matters for a full reload
    (hundreds of thousands of rows)."""
    if df.empty:
        return 0
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
    buf = io.StringIO()
    df[cols].to_csv(
        buf, index=False, header=False, na_rep=NULL_TOKEN, date_format="%Y-%m-%d %H:%M:%S%z"
    )
    buf.seek(0)
    column_list = ", ".join(cols)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TEMP TABLE _stage (LIKE {table}) ON COMMIT DROP"))
        with (
            conn.connection.cursor() as cur,
            cur.copy(
                f"COPY _stage ({column_list}) FROM STDIN WITH (FORMAT csv, NULL '{NULL_TOKEN}')"
            ) as copy,
        ):
            while chunk := buf.read(1 << 20):
                copy.write(chunk)
        conn.execute(
            text(
                f"INSERT INTO {table} ({column_list}) SELECT {column_list} FROM _stage "
                f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
            )
        )
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
