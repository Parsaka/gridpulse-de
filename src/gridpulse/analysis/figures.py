"""Static figures (matplotlib) for the analysis report, README and website.

Each title states the finding, not the chart type. Colours are colour-blind safe and used
consistently: grey = naive baseline, blue = weather model, teal = calendar-only model, amber =
perfect foresight, slate = 2025, red = 2026.
"""

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

C = {
    "naive": "#6b7280",
    "model": "#2563eb",
    "calendar": "#0d9488",
    "perfect": "#d97706",
    "y25": "#64748b",
    "y26": "#dc2626",
    "grid": "#e5e7eb",
    "profile": "#7c3aed",
}
SOURCE = "Data: Bundesnetzagentur | SMARD.de (CC BY 4.0), Deutscher Wetterdienst. GridPulse DE."


def _style():
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 140,
            "font.size": 10,
            "axes.titlesize": 12.5,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": C["grid"],
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "legend.frameon": False,
        }
    )


def _finish(fig, path: Path, note: str | None = None):
    text = textwrap.fill(note or SOURCE, width=int(fig.get_figwidth() * 15))
    lines = len(text.splitlines())
    fig.text(0.01, 0.005, text, fontsize=7.5, color="#6b7280", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.025 * lines + 0.01, 1, 1))
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def fig_regime(res, df, path):
    m = df.groupby("month").agg(
        price=("price_eur_mwh", "mean"),
        neg=("price_eur_mwh", lambda s: int((s < 0).sum())),
        spike=("price_eur_mwh", lambda s: int((s > 300).sum())),
    )
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(m))
    ax2 = ax.twinx()
    ax2.bar(x - 0.2, m["neg"], 0.4, color="#93c5fd", label="hours with negative price")
    ax2.bar(x + 0.2, m["spike"], 0.4, color="#fca5a5", label="hours above 300 EUR/MWh")
    ax2.set_ylabel("hours per month")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax.plot(x, m["price"], color="#111827", marker="o", lw=2, label="mean day-ahead price")
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.set_ylabel("EUR/MWh")
    ax.set_xticks(x[::2], [lab for lab in m.index[::2]], rotation=45, ha="right")
    ax.set_title("Prices climbed through 2026 while negative-price hours became rarer")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    return _finish(fig, path)


def fig_merit_order(res, df, path):
    cv = pd.DataFrame(res["price_level"]["curve"]).dropna(subset=["median_a", "median_b"])
    pa = res["price_level"]["aug_oct_2026_vs_2025"]
    fig, ax = plt.subplots(figsize=(9, 5))
    for k, col, lab in (("a", C["y25"], "Aug-Oct 2025"), ("b", C["y26"], "Aug-Oct 2026")):
        ax.fill_between(
            cv["residual_gw_mid"], cv[f"p25_{k}"], cv[f"p75_{k}"], color=col, alpha=0.15
        )
        ax.plot(cv["residual_gw_mid"], cv[f"median_{k}"], color=col, lw=2.4, marker="o", label=lab)
    ax.set_xlabel("residual load (GW): demand minus wind and solar")
    ax.set_ylabel("day-ahead price (EUR/MWh), median and quartiles")
    lo, hi = pa["premium_ci"]
    ax.set_title(
        f"At the same residual load, 2026 prices were ~{pa['premium_eur_mwh']:.0f} EUR/MWh higher"
    )
    ax.text(
        0.03,
        0.95,
        f"Premium holding residual load and hour of day fixed:\n+{pa['premium_eur_mwh']:.0f} EUR/MWh "
        f"(95% interval {lo:.0f} to {hi:.0f})\nMean residual load was LOWER in 2026 "
        f"({pa['mean_residual_b']:.1f} vs {pa['mean_residual_a']:.1f} GW):\nthe cause is outside this data (fuel, CO2).",
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round", "fc": "white", "ec": C["grid"]},
    )
    ax.legend(loc="lower right")
    return _finish(fig, path)


