# Runbook and incident drill

## Local stack
```bash
docker compose up -d postgres
gridpulse train --test-days 90        # writes artifacts/model.txt used by the API
docker compose --profile monitoring up -d --build
```
API http://localhost:8000 (header `X-API-Key: dev-local-key`), Prometheus :9090, Grafana :3000
(dashboard "GridPulse API health"; local credentials only).

## Alerts (monitoring/rules.yml)
| Alert | Condition | First action |
|---|---|---|
| ApiDown | Prometheus cannot scrape the API for 1 min | `docker compose logs api`, restart |
| WarehouseUnreachable | `gridpulse_db_up == 0` for 1 min | check Postgres; `/ready` returns 503 meanwhile |
| DataStale | newest market row older than 36 h for 10 min | check Airflow `gridpulse_daily`, then `dbt build` |
| HighErrorRate | more than 5% 5xx over 5 min | logs; usual cause is DB or weather API |
| HighLatencyP95 | p95 above 2 s for 10 min | check DB load and weather API latency |
| ModelStale | model older than 30 days | `gridpulse train` and redeploy artifact |

## Drill performed on 2026-10-18 (local Docker, Windows laptop)
Failure injected: `docker compose stop postgres`. Measured with 10-20 s polling, so figures are
approximate:

| Time | Observation |
|---|---|
| T+0 s | Postgres stopped |
| T+20 s | `/ready` returns 503 |
| T+39 s | `WarehouseUnreachable` pending |
| T+96 s | `WarehouseUnreachable` firing |
| recovery T+0 | `docker compose start postgres` |
| +11 s | `/ready` returns 200 again (no API restart needed, connection pool recovered) |
| +41 s | alert cleared |

Detection to firing alert was about 1.5 minutes, set by the 15 s scrape interval and the rule's
`for: 1m`. Not covered yet: notification delivery (Alertmanager or Azure Monitor action group),
which comes with the Azure deployment.

## Load test (scripts/load_test.py, API in Docker, same laptop, 1 container, 1 worker)
| Endpoint | Requests / concurrency | Result |
|---|---|---|
| `/v1/prices?hours=48` | 1000 / 20 | 1000 x 200, 61 req/s, p50 252 ms, p95 829 ms, p99 1209 ms |
| `/v1/forecast` | 200 / 10 | 200 x 200, p50 75 ms (cached), p95 1.4 s (first computation: live weather call) |

These are laptop numbers for a pandas-backed endpoint and say nothing about production capacity.

## Bugs found by this exercise
- `/v1/prices` returned HTTP 500 whenever the newest hour had no load value yet (NaN is not valid
  JSON). Fixed (NaN becomes null) with a regression test.
- Concurrent first requests to `/v1/forecast` each triggered a weather fetch; now single-flight.
