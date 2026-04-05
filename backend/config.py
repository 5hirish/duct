"""Application configuration from environment and optional `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent


class Configs(BaseSettings):
    """Backend settings; all keys optional with defaults so imports work without a full `.env`."""

    # CORS / OAuth redirect target
    frontend_origin: str = Field(default="http://localhost:3000")

    # Google OAuth (same app can back Google Ads API)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/auth/connectors/google_ads/oauth/callback",
    )

    # Google Ads API
    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_customer_id: str = ""
    google_ads_login_customer_id: str = ""

    # Google Sign-In (user identity, separate from connector OAuth)
    google_signin_redirect_uri: str = Field(
        default="http://localhost:8000/auth/signin/google/callback",
    )
    jwt_secret: str = ""

    # Cloudflare Turnstile (bot protection)
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    # Protects /api/* routes (header X-API-Key). Same value the Next app sends as X-API-Key.
    duct_api_key: str = ""

    # LLM synthesis (see agents.reporter.models for provider / model strings)
    generate_provider: str = ""
    generate_model: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _strip_string_fields(self) -> Self:
        updates: dict[str, Any] = {}
        for name in type(self).model_fields:
            val = getattr(self, name)
            if isinstance(val, str):
                stripped = val.strip()
                if stripped != val:
                    updates[name] = stripped
        if updates:
            return self.model_copy(update=updates)
        return self


@lru_cache
def get_configs() -> Configs:
    return Configs()
