import numpy as np
import pandas as pd
import pytest

from gridpulse.ml.uncertainty import day_block_bootstrap


def _backtest(days=60, better=True, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=days * 24, freq="h", tz="UTC")
    actual = 100 + rng.normal(0, 20, len(ts))
    base = actual + rng.normal(0, 20, len(ts))
    model = actual + rng.normal(0, 10 if better else 20, len(ts))
    return pd.DataFrame({"ts_utc": ts, "actual": actual, "base": base, "model": model})


def test_clearly_better_model_has_ci_excluding_zero():
    res = day_block_bootstrap(_backtest(better=True), ["model"], "base", n_boot=1000)
    m = res["models"]["model"]
    assert m["mae_diff_ci"][1] < 0  # whole interval below zero: better than baseline
    assert m["p_better_than_baseline"] > 0.99
    assert m["mae_ci"][0] < m["mae"] < m["mae_ci"][1]
    assert res["n_days"] == 60
    b = res["baseline"]
    assert b["name"] == "base" and b["mae_ci"][0] < b["mae"] < b["mae_ci"][1]


def test_equal_models_have_ci_straddling_zero():
    res = day_block_bootstrap(_backtest(better=False, seed=3), ["model"], "base", n_boot=1000)
    lo, hi = res["models"]["model"]["mae_diff_ci"]
    assert lo < 0 < hi


def test_resamples_days_not_hours():
    """Interval must be wider when errors are shared within a day (block structure)."""
    df = _backtest(days=40)
    day_shift = np.repeat(np.random.default_rng(5).normal(0, 15, 40), 24)
    df["model"] = df["actual"] + day_shift  # the whole day is off by a constant
    wide = day_block_bootstrap(df, ["model"], "base", n_boot=1000)["models"]["model"]["mae_ci"]
    shuffled = df.copy()
    shuffled["model"] = df["actual"] + np.random.default_rng(6).permutation(day_shift.repeat(1))
    narrow = day_block_bootstrap(shuffled, ["model"], "base", n_boot=1000)["models"]["model"][
        "mae_ci"
    ]
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])


def test_empty_input_raises():
    df = _backtest(days=2)
    df["model"] = np.nan
    with pytest.raises(ValueError):
        day_block_bootstrap(df, ["model"], "base")
