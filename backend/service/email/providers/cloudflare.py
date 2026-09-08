"""Cloudflare Email Service, over its REST API.

Chosen as the default when configured because the rest of the stack already
lives on Cloudflare — the app deploys to Workers, media sits in R2, bot
protection is Turnstile — so the sending domain, its DKIM records and its
reputation are managed in the same place as everything else, with no extra
vendor account to hold.

Uses ``httpx`` against the documented endpoint rather than the ``cloudflare``
SDK: one POST does not justify a dependency, and ``httpx`` is already here.
https://developers.cloudflare.com/email-service/api/send-emails/rest-api/
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

NAME = "cloudflare"

# Generous next to the invitation path, because lead reports carry a PDF.
_TIMEOUT_SECONDS = 30.0
_ACCEPTED = (200, 201, 202)


def configured(cfg: Configs) -> bool:
    return bool(cfg.cloudflare_email_api_token and cfg.cloudflare_account_id)


def _endpoint(cfg: Configs) -> str:
    return (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{cfg.cloudflare_account_id}/email-service/send"
    )


def build_payload(message: EmailMessage, cfg: Configs) -> dict[str, Any]:
    """The request body, split out so its shape is testable without a network."""
    payload: dict[str, Any] = {
        "from": sender_address(message, cfg),
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
                "type": a.content_type,
            }
            for a in message.attachments
        ]
    return payload


async def send(message: EmailMessage, cfg: Configs) -> EmailResult:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _endpoint(cfg),
                json=build_payload(message, cfg),
                headers={
                    "Authorization": f"Bearer {cfg.cloudflare_email_api_token}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Cloudflare email request failed for %s: %s", message.to, exc)
        return EmailResult(delivered=False, backend=NAME, error=str(exc))

    if response.status_code not in _ACCEPTED:
        # Error bodies echo the recipient, so log a short excerpt rather than
        # the whole payload.
        logger.warning(
            "Cloudflare rejected message to %s: %s %s",
            message.to,
            response.status_code,
            response.text[:200],
        )
        return EmailResult(
            delivered=False,
            backend=NAME,
            error=f"cloudflare responded {response.status_code}",
        )

    provider_id = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            result = body.get("result")
            source = result if isinstance(result, dict) else body
            provider_id = str(source.get("id", "") or source.get("message_id", ""))
    except ValueError:
        pass
    return EmailResult(delivered=True, backend=NAME, provider_id=provider_id)
