from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRIDPULSE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    entsoe_api_key: str = ""

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"


def get_settings() -> Settings:
    import os

    s = Settings()
    # ENTSOE_API_KEY has no GRIDPULSE_ prefix on purpose (matches entsoe-py docs)
    if not s.entsoe_api_key:
        s.entsoe_api_key = os.environ.get("ENTSOE_API_KEY", "")
    return s
