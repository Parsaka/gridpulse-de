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
| BI | Power BI semantic model as TMDL in Git, 24 DAX measures, tested | Reviewable BI code |

## Results (measured, 2 years of hourly data, 17,520 rows)
- Pipeline: daily chain runs ingestion to dbt tests to forecast logging in one Airflow DAG.
- Central question: is a public-data day-ahead forecast good enough to matter economically for a
  battery operator? Answered in [analysis.md](analysis.md) with a 13-month walk-forward test.
- Model, walk-forward over 9,192 out-of-sample hours: MAE 23.6 EUR/MWh with the real day-before weather forecast
  vs 30.3 for "same hour yesterday" (22% lower, 95% interval 17% to 26%; observed weather gives the
  same); without weather the gain
  is 4.9% and the interval includes zero.
- Economic value: a 1 MW / 2 MWh battery scheduled from the model earns -460 EUR/MW/year versus the
  naive forecast (interval -2,588 to +1,707), i.e. no measurable difference; the naive forecast
  already reaches 86% of perfect-foresight revenue.
- A free alternative wins: a plain 4-week average by hour of day, with a worse error (MAE 31.8),
  earns +3,735 EUR/MW/year more than yesterday (interval +1,894 to +5,685) and more than the model.
  The model only pulls clearly ahead of yesterday for a 4 h battery (+3,826, interval +1,433 to
  +6,279), where the free average keeps up with it.
- Market findings: at equal residual load, Aug-Oct 2026 prices are 70 EUR/MWh above 2025, and the
  monthly gas price (11.1 to 23.3 USD/mmbtu) implies about 68 of it;
  negative prices at low residual load fell from 67% to 41% of hours.
- API on one laptop container: 1000 requests at concurrency 20, all 200, p95 829 ms.
- Failure drill (database stopped): readiness failed in about 20 s, alert fired in about 96 s,
  service recovered without a restart.

## What went wrong and what it taught me
- The first model lost to the naive baseline. Prices in the test period were ~48% above the
  training mean and trees cannot extrapolate levels. Predicting the change versus yesterday fixed
  most of it, chosen on validation data only.
- I first evaluated with observed weather as a stand-in for a forecast and called the result an
  upper bound. Archived day-before forecasts (Open-Meteo) later showed the stand-in cost almost
  nothing (23.5 vs 23.6 MAE), so my noise test had been far too pessimistic.
- The Power BI model first used a measure property that Power BI's own parser rejects, and its
  slicers started with the first item selected. Schema and unit tests passed; only opening it in
  Desktop and looking at the numbers found both.
- A 22% lower error turned out to be worth nothing for a 2 MWh battery on the day-ahead market, and
  the model lost to a four-week average on revenue. Reporting
  that, instead of only the accuracy number, was the point of asking an economic question first.
- Drift monitoring flagged every seasonal feature until the reference window became "same season
  last year"; the remaining price-level drift is real.
- Load testing found a real bug (NaN in JSON caused HTTP 500) that unit tests had missed.
- CI failed on the first run for two setup reasons; fixing them took minutes because every job is
  a command I can run locally.

## Not done, said plainly
- In Azure: storage (bronze and state), Key Vault, logging and budget (Terraform, Azure for Students). The pipeline runs on a schedule in GitHub Actions against that storage; Airflow, the API and a long-lived Postgres are not hosted anywhere (the cloud jobs use a throw-away Postgres).
- The shadow log started on 2026-10-21, so scored forecast hours accumulate day by day; it is too early for a verdict.
- Power BI: verified in Desktop with real data on all five pages and the numbers match the analysis
  (screenshots in docs/powerbi.md). Publishing to the Power BI service is not done (needs an
  account).
- No carbon price, and gas only monthly. Interval calibration lags abrupt market shifts.
- Battery model: day-ahead only, one cycle per day, no intraday or balancing revenue.
