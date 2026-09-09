"""Composition: pick a template, fill it from config, hand it to the seam.

The lead-magnet flows land here rather than in the route because both need the
same three config-derived things — the internal CC list, the lead sender
address, and the PDF — and a background task in a route is the wrong place to
learn any of them. Project invitations compose in their route instead: they
need the plaintext token, which exists nowhere else.
"""

from __future__ import annotations

import logging
from typing import Any

from config import Configs, get_configs
from service.email.sender import send_email
from service.email.templates import execution_interest, lead_report

logger = logging.getLogger(__name__)


def _team(cfg: Configs) -> tuple[str, ...]:
    """Internal recipients from ``LEAD_EMAIL_CC``, comma-separated."""
    return tuple(a.strip() for a in cfg.lead_email_cc.split(",") if a.strip())


def _lead_sender(cfg: Configs) -> str:
    """Lead mail goes out from its own address when one is set, so marketing
    replies do not land wherever project invitations reply to."""
    return cfg.lead_email_from.strip() or cfg.email_from.strip()


async def send_lead_report_email(
    to_email: str,
    site_url: str,
    report_json: dict[str, Any],
) -> bool:
    """Send the branded audit email with the PDF attached. Never raises."""
    cfg = get_configs()

    # Imported here because the PDF renderer pulls in a heavy dependency tree
    # that has no business loading for an invitation email.
    from service.report_pdf import generate_report_pdf

    try:
        pdf = generate_report_pdf(report_json)
    except Exception:
        # A missing attachment is worse than no email only if the email is
        # empty; the body carries the findings, so send it either way.
        logger.exception("email: PDF generation failed for %s", site_url)
        pdf = b""

    result = await send_email(
        lead_report(
            recipient_email=to_email,
            site_url=site_url,
            report_json=report_json,
            pdf=pdf,
            cc=_team(cfg),
            sender=_lead_sender(cfg),
        ),
        cfg,
    )
    if not result.delivered:
        logger.warning(
            "email: lead report not delivered to %s (%s): %s",
            to_email,
            result.backend,
            result.error,
        )
    return result.delivered


async def send_execution_interest_notification(
    lead_email: str,
    site_url: str,
    services: list[str],
    note: str | None = None,
) -> bool:
    """Tell the internal team a lead asked for paid execution. Never raises."""
    cfg = get_configs()
    team = _team(cfg)
    if not team:
        # The demand signal this captures is the whole point of the upsell test,
        # so silence here is a finding, not a no-op.
        logger.warning(
            "email: execution-interest notify skipped for %s — LEAD_EMAIL_CC is empty",
            lead_email,
        )
        return False

    result = await send_email(
        execution_interest(
            team=team,
            lead_email=lead_email,
            site_url=site_url,
            services=services,
            note=note,
            sender=_lead_sender(cfg),
        ),
        cfg,
    )
    if not result.delivered:
        logger.warning(
            "email: execution-interest notify not delivered (%s): %s",
            result.backend,
            result.error,
        )
    return result.delivered
