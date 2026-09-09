"""The only place in the tree that names an email vendor.

Every provider exposes the same three members, so `sender.py` can pick one
without knowing anything about it:

- ``NAME``       — the value ``EMAIL_PROVIDER`` is matched against.
- ``configured`` — whether this provider has the credentials it needs.
- ``send``       — deliver one message; never raise, always return a result.

Adding a provider is one file here plus a line in ``sender.PROVIDERS``. No
template, route, or test outside this package should need to change, and a fork
that wants SMTP or SES writes that one file rather than reading our routes.
"""

from __future__ import annotations

from typing import Protocol

from config import Configs
from service.email.message import EmailMessage, EmailResult


class EmailProvider(Protocol):
    """Structural contract every module in this package satisfies."""

    NAME: str

    @staticmethod
    def configured(cfg: Configs) -> bool: ...

    @staticmethod
    async def send(message: EmailMessage, cfg: Configs) -> EmailResult: ...


def sender_address(message: EmailMessage, cfg: Configs) -> str:
    """The From address for this message, with the message's own override
    winning over the configured default."""
    return message.sender or cfg.email_from.strip()


__all__ = ["EmailProvider", "sender_address"]
