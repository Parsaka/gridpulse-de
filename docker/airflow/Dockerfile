FROM apache/airflow:2.10.5-python3.12
COPY --chown=airflow:root pyproject.toml README.md /opt/gridpulse/
COPY --chown=airflow:root src /opt/gridpulse/src
RUN pip install --no-cache-dir "/opt/gridpulse[azure]"
