# Roadmap (target: 3–4 weeks of focused work)

- [x] **Phase 1 – Ingestion**: SMARD, Bright Sky, ENTSO-E clients → Parquet bronze (idempotent), CLI, tests, CI
- [x] **Phase 2 – Orchestration**: Airflow DAGs (daily + backfill), retries, failure alerts
- [~] **Phase 3 – Azure**: Terraform written and validated (ADLS Gen2, Key Vault, Log Analytics, budget, optional Postgres); ADLS storage backend in Python. Not yet applied: needs your Azure account, see docs/azure-setup.md
- [ ] **Phase 4 – dbt**: bronze/silver/gold, star schema, incremental, tests, freshness, docs, `dbt build` in CI
- [ ] **Phase 5 – CI/CD**: GitHub Actions → Azure via OIDC, terraform plan, manual-approval deploy, rollback doc
- [~] **Phase 6 – ML**: baselines + LightGBM price model, leakage tests, MLflow registry, backtest table for BI, model card (done). Open: real forecast inputs (MOSMIX shadow mode), weekly retrain DAG, Evidently drift
- [ ] **Phase 7 – Serving & monitoring**: FastAPI on Container Apps, App Insights/Azure Monitor, incident drill
- [ ] **Phase 8 – Power BI**: PBIP/TMDL model + DAX + report pages, BPA check in CI
- [ ] **Phase 9 – Portfolio**: architecture diagram, case study on website, CV/LinkedIn update
