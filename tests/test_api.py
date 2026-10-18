import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("prometheus_client")

from fastapi.testclient import TestClient  # noqa: E402

from gridpulse.api.app import RateLimiter, create_app  # noqa: E402
from gridpulse.config import Settings  # noqa: E402
from gridpulse.ml.drift import drift_report, psi  # noqa: E402


class FakeService:
    meta = {"name": "fake-model"}

    def __init__(self, db_ok=True):
        self.db_ok = db_ok

    def ping_db(self):
        return self.db_ok

    def freshness_hours(self):
        return 3.5

    def model_age_hours(self):
        return 12.0

    def recent_prices(self, hours):
        ts = pd.date_range("2026-01-01", periods=hours, freq="h", tz="UTC")
        return pd.DataFrame(
            {"ts_utc": ts, "price_eur_mwh": 100.0, "load_mwh": 5e4, "renewable_share": 0.5}
        )

    def forecast_next_day(self):
        return {"forecast": [], "model": {"name": "fake-model"}}


def _client(db_ok=True, keys="k1,k2", limit=60):
    settings = Settings(api_keys=keys, rate_limit_per_min=limit)
    return TestClient(create_app(FakeService(db_ok), settings))


def test_health_needs_no_auth_and_ready_checks_db():
    assert _client().get("/health").json() == {"status": "ok"}
    assert _client().get("/ready").status_code == 200
    assert _client(db_ok=False).get("/ready").status_code == 503


def test_auth_required_and_fail_closed_without_keys():
    c = _client()
    assert c.get("/v1/prices").status_code == 401
    assert c.get("/v1/prices", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/v1/prices?hours=3", headers={"X-API-Key": "k2"}).status_code == 200
    assert _client(keys="").get("/v1/prices", headers={"X-API-Key": "x"}).status_code == 503


def test_rate_limit_returns_429():
    c = _client(limit=2)
    h = {"X-API-Key": "k1"}
    codes = [c.get("/v1/prices?hours=1", headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_prices_with_missing_values_serialise_as_null():
    class NanService(FakeService):
        def recent_prices(self, hours):
            df = super().recent_prices(hours)
            df.loc[df.index[-1], "load_mwh"] = float("nan")  # newest hour has no load yet
            return df

    c = TestClient(create_app(NanService(), Settings(api_keys="k")))
    r = c.get("/v1/prices?hours=3", headers={"X-API-Key": "k"})
    assert r.status_code == 200
    assert r.json()["rows"][-1]["load_mwh"] is None


def test_input_validation():
    c = _client()
    assert c.get("/v1/prices?hours=0", headers={"X-API-Key": "k1"}).status_code == 422


def test_metrics_expose_freshness_and_request_counters():
    c = _client()
    c.get("/health")
    body = c.get("/metrics").text
    assert "gridpulse_data_freshness_hours 3.5" in body
    assert "gridpulse_db_up 1.0" in body
    assert 'gridpulse_api_requests_total{method="GET",path="/health",status="200"} 1.0' in body


def test_rate_limiter_is_per_key():
    r = RateLimiter(1, window_s=1000)
    assert r.allow("a") and not r.allow("a")
    assert r.allow("b")


def test_psi_detects_shift_and_ignores_noise():
    rng = pd.Series(range(2000)).sample(frac=1, random_state=1).reset_index(drop=True) / 2000
    assert psi(rng.iloc[:1000], rng.iloc[1000:]) < 0.1
    assert psi(rng, rng + 0.5) > 0.25
    rep = drift_report(pd.DataFrame({"a": rng}), pd.DataFrame({"a": rng + 0.5}), ["a"])
    assert rep["drifted"] == ["a"]
