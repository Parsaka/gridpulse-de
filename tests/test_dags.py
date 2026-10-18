"""DAG integrity tests. Skipped automatically when Airflow is not installed (e.g. on Windows)."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow")

from airflow.models import DagBag  # noqa: E402

DAGS = Path(__file__).resolve().parents[1] / "dags"
sys.path.insert(0, str(DAGS))  # DAG files import sibling modules (_common), as the scheduler does


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=str(DAGS), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


@pytest.mark.parametrize("dag_id", ["gridpulse_daily", "gridpulse_backfill"])
def test_dag_has_retries_and_tasks(dagbag, dag_id):
    dag = dagbag.get_dag(dag_id)
    assert dag is not None
    assert dag.default_args["retries"] >= 2
    assert {"load_smard", "load_weather", "check_rows"} <= set(dag.task_ids)
    assert dag.tags


def test_daily_is_scheduled_without_catchup(dagbag):
    dag = dagbag.get_dag("gridpulse_daily")
    assert dag.catchup is False
    assert dag.max_active_runs == 1
