"""GridPulse HTTP API.

- /health  liveness (no auth)        - /ready   readiness: DB reachable + model loaded
- /v1/prices, /v1/forecast  (X-API-Key, rate limited)
- /metrics  Prometheus (keep internal; not exposed publicly by the deployment)
"""

import hmac
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from gridpulse.config import Settings


class RateLimiter:
    """Sliding-window limiter per API key. In-memory: correct for one instance only; a
    multi-replica deployment needs a shared store (Redis) or gateway-level limiting."""

    def __init__(self, limit: int, window_s: int = 60):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def create_app(service, settings: Settings) -> FastAPI:
    app = FastAPI(title="GridPulse DE API", version="0.1.0")
    keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]
    limiter = RateLimiter(settings.rate_limit_per_min)

    reg = CollectorRegistry()
    requests_total = Counter(
        "gridpulse_api_requests_total", "Requests", ["path", "method", "status"], registry=reg
    )
    latency = Histogram(
        "gridpulse_api_request_seconds",
        "Request latency",
        ["path"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        registry=reg,
    )
    forecasts_total = Counter("gridpulse_forecasts_total", "Forecasts served", registry=reg)
    db_up = Gauge("gridpulse_db_up", "1 if the warehouse is reachable", registry=reg)
    freshness = Gauge(
        "gridpulse_data_freshness_hours", "Age of the newest market row", registry=reg
    )
    model_age = Gauge(
        "gridpulse_model_age_hours", "Hours since the model was trained", registry=reg
    )

    @app.middleware("http")
    async def observe(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = route.path if route else "unmatched"  # bounded label cardinality
            latency.labels(path).observe(time.perf_counter() - start)
            requests_total.labels(path, request.method, str(status)).inc()

    def auth(request: Request, x_api_key: str | None = Header(default=None)) -> str:
        if not keys:
            raise HTTPException(503, "API keys are not configured")
        if not x_api_key or not any(hmac.compare_digest(x_api_key, k) for k in keys):
            raise HTTPException(401, "invalid or missing X-API-Key")
        if not limiter.allow(x_api_key):
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})
        return x_api_key

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        if not service.ping_db():
            raise HTTPException(503, "warehouse unreachable")
        return {"status": "ready", "model": service.meta["name"]}

    @app.get("/v1/prices", dependencies=[Depends(auth)])
    def prices(hours: int = 48):
        if not 1 <= hours <= 24 * 14:
            raise HTTPException(422, "hours must be between 1 and 336")
        df = service.recent_prices(hours)
        df["ts_utc"] = df["ts_utc"].astype(str)
        df = df.astype(object).where(df.notna(), None)  # NaN is not valid JSON
        return {"unit": "EUR/MWh", "rows": df.to_dict("records")}

    @app.get("/v1/forecast", dependencies=[Depends(auth)])
    def forecast():
        try:
            result = service.forecast_next_day()
        except Exception as exc:  # surface as 503 with no internals leaked
            raise HTTPException(503, "forecast currently unavailable") from exc
        forecasts_total.inc()
        return result

    @app.get("/metrics")
    def metrics():
        up = service.ping_db()
        db_up.set(1 if up else 0)
        if up:
            f = service.freshness_hours()
            if f is not None:
                freshness.set(f)
        model_age.set(service.model_age_hours())
        return Response(generate_latest(reg), media_type=CONTENT_TYPE_LATEST)

    return app
