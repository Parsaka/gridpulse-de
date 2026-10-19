# Roadmap (target: 3–4 weeks of focused work)

- [x] **Phase 1 – Ingestion**: SMARD, Bright Sky, ENTSO-E clients → Parquet bronze (idempotent), CLI, tests, CI
- [x] **Phase 2 – Orchestration**: Airflow DAGs (daily + backfill), retries, failure alerts
- [~] **Phase 3 – Azure**: Terraform written and validated (ADLS Gen2, Key Vault, Log Analytics, budget, optional Postgres); ADLS storage backend in Python. Not yet applied: needs your Azure account, see docs/azure-setup.md
- [ ] **Phase 4 – dbt**: bronze/silver/gold, star schema, incremental, tests, freshness, docs, `dbt build` in CI
- [ ] **Phase 5 – CI/CD**: GitHub Actions → Azure via OIDC, terraform plan, manual-approval deploy, rollback doc
- [~] **Phase 6 – ML**: baselines + LightGBM price model, leakage tests, MLflow registry, backtest table for BI, model card (done). Open: real forecast inputs (MOSMIX shadow mode), weekly retrain DAG, Evidently drift
- [~] **Phase 7 – Serving & monitoring**: FastAPI (API key, rate limit, MOSMIX-based forecast), Prometheus metrics + alert rules, Grafana, PSI drift function, load test, incident drill (done locally). Open: Container Apps deploy, Azure Monitor alert delivery, drift job in Airflow
- [~] **Phase 8 – Power BI**: PBIP/TMDL semantic model (5 tables, 20 measures), tests in CI, report skeleton, docs (done). Open: build the visuals in Desktop and capture screenshots
- [ ] **Phase 9 – Portfolio**: architecture diagram, case study on website, CV/LinkedIn update
