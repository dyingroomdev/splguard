from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    owner_id: int = Field(alias="OWNER_ID")
    admin_channel_id: int | None = Field(default=None, alias="ADMIN_CHANNEL_ID")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    presale_api_url: str | None = Field(default=None, alias="PRESALE_API_URL")
    presale_refresh_seconds: int = Field(default=60, alias="PRESALE_REFRESH_SECONDS")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: Any) -> list[int]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            return [int(part) for part in parts if part]
        if isinstance(value, int):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [int(item) for item in value]
        raise ValueError("ADMIN_IDS must be a comma-separated string or list of integers.")


settings = Settings()
