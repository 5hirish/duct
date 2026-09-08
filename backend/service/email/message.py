"""What a message is, independent of who delivers it.

Nothing in this module names a vendor, and nothing in it does I/O. Templates
build these; providers consume them. That split is the whole point of the
package: a fork that swaps the provider keeps every template, and a new
template needs to know nothing about how mail leaves the building.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def _tuple(value: str | Sequence[str] | None) -> tuple[str, ...]:
    """Accept one address or many, and drop the blanks either way.

    Callers pass a bare string far more often than a list, and a config-derived
    recipient list routinely contains empty strings from a trailing comma.
    Normalising here means no provider has to think about either case.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    return tuple(address.strip() for address in value if address and address.strip())


@dataclass(frozen=True)
class Attachment:
    """A file to hang off a message. ``content`` is raw bytes — each provider
    encodes it the way its own API wants, so callers never base64 anything."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class EmailMessage:
    """A rendered message, ready to hand to a provider.

    ``sender`` overrides the configured default address. Lead mail and project
    mail deliberately go out from different addresses, and carrying that on the
    message keeps the provider free of any idea of *why* a message exists.
    """

    to: tuple[str, ...]
    subject: str
    html: str
    text: str
    cc: tuple[str, ...] = ()
    reply_to: str | None = None
    attachments: tuple[Attachment, ...] = ()
    sender: str = ""

    def __init__(  # noqa: PLR0913 - a message is genuinely this many fields
        self,
        *,
        to: str | Sequence[str],
        subject: str,
        html: str,
        text: str,
        cc: str | Sequence[str] | None = None,
        reply_to: str | None = None,
        attachments: Sequence[Attachment] = (),
        sender: str = "",
    ) -> None:
        object.__setattr__(self, "to", _tuple(to))
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "html", html)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "cc", _tuple(cc))
        object.__setattr__(self, "reply_to", reply_to or None)
        object.__setattr__(self, "attachments", tuple(attachments))
        object.__setattr__(self, "sender", sender.strip())


@dataclass(frozen=True)
class EmailResult:
    """Outcome of one send.

    ``delivered`` is False only on a real failure — the console provider reports
    True so a provider-less environment (local dev, CI, a self-hosted install)
    is never mistaken for a broken one.
    """

    delivered: bool
    backend: str
    provider_id: str = ""
    error: str = ""
