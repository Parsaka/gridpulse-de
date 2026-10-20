"""Interactive, self-contained dashboard (one HTML file, Plotly) built from results.json + data."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

BLUE, GREY, TEAL, AMBER, SLATE, RED = (
    "#2563eb",
    "#6b7280",
    "#0d9488",
    "#d97706",
    "#64748b",
    "#dc2626",
)
LAYOUT = {
    "template": "simple_white",
    "font": {"family": "Inter, Segoe UI, Arial, sans-serif", "size": 13},
    "margin": {"l": 60, "r": 30, "t": 50, "b": 55},
    "height": 430,
    "legend": {"orientation": "h", "y": -0.2},
}


def _html(fig: go.Figure, first: bool) -> str:
    fig.update_layout(**LAYOUT)
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn" if first else False, config={"displaylogo": False}
    )


def _regime(df: pd.DataFrame) -> go.Figure:
    m = df.groupby("month").agg(
        price=("price_eur_mwh", "mean"),
        neg=("price_eur_mwh", lambda s: int((s < 0).sum())),
        spike=("price_eur_mwh", lambda s: int((s > 300).sum())),
    )
    fig = go.Figure()
    fig.add_bar(
        x=m.index, y=m["neg"], name="hours with negative price", marker_color="#93c5fd", yaxis="y2"
    )
    fig.add_bar(
        x=m.index, y=m["spike"], name="hours above 300 EUR/MWh", marker_color="#fca5a5", yaxis="y2"
    )
    fig.add_scatter(
        x=m.index,
        y=m["price"],
        name="mean price (EUR/MWh)",
        mode="lines+markers",
        line={"color": "#111827", "width": 3},
    )
    fig.update_layout(
        title="Prices climbed through 2026 while negative-price hours became rarer",
        yaxis={"title": "EUR/MWh"},
        yaxis2={"title": "hours per month", "overlaying": "y", "side": "right", "showgrid": False},
        barmode="group",
    )
    return fig


def _merit(res: dict) -> go.Figure:
    cv = pd.DataFrame(res["price_level"]["curve"]).dropna(subset=["median_a", "median_b"])
    pa = res["price_level"]["aug_oct_2026_vs_2025"]
    fig = go.Figure()
    for k, col, name in (("a", SLATE, "Aug-Oct 2025"), ("b", RED, "Aug-Oct 2026")):
        fig.add_scatter(
            x=cv["residual_gw_mid"],
            y=cv[f"p75_{k}"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
        fig.add_scatter(
            x=cv["residual_gw_mid"],
            y=cv[f"p25_{k}"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(100,116,139,0.15)" if k == "a" else "rgba(220,38,38,0.15)",
            showlegend=False,
            hoverinfo="skip",
        )
        fig.add_scatter(
            x=cv["residual_gw_mid"],
            y=cv[f"median_{k}"],
            mode="lines+markers",
            name=name,
            line={"color": col, "width": 3},
        )
    fig.update_layout(
        title=f"Same residual load, ~{pa['premium_eur_mwh']:.0f} EUR/MWh higher price in 2026",
        xaxis={"title": "residual load (GW): demand minus wind and solar"},
        yaxis={"title": "median price and quartiles (EUR/MWh)"},
    )
    return fig


def _heatmap(df: pd.DataFrame) -> go.Figure:
    neg = df[df["price_eur_mwh"] < 0]
    piv = neg.pivot_table(
        index="month", columns="hour_local", values="price_eur_mwh", aggfunc="count"
    )
    piv = piv.reindex(index=sorted(df["month"].unique()), columns=range(24)).fillna(0)
    fig = go.Figure(
        go.Heatmap(
            z=piv.to_numpy(),
            x=list(piv.columns),
            y=list(piv.index),
            colorscale="Blues",
            colorbar={"title": "hours"},
        )
    )
    fig.update_layout(
        title="Negative prices are a midday event",
        xaxis={"title": "hour of day (Berlin time)"},
        yaxis={"autorange": "reversed"},
        height=560,
    )
    return fig


def _probability(res: dict) -> go.Figure:
    rows = res["negative"]["probability_when_residual_low"]
    labels = [f"residual load <= {v['residual_max_gw']} GW" for v in rows.values()]
    fig = go.Figure()
    for tag, name, col in (("a", "Apr-Sep 2025", SLATE), ("b", "Apr-Sep 2026", RED)):
        p = [100 * v[tag]["p"] for v in rows.values()]
        err_hi = [100 * v[tag]["ci"][1] - 100 * v[tag]["p"] for v in rows.values()]
        err_lo = [100 * v[tag]["p"] - 100 * v[tag]["ci"][0] for v in rows.values()]
        fig.add_bar(
            x=labels,
            y=p,
            name=name,
            marker_color=col,
            error_y={"type": "data", "symmetric": False, "array": err_hi, "arrayminus": err_lo},
        )
    fig.update_layout(
        title="Surplus hours turn negative far less often in 2026",
        yaxis={"title": "share with a negative price (%)"},
        barmode="group",
    )
    return fig


def _skill(res: dict) -> go.Figure:
    sk = res["forecast"]["skill"]
    items = [
        ("same hour last week", sk["models"]["naive_168h"], GREY),
        ("same hour yesterday", sk["baseline"], GREY),
        ("model without weather", sk["models"]["lgbm_calendar"], TEAL),
        ("model with observed weather", sk["models"]["lgbm_weather"], BLUE),
    ]
    fig = go.Figure(
        go.Bar(
            x=[i[0] for i in items],
            y=[i[1]["mae"] for i in items],
            marker_color=[i[2] for i in items],
            error_y={
                "type": "data",
                "symmetric": False,
                "array": [i[1]["mae_ci"][1] - i[1]["mae"] for i in items],
                "arrayminus": [i[1]["mae"] - i[1]["mae_ci"][0] for i in items],
            },
        )
    )
    fig.update_layout(
        title="Forecast error over a year of monthly walk-forward tests (95% interval)",
        yaxis={"title": "mean absolute error (EUR/MWh)"},
    )
    return fig


def _explorer(wf: pd.DataFrame) -> go.Figure:
    w = wf.copy()
    w["ts_utc"] = pd.to_datetime(w["ts_utc"], utc=True)
    w["t"] = w["ts_utc"].dt.tz_convert("Europe/Berlin")
    w["month"] = w["t"].dt.strftime("%Y-%m")
    months = sorted(w["month"].unique())
    default = months[-2] if len(months) > 1 else months[-1]
    fig = go.Figure()
    for m in months:
        g = w[w["month"] == m]
        vis = m == default
        t = g["t"].dt.tz_localize(None)
        fig.add_scatter(
            x=t,
            y=g["q90"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
            visible=vis,
        )
        fig.add_scatter(
            x=t,
            y=g["q10"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(37,99,235,0.15)",
            name="model 10-90% interval",
            showlegend=vis and m == default,
            visible=vis,
        )
        fig.add_scatter(
            x=t,
            y=g["naive_24h"],
            mode="lines",
            line={"color": GREY, "dash": "dot", "width": 1.2},
            name="same hour yesterday",
            visible=vis,
        )
        fig.add_scatter(
            x=t,
            y=g["lgbm_weather"],
            mode="lines",
            line={"color": BLUE, "width": 2},
            name="weather model",
            visible=vis,
        )
        fig.add_scatter(
            x=t,
            y=g["actual"],
            mode="lines",
            line={"color": "#111827", "width": 2},
            name="actual",
            visible=vis,
        )
    buttons = []
    for i, m in enumerate(months):
        vis = [False] * (5 * len(months))
        for j in range(5):
            vis[5 * i + j] = True
        buttons.append({"label": m, "method": "update", "args": [{"visible": vis}]})
    fig.update_layout(
        title="Forecast explorer: pick a month",
        updatemenus=[
            {
                "buttons": buttons,
                "active": months.index(default),
                "x": 0,
                "y": 1.18,
                "xanchor": "left",
            }
        ],
        yaxis={"title": "EUR/MWh"},
        height=480,
    )
    return fig


def _battery(res: dict) -> go.Figure:
    st = res["battery"]["strategies"]
    order = [
        ("perfect", "perfect foresight", AMBER),
        ("lgbm_weather", "weather model", BLUE),
        ("lgbm_weather_noise50", "model, 50% weather noise", "#60a5fa"),
        ("lgbm_weather_noise100", "model, 100% weather noise", "#93c5fd"),
        ("lgbm_calendar", "model without weather", TEAL),
        ("naive_24h", "same hour yesterday", GREY),
    ]
    order = [o for o in order if o[0] in st]
    fig = go.Figure(
        go.Bar(
            x=[o[1] for o in order],
            y=[st[o[0]]["eur_per_mw_year"] for o in order],
            marker_color=[o[2] for o in order],
            text=[f"{100 * st[o[0]]['capture_of_perfect']:.0f}%" for o in order],
            textposition="outside",
            error_y={
                "type": "data",
                "symmetric": False,
                "array": [st[o[0]]["ci_per_year"][1] - st[o[0]]["eur_per_mw_year"] for o in order],
                "arrayminus": [
                    st[o[0]]["eur_per_mw_year"] - st[o[0]]["ci_per_year"][0] for o in order
                ],
            },
        )
    )
    d = res["battery"]["differences_per_year"]["lgbm_weather_minus_naive_24h"]
    fig.update_layout(
        title=f"Battery revenue (1 MW / 2 MWh): weather model vs yesterday {d['mean']:+,.0f} EUR/MW/year, interval {d['ci'][0]:+,.0f} to {d['ci'][1]:+,.0f}",
        yaxis={"title": "EUR per MW per year (day-ahead only)"},
    )
    return fig


CSS = """
body{font-family:Inter,'Segoe UI',Arial,sans-serif;margin:0;background:#f6f8fb;color:#1f2937}
header{background:#0d3b66;color:#fff;padding:36px 24px}
header h1{margin:0 0 8px;font-size:30px} header p{max-width:900px;line-height:1.6;margin:6px 0;opacity:.92}
main{max-width:1100px;margin:0 auto;padding:24px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin:-48px 0 24px}
.kpi{background:#fff;border-radius:14px;padding:18px;box-shadow:0 6px 22px rgba(13,59,102,.12)}
.kpi b{display:block;font-size:26px;color:#0d3b66}.kpi span{font-size:13px;color:#6b7280}
section{background:#fff;border-radius:14px;padding:16px 18px;margin:0 0 18px;box-shadow:0 4px 16px rgba(13,59,102,.08)}
section p{margin:6px 4px 0;color:#4b5563;font-size:14px;line-height:1.55}
footer{max-width:1100px;margin:0 auto;padding:8px 24px 40px;font-size:12px;color:#6b7280;line-height:1.6}
"""


def build_dashboard(res: dict, df: pd.DataFrame, wf: pd.DataFrame, path: str | Path) -> Path:
    sk = res["forecast"]["skill"]["models"]["lgbm_weather"]
    bat = res["battery"]["differences_per_year"]["lgbm_weather_minus_naive_24h"]
    pa = res["price_level"]["aug_oct_2026_vs_2025"]
    pr = res["negative"]["probability_when_residual_low"]["le_8_gw"]
    kpis = [
        (
            f"-{100 * sk['skill_vs_baseline']:.0f}% error",
            f"weather model vs yesterday, 95% interval {100 * sk['skill_ci'][0]:.0f} to {100 * sk['skill_ci'][1]:.0f}%",
        ),
        (
            f"{bat['mean']:+,.0f} EUR/MW/yr",
            f"battery revenue vs yesterday, interval {bat['ci'][0]:+,.0f} to {bat['ci'][1]:+,.0f}",
        ),
        (
            f"+{pa['premium_eur_mwh']:.0f} EUR/MWh",
            "price premium Aug-Oct 2026 vs 2025 at equal residual load",
        ),
        (
            f"{100 * pr['a']['p']:.0f}% to {100 * pr['b']['p']:.0f}%",
            "chance of a negative price when residual load <= 8 GW (2025 to 2026)",
        ),
    ]
    figs = [
        _regime(df),
        _merit(res),
        _heatmap(df),
        _probability(res),
        _skill(res),
        _explorer(wf),
        _battery(res),
    ]
    notes = [
        "Monthly average price with the number of negative and spike hours.",
        "Holding residual load fixed, the price level moved up by far more than any change in demand or renewables explains: fuel and CO2 prices are not in the data.",
        "Every month and hour with at least one negative price; the pattern is solar-driven.",
        "Same weather-driven surplus, but fewer negative prices in 2026: the market absorbs surplus better (cause not identified here).",
        "Walk-forward: every month predicted by models trained only on earlier data. The weather model uses OBSERVED weather as a stand-in for a forecast, so this is an upper bound.",
        "Actual versus the weather model and yesterday's price, with the model's 10-90% interval (which is too narrow: about 70% coverage).",
        "A battery scheduled from each forecast and paid at actual prices. A lower error does not automatically mean higher revenue.",
    ]
    body = "".join(
        f"<section>{_html(f, i == 0)}<p>{n}</p></section>"
        for i, (f, n) in enumerate(zip(figs, notes, strict=True))
    )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GridPulse DE: German power market analysis</title><style>{CSS}</style></head><body>
<header><h1>GridPulse DE: German day-ahead power market</h1>
<p><b>Question.</b> {res["question"]}</p>
<p>{res["meta"]["market_hours"]:,} hourly prices ({res["meta"]["market_from"][:10]} to {res["meta"]["market_to"][:10]}); {res["meta"]["walk_forward_hours"]:,} out-of-sample forecast hours.</p></header>
<main><div class="kpis">{"".join(f'<div class="kpi"><b>{a}</b><span>{b}</span></div>' for a, b in kpis)}</div>{body}</main>
<footer>Data: Bundesnetzagentur | SMARD.de (CC BY 4.0), Deutscher Wetterdienst (CC BY 4.0, via Bright Sky). Aggregated and combined by GridPulse DE; not endorsed by the publishers. Personal portfolio project; not trading or investment advice. Intervals are 95% day-block bootstrap intervals.</footer>
</body></html>"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
