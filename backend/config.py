"""Application configuration from environment and optional `.env` / `.env.local` files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent


def _settings_env_files() -> tuple[Path, ...] | None:
    """Under pytest, skip dotenv so tests are not affected by developer `.env` / `.env.local`."""
    if os.environ.get("PYTEST_VERSION"):
        return None
    return (
        _BACKEND_DIR / ".env",
        _BACKEND_DIR / ".env.local",
    )


class Configs(BaseSettings):
    """Backend settings; all keys optional with defaults so imports work without a full `.env`.

    Loads `backend/.env` then `backend/.env.local` (later overrides; missing files are ignored).
    Dotenv files are skipped when `PYTEST_VERSION` is set (pytest run).
    """

    # CORS / OAuth redirect target
    frontend_origin: str = Field(default="http://localhost:3000")

    # Public origin of this API (scheme + host [+ port], no path). Used to build OAuth redirect
    # URIs when GOOGLE_OAUTH_REDIRECT_URI / GOOGLE_SIGNIN_REDIRECT_URI are unset.
    api_public_url: str = Field(default="http://localhost:8000")

    # Primary relational store for auth-first persistence.
    database_url: str = ""
    # Safety default for deployed environments: rely on Alembic migrations, not SQLModel create_all.
    # Set INIT_DB_ON_STARTUP=true only for local/dev bootstrap workflows.
    init_db_on_startup: bool = False

    # Google OAuth (same app can back Google Ads API). If unset/empty, derived as
    # {api_public_url}/auth/google/callback (alias for the Google Ads connector callback).
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = Field(default="")

    # Google Ads API
    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_customer_id: str = ""
    google_ads_login_customer_id: str = ""
    ga4_property_id: str = ""
    gsc_site_url: str = ""

    # Google Sign-In (user identity, separate from connector OAuth). If unset/empty, derived as
    # {api_public_url}/auth/signin/google/callback.
    google_signin_redirect_uri: str = Field(default="")
    jwt_secret: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_SECRET", "DUCT_JWT_SECRET"),
    )

    # Cloudflare Turnstile (bot protection)
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    # Protects /api/* routes (header X-API-Key). Same value the Next app sends as X-API-Key.
    duct_api_key: str = ""

    # When false (default), FastAPI does not serve /openapi.json, /docs, or /redoc.
    expose_openapi_docs: bool = False

    # When expose_openapi_docs is true and this password is non-empty, /docs, /redoc, and
    # /openapi.json require HTTP Basic auth (username defaults to openapi_docs_basic_user).
    openapi_docs_basic_user: str = Field(
        default="docs",
        validation_alias=AliasChoices(
            "OPENAPI_DOCS_BASIC_USER",
            "DUCT_OPENAPI_DOCS_BASIC_USER",
        ),
    )
    openapi_docs_basic_password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "OPENAPI_DOCS_BASIC_PASSWORD",
            "DUCT_OPENAPI_DOCS_BASIC_PASSWORD",
        ),
    )

    # LLM synthesis (insight generation; see agents.models for provider/model strings)
    generate_provider: str = ""
    generate_model: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Sentry observability
    app_env: str = Field(
        default="local",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    sentry_dsn: str = ""
    sentry_send_default_pii: bool = True
    sentry_enable_logs: bool = True
    sentry_traces_sample_rate: float = 1.0
    sentry_profile_session_sample_rate: float = 1.0
    sentry_profile_lifecycle: str = "trace"
    sentry_enable_localhost: bool = False

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _strip_strings_and_derive_oauth_redirects(cls, data: Any) -> Any:
        """Strip string inputs; fill OAuth redirect URIs from api_public_url when unset."""
        if not isinstance(data, dict):
            return data
        out: dict[str, Any] = {}
        for key, val in data.items():
            if isinstance(val, str):
                out[key] = val.strip()
            else:
                out[key] = val
        base_default = cls.model_fields["api_public_url"].default
        if not isinstance(base_default, str):
            base_default = "http://localhost:8000"
        raw_base = out.get("api_public_url")
        base = (raw_base if isinstance(raw_base, str) and raw_base else base_default).rstrip("/")
        out["api_public_url"] = base
        gor = out.get("google_oauth_redirect_uri")
        if not isinstance(gor, str) or not gor:
            out["google_oauth_redirect_uri"] = f"{base}/auth/google/callback"
        gsr = out.get("google_signin_redirect_uri")
        if not isinstance(gsr, str) or not gsr:
            out["google_signin_redirect_uri"] = f"{base}/auth/signin/google/callback"
        return out


@lru_cache
def get_configs() -> Configs:
    return Configs()
