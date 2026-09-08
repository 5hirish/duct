"""Log the message instead of sending it.

The fallback when nothing else is configured, and the reason a fresh clone runs
the full invitation and lead-report flows with no vendor account. It reports
``delivered=True`` deliberately: callers treat a False as a fault worth warning
about, and "no provider configured" is a choice, not a fault.
"""

from __future__ import annotations

import logging

from config import Configs
from service.email.message import EmailMessage, EmailResult

logger = logging.getLogger(__name__)

NAME = "console"


def configured(cfg: Configs) -> bool:  # noqa: ARG001 - always available, by design
    return True


async def send(message: EmailMessage, cfg: Configs) -> EmailResult:  # noqa: ARG001
    logger.info(
        "[email:console] to=%s cc=%s subject=%s attachments=%s\n%s",
        ", ".join(message.to),
        ", ".join(message.cc),
        message.subject,
        [a.filename for a in message.attachments],
        message.text,
    )
    return EmailResult(delivered=True, backend=NAME)
