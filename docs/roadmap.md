# Roadmap (target: 3–4 weeks of focused work)

- [x] **Phase 1 – Ingestion**: SMARD, Bright Sky, ENTSO-E clients → Parquet bronze (idempotent), CLI, tests, CI
- [x] **Phase 2 – Orchestration**: Airflow DAGs (daily + backfill), retries, failure alerts
- [~] **Phase 3 – Azure**: Terraform written, validated in CI, never applied (needs your Azure subscription, see docs/azure-setup.md). Azure Blob storage backend implemented and tested against the Azurite emulator (local and CI), not against a real account
- [x] **Phase 4 – dbt**: bronze, silver, gold star schema on Postgres, incremental models, 29 data tests, source freshness, `dbt build` in CI and inside the Airflow DAG
- [~] **Phase 5 – CI/CD**: CI runs lint, tests, dbt, Terraform validate, image build (all green). `infra.yml` (OIDC plan, approval-gated apply) written but never run; rollback documented in docs/deploy.md
- [x] **Phase 6 – ML**: baselines, LightGBM, leakage test, MLflow registry, model card, shadow-mode forecast log, weekly retrain DAG with PSI drift check. Honest limit: headline gain uses observed weather; real-forecast scoring accumulates over time
- [x] **Phase 7 – Serving & monitoring**: FastAPI, Prometheus rules, Grafana dashboard (verified running), load test, incident drill. Not done: Azure Container Apps deploy and alert delivery (need Azure)
- [~] **Phase 8 – Power BI**: PBIP/TMDL semantic model (5 tables, 20 measures), tests in CI, report skeleton, docs (done). Open: build the visuals in Desktop and capture screenshots
- [~] **Phase 9 – Portfolio**: architecture diagram, case study and CV wording (docs/), project page for the personal website (separate PR, not merged). Open: make the repo public after the licence check, update CV and LinkedIn
