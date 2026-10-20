"""Figures for the factor and business views (see factors.py). Style helpers come from figures.py."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gridpulse.analysis.figures import SOURCE, C, _finish  # noqa: E402


def fig_factors(res, df, path):
    ebf = res["factors"]["error_by_factor"]
    keys = [
        "wind_speed_kmh",
        "solar_kwh_m2",
        "temperature_c",
        "d_wind",
        "d_temperature",
        "residual_gw",
        "price_yesterday",
        "season",
    ]
    fig, axes = plt.subplots(2, 4, figsize=(15, 7), sharey=True)
    for ax, k in zip(axes.ravel(), keys, strict=True):
        f = ebf[k]
        bins = f["bins"]
        x = np.arange(len(bins))
        ax.bar(x - 0.2, [b["mae_naive"] for b in bins], 0.4, color=C["naive"], label="yesterday")
        ax.bar(
            x + 0.2, [b["mae_model"] for b in bins], 0.4, color=C["model"], label="weather model"
        )
        for i, b in enumerate(bins):
            top = max(b["mae_naive"], b["mae_model"]) + 1
            ax.text(i, top, f"{100 * b['gain']:+.0f}%", ha="center", fontsize=8)
        lab = [b["bin"] for b in bins]
        ax.set_xticks(x, [f"Q{i + 1}" for i in x] if f["unit"] else lab, fontsize=8)
        ax.set_title(f["label"] + (f" ({f['unit']})" if f["unit"] else ""), fontsize=10)
        if f["unit"]:
            ax.set_xlabel(f"{lab[0]}  to  {lab[-1]}", fontsize=7.5)
    axes[0, 0].legend(fontsize=8, loc="upper left")
    axes[0, 0].set_ylabel("mean absolute error (EUR/MWh)")
    axes[1, 0].set_ylabel("mean absolute error (EUR/MWh)")
    fig.suptitle(
        "The model helps most on sunny, changing-weather and surplus hours, least in winter",
        fontweight="bold",
        fontsize=12.5,
    )
    note = (
        "Quintiles (Q1 lowest to Q5 highest); labels show the model's gain over yesterday. "
        + SOURCE
    )
    return _finish(fig, path, note)


def fig_weather_effects(res, df, path):
    we = res["factors"]["weather_effects"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    order = ["load_gw", "wind_gw", "solar_gw", "temperature_c"]
    cols = {"year 1": C["y25"], "year 2": C["y26"]}
    for j, per in enumerate(["year 1", "year 2"]):
        for i, k in enumerate(order):
            e = we["effects"][per][k]
            a1.errorbar(
                e["effect"],
                i + (j - 0.5) * 0.25,
                xerr=[[e["effect"] - e["ci"][0]], [e["ci"][1] - e["effect"]]],
                fmt="o",
                color=cols[per],
                capsize=3,
                label=per if i == 0 else None,
            )
    a1.axvline(0, color="#111827", lw=1)
    a1.set_yticks(range(len(order)), [we["effects"]["all"][k]["label"] for k in order])
    a1.invert_yaxis()
    a1.set_xlabel("price change in EUR/MWh (95% interval)")
    wind = we["effects"]["all"]["wind_gw"]["effect"]
    a1.set_title(
        f"Each extra GW of wind lowers the price by about {abs(wind):.0f} EUR/MWh", fontsize=11
    )
    a1.legend(title="12-month period", fontsize=8)
    r2 = we["r2"]
    names = list(r2)
    colors = [C["naive"], C["calendar"], C["model"], "#93c5fd"]
    a2.barh(range(len(names)), [100 * r2[n] for n in names], color=colors)
    for i, n in enumerate(names):
        a2.text(100 * r2[n] + 1, i, f"{100 * r2[n]:.0f}%", va="center", fontsize=9)
    a2.set_yticks(range(len(names)), names, fontsize=8)
    a2.invert_yaxis()
    a2.set_xlim(0, 100)
    a2.set_xlabel("share of price variation explained (%)")
    a2.set_title("Wind and solar explain the most", fontsize=11)
    return _finish(
        fig,
        path,
        "Regression with hour, month and weekend controls; descriptive, not causal. " + SOURCE,
    )


def fig_scenarios(res, df, path):
    allh = next(s for s in res["factors"]["scenarios"] if s["scenario"] == "All hours")
    sc = sorted(
        (s for s in res["factors"]["scenarios"] if s["scenario"] != "All hours"),
        key=lambda s: s["mean_price"],
    )
    fig, ax = plt.subplots(figsize=(11, 5.2))
    for i, s in enumerate(sc):
        ax.hlines(i, s["p10"], s["p90"], color=C["model"], lw=3, alpha=0.5)
        ax.scatter(s["mean_price"], i, color=C["model"], zorder=3)
        txt = f"{100 * s['share_negative']:.0f}% negative | model {100 * s['gain']:+.0f}% vs yesterday | n={s['hours']}"
        ax.text(max(s["p90"], 0) + 6, i, txt, va="center", fontsize=8)
    ax.axvline(allh["mean_price"], color="#111827", ls="--", lw=1)
    ax.text(allh["mean_price"] + 2, -0.75, "average of all hours", fontsize=8)
    ax.set_yticks(range(len(sc)), [s["scenario"] for s in sc])
    ax.set_xlim(-60, 460)
    ax.set_xlabel("day-ahead price in EUR/MWh (dot = mean, line = 10th to 90th percentile)")
    ax.set_title(
        f"A sunny weekend midday averages {sc[0]['mean_price']:.0f} EUR/MWh, a calm winter evening {sc[-1]['mean_price']:.0f}",
        fontsize=11.5,
    )
    return _finish(fig, path, "Walk-forward test period (Oct 2025 to Oct 2026). " + SOURCE)


def fig_capture(res, df, path):
    cr = res["factors"]["capture_rates"]
    m = pd.DataFrame(cr["months"])
    x = pd.to_datetime(m["month"] + "-01")
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(x, 100 * m["solar_capture"], color=C["perfect"], lw=2.5, marker="o", label="solar")
    ax.plot(x, 100 * m["wind_capture"], color=C["model"], lw=2.5, marker="o", label="wind")
    ax.axhline(100, color="#111827", lw=1, ls="--")
    ax.set_ylabel("price received as % of the average price")
    ax.set_title(
        f"Solar sells at {100 * cr['solar_capture_all']:.0f}% of the average price overall, "
        f"as low as {100 * m['solar_capture'].min():.0f}% in spring",
        fontsize=11.5,
    )
    ax.legend()
    return _finish(
        fig,
        path,
        "Generation-weighted day-ahead price divided by the plain monthly average. " + SOURCE,
    )


def fig_consumer(res, df, path):
    cs = res["factors"]["consumer_shift"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
    m = pd.DataFrame(cs["by_month"])
    x = np.arange(len(m))
    a1.bar(x - 0.2, m["flat"], 0.4, color=C["naive"], label="running flat all day")
    a1.bar(
        x + 0.2,
        m["cheapest_hours"],
        0.4,
        color=C["calendar"],
        label=f"only in the cheapest {cs['hours_per_day']} hours",
    )
    a1.set_xticks(x[::2], [s[2:] for s in m["month"]][::2], fontsize=8)
    a1.set_ylabel("average price paid (EUR/MWh)")
    a1.set_title(
        f"Moving {cs['hours_per_day']} hours of load saves {100 * cs['saving_share']:.0f}% of energy cost",
        fontsize=11,
    )
    a1.legend(fontsize=8)
    st = cs["block_start_hour_share"]
    hours = sorted(int(h) for h in st)
    a2.bar(hours, [100 * st[str(h)] for h in hours], color=C["perfect"])
    a2.set_xlabel("start hour of the cheapest 4-hour block (Berlin time)")
    a2.set_ylabel("share of days (%)")
    a2.set_title("The cheapest window is around noon", fontsize=11)
    return _finish(
        fig,
        path,
        "Energy price only (no grid fees or levies); prices are known the day before. " + SOURCE,
    )


def fig_battery_factors(res, df, path):
    bf = res["factors"]["battery_by_factor"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 4.8), gridspec_kw={"width_ratios": [1.2, 1]})
    m = bf["by_month"]
    x = np.arange(len(m))
    a1.bar(x, [r["perfect_eur_day"] for r in m], color=C["perfect"])
    a1.set_xticks(x, [r["month"][2:] for r in m], fontsize=8, rotation=45)
    a1.set_ylabel("EUR per day, 1 MW / 2 MWh battery (perfect foresight)")
    best = max(r["perfect_eur_day"] for r in m)
    worst = min(r["perfect_eur_day"] for r in m)
    a1.set_title(
        f"A battery earns {best / worst:.0f}x more in the best month than the worst", fontsize=11
    )
    pos, labels = 0, []
    for name in ["wind", "solar", "temperature"]:
        start = pos
        for i, b in enumerate(bf[name]):
            c = C["model"] if b["ci"][0] > 0 else ("#dc2626" if b["ci"][1] < 0 else "#9ca3af")
            a2.vlines(pos, b["ci"][0], b["ci"][1], color=c, lw=3)
            a2.scatter(pos, b["model_minus_naive"], color=c, zorder=3)
            labels.append(f"Q{i + 1}")
            pos += 1
        a2.text((start + pos - 1) / 2, 27, name, ha="center", fontsize=9, fontweight="bold")
        labels.append("")
        pos += 1
    a2.axhline(0, color="#111827", lw=1)
    a2.set_xticks(range(len(labels)), labels, fontsize=7.5)
    a2.set_ylim(-35, 32)
    a2.set_ylabel("weather model minus yesterday (EUR/day)")
    a2.set_title("Helps on cold, dull days; hurts on hot ones (exploratory)", fontsize=11)
    note = (
        "Q1 = lowest quarter of days. Blue: model clearly better; red: clearly worse. 12 overlapping groups, no multiplicity correction. "
        + SOURCE
    )
    return _finish(fig, path, note)


def fig_calibration(res, df, wf, path):
    fig, ax = plt.subplots(figsize=(6.8, 6.2))
    hb = ax.hexbin(
        wf["lgbm_weather"],
        wf["actual"],
        gridsize=60,
        bins="log",
        cmap="Blues",
        mincnt=1,
        extent=(-150, 450, -150, 450),
    )
    ax.plot([-150, 450], [-150, 450], color="#111827", lw=1)
    ax.set_xlim(-150, 450)
    ax.set_ylim(-150, 450)
    ax.set_xlabel("model forecast (EUR/MWh)")
    ax.set_ylabel("actual price (EUR/MWh)")
    hi = wf[wf["actual"] > 300]
    ax.set_title(
        f"Spikes are under-forecast: above 300 EUR/MWh the model averages {hi['lgbm_weather'].mean():.0f}",
        fontsize=10,
    )
    fig.colorbar(hb, ax=ax, label="hours (log scale)")
    return _finish(fig, path, "Axes clipped to -150 to 450 EUR/MWh. " + SOURCE)
