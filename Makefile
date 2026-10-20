.PHONY: install lint test check up-db load dbt train api-up down

install:        ## dev install with every extra
	pip install -e ".[dev,warehouse,dbt,ml,api,azure]"

lint:
	ruff check . && ruff format --check .

test:
	pytest -m "not live"

check: lint test   ## what CI runs for Python

up-db:
	docker compose up -d postgres

load:           ## bronze Parquet -> Postgres, then dbt
	gridpulse load-warehouse
	cd dbt && dbt deps && dbt build

train:
	gridpulse train --test-days 90

api-up:         ## API + Prometheus + Grafana
	docker compose --profile monitoring up -d --build

down:
	docker compose --profile airflow --profile monitoring --profile azure-emulator down
