"""Generate the Power BI semantic model (TMDL) from a compact spec.

Run from the repo root: python scripts/gen_tmdl.py
Output is committed, so the model is reviewable in Git; this script just keeps it consistent.
"""

from pathlib import Path

ROOT = Path("powerbi/GridPulse.SemanticModel")
DEF = ROOT / "definition"
T = "\t"
F2, F0, PCT = "#,0.00", "#,0", "0.0%"


def m_source(schema: str, table: str, dt_cols: list[str]) -> str:
    """Power Query: read a gold table; timestamptz -> UTC datetime without zone."""
    lines = [
        f"{T * 4}let",
        f"{T * 5}Source = PostgreSQL.Database(PgServer, PgDatabase),",
    ]
    if dt_cols:
        lines.append(f'{T * 5}Data = Source{{[Schema="{schema}", Item="{table}"]}}[Data],')
        fns = ", ".join(
            f'{{"{c}", each DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(_, 0)), type datetime}}'
            for c in dt_cols
        )
        lines.append(f"{T * 5}Utc = Table.TransformColumns(Data, {{{fns}}})")
        last = "Utc"
    else:
        lines.append(f'{T * 5}Data = Source{{[Schema="{schema}", Item="{table}"]}}[Data]')
        last = "Data"
    lines += [f"{T * 4}in", f"{T * 5}{last}", ""]
    return "\n".join(lines)


def table(name, columns, schema="gold", measures=(), dt_cols=()):
    out = [f"table {name}\n"]
    for col, dtype, fmt in columns:
        out.append(f"{T}column {col}\n{T * 2}dataType: {dtype}\n")
        if fmt:
            out.append(f"{T * 2}formatString: {fmt}\n")
        out.append(f"{T * 2}summarizeBy: none\n{T * 2}sourceColumn: {col}\n\n")
    for mname, expr, fmt, desc in measures:
        out.append(f"{T}/// {desc}\n{T}measure '{mname}' = {expr}\n")
        out.append(f"{T * 2}formatString: {fmt}\n\n")
    out.append(f"{T}partition {name} = m\n{T * 2}mode: import\n{T * 2}source =\n")
    out.append(m_source(schema, name, list(dt_cols)))
    return "".join(out)


def write(rel: str, text: str) -> None:
    path = DEF / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


MKT, WX, BT = "fct_market_hourly", "fct_weather_hourly", "walk_forward_backtest"
BAT, NOI, MON = "analysis_battery", "analysis_noise", "analysis_monthly_skill"
GEN = [
    "wind_onshore",
    "wind_offshore",
    "solar",
    "biomass",
    "hydro",
    "other_renewable",
    "lignite",
    "hard_coal",
    "gas",
    "nuclear",
    "other_conventional",
    "pumped_storage",
]


def s(col: str) -> str:
    return f"SUM({MKT}[{col}])"


TOTAL = f"{s('gen_renewable_mwh')} + {s('gen_conventional_mwh')}"

market_cols = [
    ("ts_utc", "dateTime", "yyyy-MM-dd HH:mm"),
    ("price_eur_mwh", "double", F2),
    ("load_mwh", "double", F0),
    ("residual_load_mwh", "double", F0),
    *[(f"gen_{g}_mwh", "double", F0) for g in GEN],
    ("gen_renewable_mwh", "double", F0),
    ("gen_conventional_mwh", "double", F0),
    ("renewable_share", "double", PCT),
]
market_measures = [
    (
        "Avg Price",
        f"AVERAGE({MKT}[price_eur_mwh])",
        F2,
        "Mean day-ahead price in EUR/MWh over the selected hours.",
    ),
    ("Max Price", f"MAX({MKT}[price_eur_mwh])", F2, "Highest hourly day-ahead price in EUR/MWh."),
    ("Min Price", f"MIN({MKT}[price_eur_mwh])", F2, "Lowest hourly day-ahead price in EUR/MWh."),
    (
        "Price Volatility",
        f"STDEV.P({MKT}[price_eur_mwh])",
        F2,
        "Standard deviation of hourly prices in EUR/MWh.",
    ),
    (
        "Negative Price Hours",
        f"CALCULATE(COUNTROWS({MKT}), {MKT}[price_eur_mwh] < 0)",
        F0,
        "Number of hours with a negative price.",
    ),
    ("Total Load GWh", f"DIVIDE({s('load_mwh')}, 1000)", F0, "Total grid load in GWh."),
    (
        "Renewable Share",
        f"DIVIDE({s('gen_renewable_mwh')}, {TOTAL})",
        PCT,
        "Renewable generation divided by total generation.",
    ),
    (
        "Wind Share",
        f"DIVIDE({s('gen_wind_onshore_mwh')} + {s('gen_wind_offshore_mwh')}, {TOTAL})",
        PCT,
        "Onshore plus offshore wind divided by total generation.",
    ),
    (
        "Solar Share",
        f"DIVIDE({s('gen_solar_mwh')}, {TOTAL})",
        PCT,
        "Solar divided by total generation.",
    ),
    (
        "Data Freshness h",
        f"DATEDIFF(MAX({MKT}[ts_utc]), UTCNOW(), HOUR)",
        F0,
        "Hours since the newest market row. The alert threshold is 36.",
    ),
    ("Hours Loaded", f"COUNTROWS({MKT})", F0, "Rows in the market fact, one per UTC hour."),
]
write(f"tables/{MKT}.tmdl", table(MKT, market_cols, measures=market_measures, dt_cols=["ts_utc"]))

