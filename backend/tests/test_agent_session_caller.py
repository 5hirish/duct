"""Who may spend an agent run.

Starting a session costs model tokens — a crawl, enrichment and synthesis for an
audit; a plan or a draft for content. The route took an optional user, so the
only thing between the open internet and an unbounded provider bill was
`X-API-Key`, which ships in the browser bundle as `NEXT_PUBLIC_DUCT_API_KEY`. A
key everybody has is not a payer.

One anonymous run survives on purpose: the public SEO-audit teaser reached from
the marketing site. It is not really anonymous — Turnstile gates the email
capture and `POST /api/lead-magnet/submit` issues a 24-hour token — so it
presents that token where a session would go. These tests pin both halves: the
teaser still works, and nothing else runs for free.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from models.lead_magnet import LeadMagnet
import routes.agents as agent_routes
import service.lead_access as lead_access
from tests.conftest import make_sqlite_engine
from utils.dates import utcnow

AUDIT = "audit_seo"
TIKTOK = "tiktok_studio"


@pytest.fixture
def engine(monkeypatch):
    """In-memory DB behind `lead_token_is_live`, which opens its own session."""
    eng = make_sqlite_engine()
    monkeypatch.setattr(lead_access, "get_engine", lambda: eng, raising=False)
    import db.session as db_session_mod

    monkeypatch.setattr(db_session_mod, "get_engine", lambda: eng)
    return eng


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


def _lead(db, *, age_hours: float = 0.0) -> str:
    """A captured lead, optionally issued `age_hours` ago. Returns its token."""
    token = str(uuid.uuid4())
    row = LeadMagnet(
        email="lead@example.com",
        website_url="https://example.com",
        magnet_type="seo_audit",
        access_token=token,
        created_at=utcnow() - timedelta(hours=age_hours),
    )
    db.add(row)
    db.commit()
    return token


class _User:
    """Stand-in for a resolved User row — the gate only checks for not-None."""

    id = uuid.uuid4()


# ---------------------------------------------------------------------------
# A signed-in caller is always fine
# ---------------------------------------------------------------------------

def test_a_signed_in_caller_may_start_any_agent(db):
    for agent in (AUDIT, TIKTOK):
        agent_routes._require_caller(agent, {"prompt": "hi"}, _User())  # no raise


def test_a_signed_in_caller_needs_no_lead_token(db):
    body = {"prompt": "hi", "lead_magnet": True}
    agent_routes._require_caller(AUDIT, body, _User())


# ---------------------------------------------------------------------------
# The teaser: a live lead token stands in for a session
# ---------------------------------------------------------------------------

def test_the_teaser_runs_on_a_live_lead_token(db):
    body = {"url": "https://example.com", "lead_magnet": True, "lead_token": _lead(db)}
    agent_routes._require_caller(AUDIT, body, None)  # no raise


def test_the_token_is_consumed_and_never_travels_further(db):
    """AuditRequest forbids unknown fields, and a credential that stops moving
    is one fewer thing to keep out of a log or a Sentry breadcrumb."""
    body = {"url": "https://example.com", "lead_magnet": True, "lead_token": _lead(db)}
    agent_routes._require_caller(AUDIT, body, None)
    assert "lead_token" not in body


def test_an_expired_lead_token_is_refused(db):
    body = {
        "url": "https://example.com",
        "lead_magnet": True,
        "lead_token": _lead(db, age_hours=lead_access.TOKEN_TTL_HOURS + 1),
    }
    with pytest.raises(HTTPException) as exc:
        agent_routes._require_caller(AUDIT, body, None)
    assert exc.value.status_code == 401


def test_an_unknown_lead_token_is_refused(db):
    body = {"url": "https://x.com", "lead_magnet": True, "lead_token": str(uuid.uuid4())}
    with pytest.raises(HTTPException) as exc:
        agent_routes._require_caller(AUDIT, body, None)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Everything else is refused
# ---------------------------------------------------------------------------

def test_the_lead_magnet_flag_alone_buys_nothing(db):
    """The flag is caller-supplied; the token is what the server issued."""
    with pytest.raises(HTTPException) as exc:
        agent_routes._require_caller(AUDIT, {"lead_magnet": True}, None)
    assert exc.value.status_code == 401


def test_an_anonymous_full_audit_is_refused(db):
    """No teaser flag: this is the run that reaches enrichment, whose prompt
    carries text scraped off the target site."""
    with pytest.raises(HTTPException) as exc:
        agent_routes._require_caller(
            AUDIT, {"url": "https://x.com", "business_context": {"industry": "saas"}}, None
        )
    assert exc.value.status_code == 401


def test_a_lead_token_does_not_unlock_the_content_agent(db):
    """The teaser exemption is one agent wide, not "anyone holding any token"."""
    body = {"lead_magnet": True, "lead_token": _lead(db), "project_id": str(uuid.uuid4())}
    with pytest.raises(HTTPException) as exc:
        agent_routes._require_caller(TIKTOK, body, None)
    assert exc.value.status_code == 401


def test_a_lookup_failure_denies_rather_than_allows(db, monkeypatch):
    """This check stands in for authentication, so it fails closed."""
    monkeypatch.setattr(lead_access, "get_engine", lambda: None, raising=False)
    import db.session as db_session_mod

    monkeypatch.setattr(db_session_mod, "get_engine", lambda: None)
    with pytest.raises(HTTPException):
        agent_routes._require_caller(
            AUDIT, {"lead_magnet": True, "lead_token": "anything"}, None
        )
