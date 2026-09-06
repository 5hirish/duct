"""API key validation and JWT user identity for protected routes."""

from __future__ import annotations

import logging
import secrets

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlmodel import Session
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from agents.models import Provider
from config import Configs, get_configs
from db.session import get_session_optional
from models.auth import User

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)

# Optional per-request bring-your-own provider API keys. auto_error=False so
# requests without them still pass; the generate route prefers any supplied key
# over the server-side config key for that provider (see get_user_provider_keys).
_anthropic_key_header = APIKeyHeader(name="X-Provider-Anthropic", auto_error=False)
_openai_key_header = APIKeyHeader(name="X-Provider-OpenAI", auto_error=False)
_gemini_key_header = APIKeyHeader(name="X-Provider-Gemini", auto_error=False)
# OpenRouter is the OpenAI-compatible transport rather than a fourth SDK (see
# agents/models.Provider), but as a *credential* it is its own provider: a
# caller's `sk-or-v1-…` must never be spent as an OpenAI key, so it gets its own
# header rather than riding on X-Provider-OpenAI.
_openrouter_key_header = APIKeyHeader(name="X-Provider-OpenRouter", auto_error=False)
_xai_key_header = APIKeyHeader(name="X-Provider-XAI", auto_error=False)


async def validate_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Configs = Depends(get_configs),
) -> bool:
    if not api_key:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="API key is required")
    if not settings.duct_api_key:
        # Misconfigured server — reject all requests rather than letting empty==empty pass.
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="API key not configured")
    if not secrets.compare_digest(api_key, settings.duct_api_key):
        logger.warning("Rejected request with invalid X-API-Key")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Could not validate API key")
    return True


async def get_user_provider_keys(
    anthropic_key: str | None = Security(_anthropic_key_header),
    openai_key: str | None = Security(_openai_key_header),
    gemini_key: str | None = Security(_gemini_key_header),
    openrouter_key: str | None = Security(_openrouter_key_header),
    xai_key: str | None = Security(_xai_key_header),
) -> dict[Provider, str]:
    """Per-request bring-your-own provider API keys from the X-Provider-* headers.

    Returns only the providers the caller actually supplied (non-blank). The
    generate route prefers these over the server-side config keys, falling back
    to the backend's own key when a provider is absent. These values are secrets:
    never log them and never persist them (see the Sentry header scrub in
    server.py).
    """
    supplied = {
        Provider.ANTHROPIC: anthropic_key,
        Provider.OPENAI: openai_key,
        Provider.GOOGLE_GENAI: gemini_key,
        Provider.OPENROUTER: openrouter_key,
        Provider.XAI: xai_key,
    }
    return {
        provider: value.strip()
        for provider, value in supplied.items()
        if value and value.strip()
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Configs = Depends(get_configs),
    session: Session | None = Depends(get_session_optional),
) -> User:
    """Validate the Bearer JWT and return the authenticated User row.

    The session is optional so that *rejecting* a caller never depends on the
    database. FastAPI resolves the dependency tree before the endpoint runs, so
    a hard ``Depends(get_session)`` here turned "you sent no token" into
    "DATABASE_URL is not configured" — a 500 about us in answer to a question
    about them. A request that gets far enough to need a user row still fails
    loudly below when there is no database to read it from.
    """
    if not credentials:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not settings.jwt_secret:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="JWT not configured")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token")

    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    if session is None:
        # A well-formed token we cannot check. Not the caller's fault and not
        # an authentication failure, so it must not be dressed up as one.
        raise RuntimeError("DATABASE_URL is not configured.")
    user = session.execute(select(User).where(User.email == email)).scalars().first()
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Configs = Depends(get_configs),
    session: Session | None = Depends(get_session_optional),
) -> User | None:
    """Like ``get_current_user`` but returns ``None`` instead of raising 401 when
    no valid Bearer token is present.

    For routes that personalise when the caller is logged in yet must keep
    working for signed-out / token-less sessions (the app degrades to local-only
    without a token). Never trusts client-supplied identity — the name comes from
    the JWT-resolved ``User`` row or not at all.

    **No token and a broken token are not the same thing.** Sending nothing is a
    signed-out visitor and degrades on purpose. Sending a token that does not
    resolve is a client that believes it is signed in — usually a session left
    over from another environment, since the JWT secret is not what distinguishes
    them. Answering that with ``None`` makes the server agree the caller is a
    stranger, and the damage is silent: an agent run drops every tool built from
    ``user_id`` (``build_connector_tools_lc`` returns nothing, ``FetchData`` is
    never mounted) and then answers the question from the prompt alone, with no
    data and no warning. A 401 is the honest answer and the client already knows
    how to act on it.
    """
    if not credentials or not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token")
    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    if session is None:
        # No database to check against is not the caller's fault, and this route
        # is allowed to run without a user — degrade rather than blame them.
        return None
    user = session.execute(select(User).where(User.email == email)).scalars().first()
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
