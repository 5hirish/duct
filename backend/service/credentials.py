"""Encryption at rest for every stored credential: connector tokens, vendor
keys and saved provider keys, all in ``connector_credentials.credentials_enc``.

Two ways to hold the key, chosen by configuration and readable side by side:

* ``CREDENTIALS_ENCRYPTION_KEY`` holds Fernet keys, comma-separated, newest
  first. A new token uses the first; any of them decrypts. That is rotation:
  put a new key in front, run ``scripts/rotate_credentials.py``, then drop the
  old key. The desktop sidecar, self-hosting, dev and tests run on this.

* ``CREDENTIALS_KMS_KEY`` names a Cloud KMS key (hosted Duct). Each
  credential is encrypted with a data key of its own, and KMS wraps that data
  key (``service/credential_kms.py``). The single Fernet key used to sit in
  the same environment as the database URL, so whoever had both could read
  every user's credentials offline, silently, for good. With KMS they hold
  wrapped keys: each unwrap is a live request that KMS logs and revoking the
  service account stops. With it set, every new token is an envelope and the
  Fernet keys only read rows written before it.

A token says which it is: ``kms1:<wrapped data key>:<Fernet token>`` for an
envelope, a bare Fernet token otherwise. So turning KMS on needs no flag day:
old rows read as before until the rotate script rewrites them.

Generate a Fernet key with:
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import base64
import json
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import HTTPException
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from config import get_configs
from service.credential_kms import GcpKms, KmsUnavailable

logger = logging.getLogger(__name__)

ENVELOPE_PREFIX = "kms1:"

# Which key a stored token is under, for the rotate script's report.
KIND_KMS = "kms"                  # an envelope
KIND_FERNET_CURRENT = "fernet"    # the first Fernet key
KIND_FERNET_OLD = "fernet-old"    # a Fernet key behind the first
KIND_UNREADABLE = "unreadable"    # no configured key opens it

# Unwrapped data keys, by their wrapped bytes. A credential is read on most
# agent runs, and a KMS round trip per read would put one on every request.
# The process holds the Fernet key in memory already; holding these is the
# same exposure, bounded.
_DATA_KEY_CACHE_SIZE = 1024


def _error(detail: str) -> HTTPException:
    return HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _fernet_keys() -> list[str]:
    raw = get_configs().credentials_encryption_key or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _multi_fernet() -> MultiFernet:
    keys = _fernet_keys()
    if not keys:
        raise _error("CREDENTIALS_ENCRYPTION_KEY is not configured.")
    return MultiFernet([Fernet(k.encode()) for k in keys])


@lru_cache(maxsize=4)
def _gcp_kms(key_name: str, service_account_json: str) -> GcpKms:
    return GcpKms(key_name, service_account_json)


def _kms() -> GcpKms | None:
    # getattr: a test's stand-in config may predate the KMS settings.
    cfg = get_configs()
    key_name = (getattr(cfg, "credentials_kms_key", "") or "").strip()
    if not key_name:
        return None
    return _gcp_kms(key_name, getattr(cfg, "credentials_kms_service_account", "") or "")


@lru_cache(maxsize=_DATA_KEY_CACHE_SIZE)
def _unwrap_cached(key_name: str, wrapped: bytes) -> bytes:
    kms = _kms()
    if kms is None or kms.key_name != key_name:
        raise KmsUnavailable("CREDENTIALS_KMS_KEY is not configured")
    return kms.unwrap(wrapped)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encrypt_credentials(data: dict) -> str:
    """A credentials dict as a token, under the current key."""
    plaintext = json.dumps(data).encode()
    kms = _kms()
    if kms is None:
        return _multi_fernet().encrypt(plaintext).decode()
    data_key = Fernet.generate_key()
    try:
        wrapped = kms.wrap(data_key)
    except KmsUnavailable as exc:
        logger.error("credentials: could not wrap a data key: %s", exc)
        raise _error("Could not encrypt credentials.") from exc
    token = Fernet(data_key).encrypt(plaintext).decode()
    return f"{ENVELOPE_PREFIX}{_b64(wrapped)}:{token}"


def decrypt_credentials(token: str) -> dict:
    """A token back to its credentials dict, whichever key it is under."""
    try:
        if token.startswith(ENVELOPE_PREFIX):
            wrapped_b64, inner = token[len(ENVELOPE_PREFIX):].split(":", 1)
            kms = _kms()
            if kms is None:
                raise _error("CREDENTIALS_KMS_KEY is not configured.")
            data_key = _unwrap_cached(kms.key_name, _unb64(wrapped_b64))
            return json.loads(Fernet(data_key).decrypt(inner.encode()))
        return json.loads(_multi_fernet().decrypt(token.encode()))
    except HTTPException:
        raise
    except KmsUnavailable as exc:
        logger.error("credentials: could not unwrap a data key: %s", exc)
        raise _error("Failed to decrypt credentials") from exc
    except (InvalidToken, ValueError) as exc:
        raise _error("Failed to decrypt credentials") from exc


def token_kind(token: str) -> str:
    """Which key a token is under, without decrypting more than it must."""
    if token.startswith(ENVELOPE_PREFIX):
        return KIND_KMS
    keys = _fernet_keys()
    if keys:
        try:
            Fernet(keys[0].encode()).decrypt(token.encode())
            return KIND_FERNET_CURRENT
        except InvalidToken:
            pass
        for key in keys[1:]:
            try:
                Fernet(key.encode()).decrypt(token.encode())
                return KIND_FERNET_OLD
            except InvalidToken:
                continue
    return KIND_UNREADABLE


def current_kind() -> str:
    """The kind a token written now would be."""
    return KIND_KMS if _kms() is not None else KIND_FERNET_CURRENT
