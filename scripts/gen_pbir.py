"""Generate the Power BI report definition (PBIR) with real visuals bound to the semantic model.

Run from the repo root: python scripts/gen_pbir.py
Output is committed. Structure is checked offline by tests/test_powerbi_report.py and against
Microsoft's published JSON schemas with scripts/validate_pbir.py (needs network).
"""

import json
import shutil
from pathlib import Path

REPORT = Path("powerbi/GridPulse.Report")
DEF = REPORT / "definition"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
MKT, WX, BT = "fct_market_hourly", "fct_weather_hourly", "walk_forward_backtest"
DT, LOC = "dim_datetime", "dim_location"
BAT, NOI, MON = "analysis_battery", "analysis_noise", "analysis_monthly_skill"
SUM, AVG = 0, 1  # Power BI aggregation function codes


def col(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def measure(entity: str, prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def agg(entity: str, prop: str, fn: int = AVG) -> dict:
    return {"Aggregation": {"Expression": col(entity, prop), "Function": fn}}


def proj(field: dict) -> dict:
    """A query projection; queryRef follows Power BI's own naming."""
    kind = next(iter(field))
    if kind == "Aggregation":
        inner = field["Aggregation"]["Expression"]["Column"]
        fn = {SUM: "Sum", AVG: "Avg"}[field["Aggregation"]["Function"]]
        ent = inner["Expression"]["SourceRef"]["Entity"]
        ref = f"{fn}({ent}.{inner['Property']})"
        native = f"{fn} of {inner['Property']}"
    else:
        node = field[kind]
        ent = node["Expression"]["SourceRef"]["Entity"]
        ref = f"{ent}.{node['Property']}"
        native = node["Property"]
    return {"field": field, "queryRef": ref, "nativeQueryRef": native}


def literal(text: str) -> dict:
    return {"expr": {"Literal": {"Value": "'" + text.replace("'", "''") + "'"}}}


def visual(name, vtype, x, y, w, h, roles=None, title=None, extra=None) -> dict:
    v: dict = {"visualType": vtype}
    if roles:
        v["query"] = {
            "queryState": {
                r: {"projections": [proj(f) for f in fields]} for r, fields in roles.items()
            }
        }
        v["drillFilterOtherVisuals"] = True
    if extra:
        v.update(extra)
    out = {
        "$schema": f"{SCHEMA}/visualContainer/2.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "width": w, "height": h},
        "visual": v,
    }
    if title:
        out["visual"]["visualContainerObjects"] = {
            "title": [
                {
                    "properties": {
                        "show": {"expr": {"Literal": {"Value": "true"}}},
                        "text": literal(title),
                    }
                }
            ]
        }
    return out


def textbox(name, x, y, w, h, paragraphs: list[tuple[str, str]]) -> dict:
    paras = [
        {
            "textRuns": [
                {
                    "value": text,
                    "textStyle": {
                        "fontSize": size,
                        "fontWeight": "bold" if size != "11pt" else "normal",
                    },
                }
            ]
        }
        for text, size in paragraphs
    ]
    return visual(
        name,
        "textbox",
        x,
        y,
        w,
        h,
        extra={"objects": {"general": [{"properties": {"paragraphs": paras}}]}},
    )


def card(name, x, y, w, h, entity, prop, title):
    return visual(name, "card", x, y, w, h, {"Values": [measure(entity, prop)]}, title)


# --------------------------------------------------------------------------------------- pages
def pages() -> list[tuple[str, str, list[dict]]]:
    answer = [
        textbox(
            "q_title",
            24,
            16,
            1232,
            70,
            [
                (
                    "Does a public-data price forecast matter economically for a battery operator?",
                    "20pt",
                )
            ],
        ),
        textbox(
            "q_sub",
            24,
            84,
            1232,
            56,
            [
                (
                    "Walk-forward test over 13 months and 9,192 out-of-sample hours; 95% day-block bootstrap intervals. "
                    "The weather model uses observed weather, so it is an upper bound.",
                    "11pt",
                )
            ],
        ),
        card("k_skill", 24, 150, 240, 100, BT, "MAE Skill vs Naive", "Error vs yesterday"),
        card("k_mae", 272, 150, 240, 100, BT, "MAE LightGBM Weather", "MAE with weather (EUR/MWh)"),
        card(
            "k_batt",
            520,
            150,
            240,
            100,
            BAT,
            "Battery Weather Model vs Naive",
            "Battery: model vs naive (EUR/MW/yr)",
        ),
        card(
            "k_prof",
            768,
            150,
            240,
            100,
            BAT,
            "Battery 4-Week Average vs Naive",
            "Battery: free 4-week avg vs naive",
        ),
        card(
            "k_cap",
            1016,
            150,
            240,
            100,
            BAT,
            "Naive Capture of Perfect",
            "Naive vs perfect foresight",
        ),
        visual(
            "battery_bars",
            "clusteredBarChart",
            24,
            270,
            620,
            430,
            {"Category": [col(BAT, "label")], "Y": [agg(BAT, "eur_per_mw_year", SUM)]},
            "Battery revenue by forecast used (EUR/MW/year)",
        ),
        visual(
            "noise_cols",
            "clusteredColumnChart",
            660,
            270,
            596,
            430,
            {"Category": [col(NOI, "label")], "Y": [agg(NOI, "gain", SUM)]},
            "Error reduction shrinks as weather input gets noisy",
        ),
    ]
    market = [
        card("k_avg", 24, 16, 296, 90, MKT, "Avg Price", "Average price (EUR/MWh)"),
        card("k_ren", 336, 16, 296, 90, MKT, "Renewable Share", "Renewable share of generation"),
        card("k_neg", 648, 16, 296, 90, MKT, "Negative Price Hours", "Hours with negative price"),
        card("k_load", 960, 16, 296, 90, MKT, "Total Load GWh", "Total load (GWh)"),
        visual(
            "line_price",
            "lineChart",
            24,
            120,
            820,
            290,
            {"Category": [col(DT, "date_local")], "Y": [measure(MKT, "Avg Price")]},
            "Daily average price",
        ),
        visual(
            "slicer_year", "slicer", 860, 120, 396, 80, {"Values": [col(DT, "year_local")]}, "Year"
        ),
        visual(
            "slicer_month",
            "slicer",
            860,
            210,
            396,
            200,
            {"Values": [col(DT, "month_local")]},
            "Month",
        ),
        visual(
            "neg_by_hour",
            "clusteredColumnChart",
            24,
            425,
            500,
            280,
            {"Category": [col(DT, "hour_local")], "Y": [measure(MKT, "Negative Price Hours")]},
            "Negative prices happen at midday",
        ),
        visual(
            "neg_matrix",
            "pivotTable",
            540,
            425,
            716,
            280,
            {
                "Rows": [col(DT, "month_local")],
                "Columns": [col(DT, "hour_local")],
                "Values": [measure(MKT, "Negative Price Hours")],
            },
            "Negative-price hours by month and hour",
        ),
    ]
    drivers = [
        visual(
            "scatter_wind",
            "scatterChart",
            24,
            16,
            620,
            330,
            {
                "Category": [col(DT, "date_local")],
                "X": [measure(WX, "Avg Wind Speed kmh")],
                "Y": [measure(MKT, "Avg Price")],
            },
            "Windy days are cheaper days",
        ),
        visual(
            "price_by_hour",
            "clusteredColumnChart",
            660,
            16,
            596,
            330,
            {"Category": [col(DT, "hour_local")], "Y": [measure(MKT, "Avg Price")]},
            "Average price by hour of day",
        ),
        visual(
            "ren_matrix",
            "pivotTable",
            24,
            362,
            820,
            342,
            {
                "Rows": [col(DT, "iso_weekday")],
                "Columns": [col(DT, "hour_local")],
                "Values": [measure(MKT, "Renewable Share")],
            },
            "Renewable share by weekday and hour",
        ),
        visual(
            "slicer_region",
            "slicer",
            860,
            362,
            396,
            342,
            {"Values": [col(LOC, "region_type")]},
            "Station region type",
        ),
    ]
    forecast = [
        card("f_naive", 24, 16, 296, 90, BT, "MAE Naive 24h", "MAE same hour yesterday"),
        card("f_wx", 336, 16, 296, 90, BT, "MAE LightGBM Weather", "MAE weather model"),
        card("f_skill", 648, 16, 296, 90, BT, "MAE Skill vs Naive", "Skill vs naive"),
        card(
            "f_cov",
            960,
            16,
            296,
            90,
            BT,
            "Interval Coverage",
            "10-90% interval coverage (nominal 80%)",
        ),
        visual(
            "fc_line",
            "lineChart",
            24,
            120,
            820,
            310,
            {
                "Category": [col(DT, "date_local")],
                "Y": [agg(BT, "actual"), agg(BT, "naive_24h"), agg(BT, "lgbm_weather")],
            },
            "Actual vs forecasts, daily mean (EUR/MWh)",
        ),
        visual(
            "slicer_fc_month",
            "slicer",
            860,
            120,
            396,
            310,
            {"Values": [col(DT, "month_local")]},
            "Month",
        ),
        visual(
            "monthly_skill",
            "clusteredColumnChart",
            24,
            445,
            820,
            260,
            {
                "Category": [col(MON, "month")],
                "Y": [agg(MON, "mae_naive", SUM), agg(MON, "mae_model", SUM)],
            },
            "MAE by test month: naive vs weather model",
        ),
        textbox(
            "fc_caveat",
            860,
            445,
            396,
            260,
            [
                ("Read this first", "12pt"),
                (
                    "The weather model uses observed weather as a stand-in for a forecast, so its error is an "
                    "optimistic upper bound. Its 80% interval covers about 70% of hours.",
                    "11pt",
                ),
            ],
        ),
    ]
    health = [
        card("h_fresh", 24, 16, 400, 110, MKT, "Data Freshness h", "Hours since last price"),
        card("h_hours", 448, 16, 400, 110, MKT, "Hours Loaded", "Hours loaded"),
        card("h_bt", 872, 16, 384, 110, BT, "Backtest Hours", "Backtest hours"),
        textbox(
            "h_note",
            24,
            150,
            1232,
            200,
            [
                ("Pipeline health", "16pt"),
                (
                    "Daily ingestion, dbt tests and forecast logging run in Airflow; metrics and alerts are in "
                    "Grafana. See docs/runbook.md.",
                    "11pt",
                ),
            ],
        ),
    ]
    return [
        ("e5f6a7b8c9d0e1f2a3b4", "The answer", answer),
        ("a1b2c3d4e5f6a7b8c9d0", "Market overview", market),
        ("b2c3d4e5f6a7b8c9d0e1", "Prices vs drivers", drivers),
        ("c3d4e5f6a7b8c9d0e1f2", "Forecast vs actual", forecast),
        ("d4e5f6a7b8c9d0e1f2a3", "Pipeline health", health),
    ]


def dump(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    if (DEF / "pages").exists():
        shutil.rmtree(DEF / "pages")
    dump(
        DEF / "report.json",
        {
            "$schema": f"{SCHEMA}/report/3.0.0/schema.json",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU10",
                    "reportVersionAtImport": {
                        "visual": "2.0.0",
                        "page": "2.0.0",
                        "report": "3.0.0",
                    },
                    "type": "SharedResources",
                }
            },
        },
    )
    plist = pages()
    dump(
        DEF / "pages" / "pages.json",
        {
            "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
            "pageOrder": [p[0] for p in plist],
            "activePageName": plist[0][0],
        },
    )
    n = 0
    for pid, title, visuals in plist:
        dump(
            DEF / "pages" / pid / "page.json",
            {
                "$schema": f"{SCHEMA}/page/2.0.0/schema.json",
                "name": pid,
                "displayName": title,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        )
        for v in visuals:
            dump(DEF / "pages" / pid / "visuals" / v["name"] / "visual.json", v)
            n += 1
    print("generated", len(plist), "pages and", n, "visuals")


if __name__ == "__main__":
    main()
