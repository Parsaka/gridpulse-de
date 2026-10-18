# GridPulse DE – guide for Claude Code

Portfolio flagship: data + forecasting platform for the German electricity market.
Goal: close CV gaps (Airflow, dbt, Terraform, CI/CD, monitoring, ML in production, BI) with
real, runnable, measurable work. Cloud: **Microsoft Azure**. BI: **Power BI** (PBIP/TMDL in Git).

## Rules
- Python 3.11+, `src/` layout, package `gridpulse`. Lint/format with ruff, tests with pytest.
- Ingestion writes are **idempotent** (partition overwrite). Never append blindly.
- No secrets in Git. Local: `.env`; cloud: Azure Key Vault; CI→Azure via OIDC.
- Every external dataset needs source + licence in `docs/data-sources.md`.
- Tests must not hit the network (mark such tests `@pytest.mark.live`).
- Work in small PRs per phase (`docs/roadmap.md`). Keep README metrics honest: only real, measured numbers.
- Ask before creating paid Azure resources; keep a budget alert.

## Commands
- `pip install -e ".[dev]"` · `pytest` · `ruff check . && ruff format .`
- `gridpulse smard --start 2025-01-01 --end 2025-01-08` · `gridpulse weather ...` · `gridpulse daily`
