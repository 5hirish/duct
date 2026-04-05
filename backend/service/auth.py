"""API key validation for protected routes."""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from config import Configs, get_configs

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Configs = Depends(get_configs),
) -> bool:
    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API key is required",
        )

    if not secrets.compare_digest(api_key, settings.duct_api_key):
        logger.warning("Rejected request with invalid X-API-Key")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Could not validate API key",
        )
    return True
