"""SMTP, the open standard every mail server speaks.

The provider for an install that holds no vendor account: Postfix or Stalwart
beside it, or any vendor's SMTP relay (Resend, SES and Gmail all take it), with
no SDK in this codebase. Locally it is how mail reaches Mailpit, whose inbox
shows what a flow actually sent, where ``console`` only logs it.

Python's own ``smtplib``, run in a worker thread: it blocks, and a slow mail
server must not hold the event loop that is streaming someone's agent run.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, formatdate, make_msgid

from config import Configs
from service.email.message import EmailMessage, EmailResult
from service.email.providers import sender_address

logger = logging.getLogger(__name__)

NAME = "smtp"

# Generous next to the invitation path, because lead reports carry a PDF.
_TIMEOUT_SECONDS = 30.0

SECURITY_STARTTLS = "starttls"
SECURITY_TLS = "tls"
# Plain text, credentials included. Only for a server on this machine, such as
# Mailpit; anything across a network takes one of the two above.
SECURITY_NONE = "none"
# SMTP_PORT=0 takes the standard port for the security mode, so the common
# setups need one setting fewer and a mode change cannot leave a stale port.
_DEFAULT_PORTS = {SECURITY_STARTTLS: 587, SECURITY_TLS: 465, SECURITY_NONE: 25}


def configured(cfg: Configs) -> bool:
    return bool(cfg.smtp_host.strip())


def _security(cfg: Configs) -> str:
    return cfg.smtp_security.strip().lower() or SECURITY_STARTTLS


def build_message(message: EmailMessage, cfg: Configs) -> MimeMessage:
    """The MIME message, split out so its shape is testable without a server.

    Text first and HTML as the alternative, the order mail clients read as
    "prefer the last part they can show". The library's default policy refuses
    a header carrying a line break, so a subject built from user input cannot
    smuggle in a header of its own.
    """
    address = sender_address(message, cfg)
    name = cfg.email_from_name.strip()

    mime = MimeMessage()
    mime["From"] = formataddr((name, address)) if name else address
    mime["To"] = ", ".join(message.to)
    if message.cc:
        mime["Cc"] = ", ".join(message.cc)
    if message.reply_to:
        mime["Reply-To"] = message.reply_to
    mime["Subject"] = message.subject
    mime["Date"] = formatdate(usegmt=True)
    mime["Message-ID"] = make_msgid(domain=address.rpartition("@")[2] or None)
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    for attachment in message.attachments:
        maintype, _, subtype = attachment.content_type.partition("/")
        mime.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return mime


def _deliver(mime: MimeMessage, cfg: Configs, security: str) -> None:
    host = cfg.smtp_host.strip()
    port = cfg.smtp_port or _DEFAULT_PORTS[security]
    context = ssl.create_default_context()
    if security == SECURITY_TLS:
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=_TIMEOUT_SECONDS)
    with client:
        if security == SECURITY_STARTTLS:
            client.starttls(context=context)
        if cfg.smtp_username:
            client.login(cfg.smtp_username, cfg.smtp_password)
        # Envelope recipients come from To and Cc, so the CC'd team is delivered
        # to as well as named.
        client.send_message(mime)


async def send(message: EmailMessage, cfg: Configs) -> EmailResult:
    security = _security(cfg)
    if security not in _DEFAULT_PORTS:
        # Never guess a weaker mode for a typo: "starrtls" falling back to plain
        # text would send the password in the clear.
        logger.warning(
            'Unknown SMTP_SECURITY "%s" — not sending %r. Known modes: %s.',
            security,
            message.subject,
            ", ".join(_DEFAULT_PORTS),
        )
        return EmailResult(delivered=False, backend=NAME, error="unknown SMTP_SECURITY")

    try:
        mime = build_message(message, cfg)
    except ValueError as exc:
        # A line break in a header, a project name in an invitation subject for
        # one: refused by the library rather than sent as a header of its own.
        logger.warning("SMTP message to %s not built: %s", message.to, exc)
        return EmailResult(delivered=False, backend=NAME, error="invalid header")

    try:
        await asyncio.to_thread(_deliver, mime, cfg, security)
    except (smtplib.SMTPException, OSError) as exc:
        # OSError covers a refused connection, a timeout and a failed TLS
        # handshake (ssl.SSLError is one).
        logger.warning("SMTP send to %s failed: %s", message.to, exc)
        return EmailResult(delivered=False, backend=NAME, error=type(exc).__name__)
    return EmailResult(delivered=True, backend=NAME, provider_id=str(mime["Message-ID"]))