write(
    "tables/dim_datetime.tmdl",
    table(
        "dim_datetime",
        [
            ("ts_utc", "dateTime", "yyyy-MM-dd HH:mm"),
            ("ts_local", "dateTime", "yyyy-MM-dd HH:mm"),
            ("date_local", "dateTime", "yyyy-MM-dd"),
            ("hour_local", "int64", "0"),
            ("iso_weekday", "int64", "0"),
            ("is_weekend", "boolean", ""),
            ("month_local", "int64", "0"),
            ("year_local", "int64", "0"),
        ],
        dt_cols=["ts_utc", "ts_local", "date_local"],
    ),
)
write(
    "tables/dim_location.tmdl",
    table(
        "dim_location",
        [
            ("location_key", "int64", "0"),
            ("location", "string", ""),
            ("latitude", "double", "0.00"),
            ("longitude", "double", "0.00"),
            ("region_type", "string", ""),
        ],
    ),
)
write(
    f"tables/{WX}.tmdl",
    table(
        WX,
        [
            ("location", "string", ""),
            ("ts_utc", "dateTime", "yyyy-MM-dd HH:mm"),
            ("temperature_c", "double", "0.0"),
            ("wind_speed_kmh", "double", "0.0"),
            ("wind_direction_deg", "double", "0"),
            ("cloud_cover_pct", "double", "0"),
            ("sunshine_min", "double", "0.0"),
            ("solar_kwh_m2", "double", "0.000"),
            ("precipitation_mm", "double", "0.0"),
            ("pressure_hpa", "double", "0.0"),
        ],
        measures=[
            (
                "Avg Temperature C",
                f"AVERAGE({WX}[temperature_c])",
                "0.0",
                "Mean temperature in degrees Celsius over the selected stations and hours.",
            ),
            (
                "Avg Wind Speed kmh",
                f"AVERAGE({WX}[wind_speed_kmh])",
                "0.0",
                "Mean wind speed in km/h over the selected stations and hours.",
            ),
        ],
        dt_cols=["ts_utc"],
    ),
)


def mae(col: str) -> str:
    return f"AVERAGEX({BT}, ABS({BT}[actual] - {BT}[{col}]))"


def rmse(col: str) -> str:
    return f"SQRT(AVERAGEX({BT}, ({BT}[actual] - {BT}[{col}]) ^ 2))"


write(
    f"tables/{BT}.tmdl",
    table(
        BT,
        [
            ("ts_utc", "dateTime", "yyyy-MM-dd HH:mm"),
            ("actual", "double", F2),
            ("naive_24h", "double", F2),
            ("naive_168h", "double", F2),
            ("lgbm_calendar", "double", F2),
            ("lgbm_weather", "double", F2),
            ("q10", "double", F2),
            ("q90", "double", F2),
        ],
        measures=[
            (
                "MAE Naive 24h",
                mae("naive_24h"),
                F2,
                "Mean absolute error of the same-hour-yesterday baseline in EUR/MWh.",
            ),
            (
                "MAE LightGBM Weather",
                mae("lgbm_weather"),
                F2,
                "MAE of the LightGBM model that uses observed weather as a forecast proxy. Optimistic upper bound.",
            ),
            (
                "MAE LightGBM Calendar",
                mae("lgbm_calendar"),
                F2,
                "MAE of the LightGBM model without weather inputs.",
            ),
            (
                "RMSE Naive 24h",
                rmse("naive_24h"),
                F2,
                "Root mean squared error of the same-hour-yesterday baseline.",
            ),
            (
                "RMSE LightGBM Weather",
                rmse("lgbm_weather"),
                F2,
                "RMSE of the weather model. Optimistic upper bound.",
            ),
            (
                "MAE Skill vs Naive",
                "1 - DIVIDE([MAE LightGBM Weather], [MAE Naive 24h])",
                PCT,
                "Relative MAE improvement over the naive baseline. Negative means worse than the baseline.",
            ),
            ("Backtest Hours", f"COUNTROWS({BT})", F0, "Hours in the walk-forward backtest."),
            (
                "Interval Coverage",
                f"DIVIDE(COUNTROWS(FILTER({BT}, {BT}[actual] >= {BT}[q10] && {BT}[actual] <= {BT}[q90])), COUNTROWS({BT}))",
                PCT,
                "Share of hours inside the model's 10-90% interval. Nominal 80%; lower means overconfident.",
            ),
        ],
        dt_cols=["ts_utc"],
    ),
)

