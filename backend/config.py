"""Application configuration from environment and optional `.env` / `.env.local` files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent


def _settings_env_files() -> tuple[Path, ...]:
    """Return dotenv files to load. Always loaded — including under pytest —
    so integration tests can use the same API keys as the running server."""
    return (
        _BACKEND_DIR / ".env",
        _BACKEND_DIR / ".env.local",
    )


class Configs(BaseSettings):
    """Backend settings; all keys optional with defaults so imports work without a full `.env`.

    Loads `backend/.env` then `backend/.env.local` (later overrides; missing files are ignored).
    """

    # CORS / OAuth redirect target
    frontend_origin: str = Field(default="http://localhost:3003")
    # Marketing site origin (getduct.ai) — allowed for public lead-magnet endpoints
    site_origin: str = Field(default="https://getduct.ai")

    # Public origin of this API (scheme + host [+ port], no path). Used to build OAuth redirect
    # URIs when GOOGLE_OAUTH_REDIRECT_URI / GOOGLE_SIGNIN_REDIRECT_URI are unset.
    api_public_url: str = Field(default="http://localhost:8002")

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

    # Fernet key for encrypting connector refresh tokens at rest.
    # Generate: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_encryption_key: str = ""

    # Asset uploads (Railway Volume mounted at /app/uploads in prod).
    # When uploads_enabled=true the server mounts the directory at /uploads as
    # a StaticFiles route. The content agent writes generated images here.
    uploads_enabled: bool = False
    uploads_dir:     str  = "/app/uploads"

    # PostBridge — server-wide API key (MVP). Used as fallback when no
    # ConnectorCredential row exists for the calling user. Future: drop
    # this once a per-user "connect PostBridge" UI lands.
    postbridge_api_key: str = ""

    # Apify API token — used by service/apify/ for TikTok content
    # discovery (trending posts / hashtags / sounds). Server-side key for
    # MVP, same shape as gemini_api_key. Future: per-user when billing
    # demands it.
    apify_api_key: str = ""

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
    # Long-lived Claude OAuth token from `claude setup-token` (the operator's own
    # Pro/Max subscription). Detected here only so the engine-status endpoint can
    # report v3 as authenticated; the Claude Agent SDK subprocess reads the real
    # CLAUDE_CODE_OAUTH_TOKEN env var itself. Intended for local/self-hosted
    # individual use — NOT for routing end users' requests through a subscription
    # (see https://code.claude.com/docs/en/legal-and-compliance). Production
    # multi-user serving must use ANTHROPIC_API_KEY (Claude Console).
    claude_code_oauth_token: str = Field(
        default="",
        validation_alias=AliasChoices("CLAUDE_CODE_OAUTH_TOKEN"),
    )
    # Engine selection: "v1" (LangChain), "v2" (Google ADK), "v3" (Claude Agent SDK)
    generate_engine: str = Field(default="v1")

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

    # Claude Agent SDK built-in OpenTelemetry tracing.
    # When sentry_dsn is set, OTEL endpoint + headers are derived automatically.
    # Set sdk_otel_enabled=true to activate SDK-level traces (turns, tool calls,
    # LLM request latencies) which appear in Sentry → Performance.
    sdk_otel_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def _jwt_secret_strength(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters.")
        return v

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
            base_default = "http://localhost:8002"
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


def allow_subscription_auth() -> bool:
    """True when the Claude Agent SDK may authenticate via a local Claude Code
    OAuth login (subscription credit) instead of an explicit ANTHROPIC_API_KEY.

    Only permitted in local dev — prod must always run on an explicit API key.
    When this returns True, an empty api_key is allowed to fall through to the
    SDK, which reuses the `claude` OAuth token in ~/.claude.
    See https://support.claude.com/en/articles/15036540
    """
    return get_configs().app_env == "local"


def claude_oauth_available() -> bool:
    """True when Claude (v3) can authenticate without an explicit ANTHROPIC_API_KEY.

    Two non-API-key paths, both for the operator's *own* ordinary use:
      - CLAUDE_CODE_OAUTH_TOKEN, a long-lived token from `claude setup-token`
        (works headless/self-hosted), or
      - a local `claude` OAuth login in ~/.claude (dev only).

    Per Anthropic's policy, subscription credentials must NOT route end users'
    requests on a third-party product — production multi-user serving uses an
    ANTHROPIC_API_KEY from the Claude Console. This helper exists so a single
    operator running their own instance isn't blocked, not to serve users.
    See https://code.claude.com/docs/en/legal-and-compliance
    """
    return bool(get_configs().claude_code_oauth_token) or allow_subscription_auth()


def sentry_otel_env(cfg: Configs) -> dict[str, str]:
    """Return OTEL env vars that route the Claude Agent SDK's built-in traces to Sentry.

    The SDK subprocess inherits these; Sentry receives spans for every turn,
    tool call, and LLM request with latencies and token counts.

    DSN format:  https://<key>@o<org>.ingest[.region].sentry.io/<project>
    OTLP format: https://o<org>.ingest[.region].sentry.io/api/<project>/integration/otlp/

    Ref: https://docs.sentry.io/concepts/otlp/
    """
    import re

    if not cfg.sdk_otel_enabled or not cfg.sentry_dsn:
        return {}

    m = re.match(
        r"https://([^@]+)@(o\d+\.ingest(?:\.[^.]+)?\.sentry\.io)/(\d+)",
        cfg.sentry_dsn.strip(),
    )
    if not m:
        return {}

    public_key, host, project_id = m.groups()
    base_endpoint = f"https://{host}/api/{project_id}/integration/otlp/"

    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY":        "1",
        "OTEL_SERVICE_NAME":                   cfg.app_env,
        "OTEL_EXPORTER_OTLP_ENDPOINT":         base_endpoint,
        "OTEL_EXPORTER_OTLP_HEADERS":          f"sentry sentry_key={public_key}",
        "OTEL_EXPORTER_OTLP_PROTOCOL":         "http/protobuf",
    }
