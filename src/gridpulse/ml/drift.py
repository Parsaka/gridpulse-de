"""Population Stability Index (PSI) for feature drift.

Rule of thumb: < 0.1 stable, 0.1-0.25 moderate, > 0.25 significant drift.
"""

import numpy as np
import pandas as pd


def psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    ref, cur = reference.dropna().to_numpy(), current.dropna().to_numpy()
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    eps = 1e-4
    p = np.histogram(ref, edges)[0] / len(ref) + eps
    q = np.histogram(cur, edges)[0] / len(cur) + eps
    return float(np.sum((q - p) * np.log(q / p)))


def drift_report(reference: pd.DataFrame, current: pd.DataFrame, features: list[str]) -> dict:
    scores = {f: psi(reference[f], current[f]) for f in features if f in reference}
    valid = [v for v in scores.values() if v == v]
    return {
        "psi": scores,
        "max_psi": max(valid, default=float("nan")),
        "drifted": [f for f, v in scores.items() if v == v and v > 0.25],
    }
