"""Catalog-driven data fetching — entity id in, connector data out.

The old pipeline bound a fixed set of zero-argument tools per goal, capped at
eight, chosen before the model saw anything. This is the replacement: the
**entity catalog is the tool surface**, the agent names an entity, and one
dispatcher resolves the connector, the account, the credentials and the call.

What that buys, beyond removing the cap:

* **Adding a connector is a catalog entry plus one line here.** Nothing in the
  agent, the prompt or the tool schema changes — which is the property the
  verification checks depend on (they declare the entities they need and are
  skipped, visibly, when a connector is absent).
* **Identifiers still never come from the model.** The one genuinely good
  property of the old zero-argument design was that a hallucinated customer id
  was structurally impossible. The account comes from the project's binding and
  the credentials from ``service/connector_access.py``; the model supplies an
  entity id and a date range and nothing else.
* **A missing connector is an instruction, not an exception.** Every failure
  path returns a payload telling the agent what to do next (bind an account,
  ask for a connection, try a different window) because a raised exception ends
  the run while a payload lets it recover.

Framework-free by construction — ``agents/insights/data_tools.py`` is the thin
LangChain binder over this.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from agents.insights.catalog.base import _CATALOGS
from utils.dates import last_n_days

logger = logging.getLogger(__name__)

# Default analysis window when the agent does not name one. Ends yesterday:
# ad platforms only settle a day's numbers after it closes, so including today
# silently understates the most recent day — one of the quieter ways a
# marketing number lies.
DEFAULT_WINDOW_DAYS = 30

# A single response is capped before it reaches the model. Search terms and geo
# rows in particular can run to hundreds of entries, and an agent that spends
# its context on row 400 has none left to reason with.
MAX_RESPONSE_CHARS = 60_000


@dataclass(frozen=True)
class FetchSpec:
    """How to call one catalog entity's fetcher.

    ``call`` takes ``(account_id, date_from, date_to, creds)`` and returns the
    raw dict. Per-connector rather than per-entity, because the argument shapes
    differ by vendor, not by report.
    """

    entity_id: str
    connector_id: str
    tool: str
    call: Callable[[str, str, str, dict], dict[str, Any]]


# ---------------------------------------------------------------------------
# Per-connector call adapters
# ---------------------------------------------------------------------------

def _google_ads(fn: Callable, **extra: Any) -> Callable[[str, str, str, dict], dict]:
    """Google Ads clients want the developer token and the MCC id as well."""

    def _call(account_id: str, date_from: str, date_to: str, creds: dict) -> dict:
        return fn(
            account_id,
            date_from=date_from,
            date_to=date_to,
            developer_token=creds.get("developer_token", ""),
            client_id=creds.get("client_id", ""),
            client_secret=creds.get("client_secret", ""),
            refresh_token=creds.get("refresh_token", ""),
            login_customer_id=creds.get("login_customer_id", ""),
            **extra,
        )

    return _call


def _google_oauth(fn: Callable) -> Callable[[str, str, str, dict], dict]:
    """GA4 and Search Console: plain OAuth, no developer token."""

    def _call(account_id: str, date_from: str, date_to: str, creds: dict) -> dict:
        return fn(
            account_id,
            date_from=date_from,
            date_to=date_to,
            refresh_token=creds.get("refresh_token", ""),
            client_id=creds.get("client_id", ""),
            client_secret=creds.get("client_secret", ""),
        )

    return _call


def _campaigns(account_id: str, date_from: str, date_to: str, creds: dict) -> dict:
    """fetch_campaigns predates the keyword-only convention the others use."""
    from service.google.fetch import fetch_campaigns

    return fetch_campaigns(
        account_id,
        developer_token=creds.get("developer_token", ""),
        client_id=creds.get("client_id", ""),
        client_secret=creds.get("client_secret", ""),
        refresh_token=creds.get("refresh_token", ""),
        date_from=date_from,
        date_to=date_to,
        login_customer_id=creds.get("login_customer_id", ""),
    )


def _build_specs() -> dict[str, FetchSpec]:
    """Entity id → how to fetch it, derived from the catalogs.

    Deferred imports throughout: the Google client libraries are heavy and a
    session that never fetches should not pay for them.
    """
    from service.google.fetch import (
        fetch_ad_group_performance,
        fetch_device_performance,
        fetch_geo_performance,
        fetch_search_terms,
    )
    from service.google.ga4 import fetch_ga4_conversion_paths, fetch_ga4_landing_pages
    from service.google.gsc import fetch_gsc_page_performance, fetch_gsc_query_performance

    by_tool: dict[str, Callable[[str, str, str, dict], dict]] = {
        "fetch_campaign_performance": _campaigns,
        "fetch_search_terms": _google_ads(fetch_search_terms),
        "fetch_device_performance": _google_ads(fetch_device_performance),
        "fetch_geo_performance": _google_ads(fetch_geo_performance),
        "fetch_ad_group_performance": _google_ads(fetch_ad_group_performance),
        "fetch_ga4_landing_pages": _google_oauth(fetch_ga4_landing_pages),
        "fetch_ga4_conversion_paths": _google_oauth(fetch_ga4_conversion_paths),
        "fetch_gsc_query_performance": _google_oauth(fetch_gsc_query_performance),
        "fetch_gsc_page_performance": _google_oauth(fetch_gsc_page_performance),
    }

    specs: dict[str, FetchSpec] = {}
    for connector_id, catalog in _CATALOGS.items():
        for entity in catalog.get("entities", []):
            tool = entity.get("tool", "")
            call = by_tool.get(tool)
            if call is None:
                # A catalog entry with no dispatcher is a real drift bug, but a
                # loud one at fetch time beats an import-time crash that takes
                # the whole agent down.
                logger.warning(
                    "insights: catalog entity %s names unknown tool %s", entity.get("entity_id"), tool
                )
                continue
            specs[entity["entity_id"]] = FetchSpec(
                entity_id=entity["entity_id"],
                connector_id=connector_id,
                tool=tool,
                call=call,
            )
    return specs


_specs: dict[str, FetchSpec] | None = None


def fetch_specs() -> dict[str, FetchSpec]:
    """The entity → fetcher map, built once."""
    global _specs
    if _specs is None:
        _specs = _build_specs()
    return _specs


def known_entities() -> list[str]:
    return sorted(fetch_specs())


# ---------------------------------------------------------------------------
# The dispatcher
# ---------------------------------------------------------------------------

def resolve_window(date_from: str, date_to: str) -> tuple[str, str]:
    """A complete, ordered window. Half-specified ranges fall back whole rather
    than pairing a real date with a guess."""
    if date_from and date_to:
        return (date_from, date_to) if date_from <= date_to else (date_to, date_from)
    return last_n_days(DEFAULT_WINDOW_DAYS)


def fetch_entity(
    entity_id: str,
    *,
    user_id: UUID,
    project_id: UUID | None,
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    """Fetch one catalog entity for this project. Never raises.

    Returns either ``{"status": "ok", ...}`` with the data, or a status the
    agent can act on: ``unknown_entity``, ``needs_account``, ``not_connected``,
    or ``fetch_failed``.
    """
    spec = fetch_specs().get(entity_id)
    if spec is None:
        return {
            "status": "unknown_entity",
            "entity_id": entity_id,
            "message": f"No such entity. Available: {', '.join(known_entities())}",
        }

    from db.session import get_session as db_session
    from service.connector_access import (
        STATUS_BOUND,
        get_data_source,
        resolve_read_credentials,
    )

    with next(db_session()) as db:
        source = get_data_source(db, spec.connector_id, user_id=user_id, project_id=project_id)
        if source is None or source.status != STATUS_BOUND or not source.account_id:
            return _not_ready(spec, source)
        account_id = source.account_id
        creds = resolve_read_credentials(
            db,
            user_id=user_id,
            project_id=project_id,
            connector_type=spec.connector_id,
            account_id=account_id,
        )

    if not creds.get("refresh_token"):
        return {
            "status": "not_connected",
            "entity_id": entity_id,
            "connector_id": spec.connector_id,
            "message": (
                f"{spec.connector_id} has no usable credentials stored. Ask the user to "
                "reconnect it with RequestConnection."
            ),
        }

    window_from, window_to = resolve_window(date_from, date_to)
    try:
        data = spec.call(account_id, window_from, window_to, creds)
    except Exception as exc:  # noqa: BLE001 — reported to the agent, never raised
        logger.warning("insights: fetch %s failed", entity_id, exc_info=True)
        return {
            "status": "fetch_failed",
            "entity_id": entity_id,
            "connector_id": spec.connector_id,
            "account_id": account_id,
            "date_from": window_from,
            "date_to": window_to,
            "message": (
                f"{spec.connector_id} returned an error: {str(exc)[:300]}. Do not retry the "
                "same call — say what you could not fetch and carry on."
            ),
        }

    return {
        "status": "ok",
        "entity_id": entity_id,
        "connector_id": spec.connector_id,
        "account_id": account_id,
        # The window travels with the data deliberately: a number without its
        # window is the single easiest way to state something false.
        "date_from": window_from,
        "date_to": window_to,
        "data": data,
    }


def _not_ready(spec: FetchSpec, source: Any) -> dict[str, Any]:
    """The connector is missing or unbound — say which, and what fixes it."""
    if source is None or source.status == "not_connected":
        return {
            "status": "not_connected",
            "entity_id": spec.entity_id,
            "connector_id": spec.connector_id,
            "message": (
                f"{spec.connector_id} is not connected to this project. Use "
                "RequestConnection if the analysis needs it, or continue without it "
                "and say so."
            ),
        }
    return {
        "status": "needs_account",
        "entity_id": spec.entity_id,
        "connector_id": spec.connector_id,
        "message": (
            f"{spec.connector_id} is connected but this project has not chosen an "
            "account. Call SelectAccount first, then fetch again."
        ),
    }
