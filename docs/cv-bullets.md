# CV and LinkedIn wording (verify each number before use)

Label it as a personal project. Do not imply professional Data Engineering experience.

**GridPulse DE | Personal project | github.com/Parsaka/gridpulse-de**
- Built an end-to-end data platform for the German power market: Python ingestion of SMARD, DWD
  and ENTSO-E open data into idempotent Parquet and PostgreSQL, modelled with dbt (star schema,
  incremental facts, 29 tests, source freshness), orchestrated with Airflow (daily and weekly DAGs).
- Trained and evaluated a LightGBM day-ahead price model against naive baselines on 2 years of
  hourly data with a leakage test; documented that its 8% MAE gain uses observed weather and
  added a shadow-mode log to score real forecasts.
- Served forecasts via FastAPI (API-key auth, rate limiting) with Prometheus metrics, Grafana and
  alert rules; load-tested (1000 requests, p95 829 ms) and ran a documented failure drill.
- Wrote Terraform for Azure (ADLS Gen2, Key Vault, budget alerts), CI/CD on GitHub Actions with
  OIDC login and approval-gated apply, and a Power BI semantic model in Git (TMDL, 20 DAX measures).

**Kurzfassung (Deutsch)**
- Datenplattform fuer den deutschen Strommarkt (SMARD, DWD, ENTSO-E): Python-Ingestion, PostgreSQL,
  dbt, Airflow, LightGBM-Prognose, FastAPI mit Monitoring, Terraform fuer Azure, Power BI-Modell.
  Persoenliches Projekt, alle Kennzahlen im Repository nachpruefbar.

Keep out of the CV until true: "deployed on Azure", "Power BI dashboard published", "production".
