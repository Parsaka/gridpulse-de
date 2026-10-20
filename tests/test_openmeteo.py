from datetime import date

import httpx
import pandas as pd

from gridpulse.ingestion import openmeteo


def _payload(names, hours=3):
    times = [f"2026-01-01T0{h}:00" for h in range(hours)]
    return {"hourly": {"time": times, **{n: [float(h) for h in range(hours)] for n in names}}}


def _client(payload, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_previous_day_forecast_uses_the_day_before_variables():
    seen = []
    client = _client(_payload(openmeteo.VARIABLES), seen)
    df = openmeteo.fetch_previous_day_forecast(client, "nrw", date(2026, 1, 1), date(2026, 1, 1))
    assert all(name.endswith("_previous_day1") for name in seen[0]["hourly"].split(","))
    assert {"temperature_c", "wind_speed_kmh", "shortwave_wm2"} <= set(df.columns)
    assert df["timestamp"].dt.tz is not None and (df["location"] == "nrw").all()


def test_live_forecast_asks_the_current_forecast_endpoint():
    seen = []
    client = _client(_payload(openmeteo.LIVE_VARIABLES), seen)
    df = openmeteo.fetch_live_forecast(client, "hesse", date(2026, 1, 1), date(2026, 1, 1))
    assert "_previous_day" not in seen[0]["hourly"]
    assert len(df) == 3


def test_national_mean_averages_stations_and_converts_radiation_to_kwh():
    a = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00"], utc=True),
            "temperature_c": [10.0],
            "wind_speed_kmh": [10.0],
            "cloud_cover_pct": [50.0],
            "shortwave_wm2": [400.0],
            "precipitation_mm": [0.0],
        }
    )
    b = a.assign(temperature_c=20.0, shortwave_wm2=600.0)
    out = openmeteo.national_mean([a, b])
    assert out["temperature_c"].iloc[0] == 15.0
    assert out["solar_kwh_m2"].iloc[0] == 0.5  # mean 500 W/m2 over the hour
    assert "ts_utc" in out.columns
