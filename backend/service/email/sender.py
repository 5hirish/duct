"""The email seam.

Everything above this line decides *what* to say — the templates, and the
routes that choose to say it. Everything below it decides *how*, and names a
vendor. Mirrors `app/src/lib/analytics/index.js` and
`desktop/src-tauri/src/telemetry/`, for the same reason: the builds we
distribute send mail through an account we hold, and a fork should be able to
point that at its own provider, or at nothing, without reading our routes.

Selected by ``EMAIL_PROVIDER``. Unset picks the first provider that has
credentials, in ``_AUTO_ORDER``, and ``console`` when none do — so an existing
deploy keeps its behaviour, and a self-hosted install that configures no vendor
still runs every flow, logging what it would have sent.
"""

from __future__ import annotations

import logging

from config import Configs, get_configs
from service.email.message import Attachment, EmailMessage, EmailResult
from service.email.providers import EmailProvider, cloudflare, console, resend

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, EmailProvider] = {
    cloudflare.NAME: cloudflare,
    resend.NAME: resend,
    console.NAME: console,
}

# Which configured provider wins when EMAIL_PROVIDER is unset. Cloudflare leads
# because the rest of the stack is already there; console is not a candidate
# here — it is what you get when nothing else answers.
_AUTO_ORDER = (cloudflare.NAME, resend.NAME)


def active_backend(cfg: Configs | None = None) -> str:
    """Name of the provider that would handle the next send."""
    settings = cfg or get_configs()

    requested = settings.email_provider.strip().lower()
    if requested:
        if requested in PROVIDERS:
            return requested
        # A typo here would otherwise send nothing and say nothing, which is the
        # failure you discover a month later from a user who never got invited.
        logger.warning(
            'Unknown EMAIL_PROVIDER "%s" — falling back to console. Known providers: %s.',
            requested,
            ", ".join(PROVIDERS),
        )
        return console.NAME

    for name in _AUTO_ORDER:
        if PROVIDERS[name].configured(settings):
            return name
    return console.NAME


async def send_email(message: EmailMessage, cfg: Configs | None = None) -> EmailResult:
    """Send one message through the active provider. Never raises — delivery is
    best-effort and the caller decides how loudly to fail."""
    settings = cfg or get_configs()
    provider = PROVIDERS[active_backend(settings)]

    if not message.to:
        # Reaches here from a config-derived recipient list that turned out
        # empty; a provider would answer with an opaque 400.
        logger.warning("Refusing to send %r with no recipients", message.subject)
        return EmailResult(delivered=False, backend=provider.NAME, error="no recipients")

    if provider is not console and not provider.configured(settings):
        # Only reachable when EMAIL_PROVIDER names a provider whose credentials
        # are missing. Explicit beats silent: this is a deployment mistake.
        logger.warning(
            "EMAIL_PROVIDER=%s but it is not configured — not sending %r",
            provider.NAME,
            message.subject,
        )
        return EmailResult(delivered=False, backend=provider.NAME, error="not configured")

    return await provider.send(message, settings)


__all__ = ["Attachment", "EmailMessage", "EmailResult", "active_backend", "send_email"]
