from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRIDPULSE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    entsoe_api_key: str = ""
    storage_backend: str = "local"  # "local" or "adls"
    adls_account_url: str = ""  # https://<account>.dfs.core.windows.net
    adls_filesystem: str = "bronze"
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    model_dir: Path = Path("./artifacts")
    api_keys: str = ""  # comma-separated; empty disables the API (fail closed)
    rate_limit_per_min: int = 60
    warehouse_url: str = (
        "postgresql+psycopg://gridpulse:gridpulse_local_only@localhost:5432/gridpulse"
    )

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"


def make_store(settings: "Settings | None" = None):
    """Return the bronze store selected by GRIDPULSE_STORAGE_BACKEND."""
    from gridpulse.storage import AdlsBronzeStore, BronzeStore

    s = settings or get_settings()
    if s.storage_backend == "adls":
        if not s.adls_account_url:
            raise RuntimeError("GRIDPULSE_ADLS_ACCOUNT_URL is required for the adls backend")
        return AdlsBronzeStore(s.adls_account_url, s.adls_filesystem)
    if s.storage_backend != "local":
        raise ValueError(f"unknown storage backend: {s.storage_backend}")
    return BronzeStore(s.bronze_dir)


def get_settings() -> Settings:
    import os

    s = Settings()
    # ENTSOE_API_KEY has no GRIDPULSE_ prefix on purpose (matches entsoe-py docs)
    if not s.entsoe_api_key:
        s.entsoe_api_key = os.environ.get("ENTSOE_API_KEY", "")
    return s
