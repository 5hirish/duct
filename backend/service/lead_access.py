"""The lead-magnet access token — one definition of what makes one live.

A lead token is issued by ``POST /api/lead-magnet/submit`` once Cloudflare
Turnstile has passed, and it is the only credential the public SEO-audit teaser
has. Four places now check it: the three lead-magnet endpoints, and agent
session creation, which accepts it in place of a signed-in user for that one
anonymous flow.

Kept here rather than in ``routes/lead_magnet.py`` so ``routes/agents.py`` can
use it without importing another route module, and so the TTL is a single
constant instead of the same ``timedelta`` written out four times — a token
that expires in one place and not another is the kind of drift this prevents.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from models.lead_magnet import LeadMagnet

# How long an issued token stays redeemable.
TOKEN_TTL_HOURS = 24


def find_live_lead(session: Session, token: str) -> LeadMagnet | None:
    """The lead this token belongs to, or None when it is unknown or expired."""
    token = (token or "").strip()
    if not token:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=TOKEN_TTL_HOURS)
    return session.exec(
        select(LeadMagnet).where(
            LeadMagnet.access_token == token,
            LeadMagnet.created_at >= cutoff,
        )
    ).first()


def lead_token_is_live(token: str) -> bool:
    """Whether `token` is redeemable, opening a session of its own.

    For callers outside the lead-magnet routes, which have no session in hand.
    Fails closed: an unconfigured or unreachable database means "no", never
    "sure, go ahead" — this is the check standing in for authentication.
    """
    from db.session import get_engine

    engine = get_engine()
    if engine is None:
        return False
    try:
        with Session(engine) as session:
            return find_live_lead(session, token) is not None
    except Exception:  # noqa: BLE001 — a broken lookup is not an authorisation
        return False
