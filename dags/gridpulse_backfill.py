"""Manual backfill. Trigger with config, e.g. {"start": "2024-01-01", "end": "2025-01-01"}.

End is exclusive (UTC). Safe to re-run: bronze writes overwrite per-day partitions.
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
from airflow.models.param import Param

START = "{{ params.start }}"
END = "{{ params.end }}"


@dag(
    dag_id="gridpulse_backfill",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    default_args={**DEFAULT_ARGS, "on_failure_callback": notify_failure},
    params={
        "start": Param("2025-01-01", type="string", format="date"),
        "end": Param("2025-02-01", type="string", format="date"),
    },
    tags=["gridpulse", "backfill"],
)
def gridpulse_backfill():
    smard_rows = load_smard.partial(start=START, end=END).expand(dataset=SMARD_DATASETS)
    weather_rows = load_weather.partial(start=START, end=END).expand(location=WEATHER_LOCATIONS)
    check_rows(smard_rows, weather_rows)


gridpulse_backfill()
