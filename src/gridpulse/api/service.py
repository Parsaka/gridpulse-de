"""Forecast service: warehouse history + DWD MOSMIX weather forecast -> next-day hourly prices."""

import threading
import time
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd
from sqlalchemy import Engine, text

from gridpulse.config import get_settings
from gridpulse.ingestion import brightsky, openmeteo
from gridpulse.ml.artifacts import load_model
from gridpulse.ml.features import TARGET, build_features

HISTORY_DAYS = 14
WEATHER_COLS = [
    "temperature_c",
    "wind_speed_kmh",
    "cloud_cover_pct",
    "solar_kwh_m2",
    "precipitation_mm",
]
_RENAME = {
    "temperature": "temperature_c",
    "wind_speed": "wind_speed_kmh",
    "cloud_cover": "cloud_cover_pct",
    "solar": "solar_kwh_m2",
    "precipitation": "precipitation_mm",
}

HISTORY_SQL = text(
    "select ts_utc, price_eur_mwh, load_mwh, renewable_share from gold.fct_market_hourly "
    "where ts_utc >= (select max(ts_utc) - make_interval(days => :d) from gold.fct_market_hourly) "
    "order by ts_utc"
)


class ForecastService:
    def __init__(
        self,
        engine: Engine,
        model_dir,
        cache_seconds: int = 1800,
        weather_source: str | None = None,
    ):
        self.engine = engine
        self.weather_source = weather_source or get_settings().weather_source
        self.model, self.meta = load_model(model_dir)
        self.cache_seconds = cache_seconds
        self._cache: tuple[float, dict] | None = None
        self._lock = threading.Lock()  # single-flight: one computation per cache window

    # ---- warehouse reads -------------------------------------------------
    def ping_db(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("select 1"))
            return True
        except Exception:
            return False

    def freshness_hours(self) -> float | None:
        with self.engine.connect() as c:
            ts = c.execute(text("select max(ts_utc) from gold.fct_market_hourly")).scalar()
        return None if ts is None else (datetime.now(UTC) - ts).total_seconds() / 3600

    def recent_prices(self, hours: int) -> pd.DataFrame:
        q = text(
            "select ts_utc, price_eur_mwh, load_mwh, renewable_share from gold.fct_market_hourly "
            "order by ts_utc desc limit :n"
        )
        return pd.read_sql(q, self.engine, params={"n": hours}).sort_values("ts_utc")

    def _history(self) -> pd.DataFrame:
        return pd.read_sql(
            HISTORY_SQL, self.engine, params={"d": HISTORY_DAYS}, parse_dates=["ts_utc"]
        )

    # ---- weather forecast ------------------------------------------------
    def _weather_forecast(self, day) -> pd.DataFrame:
        if self.weather_source == "openmeteo":
            with httpx.Client(timeout=60) as client:
                frames = [
                    openmeteo.fetch_live_forecast(client, loc, day, day)
                    for loc in brightsky.LOCATIONS
                ]
            return openmeteo.national_mean(frames)
        with httpx.Client() as client:
            frames = [brightsky.fetch_weather(client, loc, day, day) for loc in brightsky.LOCATIONS]
        w = pd.concat(frames).rename(columns=_RENAME)
        mean = w.groupby("timestamp")[WEATHER_COLS].mean().reset_index()
        return mean.rename(columns={"timestamp": "ts_utc"})

    # ---- forecast ----------------------------------------------------------
    def forecast_next_day(self) -> dict:
        if (cached := self._fresh_cache()) is not None:
            return cached
        with self._lock:
            if (cached := self._fresh_cache()) is not None:  # computed while we waited
                return cached
            return self._compute_forecast()

    def _fresh_cache(self) -> dict | None:
        if self._cache and time.monotonic() - self._cache[0] < self.cache_seconds:
            return self._cache[1]
        return None

    def _compute_forecast(self) -> dict:
        hist = self._history()
        if hist.empty:
            raise RuntimeError("no market history in the warehouse")
        # target = the UTC day after the last day with a full set of 24 prices
        counts = hist.groupby(hist["ts_utc"].dt.date)[TARGET].count()
        last_full = max(d for d, n in counts.items() if n >= 24)
        target_day = last_full + timedelta(days=1)
        hours = pd.date_range(pd.Timestamp(target_day, tz="UTC"), periods=24, freq="h")
        future = pd.DataFrame({"ts_utc": hours}).merge(
            self._weather_forecast(target_day), on="ts_utc", how="left"
        )
        hist = hist[hist["ts_utc"] < hours[0]].copy()
        for col in WEATHER_COLS:
            hist[col] = float("nan")  # weather history is not needed for the lag features
        frame = build_features(pd.concat([hist, future], ignore_index=True))
        rows = frame[frame["ts_utc"].isin(hours)]
        pred = (
            self.model.predict(rows[self.meta["features"]]) + rows[self.meta["anchor"]].to_numpy()
        )
        trained_on = self.meta.get("weather_input_at_training", "observed")
        result = {
            "target_day_utc": target_day.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "model": {
                "name": self.meta["name"],
                "trained_at": self.meta["trained_at"],
                "test_mae_eur_mwh": self.meta["test_metrics"].get("mae"),
            },
            "weather_input": (
                "Open-Meteo forecast (best-match model), nine-station mean"
                if self.weather_source == "openmeteo"
                else "DWD MOSMIX forecast via Bright Sky"
            )
            + f"; model trained on {trained_on} weather",
            "forecast": [
                {"ts_utc": t.isoformat(), "price_eur_mwh": round(float(p), 2)}
                for t, p in zip(hours, pred, strict=True)
            ],
        }
        self._cache = (time.monotonic(), result)
        return result

    def model_age_hours(self) -> float:
        trained = datetime.fromisoformat(self.meta["trained_at"])
        return (datetime.now(UTC) - trained).total_seconds() / 3600
