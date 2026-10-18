# Data sources

| Source | Access | Content | Licence / attribution |
|---|---|---|---|
| SMARD (Bundesnetzagentur) | `https://www.smard.de/app/chart_data/...`, no auth | Generation by source, load, residual load, day-ahead price (DE-LU), hourly/quarter-hourly from 2015 | CC BY 4.0, "Bundesnetzagentur \| SMARD.de" |
| ENTSO-E Transparency | Free API token (register, then email transparency@entsoe.eu); `entsoe-py` | Day-ahead prices, load forecast/actual, generation, cross-border flows | ENTSO-E terms of use; cite source |
| DWD via Bright Sky | `https://api.brightsky.dev`, no auth | Hourly observations + MOSMIX forecasts | DWD open data, "Quelle: Deutscher Wetterdienst" |

Dataset ids for SMARD live in `src/gridpulse/ingestion/smard.py`. Verify each source's terms once
more before making the repository public.
