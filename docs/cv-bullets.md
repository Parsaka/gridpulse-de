# CV and LinkedIn wording (verify each number before use)

Label it as a personal project. Do not imply professional Data Engineering experience.

**GridPulse DE | Personal project | github.com/Parsaka/gridpulse-de**
- Built an end-to-end data platform for the German power market: Python ingestion of SMARD, DWD
  and ENTSO-E open data into idempotent Parquet and PostgreSQL, modelled with dbt (star schema,
  incremental facts, 29 tests, source freshness), orchestrated with Airflow (daily and weekly DAGs).
- Framed the project around one decision question (does a public-data price forecast matter
  economically for a battery operator?) and answered it with a 13-month walk-forward evaluation
  of a LightGBM day-ahead model: 22% lower error than the naive benchmark (95% bootstrap interval
  17% to 26%, using archived day-before weather forecasts), but no measurable battery-revenue
  difference (-460 EUR/MW/year, interval spans zero) and a plain 4-week average earned more (+3,735 EUR/MW/year, interval +1,894 to +5,685):
  accuracy is not decision value. Included a battery-size sensitivity, rolling conformal calibration of the
  prediction intervals (69% to 79% coverage) and an exact linear-programming dispatch model.
- Showed that the gas price explains the year-on-year price gap at equal conditions (gas up from
  11 to 23 USD/mmbtu implies about +68 EUR/MWh against +70 measured).
- Found that prices at equal residual load rose by about 70 EUR/MWh year on year and that
  negative-price probability at low residual load fell from 67% to 41%; published the analysis,
  twenty figures, a plain-language business summary and an interactive Plotly dashboard. Added a shadow-mode log to score real forecasts.
- Quantified the drivers: each GW of wind or solar lowers the day-ahead price by about 3 EUR/MWh,
  solar sells at 54% of the average price (26% in spring), flexible load can cut energy cost by
  56% by running in the cheapest four hours, and the forecast helps most when the weather changes
  from yesterday (gain 34%) and least in winter (6%, not significant).
- Scheduled the pipeline in the cloud: daily ingest, dbt tests, next-day forecast and shadow-log
  scoring, plus a weekly retrain gated on beating the naive baseline, as GitHub Actions workflows
  with OIDC to Azure (no stored secrets), a data lake with a persistent state container, and
  Terraform for the infrastructure; a bulk `COPY` load cut a full reload from 25+ minutes to about 3.
- Served forecasts via FastAPI (API-key auth, rate limiting) with Prometheus metrics, Grafana and
  alert rules; load-tested (1000 requests, p95 829 ms) and ran a documented failure drill.
- Deployed Azure infrastructure with Terraform (ADLS Gen2, Key Vault, Log Analytics, budget alerts, remote state
  with versioning) and verified the pipeline against the real storage account; GitHub Actions with OIDC login;
  a Power BI semantic model in Git (TMDL, 24 DAX measures).

**Kurzfassung (Deutsch)**
- Datenplattform fuer den deutschen Strommarkt (SMARD, DWD, ENTSO-E): Python-Ingestion, PostgreSQL,
  dbt, Airflow, LightGBM-Prognose, FastAPI mit Monitoring, Terraform fuer Azure, Power BI-Modell.
  Persoenliches Projekt, alle Kennzahlen im Repository nachpruefbar.

Keep out of the CV until true: "Airflow/API running on Azure", "Power BI dashboard published", "production".
True now: "Azure infrastructure deployed with Terraform", "pipeline verified against Azure Data Lake storage".
