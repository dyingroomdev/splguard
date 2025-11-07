from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(default="sqlite+aiosqlite:///./splguard.db", alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    owner_id: int = Field(alias="OWNER_ID")
    admin_channel_id: int | None = Field(default=None, alias="ADMIN_CHANNEL_ID")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    presale_api_url: str | None = Field(default=None, alias="PRESALE_API_URL")
    presale_refresh_seconds: int = Field(default=60, alias="PRESALE_REFRESH_SECONDS")

    zealy_api_key: str | None = Field(default=None, alias="ZEALY_API_KEY")
    zealy_community_id: str | None = Field(default=None, alias="ZEALY_COMMUNITY_ID")
    zealy_base_url: str = Field(default="https://api.zealy.io", alias="ZEALY_BASE_URL")
    zealy_enabled: bool = Field(default=False, alias="ZEALY_ENABLED")
    zealy_webhook_token: str | None = Field(default=None, alias="ZEALY_WEBHOOK_TOKEN")
    zealy_presale_quest_id: str | None = Field(default=None, alias="ZEALY_PRESALE_QUEST_ID")
    zealy_presale_quest_slug: str | None = Field(default=None, alias="ZEALY_PRESALE_QUEST_SLUG")
    zealy_presale_xp_reward: int = Field(default=0, alias="ZEALY_PRESALE_XP_REWARD")

    solana_rpc_url: str | None = Field(default=None, alias="SOLANA_RPC_URL")
    tdl_mint: str | None = Field(default=None, alias="TDL_MINT")
    tdl_supply_display: str | None = Field(default=None, alias="TDL_SUPPLY_DISPLAY")
    presale_end_iso: str | None = Field(default=None, alias="PRESALE_END_ISO")
    listing_date_iso: str | None = Field(default=None, alias="LISTING_DATE_ISO")
    presale_smithii_program_ids: list[str] = Field(
        default_factory=list, alias="PRESALE_SMITHII_PROGRAM_IDS"
    )
    presale_vault_addresses: list[str] = Field(
        default_factory=list, alias="PRESALE_VAULT_ADDRESSES"
    )
    presale_token_mints: list[str] = Field(
        default_factory=list, alias="PRESALE_TOKEN_MINTS"
    )
    presale_min_sol_lamports: int = Field(default=0, alias="PRESALE_MIN_SOL_LAMPORTS")
    presale_min_usdc_amount: int = Field(default=0, alias="PRESALE_MIN_USDC_AMOUNT")
    presale_soft_cap_sol: float = Field(default=0.0, alias="PRESALE_SOFT_CAP_SOL")
    presale_hard_cap_sol: float = Field(default=0.0, alias="PRESALE_HARD_CAP_SOL")
    presale_min_buy_sol: float = Field(default=0.0, alias="PRESALE_MIN_BUY_SOL")
    presale_max_buy_sol: float = Field(default=0.0, alias="PRESALE_MAX_BUY_SOL")

    trusted_domains: list[str] = Field(default_factory=list, alias="TRUSTED_DOMAINS")
    trusted_domains_file: str | None = Field(default="config/trusted_domains.json", alias="TRUSTED_DOMAINS_FILE")
    trusted_links: list[str] = Field(default_factory=list, alias="TRUSTED_LINKS")
    trusted_links_file: str | None = Field(default="config/trusted_links.json", alias="TRUSTED_LINKS_FILE")


    @field_validator("redis_url", mode="before")
    @classmethod
    def _empty_to_none(cls, value: Any) -> str | None:
        if value in (None, "", "none", "null"):
            return None
        return str(value)

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

    @field_validator(
        "presale_smithii_program_ids",
        "presale_vault_addresses",
        "presale_token_mints",
        mode="before",
    )
    @classmethod
    def _split_string_list(cls, value: Any) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            return [part for part in parts if part]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("List values must be provided as comma-separated strings or iterables.")


settings = Settings()
