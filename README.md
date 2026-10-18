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
