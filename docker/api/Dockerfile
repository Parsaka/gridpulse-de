FROM python:3.15-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
USER app
ENV GRIDPULSE_MODEL_DIR=/models
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "gridpulse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
