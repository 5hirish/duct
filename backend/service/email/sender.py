"""Provider-agnostic transactional email sending."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from config import Configs, get_configs

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class EmailMessage:
    """A rendered message, ready to hand to a provider."""

    to: str
    subject: str
    html: str
    text: str
    reply_to: str | None = None


@dataclass(frozen=True)
class EmailResult:
    """Outcome of one send. ``delivered`` is False only on a real failure —
    the console backend reports True so callers can't accidentally treat a
    provider-less environment as broken."""

    delivered: bool
    backend: str
    provider_id: str = ""
    error: str = ""


def active_backend(cfg: Configs | None = None) -> str:
    """``"resend"`` when an API key is configured, else ``"console"``."""
    settings = cfg or get_configs()
    return "resend" if settings.resend_api_key else "console"


def _from_header(cfg: Configs) -> str:
    name = cfg.email_from_name.strip()
    address = cfg.email_from.strip()
    return f"{name} <{address}>" if name else address


async def send_email(message: EmailMessage, cfg: Configs | None = None) -> EmailResult:
    """Send one message through the configured backend. Never raises —
    delivery is best-effort and the caller decides how loudly to fail."""
    settings = cfg or get_configs()
    backend = active_backend(settings)

    if backend == "console":
        logger.info(
            "[email:console] to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.text,
        )
        return EmailResult(delivered=True, backend="console")

    payload: dict[str, object] = {
        "from": _from_header(settings),
        "to": [message.to],
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
    }
    if message.reply_to:
        payload["reply_to"] = message.reply_to

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Resend request failed for %s: %s", message.to, exc)
        return EmailResult(delivered=False, backend="resend", error=str(exc))

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
            backend="resend",
            error=f"resend responded {response.status_code}",
        )

    provider_id = ""
    try:
        provider_id = str(response.json().get("id", ""))
    except ValueError:
        pass
    return EmailResult(delivered=True, backend="resend", provider_id=provider_id)
