# Case study: GridPulse DE

A personal portfolio project: an end-to-end data platform and forecasting service for the German
electricity market, built on open data, with the engineering practices an on-call team would expect.

## Problem
Day-ahead power prices in Germany swing with wind, sun, demand and fuel costs. The goal was not to
beat the market but to build, run and measure the full lifecycle: ingest public data reliably,
model it, forecast, serve, monitor, and show the results, with honest numbers at each step.

## What was built
| Layer | Choice | Why |
|---|---|---|
| Ingestion | Python, httpx, tenacity; SMARD, DWD (Bright Sky), ENTSO-E | Open data, no scraping; retries and idempotent daily partitions make backfills and reruns safe |
| Storage | Parquet bronze, local or Azure Blob (ADLS Gen2), tested against the Azurite emulator | Same code path on a laptop and in Azure |
| Orchestration | Airflow: daily chain and weekly retrain DAGs | Retries with backoff, row-count guards, failure callback |
| Warehouse | PostgreSQL + dbt (bronze, silver, gold star schema) | Incremental facts with a reprocessing window for late data revisions |
| Quality | 29 dbt tests, source freshness, 37 local pytest tests (plus DAG and Postgres tests in CI), leakage test for features | Failures are caught where they happen |
| ML | LightGBM against naive baselines, MLflow, shadow-mode forecast log, PSI drift | Evaluated on a chronological split, then on real forecasts going forward |
| Serving | FastAPI, API-key auth, rate limit, Prometheus metrics, Grafana, alert rules | Fails closed, observable |
| IaC and CI | Terraform (azurerm) validated in CI, GitHub Actions, OIDC workflow for Azure | Reproducible infrastructure; no stored cloud secrets |
| BI | Power BI semantic model as TMDL in Git, 20 DAX measures, tested | Reviewable BI code |

## Results (measured, 2 years of hourly data, 17,520 rows)
- Pipeline: daily chain runs ingestion to dbt tests to forecast logging in one Airflow DAG.
- Model, last 90 days held out: MAE 32.7 EUR/MWh with observed weather vs 36.1 for "same hour
  yesterday" (+9.5%, but the 95% bootstrap interval is -0.9% to +18.1%, so not distinguishable from
  zero); without weather inputs the model is clearly worse than the baseline (41.5).
- API on one laptop container: 1000 requests at concurrency 20, all 200, p95 829 ms.
- Failure drill (database stopped): readiness failed in about 20 s, alert fired in about 96 s,
  service recovered without a restart.

## What went wrong and what it taught me
- The first model lost to the naive baseline. Prices in the test period were ~48% above the
  training mean and trees cannot extrapolate levels. Predicting the change versus yesterday fixed
  most of it, chosen on validation data only.
- The headline 9.5% uses observed weather as a stand-in for a forecast, so it is an upper bound.
  I documented that in the model card and built a shadow log to measure real forecasts instead.
- Drift monitoring flagged every seasonal feature until the reference window became "same season
  last year"; the remaining price-level drift is real.
- Load testing found a real bug (NaN in JSON caused HTTP 500) that unit tests had missed.
- CI failed on the first run for two setup reasons; fixing them took minutes because every job is
  a command I can run locally.

## Not done, said plainly
- Terraform has been validated but never applied; the Azure deployment path is documented, not run.
- Power BI report pages are a skeleton; the model and measures are tested but the visuals are to
  be built in Desktop.
- No gas or CO2 price inputs; accuracy claims are indicative (single test window).
