from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tracker:tracker@localhost:5432/tracker"
    api_prefix: str = "/api"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRACKER_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
