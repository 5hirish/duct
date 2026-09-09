"""The onboarding sign-in bundle: Google sign-in that also connects a source.

Onboarding runs the audit before anyone signs in, and the report is the one
moment asking for Search Console has a reason the user can see. So at that
moment — and only there — the Google sign-in asks for the Search Console and
Analytics **read** scopes in the same consent. One browser round-trip returns
the user signed in *with* the data the agent just asked for.

Everywhere else the sign-in stays identity-only and every connector asks for
its own scopes on the Connections page. That is a rule, not an accident:

* A sign-in that always asked for data access would be the classic
  over-scoped consent screen, and Google's verification review treats it as
  one. The bundle is requested by name, on one flow, and there is exactly one
  name.
* The bundle is read scopes only. A connector's write scope (GA4's
  ``analytics.edit``, say) is asked for by that connector, with its own
  justification on screen, when the user reaches for it.
* Declining the extra boxes still signs the user in. Google reports what was
  actually granted; a source is stored only when its scope is in that list,
  and nothing is inferred from what was asked.

The stored rows are ordinary ``connector_credentials`` rows, written by the
same upsert the Connections page uses, so the agent's ``ListDataSources``
sees them on the next turn with no browser involved.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from db.session import get_engine
from service.connector_scopes import parse_scopes
from service.connector_store import upsert_credential
from service.google.constants import (
    GA4_CONNECTOR_ID,
    GA4_READ_SCOPE,
    GSC_CONNECTOR_ID,
    GSC_READ_SCOPE,
)

logger = logging.getLogger(__name__)

# The only bundle there is. The authorize endpoint takes its name in
# ``?sources=``; anything else is ignored and the sign-in runs identity-only.
ONBOARDING_BUNDLE = "onboarding"

# connector id -> the one read scope that connector needs. Read scopes only;
# see the module docstring for why a write scope must never appear here.
BUNDLE_SOURCES: dict[str, str] = {
    GSC_CONNECTOR_ID: GSC_READ_SCOPE,
    GA4_CONNECTOR_ID: GA4_READ_SCOPE,
}


def is_bundle(name: str) -> bool:
    """True for the one bundle name the authorize endpoint honours."""
    return (name or "").strip().lower() == ONBOARDING_BUNDLE


def bundle_scopes() -> list[str]:
    """The extra scopes the bundle adds to the identity scopes, in a stable order."""
    return list(BUNDLE_SOURCES.values())


def granted_sources(granted_scopes: str | list[str] | None) -> list[str]:
    """Which bundle sources the user actually consented to, from Google's own
    list — never from what was requested."""
    granted = set(parse_scopes(granted_scopes))
    return [cid for cid, scope in BUNDLE_SOURCES.items() if scope in granted]


def store_granted_sources(
    user_id: str,
    *,
    refresh_token: str,
    granted_scopes: str | list[str] | None,
) -> list[str]:
    """Store one credential row per granted source and return their ids.

    One refresh token covers every scope in the consent, so each source gets
    the same token with its own recorded grant — which is exactly what the
    per-connector flow would have produced twice. Never raises: the sign-in
    has already succeeded by the time this runs, and a storage failure must
    not turn it into an error page after the user approved at Google.
    """
    sources = granted_sources(granted_scopes)
    if not sources or not refresh_token or not user_id:
        return []
    engine = get_engine()
    if engine is None:
        logger.warning("signin sources: no database, %s not stored", ", ".join(sources))
        return []
    try:
        with Session(engine) as session:
            for connector_id in sources:
                upsert_credential(
                    session,
                    user_id=UUID(str(user_id)),
                    connector_type=connector_id,
                    credentials={"refresh_token": refresh_token},
                    granted_scopes=BUNDLE_SOURCES[connector_id],
                )
            session.commit()
    except Exception:  # noqa: BLE001 — the sign-in stands; the loss is logged
        logger.exception("signin sources: storing %s failed", ", ".join(sources))
        return []
    logger.info("signin sources: stored %s for user %s", ", ".join(sources), user_id)
    return sources
