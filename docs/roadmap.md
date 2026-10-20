# Roadmap (target: 3–4 weeks of focused work)

- [x] **Phase 1 – Ingestion**: SMARD, Bright Sky, ENTSO-E clients → Parquet bronze (idempotent), CLI, tests, CI
- [x] **Phase 2 – Orchestration**: Airflow DAGs (daily + backfill), retries, failure alerts
- [~] **Phase 3 – Azure**: Terraform applied to Azure for Students (Sweden Central): ADLS Gen2, Key Vault, Log Analytics, budget; re-plan shows no changes. Azure Blob storage backend verified against the real account and the Azurite emulator. Scheduled pipeline runs on GitHub Actions against the lake (see docs/cloud.md); no Azure-hosted Postgres or API
- [x] **Phase 4 – dbt**: bronze, silver, gold star schema on Postgres, incremental models, 29 data tests, source freshness, `dbt build` in CI and inside the Airflow DAG
- [~] **Phase 5 – CI/CD**: CI runs lint, tests, dbt, Terraform validate, image build (all green). `infra.yml` verified on 2026-10-20: OIDC login, plan on PR, manual plan+apply from main (no changes, as the stack was applied from a laptop). Not yet tried: a CI apply that changes something; no reviewer gate on the free plan. Rollback in docs/deploy.md
- [x] **Phase 6 – ML**: baselines, LightGBM, leakage test, MLflow registry, model card, shadow-mode forecast log, weekly retrain DAG with PSI drift check. Honest limit: headline gain uses observed weather; real-forecast scoring accumulates over time
- [x] **Phase 7 – Serving & monitoring**: FastAPI, Prometheus rules, Grafana dashboard (verified running), load test, incident drill. Alert delivery via Alertmanager and a webhook is verified locally. Not done: Azure Container Apps deploy, a real chat webhook URL
- [~] **Phase 8 – Power BI**: PBIP/TMDL semantic model (5 tables, 20 measures), tests in CI, report skeleton, docs (done). Open: build the visuals in Desktop and capture screenshots
- [~] **Phase 9 – Portfolio**: architecture diagram, case study and CV wording (docs/), project page for the personal website (separate PR, not merged). Open: make the repo public after the licence check, update CV and LinkedIn
