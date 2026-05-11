"""Async HTTP helpers for the SEO audit crawler."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "DuctAuditBot/1.0 (+https://getduct.ai/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=_HEADERS,
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
    )


async def fetch_text(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    """Fetch URL and return (body_text, status_code). Empty string on error."""
    try:
        resp = await client.get(url)
        return resp.text, resp.status_code
    except Exception as exc:
        logger.debug("fetch_text %s failed: %s", url, exc)
        return "", 0


async def fetch_bytes(client: httpx.AsyncClient, url: str) -> tuple[bytes, int]:
    """Fetch URL and return (body_bytes, status_code). Empty bytes on error."""
    try:
        resp = await client.get(url)
        return resp.content, resp.status_code
    except Exception as exc:
        logger.debug("fetch_bytes %s failed: %s", url, exc)
        return b"", 0
