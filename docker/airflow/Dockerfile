FROM apache/airflow:2.10.5-python3.12
USER root
# LightGBM needs the OpenMP runtime, which the base image lacks
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
USER airflow
COPY --chown=airflow:root pyproject.toml README.md /opt/gridpulse/
COPY --chown=airflow:root src /opt/gridpulse/src
# Airflow's own environment only needs the ingestion code (its pinned SQLAlchemy 1.4 rules out the
# warehouse extra).
RUN pip install --no-cache-dir "/opt/gridpulse[azure]"
# Heavy tasks (warehouse load, dbt, training, forecasting) run from a separate virtualenv so their
# dependencies (SQLAlchemy 2, LightGBM, dbt) cannot clash with Airflow's constraints.
RUN python -m venv /home/airflow/gp-venv \
    && /home/airflow/gp-venv/bin/pip install --no-cache-dir \
       "/opt/gridpulse[azure,warehouse,ml,api,dbt]"
