"""Object storage for generated / user images — pluggable backend.

Two backends, chosen by config (``storage_backend``, or auto when R2 creds exist):

  - ``r2``    → Cloudflare R2 over the S3 API (boto3). Deployed default: images
                are served straight from R2's CDN (zero egress), so they never
                route through this app. Returns an ABSOLUTE public URL.
  - ``local`` → local disk under ``uploads_dir``, served by FastAPI StaticFiles
                at ``/uploads/...``. The dev default and what legacy URLs use.
                Returns a RELATIVE ``/uploads/...`` URL.

The stored ``key`` keeps the existing layout
(``projects/{project_id}/generated/{uuid}.{ext}``) so the rest of the app is
unchanged. ``get_bytes`` resolves any stored URL back to bytes (local disk,
absolute CDN URL, or a repo-bundled ``/static/references/...`` asset) — used when
a prior image is fed back to Gemini as a character/style reference.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from config import get_configs

logger = logging.getLogger(__name__)

# Immutable: every key is unique (uuid/content), so images can cache forever.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


def storage_backend() -> str:
    """'r2' when explicitly selected or fully configured, else 'local'."""
    cfg = get_configs()
    if (cfg.storage_backend or "").lower() == "r2":
        return "r2"
    if cfg.storage_backend in ("", "auto") and _r2_configured(cfg):
        return "r2"
    return "local"


def _r2_configured(cfg) -> bool:
    return bool(
        cfg.r2_account_id and cfg.r2_access_key_id
        and cfg.r2_secret_access_key and cfg.r2_bucket and cfg.r2_public_base_url
    )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def put_image(key: str, data: bytes, content_type: str) -> str:
    """Persist image bytes under ``key``; return the public URL to store on the
    asset row. Raises on failure (callers surface a friendly error)."""
    if storage_backend() == "r2":
        return _r2_put(key, data, content_type)
    return _local_put(key, data)


def _local_put(key: str, data: bytes) -> str:
    cfg = get_configs()
    base = Path(cfg.uploads_dir or "/app/uploads")
    path = base / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("storage(local): wrote %d bytes to %s", len(data), path)
    return f"/uploads/{key}"


def _r2_put(key: str, data: bytes, content_type: str) -> str:
    cfg = get_configs()
    _r2_client().put_object(
        Bucket=cfg.r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
        CacheControl=_CACHE_CONTROL,
    )
    public_url = f"{cfg.r2_public_base_url.rstrip('/')}/{key}"
    logger.info("storage(r2): put %d bytes → %s", len(data), public_url)
    return public_url


# ---------------------------------------------------------------------------
# Read (resolve a stored URL back to bytes — for reference images)
# ---------------------------------------------------------------------------

def get_bytes(url: str) -> bytes | None:
    """Resolve a stored asset URL to its raw bytes, or None if unavailable.

    Handles every URL family we emit: absolute CDN/R2 URLs (HTTP GET), local
    ``/uploads/...`` (disk), and repo-bundled ``/static/references/...``.
    """
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return _http_get(url)
    if url.startswith("/uploads/"):
        cfg = get_configs()
        path = Path(cfg.uploads_dir or "/app/uploads") / url[len("/uploads/"):]
        return path.read_bytes() if path.exists() else None
    # Repo-bundled global reference library — no bucket round-trip.
    from service.content_references import disk_path_for_public_url
    resolved = disk_path_for_public_url(url)
    if resolved is not None and resolved.exists():
        return resolved.read_bytes()
    return None


def _http_get(url: str) -> bytes | None:
    import httpx
    try:
        resp = httpx.get(url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        logger.warning("storage: failed to fetch reference bytes from URL", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# R2 client (lazy — boto3 only imported/required when the R2 backend is used)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _r2_client():
    import boto3
    from botocore.config import Config

    cfg = get_configs()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=cfg.r2_access_key_id,
        aws_secret_access_key=cfg.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
