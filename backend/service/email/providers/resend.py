"""Resend, over its REST API.

Kept alongside the Cloudflare provider rather than replaced by it: it was the
original transactional backend, some deploys still hold a key for it, and a
seam with one real implementation is a seam nobody can trust.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from config import Configs
from service.email.message import EmailMessage, EmailResult
from service.email.providers import sender_address

logger = logging.getLogger(__name__)

NAME = "resend"

_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 30.0


def configured(cfg: Configs) -> bool:
    return bool(cfg.resend_api_key)


def _from_header(message: EmailMessage, cfg: Configs) -> str:
    address = sender_address(message, cfg)
    name = cfg.email_from_name.strip()
    return f"{name} <{address}>" if name else address


def build_payload(message: EmailMessage, cfg: Configs) -> dict[str, Any]:
    """The request body, split out so its shape is testable without a network."""
    payload: dict[str, Any] = {
        "from": _from_header(message, cfg),
        "to": list(message.to),
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
    }
    if message.cc:
        payload["cc"] = list(message.cc)
    if message.reply_to:
        payload["reply_to"] = message.reply_to
    if message.attachments:
        payload["attachments"] = [
            {
                "filename": a.filename,
                "content": base64.b64encode(a.content).decode(),
                "content_type": a.content_type,
            }
            for a in message.attachments
        ]
    return payload


async def send(message: EmailMessage, cfg: Configs) -> EmailResult:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _ENDPOINT,
                json=build_payload(message, cfg),
                headers={"Authorization": f"Bearer {cfg.resend_api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Resend request failed for %s: %s", message.to, exc)
        return EmailResult(delivered=False, backend=NAME, error=str(exc))

    if response.status_code >= 400:
        # Resend echoes the recipient in error bodies; log the status and a
        # short excerpt rather than the whole payload.
        logger.warning(
            "Resend rejected message to %s: %s %s",
            message.to,
            response.status_code,
            response.text[:200],
        )
        return EmailResult(
            delivered=False,
            backend=NAME,
            error=f"resend responded {response.status_code}",
        )

    provider_id = ""
    try:
        provider_id = str(response.json().get("id", ""))
    except ValueError:
        pass
    return EmailResult(delivered=True, backend=NAME, provider_id=provider_id)
