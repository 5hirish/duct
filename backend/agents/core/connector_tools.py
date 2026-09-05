"""Connector discovery tools — the agent works out what it can reach.

These replace the first four steps of the insights wizard, which existed only
because the backend had no way to ask. The agent now discovers what is
connected, asks for what is missing, and carries on without what the user
declines.

Three tools, in the order an agent uses them:

  ``ListDataSources``   — what this project has, needs an account for, or has
                          not connected. Read-only; never pauses.
  ``SelectAccount``     — resolve WHICH account/property/site. Binds silently
                          when there is exactly one answer; pauses only when the
                          choice is genuinely ambiguous.
  ``RequestConnection`` — pause and offer to connect one the project lacks.
                          **Skipping is a first-class outcome**: the run
                          continues and the artifact says what it could not see.

Design rules, each of which was a decision:

* **Credentials never reach the model.** Tools return account ids and labels;
  the secret stays in ``service/connector_access.py`` and is closed over by the
  fetch layer. There is no tool that returns a token.
* **Never ask a question with one possible answer.** A single stored account is
  bound silently. Being asked to choose from a list of one is how a wizard feels.
* **A pause is not an error.** Every pause can be skipped (or, on the in-process
  bridge, time out), and each tool returns a status the model can act on
  rather than raising.
* **The tool body does not know how it pauses.** It is handed a ``PauseFn``
  (``agents/core/session.py``) and the binder decides which one: the Future
  bridge for an agent without a checkpointer, LangGraph's ``interrupt`` for one
  with durable threads. Same body, same events, either way.
* **Writes are narrow.** The only state these change is *which account this
  project uses* — a ``project_connectors`` binding, plus the account-specific
  credential row the Connections page would have written anyway. No tool here
  creates, edits or deletes a connector's authorization.

Domain logic is plain Python; ``build_connector_tools_lc`` is the thin binder,
the same split as ``agents/core/memory_tools.py``. Only a LangChain binder
exists because only V1 mounts these — write the SDK one if V3 ever needs it,
not before.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field

from agents.core.events import AgentEvent
from agents.core.session import BaseAgentSession, PauseFn, make_future_pause
from agents.core.telemetry import tool_span

logger = logging.getLogger(__name__)

# A connection is a browser round-trip: OAuth in another tab, maybe a login and
# a consent screen. Far longer than a clarifying question deserves.
CONNECT_TIMEOUT = 600.0
# Picking from a list already on screen.
SELECT_TIMEOUT = 300.0

LIST_DESCRIPTION = (
    "List the data sources this project can reach, with the account each is pointed "
    "at. Call this BEFORE claiming you cannot answer something and before asking the "
    "user what they have connected — it is the authoritative answer. Each source has "
    "a status: 'bound' (ready to use), 'available' (authorized, but this project has "
    "not chosen an account — call SelectAccount), or 'not_connected' (call "
    "RequestConnection if the analysis genuinely needs it)."
)

SELECT_DESCRIPTION = (
    "Resolve which account, property or site this project uses for one connector, and "
    "remember the choice for future sessions. Call it when a source is 'available' or "
    "when the user asks to switch accounts. If there is exactly one candidate it is "
    "selected silently; if there are several the user is asked to pick. Pass account_id "
    "only when the user has already named the account they want."
)

CONNECT_DESCRIPTION = (
    "Ask the user to connect a data source this project does not have. Use it only "
    "when the analysis genuinely needs that source, and say plainly in `reason` what "
    "you would do with it — the user sees that sentence next to the connect button. "
    "They may decline: a 'skipped' result is a normal answer, not a failure. When they "
    "do, continue with what you have and state in your output which source was missing "
    "and what that leaves unverified. Never ask twice for the same connector in one "
    "session."
)


class ConnectorArgs(BaseModel):
    connector_id: str = Field(
        description="Connector id exactly as ListDataSources reports it, e.g. 'google_ads', 'ga4', 'gsc'."
    )


class SelectAccountArgs(ConnectorArgs):
    account_id: str = Field(
        default="",
        description=(
            "Optional. The specific account/property/site id to use, when the user has "
            "already named it. Leave empty to let the tool resolve or ask."
        ),
    )


class RequestConnectionArgs(ConnectorArgs):
    reason: str = Field(
        description=(
            "One sentence, shown to the user beside the connect button: what you need "
            "this source for and what it unlocks. Concrete beats generic — 'to see which "
            "search terms are wasting spend' rather than 'for better analysis'."
        )
    )


# ---------------------------------------------------------------------------
# Domain logic — no framework, no harness
# ---------------------------------------------------------------------------

def _sources_sync(*, user_id: UUID | None, project_id: UUID | None) -> dict:
    from db.session import get_session as db_session
    from service.connector_access import list_data_sources

    with next(db_session()) as db:
        sources = list_data_sources(db, user_id=user_id, project_id=project_id)
    return {"sources": [s.as_dict() for s in sources]}


def _source_sync(connector_id: str, *, user_id: UUID | None, project_id: UUID | None) -> dict | None:
    from db.session import get_session as db_session
    from service.connector_access import get_data_source

    with next(db_session()) as db:
        source = get_data_source(db, connector_id, user_id=user_id, project_id=project_id)
    return source.as_dict() if source else None


def _bind_sync(
    connector_id: str,
    account_id: str,
    account_name: str,
    *,
    user_id: UUID,
    project_id: UUID,
) -> dict:
    from db.session import get_session as db_session
    from service.connector_access import attach_account

    with next(db_session()) as db:
        row = attach_account(
            db,
            project_id=project_id,
            user_id=user_id,
            connector_type=connector_id,
            account_id=account_id,
            account_name=account_name,
        )
        if row is None:
            return {"status": "error", "message": (
                f"No authorized {connector_id} credentials to attach that account to. "
                "Ask the user to connect it first."
            )}
        return {
            "status": "selected",
            "connector_id": connector_id,
            "account_id": row.account_id,
            "account_name": row.account_name,
        }


def _live_accounts_sync(connector_id: str, *, user_id: UUID, project_id: UUID | None) -> list[dict]:
    """Accounts the provider itself reports, for a connector authorized but
    unassigned. This is the lookup the wizard's dropdowns did.

    Best-effort by contract: no credentials, no adapter, no network, or a
    provider error all return ``[]`` and the caller falls back to asking the
    user to finish setup on the Connections page.
    """
    from db.session import get_session as db_session
    from service.connector_access import resolve_read_credentials
    from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, get_connector

    try:
        meta, adapter = get_connector(connector_id)
    except KeyError:
        return []
    if CAP_ACCOUNTS not in meta.capabilities:
        return []

    try:
        with next(db_session()) as db:
            creds = resolve_read_credentials(
                db, user_id=user_id, project_id=project_id, connector_type=connector_id
            )
        if not creds:
            return []
        auth = ConnectorAuthContext(
            connector_id=connector_id,
            refresh_token=creds.get("refresh_token") or None,
            extras={k: str(v) for k, v in creds.items() if v and k != "refresh_token"},
        )
        return list(adapter.list_accounts(auth) or [])
    except Exception:  # noqa: BLE001 — a provider outage must not end the turn
        logger.warning("connector_tools: live account lookup failed for %s", connector_id, exc_info=True)
        return []


def _authorize_path(connector_id: str) -> str:
    """Relative OAuth entry point. Relative deliberately: the app owns its API
    base URL (and the desktop shell rewrites it), so the backend must not guess
    one. Empty for manual-credential connectors, which have no link to offer."""
    from service.connectors import registry

    entry = registry().get(connector_id)
    if entry is None or not entry[0].oauth_scope:
        return ""
    return f"/auth/connectors/{connector_id}/oauth/authorize"


def _label(connector_id: str) -> str:
    from service.connectors import registry

    entry = registry().get(connector_id)
    return entry[0].label if entry else connector_id


async def _run(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run a sync DB/network callable off the event loop, never raising into
    the agent loop — a raised exception ends the run, a payload lets it retry."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("connector_tools: %s failed", getattr(fn, "__name__", fn))
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# LangChain binder
# ---------------------------------------------------------------------------

def build_connector_tools_lc(
    project_id: UUID | None,
    *,
    user_id: UUID | None = None,
    session: BaseAgentSession | None = None,
    session_id: str = "",
    emit: Callable | None = None,
    log_prefix: str = "agent",
    pause: PauseFn | None = None,
) -> list:
    """ListDataSources / SelectAccount / RequestConnection as LangChain tools.

    ``ListDataSources`` needs only a user; the two that write or pause need a
    project and a way to pause as well, so a session without them gets the
    read-only tool alone rather than tools that fail when called.

    ``pause`` picks the pause implementation. Omitted, it is the in-process
    Future bridge over ``session`` + ``emit``; a runner with durable threads
    passes ``interrupt_pause`` and the session is then only needed for the
    read-only tool's scoping.
    """
    from langchain_core.tools import StructuredTool

    if user_id is None:
        return []

    if pause is None and session is not None and emit is not None:
        pause = make_future_pause(session, session_id, emit, log_prefix=log_prefix)
    can_pause = pause is not None and project_id is not None
    pause = pause if can_pause else None

    async def list_data_sources_tool() -> str:
        with tool_span(tool_name="ListDataSources", agent_name=log_prefix):
            return json.dumps(
                await _run(_sources_sync, user_id=user_id, project_id=project_id),
                indent=2,
            )

    async def select_account(connector_id: str, account_id: str = "") -> str:
        with tool_span(tool_name="SelectAccount", agent_name=log_prefix):
            return json.dumps(
                await _select_account(
                    connector_id, account_id,
                    user_id=user_id, project_id=project_id, pause=pause,
                ),
                indent=2,
            )

    async def request_connection(connector_id: str, reason: str) -> str:
        with tool_span(tool_name="RequestConnection", agent_name=log_prefix):
            return json.dumps(
                await _request_connection(
                    connector_id, reason,
                    user_id=user_id, project_id=project_id, pause=pause,
                ),
                indent=2,
            )

    tools = [
        StructuredTool.from_function(
            coroutine=list_data_sources_tool,
            name="ListDataSources",
            description=LIST_DESCRIPTION,
            args_schema=_NoArgs,
        )
    ]
    if can_pause:
        tools += [
            StructuredTool.from_function(
                coroutine=select_account,
                name="SelectAccount",
                description=SELECT_DESCRIPTION,
                args_schema=SelectAccountArgs,
            ),
            StructuredTool.from_function(
                coroutine=request_connection,
                name="RequestConnection",
                description=CONNECT_DESCRIPTION,
                args_schema=RequestConnectionArgs,
            ),
        ]
    return tools


class _NoArgs(BaseModel):
    """ListDataSources takes nothing — the project is closed over at bind time."""


# ---------------------------------------------------------------------------
# Tool bodies — harness-neutral, so a second binder needs no new logic
# ---------------------------------------------------------------------------

async def _select_account(
    connector_id: str,
    account_id: str,
    *,
    user_id: UUID,
    project_id: UUID | None,
    pause: PauseFn | None,
) -> dict:
    """``pause`` is None when nobody can answer — an unattended run, or a
    session without a project — and the tool then reports the ambiguity
    instead of parking."""
    source = await _run(_source_sync, connector_id, user_id=user_id, project_id=project_id)
    if isinstance(source, dict) and source.get("status") == "error":
        return source
    if source is None:
        return {"status": "unknown_connector", "connector_id": connector_id}

    # The user already named one — take it.
    if account_id.strip():
        return await _run(
            _bind_sync, connector_id, account_id.strip(), "",
            user_id=user_id, project_id=project_id,
        )

    if source["status"] == "bound":
        return {
            "status": "already_selected",
            "connector_id": connector_id,
            "account_id": source["account_id"],
            "account_name": source["account_name"],
        }
    if source["status"] == "not_connected":
        return {
            "status": "not_connected",
            "connector_id": connector_id,
            "message": (
                f"{source['label']} is not connected. Call RequestConnection if the "
                "analysis needs it."
            ),
        }

    candidates = [c for c in source.get("stored_accounts", []) if c.get("account_id")]
    if not candidates:
        # Authorized but no account chosen — ask the provider what exists.
        # This is the lookup the wizard's dropdown did.
        candidates = [
            {
                "account_id": str(a.get("id") or a.get("account_id") or ""),
                "account_name": str(a.get("name") or a.get("account_name") or ""),
            }
            for a in await _run(_live_accounts_sync, connector_id, user_id=user_id, project_id=project_id)
            if isinstance(a, dict)
        ]
        candidates = [c for c in candidates if c["account_id"]]

    if len(candidates) == 1:
        # Never ask a question with one possible answer.
        only = candidates[0]
        return await _run(
            _bind_sync, connector_id, only["account_id"], only.get("account_name", ""),
            user_id=user_id, project_id=project_id,
        )
    if not candidates:
        return {
            "status": "needs_setup",
            "connector_id": connector_id,
            "message": (
                f"{source['label']} is authorized but no account is available to select. "
                "Ask the user to finish setting it up on the Connections page."
            ),
        }
    if pause is None:
        return {"status": "ambiguous", "connector_id": connector_id, "candidates": candidates}

    answer = await pause(
        AgentEvent.ACCOUNT_SELECTION_REQUIRED,
        {
            "connector_id": connector_id,
            "label": source["label"],
            "candidates": candidates,
        },
        timeout=SELECT_TIMEOUT,
    )
    chosen = str(answer.get("account_id") or "").strip()
    if not chosen:
        return {
            "status": "skipped",
            "connector_id": connector_id,
            "message": (
                f"The user did not choose a {source['label']} account. Continue without "
                "it and say so in your output. Do not ask again this session."
            ),
        }
    return await _run(
        _bind_sync, connector_id, chosen, str(answer.get("account_name") or ""),
        user_id=user_id, project_id=project_id,
    )


async def _request_connection(
    connector_id: str,
    reason: str,
    *,
    user_id: UUID,
    project_id: UUID | None,
    pause: PauseFn | None,
) -> dict:
    source = await _run(_source_sync, connector_id, user_id=user_id, project_id=project_id)
    if isinstance(source, dict) and source.get("status") == "error":
        return source
    if source is None:
        return {"status": "unknown_connector", "connector_id": connector_id}

    # Already there — answer the question rather than interrupting the user.
    if source["status"] != "not_connected":
        return {
            "status": "already_connected",
            "connector_id": connector_id,
            "account_id": source["account_id"],
            "account_name": source["account_name"],
            "message": (
                f"{source['label']} is already connected. "
                + ("Call SelectAccount to choose an account." if source["status"] == "available" else "")
            ),
        }
    if pause is None:
        return {"status": "not_connected", "connector_id": connector_id}

    answer = await pause(
        AgentEvent.CONNECTION_REQUIRED,
        {
            "connector_id": connector_id,
            "label": source["label"],
            "auth_kind": source["auth_kind"],
            "authorize_path": _authorize_path(connector_id),
            "reason": reason,
        },
        timeout=CONNECT_TIMEOUT,
    )
    if answer.get("skipped") or not answer:
        return {
            "status": "skipped",
            "connector_id": connector_id,
            "message": (
                f"The user declined to connect {source['label']}. Continue without it, "
                "and state in your output which source is missing and what that leaves "
                "unverified. Do not ask again this session."
            ),
        }

    # Re-read rather than trusting the answer: the OAuth round-trip is what
    # actually created the row, and the client only reports that it finished.
    refreshed = await _run(_source_sync, connector_id, user_id=user_id, project_id=project_id)
    if isinstance(refreshed, dict) and refreshed.get("status") in (None, "error"):
        refreshed = None
    if not refreshed or refreshed["status"] == "not_connected":
        return {
            "status": "not_connected",
            "connector_id": connector_id,
            "message": (
                f"{_label(connector_id)} still is not connected — the sign-in may not have "
                "completed. Continue without it rather than asking again."
            ),
        }
    return {
        "status": "connected",
        "connector_id": connector_id,
        "account_id": refreshed["account_id"],
        "account_name": refreshed["account_name"],
        "next": (
            "Call SelectAccount to choose which account to use."
            if refreshed["status"] == "available" else ""
        ),
    }