write(
    f"tables/{BAT}.tmdl",
    table(
        BAT,
        [
            ("strategy", "string", None),
            ("label", "string", None),
            ("eur_per_mw_year", "double", F0),
            ("ci_low", "double", F0),
            ("ci_high", "double", F0),
            ("capture_of_perfect", "double", PCT),
        ],
        measures=[
            (
                "Battery Weather Model vs Naive",
                f'CALCULATE(SUM({BAT}[eur_per_mw_year]), {BAT}[strategy] = "lgbm_weather") - CALCULATE(SUM({BAT}[eur_per_mw_year]), {BAT}[strategy] = "naive_24h")',
                F0,
                "Yearly revenue per MW of the weather-model schedule minus the same-hour-yesterday schedule, EUR/MW/year. The 95% interval spans zero.",
            ),
            (
                "Battery 4-Week Average vs Naive",
                f'CALCULATE(SUM({BAT}[eur_per_mw_year]), {BAT}[strategy] = "profile_28d") - CALCULATE(SUM({BAT}[eur_per_mw_year]), {BAT}[strategy] = "naive_24h")',
                F0,
                "Yearly revenue per MW of scheduling from a plain 4-week average by hour minus the same-hour-yesterday schedule, EUR/MW/year.",
            ),
            (
                "Naive Capture of Perfect",
                f'CALCULATE(SUM({BAT}[capture_of_perfect]), {BAT}[strategy] = "naive_24h")',
                PCT,
                "Revenue of the naive schedule as a share of perfect foresight.",
            ),
        ],
    ),
)
write(
    f"tables/{NOI}.tmdl",
    table(
        NOI,
        [
            ("label", "string", None),
            ("noise_pct", "double", F0),
            ("mae", "double", F2),
            ("gain", "double", PCT),
            ("gain_low", "double", PCT),
            ("gain_high", "double", PCT),
        ],
    ),
)
write(
    f"tables/{MON}.tmdl",
    table(
        MON,
        [
            ("month", "string", None),
            ("mae_naive", "double", F2),
            ("mae_model", "double", F2),
            ("diff", "double", F2),
            ("diff_low", "double", F2),
            ("diff_high", "double", F2),
        ],
    ),
)

RELS = [
    (MKT, "ts_utc", "dim_datetime", "ts_utc"),
    (WX, "ts_utc", "dim_datetime", "ts_utc"),
    (WX, "location", "dim_location", "location"),
    (BT, "ts_utc", "dim_datetime", "ts_utc"),
]
write(
    "relationships.tmdl",
    "\n".join(
        f"relationship {a}_{ac}_to_{b}_{bc}\n{T}fromColumn: {a}.{ac}\n{T}toColumn: {b}.{bc}\n"
        for a, ac, b, bc in RELS
    ),
)
write(
    "expressions.tmdl",
    'expression PgServer = "localhost" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
    f"{T}lineageTag: 6f1c1b50-0a52-4a6d-9a3a-0c1d6a2f0001\n\n"
    'expression PgDatabase = "gridpulse" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
    f"{T}lineageTag: 6f1c1b50-0a52-4a6d-9a3a-0c1d6a2f0002\n",
)
tables = [MKT, "dim_datetime", "dim_location", WX, BT, BAT, NOI, MON]
write(
    "model.tmdl",
    "model Model\n"
    f"{T}culture: en-US\n{T}defaultPowerBIDataSourceVersion: powerBI_V3\n\n"
    + "".join(f"ref table {n}\n" for n in tables)
    + "\nref expression PgServer\nref expression PgDatabase\n",
)
write("database.tmdl", f"database GridPulse\n{T}compatibilityLevel: 1601\n")
(ROOT / "definition.pbism").write_text(
    '{\n  "version": "4.0",\n  "settings": {}\n}\n', encoding="utf-8"
)
Path("powerbi/GridPulse.pbip").write_text(
    '{\n  "version": "1.0",\n  "artifacts": [\n    {\n      "report": {\n        "path": "GridPulse.Report"\n      }\n    }\n  ],\n'
    '  "settings": {\n    "enableAutoRecovery": true\n  }\n}\n',
    encoding="utf-8",
)
print("generated", len(list(DEF.rglob("*.tmdl"))), "tmdl files")
