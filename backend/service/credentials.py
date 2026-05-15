"""Fernet symmetric encryption for connector credentials.

The encryption key is read from the CREDENTIALS_ENCRYPTION_KEY env var.
Generate one with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from config import get_configs


def _fernet() -> Fernet:
    key = get_configs().credentials_encryption_key
    if not key:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CREDENTIALS_ENCRYPTION_KEY is not configured.",
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credentials(data: dict) -> str:
    """Encrypt a credentials dict to a Fernet token string."""
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(token: str) -> dict:
    """Decrypt a Fernet token string back to a credentials dict."""
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to decrypt credentials") from exc
