"""What is a better day-ahead forecast worth? A battery scheduling backtest.

A battery is planned one day ahead from a price FORECAST (dynamic programming over the day), then
paid at the ACTUAL day-ahead prices. Comparing strategies that differ only in the forecast used
(naive, model, perfect foresight) isolates the value of forecast quality.

Deliberately simple and stated plainly: day-ahead prices only; no intraday, balancing or grid
fees; the battery starts and ends each local day empty; one hour per step; round-trip efficiency is
applied symmetrically; a small throughput cost stands in for degradation.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Battery:
    power_mw: float = 1.0
    capacity_mwh: float = 2.0
    round_trip_eff: float = 0.88
    throughput_cost: float = 3.0  # EUR per MWh discharged (degradation proxy)

    @property
    def eff_one_way(self) -> float:
        return self.round_trip_eff**0.5


DEFAULT_BATTERY = Battery()


def plan_day(prices: np.ndarray, bat: Battery = DEFAULT_BATTERY) -> np.ndarray:
    """Optimal action per hour for the given prices: +1 charge, -1 discharge, 0 idle (in units of
    one step of power). Exact dynamic programming over state of charge in steps of `power_mw`."""
    n = len(prices)
    levels = int(round(bat.capacity_mwh / bat.power_mw))  # SOC states 0..levels
    e = bat.eff_one_way
    neg_inf = -1e18
    value = np.full((n + 1, levels + 1), neg_inf)
    value[n, 0] = 0.0  # must end empty
    choice = np.zeros((n, levels + 1), dtype=int)
    stored = bat.power_mw  # MWh stored or released per active hour
    for t in range(n - 1, -1, -1):
        p = prices[t]
        for s in range(levels + 1):
            best, act = value[t + 1, s], 0  # idle
            if s < levels:  # charge: buy stored/e from the grid
                v = value[t + 1, s + 1] - p * stored / e
                if v > best:
                    best, act = v, 1
            if s > 0:  # discharge: sell stored*e, pay degradation per MWh stored
                v = value[t + 1, s - 1] + p * stored * e - bat.throughput_cost * stored
                if v > best:
                    best, act = v, -1
            value[t, s], choice[t, s] = best, act
    actions, s = np.zeros(n, dtype=int), 0
    for t in range(n):
        a = choice[t, s]
        actions[t] = a
        s += a
    return actions


def realised_profit(
    actions: np.ndarray, prices: np.ndarray, bat: Battery = DEFAULT_BATTERY
) -> float:
    e, stored = bat.eff_one_way, bat.power_mw
    charge = actions == 1
    discharge = actions == -1
    cost = (prices[charge] * stored / e).sum()
    revenue = (
        prices[discharge] * stored * e
    ).sum() - bat.throughput_cost * stored * discharge.sum()
    return float(revenue - cost)


def backtest(
    wf: pd.DataFrame, strategies: dict[str, str], bat: Battery = DEFAULT_BATTERY
) -> pd.DataFrame:
    """Daily realised profit (EUR per day for the battery) per strategy.

    wf: hourly rows with ts_utc, actual and one column per forecast; strategies maps a strategy
    name to its forecast column ("actual" = perfect foresight). Only complete local days count.
    """
    df = wf.copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df["day"] = df["ts_utc"].dt.tz_convert("Europe/Berlin").dt.date
    out = []
    for day, g in df.sort_values("ts_utc").groupby("day"):
        if len(g) < 23:  # skip partial days (DST days have 23 or 25 hours)
            continue
        actual = g["actual"].to_numpy(float)
        row = {"day": day}
        for name, col in strategies.items():
            plan = plan_day(g[col].to_numpy(float), bat)
            row[name] = realised_profit(plan, actual, bat)
        out.append(row)
    return pd.DataFrame(out)


def summarise(daily: pd.DataFrame, perfect: str = "perfect", n_boot: int = 4000, seed: int = 0):
    """Mean EUR per MW per day, annualised, capture of perfect foresight, bootstrap intervals."""
    strategies = [c for c in daily.columns if c != "day"]
    arr = daily[strategies].to_numpy(float)
    n = len(arr)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = arr[idx].mean(axis=1)  # (n_boot, strategies)
    col = {c: i for i, c in enumerate(strategies)}
    res = {"n_days": n, "strategies": {}}
    for c in strategies:
        i = col[c]
        res["strategies"][c] = {
            "eur_per_day": float(arr[:, i].mean()),
            "eur_per_mw_year": float(arr[:, i].mean() * 365),
            "ci_per_year": [
                float(np.percentile(boot[:, i], 2.5) * 365),
                float(np.percentile(boot[:, i], 97.5) * 365),
            ],
            "capture_of_perfect": float(arr[:, i].mean() / arr[:, col[perfect]].mean()),
        }
    res["differences_per_year"] = {}
    for c in strategies:
        if c in (perfect, "naive_24h") or "naive_24h" not in col:
            continue
        d = boot[:, col[c]] - boot[:, col["naive_24h"]]
        res["differences_per_year"][f"{c}_minus_naive_24h"] = {
            "mean": float((arr[:, col[c]] - arr[:, col["naive_24h"]]).mean() * 365),
            "ci": [float(np.percentile(d, 2.5) * 365), float(np.percentile(d, 97.5) * 365)],
            "p_better": float((d > 0).mean()),
        }
    return res
