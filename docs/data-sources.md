# Data sources and licences

Checked on 2026-10-20 against the publishers' own pages. "Verified" means I read it there;
"Not verified" means the page could not be retrieved or does not state the terms.

| Source | Access | Content | Licence and attribution | Status |
|---|---|---|---|---|
| SMARD (Bundesnetzagentur) | `https://www.smard.de/app/chart_data/...`, no auth | Generation by source, load, residual load, day-ahead price (DE-LU), hourly from 2015 | Market data is licensed CC BY 4.0 (legal basis: section 111d EnWG). Required credit: **"Bundesnetzagentur \| SMARD.de"**. The site's imprint puts the site's *own* texts and graphics under CC BY-ND 4.0; this project reuses data, not those texts or graphics | Verified ([data use](https://www.smard.de/en/datennutzung)) |
| DWD via Bright Sky | `https://api.brightsky.dev`, no auth | Hourly observations and MOSMIX forecasts | DWD freely accessible geodata, including meteorological data with a location reference, may be reused under CC BY 4.0 **with a source note** (Quellenvermerk). The exact required wording is on a DWD template page I could not retrieve; this project uses "Quelle: Deutscher Wetterdienst" and states that data was aggregated. Bright Sky's code is MIT; its README states no data licence and no fair-use limits for the public instance, so keep request volume modest | Partly verified ([dwd.de/copyright](https://www.dwd.de/copyright)); wording and limits not verified |
| ENTSO-E Transparency | Free API token (register, then email transparency@entsoe.eu with subject "Restful API access"); `entsoe-py` | Day-ahead prices, load, generation, cross-border flows | **Not verified.** I could not find the platform's re-use terms. The client is implemented but no ENTSO-E data is used in any published result. Read the terms on transparency.entsoe.eu before ingesting or redistributing | Not verified |

## Attribution text used by this project

> Contains data from Bundesnetzagentur | SMARD.de (CC BY 4.0) and Deutscher Wetterdienst
> (CC BY 4.0, via Bright Sky). Quelle: Deutscher Wetterdienst. Data was aggregated and combined by
> GridPulse DE; changes are not endorsed by the publishers.

## Before making the repository public
- The repository does not contain raw data (`data/` is ignored); it holds code, documentation and
  derived numbers only, so redistribution terms mainly concern the attribution above.
- Keep the attribution in the README (it is) and on the portfolio page.
- Do not commit ENTSO-E data until its terms are read.
- Dataset ids for SMARD live in `src/gridpulse/ingestion/smard.py`.
