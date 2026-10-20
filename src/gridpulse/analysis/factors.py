"""What drives prices and forecast quality? Factor-by-factor effects, scenarios, business views
(solar and wind capture rates, flexible-load savings) and a hunt for illogical data points."""

import numpy as np
import pandas as pd

FACTORS = {
    # name: (column, label, unit)
    "wind_speed_kmh": ("wind_speed_kmh", "Wind speed (national mean)", "km/h"),
    "solar_kwh_m2": ("solar_kwh_m2", "Solar radiation", "kWh/m2"),
    "temperature_c": ("temperature_c", "Temperature", "C"),
    "cloud_cover_pct": ("cloud_cover_pct", "Cloud cover", "%"),
    "wind_gw": ("wind_gw", "Wind generation", "GW"),
    "solar_gw": ("solar_gw", "Solar generation", "GW"),
    "load_gw": ("load_gw", "Electricity demand", "GW"),
    "residual_gw": ("residual_gw", "Residual load", "GW"),
    "d_temperature": ("d_temperature", "Temperature change vs yesterday", "C"),
    "d_wind": ("d_wind", "Wind speed change vs yesterday", "km/h"),
    "price_yesterday": ("price_yesterday_mean", "Yesterday's average price", "EUR/MWh"),
    "volatility_yesterday": ("price_yesterday_std", "Yesterday's price volatility", "EUR/MWh"),
}


