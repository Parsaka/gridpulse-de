"""ASGI entrypoint: `uvicorn gridpulse.api.main:app`."""

from sqlalchemy import create_engine

from gridpulse.api.app import create_app
from gridpulse.api.service import ForecastService
from gridpulse.config import get_settings

settings = get_settings()
app = create_app(
    ForecastService(create_engine(settings.warehouse_url, pool_pre_ping=True), settings.model_dir),
    settings,
)