def fig_negative_heatmap(res, df, path):
    neg = df[df["price_eur_mwh"] < 0]
    piv = neg.pivot_table(
        index="month", columns="hour_local", values="price_eur_mwh", aggfunc="count"
    )
    piv = piv.reindex(index=sorted(df["month"].unique()), columns=range(24)).fillna(0)
    s = res["negative"]["summary"]
    fig, ax = plt.subplots(figsize=(10, 6.4))
    im = ax.imshow(piv.to_numpy(), aspect="auto", cmap="Blues")
    ax.set_yticks(range(len(piv)), piv.index)
    ax.set_xticks(range(0, 24, 2), range(0, 24, 2))
    ax.set_xlabel("hour of day (Berlin time)")
    ax.grid(False)
    ax.set_title(
        f"Negative prices are a midday event: {100 * s['midday_share_of_negative']:.0f}% fall "
        f"between 10 and 16 h"
    )
    fig.colorbar(im, ax=ax, label="hours with a negative price")
    return _finish(fig, path)


def fig_negative_probability(res, df, path):
    rows = res["negative"]["probability_when_residual_low"]
    labels, pa, pb, ea, eb = [], [], [], [], []
    for v in rows.values():
        labels.append(f"residual load\n<= {v['residual_max_gw']} GW")
        for tag, p_, e_ in (("a", pa, ea), ("b", pb, eb)):
            p_.append(100 * v[tag]["p"])
            e_.append(
                [
                    100 * v[tag]["p"] - 100 * v[tag]["ci"][0],
                    100 * v[tag]["ci"][1] - 100 * v[tag]["p"],
                ]
            )
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(x - 0.2, pa, 0.4, yerr=np.array(ea).T, color=C["y25"], capsize=4, label="Apr-Sep 2025")
    ax.bar(x + 0.2, pb, 0.4, yerr=np.array(eb).T, color=C["y26"], capsize=4, label="Apr-Sep 2026")
    ax.set_xticks(x, labels)
    ax.set_ylabel("share of those hours with a negative price (%)")
    ax.set_title("Surplus hours turn negative far less often in 2026 than in 2025")
    ax.legend()
    return _finish(fig, path)


def fig_skill(res, df, path):
    sk = res["forecast"]["skill"]
    models = [
        ("naive_168h", "same hour\nlast week", C["naive"], sk["models"]["naive_168h"]),
        ("naive_24h", "same hour\nyesterday", C["naive"], sk["baseline"]),
        ("profile_28d", "4-week average\nby hour", C["profile"], sk["models"]["profile_28d"]),
        ("lgbm_calendar", "model without\nweather", C["calendar"], sk["models"]["lgbm_calendar"]),
        ("lgbm_weather", "model with\nobserved weather", C["model"], sk["models"]["lgbm_weather"]),
    ]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1, 1.25]})
    for i, (_, _lab, col, m) in enumerate(models):
        a1.bar(
            i,
            m["mae"],
            color=col,
            yerr=[[m["mae"] - m["mae_ci"][0]], [m["mae_ci"][1] - m["mae"]]],
            capsize=5,
        )
        a1.text(i, m["mae"] + 3, f"{m['mae']:.1f}", ha="center", fontsize=9)
    a1.set_xticks(range(len(models)), [m[1] for m in models], fontsize=8.5)
    a1.set_ylabel("mean absolute error (EUR/MWh), 95% interval")
    g = sk["models"]["lgbm_weather"]
    a1.set_title(f"Weather model: {100 * g['skill_vs_baseline']:.0f}% lower error than yesterday")
    mo = res["forecast"]["monthly"]
    y = np.arange(len(mo))
    d = np.array([r["diff"] for r in mo])
    lo = np.array([r["diff_ci"][0] for r in mo])
    hi = np.array([r["diff_ci"][1] for r in mo])
    col = [C["model"] if h < 0 else "#9ca3af" for h in hi]
    a2.hlines(y, lo, hi, color=col, lw=2.2)
    a2.scatter(d, y, color=col, zorder=3)
    a2.axvline(0, color="#111827", lw=1)
    a2.set_yticks(y, [r["month"] for r in mo])
    a2.invert_yaxis()
    a2.set_xlabel("error change vs yesterday (EUR/MWh, negative = model better)")
    wins = sum(1 for r in mo if r["diff_ci"][1] < 0)
    a2.set_title(f"Month by month: clearly better in {wins} of {len(mo)} months")
    return _finish(fig, path)