def feature_frame(wf: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward rows joined with weather, generation and 'yesterday' context."""
    d = df.copy()
    d["ts_utc"] = pd.to_datetime(d["ts_utc"], utc=True)
    d = d.set_index("ts_utc").sort_index()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="h", tz="UTC"))
    d["d_temperature"] = d["temperature_c"] - d["temperature_c"].shift(24)
    d["d_wind"] = d["wind_speed_kmh"] - d["wind_speed_kmh"].shift(24)
    daily = d["price_eur_mwh"].groupby(d.index.tz_convert("Europe/Berlin").date)
    mean, std = daily.mean(), daily.std()
    local_day = pd.Series(d.index.tz_convert("Europe/Berlin").date, index=d.index)
    mean.index = pd.to_datetime(mean.index)
    std.index = pd.to_datetime(std.index)
    ld = pd.to_datetime(local_day)
    d["price_yesterday_mean"] = (ld - pd.Timedelta(days=1)).map(mean).to_numpy()
    d["price_yesterday_std"] = (ld - pd.Timedelta(days=1)).map(std).to_numpy()
    w = wf.copy()
    w["ts_utc"] = pd.to_datetime(w["ts_utc"], utc=True)
    cols = [c for c in d.columns if c not in w.columns]
    out = w.merge(d[cols], left_on="ts_utc", right_index=True, how="left")
    loc = out["ts_utc"].dt.tz_convert("Europe/Berlin")
    out["day"] = loc.dt.date
    out["hour_local"] = loc.dt.hour
    out["weekday"] = loc.dt.dayofweek
    out["month"] = loc.dt.strftime("%Y-%m")
    out["season"] = loc.dt.month.map(
        {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring"}
        | {6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
    )
    import holidays

    hol = set(holidays.Germany(years=range(loc.dt.year.min(), loc.dt.year.max() + 1)).keys())
    out["is_holiday"] = out["day"].isin(hol)
    return out


def _gain_ci(sub: pd.DataFrame, n_boot: int, seed: int = 0):
    g = sub.groupby("day").agg(a=("e_naive", "sum"), b=("e_model", "sum"), n=("e_naive", "size"))
    a, b = g["a"].to_numpy(), g["b"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n_boot, len(g)))
    gains = 1 - b[idx].sum(axis=1) / a[idx].sum(axis=1)
    return [float(np.percentile(gains, 2.5)), float(np.percentile(gains, 97.5))]


def _bin_table(ff: pd.DataFrame, key: pd.Series, labels, n_boot: int) -> list[dict]:
    rows = []
    for lab in labels:
        sub = ff[key == lab]
        if len(sub) < 30:
            continue
        mn, mm = sub["e_naive"].mean(), sub["e_model"].mean()
        rows.append(
            {
                "bin": str(lab),
                "hours": int(len(sub)),
                "mae_naive": float(mn),
                "mae_model": float(mm),
                "gain": float(1 - mm / mn),
                "gain_ci": _gain_ci(sub, n_boot),
                "mean_price": float(sub["actual"].mean()),
            }
        )
    return rows


def error_by_factor(ff: pd.DataFrame, n_boot: int = 400) -> dict:
    """Model vs naive error by quintile of every numeric factor and by calendar groupings."""
    ff = ff.copy()
    ff["e_naive"] = (ff["actual"] - ff["naive_24h"]).abs()
    ff["e_model"] = (ff["actual"] - ff["lgbm_weather"]).abs()
    out = {}
    for name, (col, label, unit) in FACTORS.items():
        s = ff[col]
        if s.notna().sum() < 500:
            continue
        q = pd.qcut(s, 5, duplicates="drop")
        labels = list(q.cat.categories)
        key = q.astype(object)
        rows = _bin_table(ff, key, labels, n_boot)
        for r, lab in zip(rows, labels, strict=False):
            r["bin"] = f"{lab.left:.3g} to {lab.right:.3g}"
        out[name] = {"label": label, "unit": unit, "bins": rows}
    ff["daypart"] = pd.cut(
        ff["hour_local"],
        [-1, 5, 9, 15, 20, 23],
        labels=["night", "morning", "midday", "evening", "late"],
    )
    cal = {
        "daypart": (
            "Time of day",
            ff["daypart"].astype(object),
            ["night", "morning", "midday", "evening", "late"],
        ),
        "weekend": (
            "Weekend",
            ff["weekday"].map(lambda x: "weekend" if x >= 5 else "weekday"),
            ["weekday", "weekend"],
        ),
        "holiday": (
            "Public holiday",
            ff["is_holiday"].map({True: "holiday", False: "normal day"}),
            ["normal day", "holiday"],
        ),
        "season": ("Season", ff["season"], ["winter", "spring", "summer", "autumn"]),
    }
    for name, (label, key, labels) in cal.items():
        out[name] = {"label": label, "unit": "", "bins": _bin_table(ff, key, labels, n_boot)}
    return out


def _ols(X: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    return beta, 1 - res.var() / y.var()


def _design(
    d: pd.DataFrame, cols: list[str], with_calendar: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    parts = [np.ones((len(d), 1))]
    if with_calendar:
        parts.append(pd.get_dummies(d["hour_local"], drop_first=True).to_numpy(float))
        parts.append(pd.get_dummies(d["month_only"], drop_first=True).to_numpy(float))
        parts.append(d[["is_weekend"]].to_numpy(float))
    if cols:
        parts.append(d[cols].to_numpy(float))
    return np.hstack(parts), d["price_eur_mwh"].to_numpy(float)


def weather_effects(df: pd.DataFrame, n_boot: int = 300) -> dict:
    """Price effect of one more GW of wind or solar, one more GW of demand and one more degree,
    holding the others, the hour of day and the month fixed. Descriptive regression, not causal."""
    d = df.dropna(subset=["wind_gw", "solar_gw", "load_gw", "temperature_c"]).copy()
    d["ts_utc"] = pd.to_datetime(d["ts_utc"], utc=True)
    loc = d["ts_utc"].dt.tz_convert("Europe/Berlin")
    d["month_only"] = loc.dt.month
    d["is_weekend"] = (d["weekday"] >= 5).astype(float)
    d["day"] = loc.dt.date
    d["period"] = np.where(d["ts_utc"] < pd.Timestamp("2025-10-19", tz="UTC"), "year 1", "year 2")
    cols = ["load_gw", "wind_gw", "solar_gw", "temperature_c"]
    labels = {
        "load_gw": "+1 GW demand",
        "wind_gw": "+1 GW wind",
        "solar_gw": "+1 GW solar",
        "temperature_c": "+1 C temperature",
    }
    out = {"effects": {}, "r2": {}}
    for per, sub in [
        ("all", d),
        ("year 1", d[d.period == "year 1"]),
        ("year 2", d[d.period == "year 2"]),
    ]:
        if len(sub) < 500:  # too little data for a stable regression
            continue
        X, y = _design(sub, cols)
        beta, r2 = _ols(X, y)
        k = len(beta) - len(cols)
        days = sub["day"].to_numpy()
        ud, inv = np.unique(days, return_inverse=True)
        rng = np.random.default_rng(0)
        boots = []
        order = [np.flatnonzero(inv == i) for i in range(len(ud))]
        for _ in range(n_boot):
            pick = rng.integers(0, len(ud), len(ud))
            rows = np.concatenate([order[i] for i in pick])
            b, _ = _ols(X[rows], y[rows])
            boots.append(b[k:])
        boots = np.array(boots)
        out["effects"][per] = {
            c: {
                "label": labels[c],
                "effect": float(beta[k + i]),
                "ci": [
                    float(np.percentile(boots[:, i], 2.5)),
                    float(np.percentile(boots[:, i], 97.5)),
                ],
            }
            for i, c in enumerate(cols)
        }
    base = {"all": d}
    ladder = [
        ("hour of day, month, weekend", []),
        ("+ electricity demand", ["load_gw"]),
        ("+ wind and solar generation", ["load_gw", "wind_gw", "solar_gw"]),
        ("+ temperature", ["load_gw", "wind_gw", "solar_gw", "temperature_c"]),
    ]
    for name, c in ladder:
        X, y = _design(base["all"], c)
        out["r2"][name] = float(_ols(X, y)[1])
    return out


def scenarios(ff: pd.DataFrame, df: pd.DataFrame) -> list[dict]:
    """Named weather situations: what do prices and the forecast do in them?"""
    ff = ff.copy()
    ff["e_naive"] = (ff["actual"] - ff["naive_24h"]).abs()
    ff["e_model"] = (ff["actual"] - ff["lgbm_weather"]).abs()
    ff["month_n"] = ff["ts_utc"].dt.tz_convert("Europe/Berlin").dt.month
    solar_hi = df["solar_gw"].quantile(0.67)
    wind_lo, wind_hi = df["wind_gw"].quantile(0.33), df["wind_gw"].quantile(0.67)
    weekend = ff["weekday"] >= 5
    midday = ff["hour_local"].between(11, 15)
    eve = ff["hour_local"].between(17, 20)
    winter = ff["month_n"].isin([11, 12, 1, 2])
    spec = {
        "Sunny weekend midday": weekend & midday & (ff["solar_gw"] >= solar_hi),
        "Sunny weekday midday": ~weekend & midday & (ff["solar_gw"] >= solar_hi),
        "Windy night": ff["hour_local"].between(0, 5) & (ff["wind_gw"] >= wind_hi),
        "Calm winter evening": winter & eve & (ff["wind_gw"] <= wind_lo),
        "Windy winter evening": winter & eve & (ff["wind_gw"] >= wind_hi),
        "Cold day (below 0 C)": ff["temperature_c"] < 0,
        "Hot day (above 28 C)": ff["temperature_c"] > 28,
        "Public holiday": ff["is_holiday"],
        "Overcast summer midday": ff["month_n"].isin([6, 7, 8])
        & midday
        & (ff["cloud_cover_pct"] >= 90),
        "All hours": pd.Series(True, index=ff.index),
    }
    out = []
    for name, m in spec.items():
        s = ff[m.fillna(False)]
        if len(s) < 20:
            continue
        out.append(
            {
                "scenario": name,
                "hours": int(len(s)),
                "mean_price": float(s["actual"].mean()),
                "p10": float(s["actual"].quantile(0.1)),
                "p90": float(s["actual"].quantile(0.9)),
                "share_negative": float((s["actual"] < 0).mean()),
                "share_above_200": float((s["actual"] > 200).mean()),
                "mae_naive": float(s["e_naive"].mean()),
                "mae_model": float(s["e_model"].mean()),
                "gain": float(1 - s["e_model"].mean() / s["e_naive"].mean()),
            }
        )
    return out


def capture_rates(df: pd.DataFrame) -> dict:
    """Generation-weighted price relative to the plain average price, by month."""
    d = df.dropna(subset=["price_eur_mwh", "wind_gw", "solar_gw"]).copy()
    rows = []
    for m, g in d.groupby("month"):
        base = g["price_eur_mwh"].mean()
        sol = (g["price_eur_mwh"] * g["solar_gw"]).sum() / g["solar_gw"].sum()
        wind = (g["price_eur_mwh"] * g["wind_gw"]).sum() / g["wind_gw"].sum()
        rows.append(
            {
                "month": m,
                "baseload": float(base),
                "solar_price": float(sol),
                "wind_price": float(wind),
                "solar_capture": float(sol / base),
                "wind_capture": float(wind / base),
            }
        )
    tot = d["price_eur_mwh"].mean()
    return {
        "months": rows,
        "solar_capture_all": float(
            (d["price_eur_mwh"] * d["solar_gw"]).sum() / d["solar_gw"].sum() / tot
        ),
        "wind_capture_all": float(
            (d["price_eur_mwh"] * d["wind_gw"]).sum() / d["wind_gw"].sum() / tot
        ),
    }


def consumer_shift(df: pd.DataFrame, hours: int = 4) -> dict:
    """A flexible consumer that knows tomorrow's prices (they are published the day before)
    moves `hours` of load per day into the cheapest hours, against running flat all day."""
    d = df.dropna(subset=["price_eur_mwh"]).copy()
    rows, starts = [], []
    for day, g in d.groupby("date_local"):
        if len(g) < 23:
            continue
        p = g.sort_values("ts_utc")["price_eur_mwh"].to_numpy()
        cheapest = np.sort(p)[:hours].mean()
        win = np.convolve(p, np.ones(hours) / hours, mode="valid")
        rows.append((str(day)[:7], p.mean(), cheapest, win.min()))
        starts.append(int(win.argmin()))
    t = pd.DataFrame(rows, columns=["month", "flat", "cheapest_hours", "cheapest_block"])
    m = t.groupby("month").mean()
    saving = (t["flat"] - t["cheapest_hours"]).mean()
    return {
        "hours_per_day": hours,
        "avg_flat": float(t["flat"].mean()),
        "avg_cheapest_hours": float(t["cheapest_hours"].mean()),
        "avg_cheapest_block": float(t["cheapest_block"].mean()),
        "saving_eur_mwh": float(saving),
        "saving_share": float(saving / t["flat"].mean()),
        "eur_per_mw_year_if_load_is_hours": float(saving * hours * 365),
        "by_month": [
            {"month": k, "flat": float(v.flat), "cheapest_hours": float(v.cheapest_hours)}
            for k, v in m.iterrows()
        ],
        "block_start_hour_share": {
            str(h): float(np.mean(np.array(starts) == h))
            for h in range(24)
            if np.mean(np.array(starts) == h) > 0.005
        },
    }


def battery_by_factor(daily: pd.DataFrame, ff: pd.DataFrame, n_boot: int = 1000) -> dict:
    """How much a battery earns, and whether the model helps, by weather of the day."""
    g = ff.groupby("day").agg(
        wind=("wind_gw", "mean"),
        solar=("solar_gw", "mean"),
        temp=("temperature_c", "mean"),
        month=("month", "first"),
        weekend=("weekday", lambda s: bool((s >= 5).mean() > 0.5)),
    )
    d = daily.set_index("day").join(g)
    d["diff"] = d["lgbm_weather"] - d["naive_24h"]
    out = {}
    rng = np.random.default_rng(0)
    for name, col in [("wind", "wind"), ("solar", "solar"), ("temperature", "temp")]:
        q = pd.qcut(d[col], 4, duplicates="drop")
        rows = []
        for cat in q.cat.categories:
            s = d[q == cat]
            x = s["diff"].to_numpy(float)
            bm = x[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
            rows.append(
                {
                    "bin": f"{cat.left:.3g} to {cat.right:.3g}",
                    "days": int(len(s)),
                    "perfect_eur_day": float(s["perfect"].mean()),
                    "naive_eur_day": float(s["naive_24h"].mean()),
                    "model_minus_naive": float(x.mean()),
                    "ci": [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))],
                }
            )
        out[name] = rows
    out["by_month"] = [
        {
            "month": m,
            "perfect_eur_day": float(s["perfect"].mean()),
            "naive_eur_day": float(s["naive_24h"].mean()),
            "model_minus_naive": float(s["diff"].mean()),
        }
        for m, s in d.groupby("month")
    ]
    return out


def anomalies(ff: pd.DataFrame, df: pd.DataFrame) -> dict:
    """Illogical or odd points: they are listed, not silently dropped."""
    d = df.copy()
    n = len(d)
    neg_high_res = d[(d["price_eur_mwh"] < 0) & (d["residual_gw"] > 25)]
    spike_low_res = d[(d["price_eur_mwh"] > 250) & (d["residual_gw"] < 20)]
    jumps = d["price_eur_mwh"].diff().abs()
    f = ff.copy()
    f["err"] = (f["actual"] - f["lgbm_weather"]).abs()
    worst = f.nlargest(12, "err")
    return {
        "rows": int(n),
        "missing_residual_load_hours": int(d["residual_load_mwh"].isna().sum()),
        "missing_weather_hours": int(d["temperature_c"].isna().sum()),
        "min_price": float(d["price_eur_mwh"].min()),
        "min_price_time": str(d.loc[d["price_eur_mwh"].idxmin(), "ts_utc"]),
        "max_price": float(d["price_eur_mwh"].max()),
        "max_price_time": str(d.loc[d["price_eur_mwh"].idxmax(), "ts_utc"]),
        "hours_near_zero": int((d["price_eur_mwh"].abs() <= 0.1).sum()),
        "share_near_zero": float((d["price_eur_mwh"].abs() <= 0.1).mean()),
        "negative_with_high_residual_load": {
            "hours": int(len(neg_high_res)),
            "example": [
                {
                    "ts": str(r.ts_utc),
                    "price": float(r.price_eur_mwh),
                    "residual_gw": float(r.residual_gw),
                }
                for r in neg_high_res.head(5).itertuples()
            ],
        },
        "spike_with_low_residual_load": {
            "hours": int(len(spike_low_res)),
            "example": [
                {
                    "ts": str(r.ts_utc),
                    "price": float(r.price_eur_mwh),
                    "residual_gw": float(r.residual_gw),
                }
                for r in spike_low_res.head(5).itertuples()
            ],
        },
        "hourly_jumps_above_300": int((jumps > 300).sum()),
        "worst_forecast_hours": [
            {
                "ts": str(r.ts_utc),
                "actual": float(r.actual),
                "forecast": float(r.lgbm_weather),
                "naive": float(r.naive_24h),
                "wind_gw": None if pd.isna(r.wind_gw) else float(r.wind_gw),
                "residual_gw": None if pd.isna(r.residual_gw) else float(r.residual_gw),
            }
            for r in worst.itertuples()
        ],
        "spike_hours_in_test": int((f["actual"] > 300).sum()),
        "spike_mean_actual": float(f.loc[f["actual"] > 300, "actual"].mean()),
        "spike_mean_forecast": float(f.loc[f["actual"] > 300, "lgbm_weather"].mean()),
        "share_error_above_100": float((f["err"] > 100).mean()),
        "share_of_total_error_from_worst_1pct": float(
            f["err"].nlargest(max(1, int(0.01 * len(f)))).sum() / f["err"].sum()
        ),
    }


def fuel_effect(
    df: pd.DataFrame,
    fuel: pd.DataFrame,
    period_a=("2025-08", "2025-10"),
    period_b=("2026-08", "2026-10"),
) -> dict:
    """How much of the month-to-month price level does the gas price explain?

    Step 1: month fixed effects from price ~ hour + residual load + month (so load and renewables
    are held fixed). Step 2: regress those month effects on the monthly European gas price."""
    d = df.dropna(subset=["residual_gw", "price_eur_mwh"]).copy()
    d = d[d["month"].isin(fuel["month"])]
    hours = pd.get_dummies(d["hour_local"], drop_first=True).to_numpy(float)
    months = pd.get_dummies(d["month"], drop_first=False)
    month_names = list(months.columns)
    X = np.hstack([hours, d[["residual_gw"]].to_numpy(float), months.to_numpy(float)])
    beta, *_ = np.linalg.lstsq(X, d["price_eur_mwh"].to_numpy(float), rcond=None)
    fe = pd.Series(beta[-len(month_names) :], index=month_names, name="level")
    t = pd.DataFrame({"level": fe}).join(fuel.set_index("month"))
    t = t.dropna()
    gas = t["gas_europe_usd_mmbtu"].to_numpy()
    y = t["level"].to_numpy()
    slope, icpt = np.polyfit(gas, y, 1)
    pred = icpt + slope * gas
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(2000):
        i = rng.integers(0, len(t), len(t))
        if np.ptp(gas[i]) > 0:
            boots.append(np.polyfit(gas[i], y[i], 1)[0])
    a = t.loc[period_a[0] : period_a[1], "gas_europe_usd_mmbtu"].mean()
    b = t.loc[period_b[0] : period_b[1], "gas_europe_usd_mmbtu"].mean()
    # a gas plant with ~50% efficiency burns ~2 MWh_th per MWh_el; 1 mmbtu = 0.293 MWh_th
    physical = 2 * 3.412
    return {
        "months": int(len(t)),
        "slope_eur_per_usd_mmbtu": float(slope),
        "slope_ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
        "r2": float(r2),
        "physical_slope_usd_per_mmbtu_gas_at_50pct_efficiency": float(physical),
        "gas_avg_period_a": float(a),
        "gas_avg_period_b": float(b),
        "gas_change": float(b - a),
        "implied_premium": float(slope * (b - a)),
        "series": [
            {
                "month": m,
                "level": float(r.level),
                "gas": float(r.gas_europe_usd_mmbtu),
                "coal": float(r.coal_australia_usd_t),
            }
            for m, r in t.iterrows()
        ],
    }
