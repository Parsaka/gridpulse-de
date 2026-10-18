# Power BI

The semantic model lives in Git as text (PBIP + TMDL), so changes are reviewable and tested.

```
powerbi/
  GridPulse.pbip                      open this in Power BI Desktop
  GridPulse.SemanticModel/definition/ TMDL: 5 tables, 20 DAX measures, 4 relationships, 2 parameters
  GridPulse.Report/                   report skeleton: 4 empty pages bound to the model
scripts/gen_tmdl.py                   regenerates the TMDL (a test fails if the committed files drift)
```

## Open it
1. Start the warehouse and fill it: `docker compose up -d postgres`, `gridpulse load-warehouse`,
   `cd dbt && dbt build`, then `gridpulse train` (creates `gold.price_forecast_backtest`).
2. Open `powerbi/GridPulse.pbip` in Power BI Desktop. On first refresh, give the PostgreSQL
   credentials (local: user `gridpulse`, the password from `docker-compose.yml`). Parameters
   `PgServer` / `PgDatabase` default to `localhost` / `gridpulse`; change them under Transform data.
3. Build the visuals below by dragging fields and the named measures. Save as PBIP so the report
   definition goes to Git with the model.

## Pages to build
| Page | Visuals (fields and measures) |
|---|---|
| Market overview | Cards: Avg Price, Renewable Share, Negative Price Hours, Total Load GWh. Line: Avg Price by `dim_datetime[date_local]`. Stacked area: `gen_*` columns by day. Slicers: `dim_datetime[year_local]`, `month_local` |
| Prices vs drivers | Scatter: Avg Wind Speed kmh (x) vs Avg Price (y) by day. Column: Avg Price by `hour_local` (shows the daily shape). Matrix: Renewable Share by weekday x hour. Slicer: `dim_location[region_type]` |
| Forecast vs actual | Line: `actual` vs `pred_naive_24h` vs `pred_lgbm_with_weather` by `ts_utc`. Cards: MAE Naive 24h, MAE LightGBM Weather, MAE Skill vs Naive, RMSE LightGBM Weather. Text box with the caveat below |
| Pipeline health | Cards: Data Freshness h (red above 36), Hours Loaded, Backtest Hours. Link or screenshot of the Airflow and Grafana views |

Required caveat on the forecast page: the weather model uses observed weather as a stand-in for a
forecast, so its error is an optimistic upper bound (see [model-card.md](model-card.md)).

## Status and limits
- Checked without Power BI: tests verify measure metadata, relationships, DAX column references,
  generator sync, and the column list of every table was compared with the live Postgres `gold`
  schema (all matched).
- **Not opened in Power BI Desktop by the author's tooling** (no desktop control was available).
  If Desktop rejects the report folder, create a blank report, "Save as" PBIP, and keep the
  `GridPulse.SemanticModel` folder, which is the part that matters.
- The data connection is Import mode over a local PostgreSQL; publishing to the Power BI service
  needs a gateway for a local database and an account that allows publishing. The portfolio
  alternative is screenshots or a short screen recording plus these files.
- Time-intelligence measures are not included; the model has no marked date table yet.
