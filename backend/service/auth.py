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

from config import Configs, get_configs
from db.session import get_session
from models.auth import User

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Configs = Depends(get_configs),
    session: Session = Depends(get_session),
) -> User:
    """Validate the Bearer JWT and return the authenticated User row."""
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

    user = session.execute(select(User).where(User.email == email)).scalars().first()
    if user is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Configs = Depends(get_configs),
    session: Session = Depends(get_session),
) -> User | None:
    """Like ``get_current_user`` but returns ``None`` instead of raising 401 when
    no valid Bearer token is present.

    For routes that personalise when the caller is logged in yet must keep
    working for signed-out / token-less sessions (the app degrades to local-only
    without a token). Never trusts client-supplied identity — the name comes from
    the JWT-resolved ``User`` row or not at all.
    """
    if not credentials or not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError:  # includes ExpiredSignatureError
        return None
    email: str = payload.get("sub", "")
    if not email:
        return None
    return session.execute(select(User).where(User.email == email)).scalars().first()
