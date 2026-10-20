"""What is a better day-ahead forecast worth? A battery scheduling backtest.

A battery is planned one day ahead from a price FORECAST (an exact linear programme over the day),
then paid at the ACTUAL day-ahead prices. Comparing strategies that differ only in the forecast
used (naive, model, perfect foresight) isolates the value of forecast quality.

Deliberately simple and stated plainly: day-ahead prices only; no intraday, balancing or grid fees;
the battery starts and ends each local day empty; one hour per step; grid-side power is limited to
`power_mw` in both directions; round-trip efficiency is split evenly between charging and
discharging; a throughput cost per MWh sold stands in for degradation. Needs scipy (viz extra).
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Battery:
    power_mw: float = 1.0
    capacity_mwh: float = 2.0
    round_trip_eff: float = 0.88
    throughput_cost: float = 3.0  # EUR per MWh sold (degradation proxy)

    @property
    def eff_one_way(self) -> float:
        return self.round_trip_eff**0.5


DEFAULT_BATTERY = Battery()


@lru_cache(maxsize=8)
def _constraints(n: int, capacity: float, e: float):
    """SOC bounds 0 <= soc_t <= capacity for every hour, and an empty battery at the end."""
    tri = np.tril(np.ones((n, n)))
    soc = np.hstack([tri * e, -tri / e])  # soc_t = sum_{k<=t} (c_k * e - d_k / e)
    a_ub = np.vstack([soc, -soc])
    b_ub = np.r_[np.full(n, capacity), np.zeros(n)]
    a_eq = soc[-1:].copy()
    return a_ub, b_ub, a_eq


def plan_day(prices: np.ndarray, bat: Battery = DEFAULT_BATTERY) -> tuple[np.ndarray, np.ndarray]:
    """Profit-maximising (charge, discharge) in grid-side MW per hour for the given prices."""
    from scipy.optimize import linprog

    prices = np.asarray(prices, float)
    n = len(prices)
    a_ub, b_ub, a_eq = _constraints(n, bat.capacity_mwh, bat.eff_one_way)
    cost = np.r_[prices, -prices + bat.throughput_cost]  # minimise: buy - sell + degradation
    res = linprog(
        cost,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=[0.0],
        bounds=[(0, bat.power_mw)] * (2 * n),
        method="highs",
    )
    if not res.success:  # cannot happen for finite prices; fail loudly rather than return zeros
        raise RuntimeError(f"battery LP failed: {res.message}")
    return res.x[:n], res.x[n:]


def realised_profit(
    plan: tuple[np.ndarray, np.ndarray], prices: np.ndarray, bat: Battery = DEFAULT_BATTERY
) -> float:
    """EUR earned by following `plan` when the real prices are `prices`."""
    charge, discharge = plan
    prices = np.asarray(prices, float)
    return float(prices @ (discharge - charge) - bat.throughput_cost * discharge.sum())


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
            row[name] = realised_profit(plan_day(g[col].to_numpy(float), bat), actual, bat)
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
