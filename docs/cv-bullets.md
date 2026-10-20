# CV and LinkedIn wording (verify each number before use)

Label it as a personal project. Do not imply professional Data Engineering experience.

**GridPulse DE | Personal project | github.com/Parsaka/gridpulse-de**
- Built an end-to-end data platform for the German power market: Python ingestion of SMARD, DWD
  and ENTSO-E open data into idempotent Parquet and PostgreSQL, modelled with dbt (star schema,
  incremental facts, 29 tests, source freshness), orchestrated with Airflow (daily and weekly DAGs).
- Framed the project around one decision question (does a public-data price forecast matter
  economically for a battery operator?) and answered it with a 13-month walk-forward evaluation
  of a LightGBM day-ahead model: 22% lower error than the naive benchmark (95% bootstrap interval
  18% to 26%), but no measurable battery-revenue difference (+153 EUR/MW/year, interval spans
  zero), with a weather-noise sensitivity test and an exact dynamic-programming dispatch model.
- Found that prices at equal residual load rose by about 70 EUR/MWh year on year and that
  negative-price probability at low residual load fell from 67% to 41%; published the analysis,
  ten figures and an interactive Plotly dashboard. Added a shadow-mode log to score real forecasts.
- Served forecasts via FastAPI (API-key auth, rate limiting) with Prometheus metrics, Grafana and
  alert rules; load-tested (1000 requests, p95 829 ms) and ran a documented failure drill.
- Deployed Azure infrastructure with Terraform (ADLS Gen2, Key Vault, Log Analytics, budget alerts, remote state
  with versioning) and verified the pipeline against the real storage account; GitHub Actions with OIDC login;
  a Power BI semantic model in Git (TMDL, 23 DAX measures).

**Kurzfassung (Deutsch)**
- Datenplattform fuer den deutschen Strommarkt (SMARD, DWD, ENTSO-E): Python-Ingestion, PostgreSQL,
  dbt, Airflow, LightGBM-Prognose, FastAPI mit Monitoring, Terraform fuer Azure, Power BI-Modell.
  Persoenliches Projekt, alle Kennzahlen im Repository nachpruefbar.

Keep out of the CV until true: "Airflow/API running on Azure", "Power BI dashboard published", "production".
True now: "Azure infrastructure deployed with Terraform", "pipeline verified against Azure Data Lake storage".
