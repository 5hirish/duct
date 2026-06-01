"""Cloudflare Turnstile token verification."""

from __future__ import annotations

import httpx

from config import get_configs


async def verify_turnstile(token: str, remote_ip: str) -> bool:
    """Verify a Cloudflare Turnstile token against the siteverify API.

    Returns True if valid. Skips verification in local dev (app_env == "local")
    or when turnstile_secret_key is not configured — Cloudflare rejects tokens
    issued from localhost against a production site key.
    """
    cfg = get_configs()
    if not cfg.turnstile_secret_key or cfg.app_env == "local":
        return True
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": cfg.turnstile_secret_key,
                "response": token,
                "remoteip": remote_ip,
            },
        )
        result = resp.json()
        return result.get("success", False)
