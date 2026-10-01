import ipaddress
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from argon2 import PasswordHasher, extract_parameters
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    auth_window_seconds: int = Field(default=900, ge=1)
    login_account_limit: int = Field(default=10, ge=1)
    login_address_limit: int = Field(default=100, ge=1)
    register_account_limit: int = Field(default=3, ge=1)
    register_address_limit: int = Field(default=20, ge=1)
    verify_account_limit: int = Field(default=10, ge=1)
    verify_address_limit: int = Field(default=100, ge=1)
    auth_dummy_hash: str = (
        "$argon2id$v=19$m=65536,t=3,p=4$rqlB/2Z/6asIaKYGaTkeiw$"
        "AfEDjQCOtb4Pti//zQOiGgMPGA1jFcy+olsAudC+qw8"
    )
    breached_password_file: str | None = None
    trusted_proxy_networks: list[str] = []
    public_app_url: str = "http://localhost:5173"
    verification_lifetime_seconds: int = Field(default=3600, ge=60)
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = "noreply@example.com"
    smtp_security: Literal["starttls", "tls", "plain"] = "starttls"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    mail_worker_interval_seconds: int = Field(default=5, ge=1)
    api_prefix: str = "/api"
    auth_secret_key: str = "development-secret-key-change-in-production-0123456789"
    cors_origins: list[str] = ["http://localhost:5173"]
    access_token_expire_minutes: int = 60
    deadline_worker_interval_seconds: int = 60

    @field_validator("auth_dummy_hash")
    @classmethod
    def valid_dummy_hash(cls, value: str) -> str:
        parameters = extract_parameters(value)
        current = PasswordHasher()
        if (
            parameters.type != current.type
            or parameters.version != 19
            or parameters.memory_cost != current.memory_cost
            or parameters.time_cost != current.time_cost
            or parameters.parallelism != current.parallelism
            or parameters.hash_len != current.hash_len
            or parameters.salt_len != current.salt_len
        ):
            raise ValueError("Dummy hash must use the current Argon2 parameters")
        return value

    @field_validator("trusted_proxy_networks")
    @classmethod
    def valid_proxy_networks(cls, values: list[str]) -> list[str]:
        for value in values:
            network = ipaddress.ip_network(value)
            if network.prefixlen == 0:
                raise ValueError("Do not trust all client addresses as proxies")
        return values

    @field_validator("public_app_url")
    @classmethod
    def valid_public_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Public app URL must be an HTTP(S) URL without credentials/query/fragment"
            )
        return value.rstrip("/")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRACKER_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
