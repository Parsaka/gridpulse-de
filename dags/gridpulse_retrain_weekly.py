"""Weekly model refresh: retrain, score the shadow forecasts, check feature drift.

The drift task exits 99 when a monitored feature has PSI > 0.25. Airflow turns that into a
SKIPPED task (a visible warning) instead of a failure, because input drift is information, not a
broken pipeline; retraining cannot remove it.
"""

from datetime import datetime

from _common import DEFAULT_ARGS, GP, notify_failure, venv_task
from airflow.decorators import dag


@dag(
    dag_id="gridpulse_retrain_weekly",
    schedule="0 6 * * 1",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "on_failure_callback": notify_failure},
    tags=["gridpulse", "ml"],
)
def gridpulse_retrain_weekly():
    train = venv_task("train", f"{GP}/gridpulse train --test-days 90")
    shadow = venv_task("shadow_eval", f"{GP}/gridpulse shadow-eval")
    drift = venv_task("drift_check", f"{GP}/gridpulse drift", retries=0, skip_on_exit_code=99)
    train >> shadow >> drift


gridpulse_retrain_weekly()
