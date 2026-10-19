"""Feature drift check for the deployed model: recent window vs the training reference."""

import pandas as pd
from sqlalchemy import Engine

from gridpulse.ml import data
from gridpulse.ml.drift import drift_report
from gridpulse.ml.features import CALENDAR, WEATHER, build_features


def check_drift(engine: Engine, features: list[str], recent_days: int = 14, margin_days: int = 7):
    """Recent window vs the SAME season one year earlier (so seasonality is not flagged as drift).

    Calendar features (deterministic) and weather (exogenous, noisy over 2 weeks) are skipped.
    Needs at least ~13 months of history.
    """
    feat = build_features(data.load_training_frame(engine))
    last = feat["ts_utc"].max()
    cut = last - pd.Timedelta(days=recent_days)
    current = feat[feat["ts_utc"] > cut]
    year_ago = pd.Timedelta(days=364)  # whole weeks, so weekday mix matches
    reference = feat[
        (feat["ts_utc"] > cut - year_ago - pd.Timedelta(days=margin_days))
        & (feat["ts_utc"] <= last - year_ago + pd.Timedelta(days=margin_days))
    ]
    monitored = [f for f in features if f not in CALENDAR and f not in WEATHER]
    report = drift_report(reference, current, monitored)
    report["window"] = {
        "recent_days": recent_days,
        "reference": "same season one year earlier",
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "last_ts": str(last),
    }
    return report
