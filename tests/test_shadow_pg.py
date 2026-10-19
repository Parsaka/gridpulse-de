"""Shadow-log tests against a real PostgreSQL that already holds dbt gold tables.

Runs only when GRIDPULSE_TEST_WAREHOUSE_URL is set (the CI dbt job sets it, after `dbt build`
on synthetic data). It writes to ops.forecast_log, so never point it at a real warehouse.
"""

import os
from datetime import UTC, datetime

import pandas as pd
import pytest

URL = os.environ.get("GRIDPULSE_TEST_WAREHOUSE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="GRIDPULSE_TEST_WAREHOUSE_URL not set")


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine, text

    from gridpulse.ml import shadow

    eng = create_engine(URL)
    shadow.init(eng)
    with eng.begin() as c:
        c.execute(text("truncate ops.forecast_log"))
    return eng


def _forecast(engine, day: str, offset: float, issued: str) -> dict:
    actual = pd.read_sql(
        "select ts_utc, price_eur_mwh from gold.fct_market_hourly "
        f"where ts_utc >= '{day}' and ts_utc < '{day}'::date + 1 order by ts_utc",
        engine,
    )
    return {
        "generated_at": issued,
        "model": {"name": "test-model", "trained_at": "2026-01-01T00:00:00+00:00"},
        "forecast": [
            {"ts_utc": t.isoformat(), "price_eur_mwh": float(p) + offset}
            for t, p in zip(actual["ts_utc"], actual["price_eur_mwh"], strict=True)
        ],
    }


def test_log_is_idempotent_and_evaluation_scores_only_prior_issued_forecasts(engine):
    from gridpulse.ml import shadow

    good = _forecast(engine, "2026-01-05", 10.0, "2026-01-04T05:00:00+00:00")
    assert shadow.log_forecast(engine, good) == 24
    assert shadow.log_forecast(engine, good) == 24  # re-issue replaces, no duplicates
    res = shadow.evaluate(engine)
    assert res["n_hours"] == 24
    assert res["mae_model"] == pytest.approx(10.0)
    assert res["mae_naive_24h"] > 0

    # a forecast "issued" after the hours it predicts is hindsight and must be ignored
    late = _forecast(engine, "2026-01-06", 0.0, datetime(2026, 1, 7, tzinfo=UTC).isoformat())
    shadow.log_forecast(engine, late)
    assert shadow.evaluate(engine)["n_hours"] == 24
