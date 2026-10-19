"""Daily pipeline: SMARD + DWD weather -> bronze -> Postgres -> dbt -> freshness + shadow forecast.

Each run re-loads a 3-day lookback window because SMARD revises recent values; writes are
idempotent partition overwrites, so reruns are safe.
"""

from datetime import datetime

from _common import (
    DEFAULT_ARGS,
    GP,
    SMARD_DATASETS,
    WEATHER_LOCATIONS,
    check_rows,
    load_smard,
    load_weather,
    notify_failure,
    venv_task,
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
    checked = check_rows(smard_rows, weather_rows)

    # bronze Parquet -> Postgres -> dbt (silver/gold, tests) -> freshness -> shadow forecast
    load_wh = venv_task(
        "load_warehouse", f"{GP}/gridpulse load-warehouse --since-days {LOOKBACK_DAYS + 4}"
    )
    dbt_dir = "cd /opt/airflow/dbt"
    dbt_build = venv_task("dbt_build", f"{dbt_dir} && {GP}/dbt deps && {GP}/dbt build")
    freshness = venv_task("dbt_source_freshness", f"{dbt_dir} && {GP}/dbt source freshness")
    forecast = venv_task("forecast_log", f"{GP}/gridpulse forecast-log", retries=1)
    checked >> load_wh >> dbt_build >> [freshness, forecast]


gridpulse_daily()
