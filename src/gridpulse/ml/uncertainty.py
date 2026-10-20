"""Confidence intervals for backtest metrics via a day-block bootstrap.

Hourly errors within a day are strongly correlated, so resampling single hours would give
intervals that are far too narrow. Whole days are resampled instead. All models are scored on the
same resampled days, which makes the *difference* to the baseline meaningful.
"""

import numpy as np
import pandas as pd


def day_block_bootstrap(
    backtest: pd.DataFrame,
    preds: list[str],
    baseline: str,
    n_boot: int = 4000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict:
    """Return point estimates and (1 - alpha) percentile intervals.

    backtest: columns `ts_utc`, `actual` and one column per entry of `preds` (plus `baseline`).
    """
    cols = list(dict.fromkeys([*preds, baseline]))
    df = backtest.dropna(subset=["actual", *cols]).copy()
    if df.empty:
        raise ValueError("no rows with all predictions available")
    day = pd.to_datetime(df["ts_utc"], utc=True).dt.floor("D")
    err = {c: (df["actual"] - df[c]).abs().to_numpy() for c in cols}

    # per-day sums so that each bootstrap draw is a cheap weighted sum
    days = day.to_numpy()
    uniq, inv = np.unique(days, return_inverse=True)
    n_days = len(uniq)
    counts = np.bincount(inv, minlength=n_days).astype(float)
    sums = {c: np.bincount(inv, weights=err[c], minlength=n_days) for c in cols}

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_days, size=(n_boot, n_days))
    tot = counts[draws].sum(axis=1)
    mae_draw = {c: sums[c][draws].sum(axis=1) / tot for c in cols}

    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)

    def ci(x):
        return [float(np.percentile(x, lo)), float(np.percentile(x, hi))]

    out = {"n_hours": int(len(df)), "n_days": int(n_days), "n_boot": n_boot, "models": {}}
    base_point = float(sum(sums[baseline]) / counts.sum())
    out["baseline"] = {"name": baseline, "mae": base_point, "mae_ci": ci(mae_draw[baseline])}
    for c in preds:
        point = float(sum(sums[c]) / counts.sum())
        skill_draw = 1 - mae_draw[c] / mae_draw[baseline]
        diff_draw = mae_draw[c] - mae_draw[baseline]
        out["models"][c] = {
            "mae": point,
            "mae_ci": ci(mae_draw[c]),
            "mae_diff_vs_baseline": point - base_point,
            "mae_diff_ci": ci(diff_draw),
            "skill_vs_baseline": 1 - point / base_point,
            "skill_ci": ci(skill_draw),
            # fraction of resamples in which the model beats the baseline on MAE
            "p_better_than_baseline": float((diff_draw < 0).mean()),
        }
    return out
