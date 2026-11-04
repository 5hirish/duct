"""The email seam: which provider is chosen, and what it is handed.

Lives apart from `test_project_invitations.py` because none of this is about
invitations — invitations are just the flow that happened to need mail first.
The lead-magnet templates moved into `service/email/templates/lead.py` from a
vendor-named module that had no tests at all; these cover the parts that were
silently wrong there (an empty CC list, a missing PDF).

No test here touches a network. `clean_env` is not decoration: `Configs` reads
`backend/.env.local` on purpose, so without it a developer holding real
credentials gets different answers than CI does.
"""

from __future__ import annotations

import base64
import logging
from contextlib import contextmanager

import pytest

from config import Configs
from service.email import EmailMessage, active_backend, send_email
from service.email.templates import execution_interest, lead_report

REPORT = {
    "structured_data": {
        "overall_score": 62,
        "top_priorities": [{"rank": 1, "title": "No <title> on /pricing", "severity": "fail"}],
        "wins": ["Sitemap is clean"],
        "key_signals": ["11 pages indexed"],
    }
}



@contextmanager
def _captured(logger_name: str, level: int = logging.WARNING):
    """Collect records a logger emits, whatever the app's handler config is."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(logger_name)
    handler = _Collect(level=level)
    logger.addHandler(handler)
    # Uvicorn's dictConfig runs somewhere in a full-suite run and disables every
    # logger that already existed, this one included — so a test that asserts on
    # a warning passes alone and fails in CI unless it undoes that.
    was_disabled, logger.disabled = logger.disabled, False
    try:
        yield records
    finally:
        logger.disabled = was_disabled
        logger.removeHandler(handler)
# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def test_no_credentials_means_console(clean_env):
    assert active_backend(Configs()) == "console"


def test_the_first_configured_provider_wins_and_cloudflare_leads(clean_env):
    """Unset EMAIL_PROVIDER picks whichever provider has credentials, preferring
    Cloudflare — the sending domain is managed alongside the rest of the stack."""
    assert active_backend(Configs(smtp_host="mail.acme.com")) == "smtp"
    assert (
        active_backend(Configs(cloudflare_email_api_token="cf", cloudflare_account_id="a"))
        == "cloudflare"
    )
    assert (
        active_backend(
            Configs(
                smtp_host="mail.acme.com",
                cloudflare_email_api_token="cf",
                cloudflare_account_id="a",
            )
        )
        == "cloudflare"
    )


def test_email_provider_overrides_what_is_configured(clean_env):
    """The escape hatch a self-hosted install needs: hold credentials, send
    nothing."""
    cfg = Configs(
        email_provider="console",
        cloudflare_email_api_token="cf",
        cloudflare_account_id="a",
    )
    assert active_backend(cfg) == "console"


def test_an_unknown_provider_name_falls_back_to_console_loudly(clean_env):
    """A typo must not silently send nothing — that is the failure you find out
    about a month later from a user who never got invited.

    Captured with an own handler rather than `caplog`: `server.py` sets
    propagate=False across the `service` namespace, and the suite runs with
    `log_cli`, which between them leave `caplog` empty here.
    """
    with _captured("service.email.sender") as records:
        assert active_backend(Configs(email_provider="sendgird")) == "console"
    assert any("sendgird" in r.getMessage() for r in records)


@pytest.mark.asyncio
async def test_console_reports_delivery_so_a_provider_less_env_is_not_a_fault(clean_env):
    result = await send_email(
        EmailMessage(to="ana@acme.com", subject="s", html="<p>h</p>", text="t"), Configs()
    )
    assert result.delivered is True
    assert result.backend == "console"


@pytest.mark.asyncio
async def test_a_named_provider_without_credentials_refuses_rather_than_pretending(clean_env):
    result = await send_email(
        EmailMessage(to="ana@acme.com", subject="s", html="<p>h</p>", text="t"),
        Configs(email_provider="cloudflare"),
    )
    assert result.delivered is False
    assert result.error == "not configured"


@pytest.mark.asyncio
async def test_an_empty_recipient_list_is_refused_before_it_reaches_a_provider(clean_env):
    """LEAD_EMAIL_CC parses to nothing more often than you would like, and a
    provider answers that with an opaque 400."""
    result = await send_email(
        EmailMessage(to=["", "  "], subject="s", html="<p>h</p>", text="t"),
        Configs(email_provider="console"),
    )
    assert result.delivered is False
    assert result.error == "no recipients"


# ---------------------------------------------------------------------------
# What each provider is handed
# ---------------------------------------------------------------------------


def test_each_provider_encodes_one_attachment_its_own_way(clean_env):
    """One `Attachment` of raw bytes, two wire formats — the divergence the seam
    exists to hide. Cloudflare takes JSON with the file base64'd under `type`;
    SMTP takes a MIME part, and alone carries a display name in From."""
    from service.email.message import Attachment
    from service.email.providers import cloudflare, smtp

    message = EmailMessage(
        to="ana@acme.com",
        cc="team@getduct.ai",
        subject="s",
        html="<p>h</p>",
        text="t",
        attachments=[Attachment("r.pdf", b"%PDF-1.4", "application/pdf")],
    )
    cfg = Configs(email_from="noreply@getduct.ai", email_from_name="Duct")
    encoded = base64.b64encode(b"%PDF-1.4").decode()

    cf = cloudflare.build_payload(message, cfg)
    assert cf["from"] == "noreply@getduct.ai"
    assert cf["to"] == ["ana@acme.com"] and cf["cc"] == ["team@getduct.ai"]
    assert cf["attachments"] == [
        {"filename": "r.pdf", "content": encoded, "type": "application/pdf"}
    ]

    mime = smtp.build_message(message, cfg)
    assert mime["From"] == "Duct <noreply@getduct.ai>"
    assert mime["To"] == "ana@acme.com" and mime["Cc"] == "team@getduct.ai"
    assert mime["Message-ID"].endswith("@getduct.ai>")
    body = mime.get_body(preferencelist=("html", "plain"))
    assert body.get_content_type() == "text/html" and "<p>h</p>" in body.get_content()
    (pdf,) = mime.iter_attachments()
    assert pdf.get_filename() == "r.pdf"
    assert pdf.get_content_type() == "application/pdf"
    assert pdf.get_content() == b"%PDF-1.4"


def test_optional_headers_are_omitted_rather_than_sent_empty(clean_env):
    """An empty `cc` or `reply_to` is rejected by some servers and silently
    accepted by others; sending neither is the only portable move."""
    from service.email.providers import cloudflare, smtp

    message = EmailMessage(to="ana@acme.com", subject="s", html="<p>h</p>", text="t")
    cfg = Configs(email_from="noreply@getduct.ai")

    payload = cloudflare.build_payload(message, cfg)
    assert "cc" not in payload
    assert "reply_to" not in payload
    assert "attachments" not in payload

    mime = smtp.build_message(message, cfg)
    assert mime["Cc"] is None and mime["Reply-To"] is None
    assert list(mime.iter_attachments()) == []


def test_a_message_sender_overrides_the_configured_default(clean_env):
    """Lead mail and project mail go out from different addresses on purpose."""
    from service.email.providers import sender_address

    cfg = Configs(email_from="noreply@getduct.ai")
    default = EmailMessage(to="a@b.com", subject="s", html="", text="")
    override = EmailMessage(to="a@b.com", subject="s", html="", text="", sender="hello@getduct.ai")

    assert sender_address(default, cfg) == "noreply@getduct.ai"
    assert sender_address(override, cfg) == "hello@getduct.ai"


# ---------------------------------------------------------------------------
# SMTP: what is said to the server, in what order
# ---------------------------------------------------------------------------

_SMTP_MESSAGE = EmailMessage(to="ana@acme.com", subject="s", html="<p>h</p>", text="t")


def _fake_smtp(monkeypatch, fail_with=None):
    from service.email.providers import smtp
    from tests.fakes import FakeSMTP

    fake = FakeSMTP(fail_with=fail_with)
    fake.install(monkeypatch, smtp)
    return fake


def _smtp(**settings) -> Configs:
    return Configs(email_provider="smtp", smtp_host="mail.acme.com", **settings)


@pytest.mark.asyncio
async def test_smtp_upgrades_to_tls_before_it_sends_the_password(clean_env, monkeypatch):
    """STARTTLS on 587 is the default, and the login comes after the upgrade:
    the other order sends the password in the clear on every message."""
    fake = _fake_smtp(monkeypatch)
    result = await send_email(_SMTP_MESSAGE, _smtp(smtp_username="duct", smtp_password="pw"))

    assert result.delivered is True and result.backend == "smtp"
    (session,) = fake.sessions
    assert (session["host"], session["port"], session["tls"]) == ("mail.acme.com", 587, False)
    assert [call[0] for call in session["calls"]] == ["starttls", "login", "send_message"]
    assert session["calls"][1] == ("login", "duct", "pw")
    assert result.provider_id == session["calls"][2][1]["Message-ID"]


@pytest.mark.asyncio
async def test_each_security_mode_takes_its_own_transport_and_port(clean_env, monkeypatch):
    """Implicit TLS opens an encrypted socket on 465; "none" talks plain text and
    is what Mailpit on :1025 takes. No username means no login at all."""
    fake = _fake_smtp(monkeypatch)
    await send_email(_SMTP_MESSAGE, _smtp(smtp_security="tls"))
    await send_email(_SMTP_MESSAGE, _smtp(smtp_security="none", smtp_port=1025))

    implicit, plain = fake.sessions
    assert (implicit["port"], implicit["tls"]) == (465, True)
    assert [call[0] for call in implicit["calls"]] == ["send_message"]
    assert (plain["port"], plain["tls"]) == (1025, False)
    assert [call[0] for call in plain["calls"]] == ["send_message"]


@pytest.mark.asyncio
async def test_an_unknown_security_mode_refuses_rather_than_falling_back(clean_env, monkeypatch):
    """A typo must never become plain text with the password in it."""
    fake = _fake_smtp(monkeypatch)
    result = await send_email(_SMTP_MESSAGE, _smtp(smtp_security="starrtls", smtp_password="pw"))

    assert result.delivered is False
    assert result.error == "unknown SMTP_SECURITY"
    assert fake.sessions == []


@pytest.mark.asyncio
async def test_a_refusing_server_is_a_result_not_an_exception(clean_env, monkeypatch):
    """A provider never raises: a refused login or a dropped connection comes
    back as an undelivered result the caller can report."""
    import smtplib

    _fake_smtp(monkeypatch, fail_with=smtplib.SMTPAuthenticationError(535, b"bad credentials"))
    result = await send_email(_SMTP_MESSAGE, _smtp(smtp_username="duct", smtp_password="pw"))

    assert result.delivered is False
    assert result.error == "SMTPAuthenticationError"


@pytest.mark.asyncio
async def test_a_line_break_in_a_header_is_refused_not_sent(clean_env, monkeypatch):
    """An invitation's subject carries a project name somebody typed; a line
    break in it must not become a header of its own."""
    fake = _fake_smtp(monkeypatch)
    message = EmailMessage(to="ana@acme.com", subject="Join Acme\nBcc: x@evil.test", html="", text="")
    result = await send_email(message, _smtp())

    assert result.delivered is False
    assert result.error == "invalid header"
    assert fake.sessions == []


# ---------------------------------------------------------------------------
# Lead-magnet templates
# ---------------------------------------------------------------------------


def test_lead_report_carries_the_score_and_attaches_the_pdf():
    message = lead_report(
        recipient_email="lead@acme.com",
        site_url="https://acme.com/pricing",
        report_json=REPORT,
        pdf=b"%PDF-1.4",
        cc=("team@getduct.ai",),
        sender="hello@getduct.ai",
    )
    assert message.to == ("lead@acme.com",)
    assert message.cc == ("team@getduct.ai",)
    assert message.sender == "hello@getduct.ai"
    # The subject is the whole open-rate argument: domain, not URL, and a score.
    assert "acme.com" in message.subject and "62/100" in message.subject
    assert message.attachments[0].filename == "seo-audit-acme.com.pdf"
    assert message.attachments[0].content_type == "application/pdf"
    assert "No &lt;title&gt; on /pricing" in message.html


def test_lead_report_still_sends_when_the_pdf_could_not_be_built():
    """The body carries the findings, so a failed render costs the attachment,
    not the email."""
    message = lead_report(
        recipient_email="lead@acme.com", site_url="https://acme.com", report_json=REPORT
    )
    assert message.attachments == ()
    assert "62" in message.html


def test_execution_interest_names_the_services_a_lead_asked_for():
    message = execution_interest(
        team=("team@getduct.ai",),
        lead_email="lead@acme.com",
        site_url="https://acme.com",
        services=["ai_ready_fixes", "translation"],
        note="Wants Spanish first",
    )
    assert message.to == ("team@getduct.ai",)
    assert "AI-ready fixes" in message.html
    assert "Translation / localization" in message.html
    assert "Wants Spanish first" in message.html
    assert "lead@acme.com" in message.subject
