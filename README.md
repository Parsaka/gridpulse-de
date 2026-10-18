# GridPulse DE

Data and forecasting platform for the German electricity market: open data (SMARD, ENTSO-E, DWD)
→ Parquet bronze → dbt models → price/load forecasts → API → Power BI. Built on Azure with
Terraform, Airflow and GitHub Actions.

> Personal portfolio project. Status: **Phases 1–2 (ingestion, Airflow) done**; see [roadmap](docs/roadmap.md).

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
gridpulse smard --start 2025-01-01 --end 2025-01-08 --dataset price_day_ahead
gridpulse weather --start 2025-01-01 --end 2025-01-08
pytest
```

Data lands in `data/bronze/<source>/<dataset>/date=YYYY-MM-DD/part.parquet`. Re-running a day
overwrites that partition (idempotent), so backfills and retries are safe.

## Architecture (target)

```
SMARD / ENTSO-E / DWD → Python ingestion → ADLS Gen2 (bronze Parquet)
   → Airflow → PostgreSQL (dbt: bronze/silver/gold) → LightGBM + MLflow → FastAPI (Container Apps)
   → Power BI · Azure Monitor · Terraform + GitHub Actions (OIDC)
```

Data sources and licences: [docs/data-sources.md](docs/data-sources.md). Decisions: [docs/adr](docs/adr).

## Run with Airflow (local)

```bash
docker compose --profile airflow up -d --build   # UI: http://localhost:8080 (admin / admin, local only)
```

- `gridpulse_daily` (05:00 UTC): SMARD + DWD with a 3-day lookback, retries with exponential backoff,
  failure callback, and a row-count check so silent empty loads fail loudly.
- `gridpulse_backfill`: manual run with `start`/`end` params; idempotent, so safe to repeat.

## Warehouse and dbt (local)

```bash
docker compose up -d postgres
pip install -e ".[warehouse,dbt]"
gridpulse load-warehouse                 # bronze Parquet -> Postgres schema `bronze` (upsert)
cd dbt && export DBT_PROFILES_DIR=. && dbt deps && dbt build
dbt source freshness && dbt docs generate && dbt docs serve
```

Layers: `bronze` (raw, loaded) ? `silver` (typed, deduplicated views, seed `locations`) ?
`gold` (`fct_market_hourly`, `fct_weather_hourly`, `dim_datetime`, `dim_location`). Facts are
incremental with a 3-day reprocessing window because SMARD revises recent values.
CI runs `dbt build` against a Postgres service using deterministic **synthetic** data
(`gridpulse sample-data`), so no network is needed.

## Price model

```bash
pip install -e ".[warehouse,ml]"
gridpulse train --test-days 90      # baselines + LightGBM, logs to MLflow, writes gold.price_forecast_backtest
```

On the last 90 days, LightGBM with weather inputs reaches MAE 33.1 vs 36.1 EUR/MWh for the
"same hour yesterday" baseline, **but that uses observed weather as a forecast proxy and is an
upper bound**; without weather the model is worse than the baseline. Details and limits:
[docs/model-card.md](docs/model-card.md).

## API and monitoring

```bash
gridpulse train && docker compose --profile monitoring up -d --build
curl -H "X-API-Key: dev-local-key" http://localhost:8000/v1/forecast
```

`/health`, `/ready`, `/v1/prices`, `/v1/forecast` (next-day hourly prices from a DWD MOSMIX weather
forecast), `/metrics` for Prometheus. Alert rules, Grafana dashboard, the measured load test and a
documented failure drill are in [docs/runbook.md](docs/runbook.md). The forecast is a portfolio
demo, not trading advice; see the [model card](docs/model-card.md) for its limits.

## Power BI

Semantic model (TMDL, 20 DAX measures, star schema over the gold tables) and a report skeleton in
[powerbi/](powerbi/), with setup, page designs and limits in [docs/powerbi.md](docs/powerbi.md).
