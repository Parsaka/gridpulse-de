# Changelog

## 1.0.0 (2026-10-21)

First complete version. Every claim below is backed by a test, a CI job or a measured run; see the
linked documents for numbers and limits.

### Platform
- Ingestion of SMARD, DWD (Bright Sky), Open-Meteo and ENTSO-E (client) into idempotent Parquet
  partitions; local or Azure Data Lake backend.
- PostgreSQL warehouse (bulk `COPY` upserts) and dbt star schema (38 nodes, 29 data tests, source
  freshness); Airflow DAGs for the daily chain, backfill and weekly retrain (local, Docker).
- LightGBM day-ahead model predicting the change versus yesterday; MLflow tracking; shadow-mode
  forecast log; PSI drift check.
- FastAPI service with API-key auth, rate limiting, Prometheus metrics, Grafana, alert rules and
  webhook delivery.
- Terraform for Azure (data lake with `bronze` and `state`, Key Vault, Log Analytics, budget alert);
  GitHub Actions CI (7 jobs) and OIDC deployment workflow.
- **Cloud schedule:** daily pipeline and weekly retrain on GitHub Actions against Azure
  ([docs/cloud.md](docs/cloud.md)).

### Analysis
- Central question: does a public-data day-ahead forecast matter economically for a battery
  operator? 13-month walk-forward evaluation, battery dispatch by exact linear programming, factor
  analysis, gas-price explanation, conformal intervals; 21 figures, an interactive dashboard and a
  plain-language page ([docs/analysis.md](docs/analysis.md), [docs/for-business.md](docs/for-business.md)).
- Power BI model and report (TMDL and PBIR), opened and checked in Power BI Desktop with real data
  ([docs/powerbi.md](docs/powerbi.md)).

### Known limits
- No hosted API and no long-lived cloud database; the scheduled jobs use a throw-away Postgres.
- The shadow log started on 2026-10-21. Its first 48 scored hours are worse than yesterday's price (MAE 70.1 vs 53.5); two days are too few to judge.
- No carbon price; gas price is monthly. One market, about two years of data.
- Power BI Service publishing is not done (needs an account).
