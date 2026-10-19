"""Shadow-mode forecast log: store every issued forecast, later score it against the actuals.

This is the honest evaluation path. The backtest in the model card feeds the model observed
weather; here the model is fed a real weather FORECAST at issue time and judged on prices that
were unknown when the forecast was made.
"""

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

DDL = [
    "CREATE SCHEMA IF NOT EXISTS ops",
    """CREATE TABLE IF NOT EXISTS ops.forecast_log (
        issued_at timestamptz NOT NULL,
        ts_utc timestamptz NOT NULL,
        predicted_eur_mwh double precision NOT NULL,
        model_name text NOT NULL,
        model_trained_at timestamptz,
        PRIMARY KEY (ts_utc, model_name))""",
]
# One forecast per target hour and model: re-issuing the same day replaces it (idempotent), and a
# forecast is only valid if it was issued before the actual price existed (checked in evaluate()).


def init(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))


def log_forecast(engine: Engine, forecast: dict) -> int:
    """Persist the dict returned by ForecastService.forecast_next_day()."""
    init(engine)
    issued = datetime.fromisoformat(forecast["generated_at"])
    trained = datetime.fromisoformat(forecast["model"]["trained_at"])
    rows = [
        {
            "issued_at": issued,
            "ts_utc": datetime.fromisoformat(r["ts_utc"]),
            "p": r["price_eur_mwh"],
            "m": forecast["model"]["name"],
            "t": trained,
        }
        for r in forecast["forecast"]
    ]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.forecast_log VALUES (:issued_at, :ts_utc, :p, :m, :t) "
                "ON CONFLICT (ts_utc, model_name) DO UPDATE SET issued_at = EXCLUDED.issued_at, "
                "predicted_eur_mwh = EXCLUDED.predicted_eur_mwh, "
                "model_trained_at = EXCLUDED.model_trained_at"
            ),
            rows,
        )
    return len(rows)


EVAL_SQL = text(
    """
    select f.ts_utc, f.predicted_eur_mwh, m.price_eur_mwh as actual,
           m24.price_eur_mwh as naive_24h
    from ops.forecast_log f
    join gold.fct_market_hourly m on m.ts_utc = f.ts_utc
    left join gold.fct_market_hourly m24 on m24.ts_utc = f.ts_utc - interval '24 hours'
    where m.price_eur_mwh is not null
      and f.issued_at < f.ts_utc  -- only forecasts issued before the hour they predict
    order by f.ts_utc
    """
)


def evaluate(engine: Engine) -> dict:
    """MAE of logged forecasts vs actuals, next to the same-hour-yesterday baseline."""
    df = pd.read_sql(EVAL_SQL, engine)
    df = df.dropna(subset=["naive_24h"])
    if df.empty:
        return {"n_hours": 0}
    mae = lambda col: float((df["actual"] - df[col]).abs().mean())  # noqa: E731
    model_mae, naive_mae = mae("predicted_eur_mwh"), mae("naive_24h")
    return {
        "n_hours": int(len(df)),
        "first_ts": df["ts_utc"].min().isoformat(),
        "last_ts": df["ts_utc"].max().isoformat(),
        "mae_model": round(model_mae, 3),
        "mae_naive_24h": round(naive_mae, 3),
        "mae_skill_vs_naive_24h": round(1 - model_mae / naive_mae, 4),
        "evaluated_at": datetime.now(UTC).isoformat(),
    }
