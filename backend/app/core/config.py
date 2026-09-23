"""Application configuration loaded from environment variables.

All secrets come from the environment; nothing sensitive is hard-coded. In
production (`APP_ENV=production`) insecure defaults are rejected at startup.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEV_JWT_SECRET = "dev-insecure-jwt-secret-change-me-0123456789"  # noqa: S105 - dev-only default, rejected in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    # --- Application -----------------------------------------------------
    app_name: str = "GenOra Marketplace API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    public_base_url: str = "http://localhost:3000"

    # --- Database --------------------------------------------------------
    database_url: str = "postgresql+psycopg://genora:genora_dev_password@localhost:5433/genora"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Auth ------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "genora-marketplace"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    password_reset_ttl_minutes: int = 30
    email_verification_ttl_hours: int = 48
    refresh_cookie_name: str = "genora_refresh"
    refresh_cookie_secure: bool = False
    auth_rate_limit_per_minute: int = 20

    # --- Commerce --------------------------------------------------------
    default_currency: str = "USD"
    tax_rate: Decimal = Decimal("0.08")
    shipping_flat_rate: Decimal = Decimal("5.99")
    free_shipping_threshold: Decimal = Decimal("75.00")
    payment_provider: Literal["sandbox", "stripe"] = "sandbox"
    stripe_api_key: SecretStr | None = None
    negotiated_price_ttl_hours: int = 48

    # --- Storage ---------------------------------------------------------
    storage_provider: Literal["local"] = "local"
    media_root: str = "media"
    media_url_prefix: str = "/api/v1/media/files"
    max_upload_mb: int = 8

    # --- AI (provider independent, OpenAI-compatible) ---------------------
    llm_provider: Literal["none", "openai_compatible"] = "none"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0
    llm_temperature: float = 0.2
    embedding_provider: Literal["hashing", "fastembed", "openai_compatible"] = "hashing"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    vision_provider: Literal["none", "openai_compatible"] = "none"
    vision_model_name: str = "gpt-4o-mini"
    agent_max_history_messages: int = 20
    external_price_providers: Annotated[list[str], NoDecode] = Field(default_factory=list)
    external_price_feed_path: str | None = None

    # --- Forecasting -----------------------------------------------------
    forecast_default_provider: str = "baseline"
    forecast_max_horizon_days: int = 90

    # --- Bootstrapping -----------------------------------------------------
    seed_on_start: bool = False
    run_migrations: bool = False

    @field_validator("cors_origins", "external_price_providers", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == _DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a strong value (>=32 chars) in production")
        if self.llm_provider == "openai_compatible" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai_compatible")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
