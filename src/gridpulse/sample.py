"""Deterministic synthetic bronze data for CI and offline demos (not real market data)."""

import numpy as np
import pandas as pd

from gridpulse.ingestion import brightsky, smard
from gridpulse.storage import BronzeStore

# rough average MW per source, used only to shape synthetic series
_BASE = {
    "generation_lignite": 9000,
    "generation_nuclear": 0,
    "generation_wind_offshore": 3000,
    "generation_hydro": 1500,
    "generation_other_conventional": 1500,
    "generation_other_renewable": 400,
    "generation_biomass": 4000,
    "generation_wind_onshore": 12000,
    "generation_solar": 8000,
    "generation_hard_coal": 3000,
    "generation_pumped_storage": 800,
    "generation_gas": 6000,
}


def write_sample_bronze(store: BronzeStore, start: str, days: int, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=days * 24, freq="h", tz="UTC")
    hour = ts.hour.to_numpy()
    solar_shape = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)

    for name, (_, region) in smard.DATASETS.items():
        if name.startswith("generation_"):
            base = _BASE[name]
            shape = solar_shape if name.endswith("solar") else 1.0
            values = base * shape * rng.uniform(0.7, 1.3, len(ts))
        elif name == "load_total":
            values = (
                55000 + 8000 * np.sin((hour - 8) / 24 * 2 * np.pi) + rng.normal(0, 1000, len(ts))
            )
        elif name == "load_residual":
            values = 30000 + rng.normal(0, 3000, len(ts))
        else:  # price_day_ahead
            values = 90 + 40 * np.sin((hour - 6) / 24 * 2 * np.pi) + rng.normal(0, 15, len(ts))
        df = pd.DataFrame(
            {"value": values.round(2), "timestamp": ts, "dataset": name, "region": region}
        )
        store.write(df, "smard", name)

    for i, loc in enumerate(brightsky.LOCATIONS):
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "temperature": 10
                + 8 * np.sin((hour - 9) / 24 * 2 * np.pi)
                + rng.normal(0, 1, len(ts)),
                "wind_speed": rng.gamma(2.0, 6.0, len(ts)),
                "wind_direction": rng.uniform(0, 360, len(ts)),
                "cloud_cover": rng.uniform(0, 100, len(ts)),
                "sunshine": rng.uniform(0, 60, len(ts)) * solar_shape,
                "solar": 0.5 * solar_shape,
                "precipitation": rng.exponential(0.1, len(ts)),
                "pressure_msl": 1013 + rng.normal(0, 5, len(ts)) + i * 0,
                "location": loc,
            }
        )
        store.write(df, "dwd", f"weather_{loc}")
