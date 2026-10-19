"""Shared task definitions for the GridPulse DAGs (thin wrappers over gridpulse.pipeline)."""

import logging
from datetime import datetime, timedelta

from airflow.decorators import task
from airflow.operators.bash import BashOperator

from gridpulse import pipeline
from gridpulse.ingestion import brightsky, smard

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "parsa",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(minutes=20),
}


def notify_failure(context):
    """Hook point for alerting. Phase 7 wires this to Azure Monitor / email."""
    ti = context["task_instance"]
    log.error(
        "ALERT task failed: dag=%s task=%s map_index=%s try=%s",
        ti.dag_id,
        ti.task_id,
        ti.map_index,
        ti.try_number,
    )


@task
def load_smard(dataset: str, start: str, end: str) -> int:
    return pipeline.load_smard_dataset(
        dataset, datetime.fromisoformat(start), datetime.fromisoformat(end)
    )


@task
def load_weather(location: str, start: str, end: str) -> int:
    return pipeline.load_weather_location(
        location, datetime.fromisoformat(start), datetime.fromisoformat(end)
    )


@task
def check_rows(smard_rows: list[int], weather_rows: list[int]) -> dict:
    """Fail loudly if a source silently returned nothing."""
    result = {"smard_rows": sum(smard_rows), "weather_rows": sum(weather_rows)}
    if result["smard_rows"] == 0:
        raise ValueError("SMARD returned 0 rows for the whole window")
    if result["weather_rows"] == 0:
        raise ValueError("Bright Sky returned 0 rows for the whole window")
    return result


SMARD_DATASETS = list(smard.DATASETS)
WEATHER_LOCATIONS = list(brightsky.LOCATIONS)


GP = "/home/airflow/gp-venv/bin"


def venv_task(task_id: str, command: str, **kwargs) -> BashOperator:
    """Run a command from the heavy virtualenv (see docker/airflow/Dockerfile)."""
    return BashOperator(task_id=task_id, bash_command=f"set -euo pipefail; {command}", **kwargs)