def fig_noise(res, df, path):
    nz = res["forecast"]["noise"]
    pts = [n for n in nz if n["noise_pct_of_std"] is not None]
    cal = next(n for n in nz if n["noise_pct_of_std"] is None)
    x = [n["noise_pct_of_std"] for n in pts]
    g = [100 * n["gain"] for n in pts]
    lo = [100 * n["gain_ci"][0] for n in pts]
    hi = [100 * n["gain_ci"][1] for n in pts]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.fill_between(x, lo, hi, color=C["model"], alpha=0.15)
    ax.plot(x, g, color=C["model"], marker="o", lw=2.4, label="model with noisy weather")
    ax.axhline(100 * cal["gain"], color=C["calendar"], ls="--", label="model without any weather")
    ax.axhline(0, color="#111827", lw=1)
    ax.set_xlabel("noise added to weather inputs (% of each feature's standard deviation)")
    ax.set_ylabel("error reduction vs yesterday (%)")
    ax.set_title("The gain depends on how good the weather forecast is")
    ax.legend()
    note = SOURCE + " Noise is illustrative, not calibrated to real forecast errors."
    return _finish(fig, path, note)


def fig_errors(res, df, path):
    fh = pd.DataFrame(res["forecast"]["by_hour"])
    fr = pd.DataFrame(res["forecast"]["by_regime"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
    a1.plot(
        fh["hour_local"], fh["mae_naive_24h"], color=C["naive"], lw=2, label="same hour yesterday"
    )
    a1.plot(
        fh["hour_local"], fh["mae_lgbm_weather"], color=C["model"], lw=2.4, label="weather model"
    )
    a1.set_xlabel("hour of day (Berlin time)")
    a1.set_ylabel("mean absolute error (EUR/MWh)")
    a1.set_title("Biggest errors in the morning and evening ramps")
    a1.legend()
    x = np.arange(len(fr))
    a2.bar(x - 0.2, fr["mae_naive_24h"], 0.4, color=C["naive"], label="yesterday")
    a2.bar(x + 0.2, fr["mae_lgbm_weather"], 0.4, color=C["model"], label="weather model")
    a2.set_xticks(
        x, [f"{r}\n(n={n})" for r, n in zip(fr["regime"], fr["n"], strict=True)], fontsize=7.5
    )
    a2.set_title("Extreme prices stay hard to forecast")
    a2.legend()
    return _finish(fig, path)


def fig_forecast_week(res, df, wf, path):
    w = wf.copy()
    w["ts_utc"] = pd.to_datetime(w["ts_utc"], utc=True)
    peak = w.loc[w["actual"].idxmax(), "ts_utc"]
    start = (peak - pd.Timedelta(days=3)).floor("D")
    s = w[(w["ts_utc"] >= start) & (w["ts_utc"] < start + pd.Timedelta(days=7))]
    t = s["ts_utc"].dt.tz_convert("Europe/Berlin")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.fill_between(
        t, s["q10"], s["q90"], color=C["model"], alpha=0.15, label="model 10-90% interval"
    )
    ax.plot(t, s["naive_24h"], color=C["naive"], lw=1.2, ls="--", label="same hour yesterday")
    ax.plot(t, s["lgbm_weather"], color=C["model"], lw=2, label="weather model")
    ax.plot(t, s["actual"], color="#111827", lw=2, label="actual")
    ax.set_ylabel("EUR/MWh")
    ax.set_title(f"A week around the highest price in the test year ({t.min():%d %b %Y})")
    ax.legend(ncol=4, loc="upper left")
    return _finish(fig, path)


def fig_battery(res, df, path):
    st = res["battery"]["strategies"]
    order = [
        ("perfect", "perfect\nforesight", C["perfect"]),
        ("profile_28d", "4-week average\nby hour", C["profile"]),
        ("lgbm_weather", "weather\nmodel", C["model"]),
        ("lgbm_weather_noise50", "model, 50%\nweather noise", "#60a5fa"),
        ("lgbm_weather_noise100", "model, 100%\nweather noise", "#93c5fd"),
        ("lgbm_calendar", "model without\nweather", C["calendar"]),
        ("naive_24h", "same hour\nyesterday", C["naive"]),
    ]
    order = [o for o in order if o[0] in st]
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (k, _lab, col) in enumerate(order):
        v = st[k]
        ax.bar(
            i,
            v["eur_per_mw_year"] / 1000,
            color=col,
            yerr=[
                [(v["eur_per_mw_year"] - v["ci_per_year"][0]) / 1000],
                [(v["ci_per_year"][1] - v["eur_per_mw_year"]) / 1000],
            ],
            capsize=5,
        )
        ax.text(
            i,
            v["ci_per_year"][1] / 1000 + 2,
            f"{100 * v['capture_of_perfect']:.0f}%",
            ha="center",
            fontsize=9,
        )
    ax.set_xticks(range(len(order)), [o[1] for o in order], fontsize=8.5)
    ax.set_ylabel("revenue per MW of battery per year (thousand EUR)")
    p = res["battery"]["parameters"]
    gain = res["forecast"]["skill"]["models"]["lgbm_weather"]["skill_vs_baseline"]
    d = res["battery"]["differences_per_year"]["lgbm_weather_minus_naive_24h"]
    spans_zero = d["ci"][0] <= 0 <= d["ci"][1]
    verdict = (
        f"but battery revenue is unchanged ({d['mean']:+,.0f} EUR/MW/year, interval spans zero)"
        if spans_zero
        else f"and battery revenue differs by {d['mean']:+,.0f} EUR/MW/year"
    )
    ax.set_title(f"{100 * gain:.0f}% lower forecast error, {verdict}", fontsize=11.5)
    pv = res["battery"]["differences_per_year"]["profile_28d_minus_naive_24h"]
    if pv["ci"][0] > 0:
        ax.text(
            0.99,
            0.97,
            f"A plain 4-week average by hour earns {pv['mean']:+,.0f} EUR/MW/year\nmore than yesterday's price (interval {pv['ci'][0]:+,.0f} to {pv['ci'][1]:+,.0f})",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color=C["profile"],
        )

    note = (
        f"Battery {p['power_mw']:.0f} MW / {p['capacity_mwh']:.0f} MWh, round-trip efficiency "
        f"{100 * p['round_trip_efficiency']:.0f}%, {p['throughput_cost_eur_per_mwh']:.0f} EUR/MWh degradation; "
        f"day-ahead prices only, no intraday or fees. Bars: 95% day-bootstrap interval; labels: % of perfect. "
        + SOURCE
    )
    return _finish(fig, path, note)


def fig_interval(res, df, path):
    ir = res["forecast"]["interval"]
    reg = pd.DataFrame(ir["by_regime"])
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.bar(range(len(reg)), 100 * reg["coverage"], color=C["model"])
    ax.axhline(100 * ir["nominal"], color="#111827", ls="--", label="nominal 80%")
    ax.set_xticks(
        range(len(reg)),
        [f"{r}\n(n={n})" for r, n in zip(reg["regime"], reg["n"], strict=True)],
        fontsize=8,
    )
    ax.set_ylabel("actual price inside the 10-90% interval (%)")
    ax.set_title(
        f"The prediction interval is too narrow: {100 * ir['coverage']:.0f}% coverage, not 80%"
    )
    ax.legend()
    return _finish(fig, path)


def fig_cumulative(res, df, path):
    cu = res["battery"]["cumulative"]
    days = pd.to_datetime(cu["days"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    spec = [
        ("perfect", "perfect foresight", C["perfect"], 2.4),
        ("profile_28d", "4-week average by hour", C["profile"], 2),
        ("lgbm_weather", "weather model", C["model"], 2),
        ("naive_24h", "same hour yesterday", C["naive"], 2),
    ]
    for k, lab, col, lw in spec:
        ax.plot(days, np.array(cu[k]) / 1000, label=lab, color=col, lw=lw)
    ax.set_ylabel("cumulative revenue of a 1 MW / 2 MWh battery (thousand EUR)")
    conc = res["battery"]["concentration"]
    ax.set_title(
        f"Revenue is lumpy: the best {conc['top10pct_days']} days earn "
        f"{100 * conc['top10pct_share_of_perfect_revenue']:.0f}% of the year"
    )
    ax.legend(loc="upper left")
    return _finish(fig, path)


def fig_sizes(res, df, path):
    sz = res["battery"]["sizes"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.2, 1]})
    x = np.arange(len(sz))
    w = 0.2
    for j, (k, lab, col) in enumerate(
        [
            ("naive_24h", "same hour yesterday", C["naive"]),
            ("profile_28d", "4-week average", C["profile"]),
            ("lgbm_weather", "weather model", C["model"]),
            ("perfect", "perfect foresight", C["perfect"]),
        ]
    ):
        a1.bar(x + (j - 1.5) * w, [r[k] / 1000 for r in sz], w, label=lab, color=col)
    a1.set_xticks(x, [f"{r['duration_h']:.0f} h" for r in sz])
    a1.set_xlabel("battery duration at 1 MW (capacity in MWh)")
    a1.set_ylabel("revenue (thousand EUR per MW per year)")
    a1.legend(loc="upper left", fontsize=8)
    a1.set_title("Longer batteries earn more")
    d = np.array([r["model_minus_naive"] for r in sz])
    lo = np.array([r["model_minus_naive_ci"][0] for r in sz])
    hi = np.array([r["model_minus_naive_ci"][1] for r in sz])
    col = [C["model"] if lo_ > 0 else "#9ca3af" for lo_ in lo]
    a2.vlines(x, lo, hi, color=col, lw=3)
    a2.scatter(x, d, color=col, zorder=3)
    a2.axhline(0, color="#111827", lw=1)
    a2.set_xticks(x, [f"{r['duration_h']:.0f} h" for r in sz])
    a2.set_xlabel("battery duration")
    a2.set_ylabel("weather model minus yesterday (EUR/MW/year)")
    sig = [r for r in sz if r["model_minus_naive_ci"][0] > 0]
    a2.set_title(
        "The forecast starts to pay at "
        + (f"{sig[0]['duration_h']:.0f} h" if sig else "no tested size")
    )
    return _finish(fig, path)


def fig_day_types(res, df, path):
    dt = res["battery"]["day_types"]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    y = np.arange(len(dt))
    for i, r in enumerate(dt):
        ax.hlines(i, r["ci"][0], r["ci"][1], color=C["model"], lw=2.4)
        ax.scatter(r["mean_diff_eur_per_day"], i, color=C["model"], zorder=3)
    ax.axvline(0, color="#111827", lw=1)
    ax.set_yticks(y, [f"{r['group']} (n={r['days']})" for r in dt], fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlabel("weather model minus yesterday (EUR per day, 95% interval)")
    conc = res["battery"]["concentration"]
    ax.set_title(
        f"No kind of day where the model clearly wins: it beats yesterday on only "
        f"{100 * conc['model_beats_naive_share_of_days']:.0f}% of days"
    )
    return _finish(
        fig, path, "Exploratory: six overlapping groups, no multiplicity correction. " + SOURCE
    )


def make_figures(res: dict, df: pd.DataFrame, wf: pd.DataFrame, out_dir: str | Path) -> list[Path]:
    _style()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wf = wf.copy()
    paths = [
        fig_regime(res, df, out / "01_market_regime.png"),
        fig_merit_order(res, df, out / "02_same_residual_load_higher_price.png"),
        fig_negative_heatmap(res, df, out / "03_negative_prices_heatmap.png"),
        fig_negative_probability(res, df, out / "04_negative_probability.png"),
        fig_skill(res, df, out / "05_forecast_skill.png"),
        fig_errors(res, df, out / "07_error_structure.png"),
        fig_forecast_week(res, df, wf, out / "08_forecast_week.png"),
        fig_battery(res, df, out / "09_battery_value.png"),
        fig_interval(res, df, out / "10_interval_coverage.png"),
        fig_cumulative(res, df, out / "11_cumulative_revenue.png"),
        fig_sizes(res, df, out / "12_battery_size.png"),
        fig_day_types(res, df, out / "13_day_types.png"),
    ]
    from gridpulse.analysis import figures_factors as ff

    paths += [
        ff.fig_factors(res, df, out / "14_forecast_by_factor.png"),
        ff.fig_weather_effects(res, df, out / "15_weather_effects.png"),
        ff.fig_scenarios(res, df, out / "16_weather_scenarios.png"),
        ff.fig_capture(res, df, out / "17_solar_wind_capture.png"),
        ff.fig_consumer(res, df, out / "18_flexible_load_savings.png"),
        ff.fig_battery_factors(res, df, out / "19_battery_by_season_weather.png"),
        ff.fig_calibration(res, df, wf, out / "20_actual_vs_forecast.png"),
    ]
    if res["forecast"]["noise"]:
        paths.insert(5, fig_noise(res, df, out / "06_noise_sensitivity.png"))
    return paths
