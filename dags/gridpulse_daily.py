"""Daily incremental ingestion: SMARD + DWD weather -> bronze Parquet.

Each run re-loads a 3-day lookback window because SMARD revises recent values; writes are
idempotent partition overwrites, so reruns are safe.
"""

from datetime import datetime

from _common import (
    DEFAULT_ARGS,
    SMARD_DATASETS,
    WEATHER_LOCATIONS,
    check_rows,
    load_smard,
    load_weather,
    notify_failure,
)
from airflow.decorators import dag

LOOKBACK_DAYS = 3
START = (
    "{{ (data_interval_start - macros.timedelta(days=" + str(LOOKBACK_DAYS) + ")).isoformat() }}"
)
END = "{{ data_interval_end.isoformat() }}"


@dag(
    dag_id="gridpulse_daily",
    schedule="0 5 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "on_failure_callback": notify_failure},
    tags=["gridpulse", "ingestion"],
)
def gridpulse_daily():
    smard_rows = load_smard.partial(start=START, end=END).expand(dataset=SMARD_DATASETS)
    weather_rows = load_weather.partial(start=START, end=END).expand(location=WEATHER_LOCATIONS)
    check_rows(smard_rows, weather_rows)


gridpulse_daily()
