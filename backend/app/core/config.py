from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    api_prefix: str = "/api"
    auth_secret_key: str = "development-secret-key-change-in-production-0123456789"
    cors_origins: list[str] = ["http://localhost:5173"]
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRACKER_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
