"""Memory tools every agent gets — RememberFact / SearchMemory / GetMemory.

Cross-agent by design (like ``agents/core/context.py``): the audit, content and
insights agents all remember the same project. One implementation of the tool
*behaviour* lives here, with a thin adapter per harness:

* :func:`build_memory_tools_sdk` — Claude Agent SDK in-process MCP tools (V3,
  still the production path for audit and content).
* :func:`build_memory_tools_lc` — LangChain ``StructuredTool``s (V1, the target
  harness). Same names, same descriptions, so behaviour is identical across
  engines; only the argument transport differs.

Both are scoped to one membership-checked project — ``routes/agents.py`` stamps
``artifact_project_id`` on the session only after verifying the caller belongs
to it, and these tools take the same id. Nothing crosses project boundaries.

DB work runs in a worker thread (sync SQLModel session), so a tool call never
blocks the streaming event loop, and every failure returns a payload rather than
raising — a raised exception ends the agent loop, a payload lets the model retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field

from models.memory import SCOPE_PROJECT, SCOPE_USER, SOURCE_AGENT, SOURCE_USER
from utils.dates import parse_iso

logger = logging.getLogger(__name__)

_SEARCH_LIMIT = 15

# The durable bar, stated once and shared by both harnesses. Adapted from
# Claude Code's memory discipline: a fact earns a row only when it will still
# matter next session AND cannot be re-derived by calling a tool.
REMEMBER_DESCRIPTION = (
    "Remember one durable fact about this project so future sessions start knowing it. "
    "Write a memory when something is TRUE ACROSS SESSIONS and NOT re-derivable by "
    "calling a tool or opening an artifact: a decision and its reason, a goal or target, "
    "an incident with when it started and what caused it, a milestone, a change to the "
    "site or account, a conclusion you reached with its evidence, or something to watch. "
    "Metrics are the exception to 're-derivable' — a dated value for a named period is "
    "exactly what memory is for. Do NOT remember: anything you can fetch again, running "
    "commentary, restated user questions, or judgements about the person. "
    "Use ABSOLUTE dates (2026-08-14), never 'last Thursday'. One fact per call. "
    "Set entity_key + attribute when the fact is the current STATE of something "
    "(e.g. entity_key='page:/pricing', attribute='indexation') — a later value for the "
    "same key closes this one automatically instead of contradicting it."
)

SEARCH_DESCRIPTION = (
    "Search this project's memory for facts that are not in the <project_memory> digest — "
    "older incidents, past metric values, superseded goals, earlier decisions. Use it "
    "BEFORE answering 'when did X happen', 'have we seen this before', or 'what did we "
    "decide about Y', and before saying something is unknown. Filter by kind, by entity, "
    "or by date range; leave query empty to list everything in a window."
)

GET_DESCRIPTION = (
    "Fetch one memory entry in full by its id (e.g. 'm_a1b2c3d4' as shown in the "
    "<project_memory> digest or in SearchMemory results) — the complete body, its "
    "validity period, evidence links, and what superseded it if anything did."
)

KIND_HELP = (
    "One of: status, goal, milestone, event, incident, metric, decision, conclusion, "
    "action, watch, entity."
)


class RememberFactArgs(BaseModel):
    """Arguments for RememberFact (LangChain transport)."""

    kind: str = Field(description=KIND_HELP)
    title: str = Field(description="The fact in one line, with its number or date if it has one.")
    body: str = Field(
        default="",
        description=(
            "The detail: what was observed, Why it matters, and How to apply it next time. "
            "Keep it dense — a few sentences, not a report."
        ),
    )
    entity_key: str = Field(
        default="",
        description=(
            "What this fact is about, as type:id — 'page:/pricing', 'campaign:Brand', "
            "'kpi:cpa', 'competitor:databox'. Required for facts that have a current value."
        ),
    )
    attribute: str = Field(
        default="",
        description="Which property of the entity this states — 'status', 'target', 'clicks_wow'.",
    )
    period: str = Field(
        default="",
        description="For metrics, the period the value covers: '2026-08-01..14', '2026-W33'.",
    )
    value: dict = Field(
        default_factory=dict,
        description='Typed payload for metrics/goals: {"value": 71, "unit": "USD", "delta": 0.38}.',
    )
    observed_at: str = Field(
        default="",
        description="ISO date the fact was observed or happened (YYYY-MM-DD). Defaults to now.",
    )
    confidence: str = Field(
        default="medium", description="How sure you are: low | medium | high."
    )
    importance: int = Field(
        default=5, description="0–10. 8+ for goals and decisions, 3 for routine observations."
    )


class SearchMemoryArgs(BaseModel):
    """Arguments for SearchMemory (LangChain transport)."""

    query: str = Field(default="", description="Words to match in the title, body or entity.")
    kinds: list[str] = Field(default_factory=list, description=f"Restrict to kinds. {KIND_HELP}")
    entity: str = Field(default="", description="Restrict to one entity key, e.g. 'page:/pricing'.")
    from_date: str = Field(default="", description="Earliest observation date (YYYY-MM-DD).")
    to_date: str = Field(default="", description="Latest observation date (YYYY-MM-DD).")
    include_superseded: bool = Field(
        default=False,
        description="Include closed/replaced entries — use when asking what was true in the past.",
    )
    limit: int = Field(default=_SEARCH_LIMIT, description=f"Max entries (default {_SEARCH_LIMIT}).")


class GetMemoryArgs(BaseModel):
    """Arguments for GetMemory (LangChain transport)."""

    memory_id: str = Field(description="The entry id, e.g. 'm_a1b2c3d4'.")


# ---------------------------------------------------------------------------
# Harness-independent behaviour
# ---------------------------------------------------------------------------

def _entry_payload(row, *, full: bool = False) -> dict:
    from service.memory import short_id

    out = {
        "id": short_id(row.id),
        "kind": row.kind,
        "title": row.title,
        "observed_at": row.observed_at.isoformat() if row.observed_at else "",
        "status": row.status,
    }
    if row.entity_key:
        out["entity_key"] = row.entity_key
    if row.attribute:
        out["attribute"] = row.attribute
    if row.period:
        out["period"] = row.period
    if row.value:
        out["value"] = row.value
    if full or row.body:
        out["body"] = row.body
    if full:
        out["valid_from"] = row.valid_from.isoformat() if row.valid_from else ""
        out["valid_to"] = row.valid_to.isoformat() if row.valid_to else ""
        out["confidence"] = row.confidence
        out["importance"] = row.importance
        out["source_type"] = row.source_type
        out["source_refs"] = row.source_refs
        out["superseded_by"] = short_id(row.superseded_by) if row.superseded_by else ""
    return out


def _remember_sync(args: dict, *, project_id, user_id, conversation_id, agent_type, scope, source_type) -> dict:
    from db.session import get_session as db_session
    from service.memory import remember, short_id

    refs: list[dict] = []
    if conversation_id:
        refs.append({"conversation_id": str(conversation_id)})

    with next(db_session()) as db:
        row = remember(
            db,
            scope=scope,
            kind=str(args.get("kind") or "").strip(),
            title=str(args.get("title") or "").strip(),
            body=str(args.get("body") or ""),
            project_id=project_id,
            user_id=user_id,
            entity_key=str(args.get("entity_key") or ""),
            attribute=str(args.get("attribute") or ""),
            period=str(args.get("period") or ""),
            value=args.get("value") if isinstance(args.get("value"), dict) else {},
            observed_at=parse_iso(args.get("observed_at") or ""),
            source_type=source_type,
            source_refs=refs,
            confidence=str(args.get("confidence") or "medium"),
            importance=int(args.get("importance") or 5),
            agent_type=agent_type,
            conversation_id=conversation_id,
        )
        if row is None:
            return {
                "status": "not_stored",
                "message": (
                    "Rejected — a memory needs a kind and a one-line title, and the entry "
                    "must belong to this project. Nothing was written."
                ),
            }
        return {
            "status": "remembered",
            "memory": {"id": short_id(row.id), "kind": row.kind, "title": row.title,
                       "entry_status": row.status},
        }


def _search_sync(args: dict, *, project_id, user_id, scope) -> dict:
    from db.session import get_session as db_session
    from service.memory import search

    kinds = [str(k).strip() for k in (args.get("kinds") or []) if str(k).strip()]
    with next(db_session()) as db:
        rows = search(
            db,
            project_id=project_id,
            user_id=user_id,
            scope=scope if scope == SCOPE_USER else None,
            query=str(args.get("query") or ""),
            kinds=kinds or None,
            entity=str(args.get("entity") or ""),
            since=parse_iso(args.get("from_date") or ""),
            until=parse_iso(args.get("to_date") or ""),
            include_superseded=bool(args.get("include_superseded")),
            limit=int(args.get("limit") or _SEARCH_LIMIT),
        )
        return {"count": len(rows), "memories": [_entry_payload(r) for r in rows]}


def _get_sync(memory_id: str, *, project_id, user_id) -> dict:
    from db.session import get_session as db_session
    from service.memory import resolve_short_id

    with next(db_session()) as db:
        row = resolve_short_id(db, memory_id, project_id=project_id, user_id=user_id)
        if row is None:
            return {
                "status": "not_found",
                "message": f"No memory {memory_id!r} in this project. Use SearchMemory to find it.",
            }
        return {"memory": _entry_payload(row, full=True)}


async def _run(fn, *args, **kwargs) -> dict:
    """Run a sync DB helper off the event loop, turning failures into payloads."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — tools report errors, never raise
        logger.warning("memory tool failed", exc_info=True)
        return {"status": "error", "message": str(exc)}


async def _notify(on_memory: Callable[[dict], Any] | None, payload: dict) -> None:
    """Emit MEMORY_WRITTEN — the quiet 'Remembered: …' line. UI sugar, never fatal."""
    if on_memory is None or payload.get("status") != "remembered":
        return
    try:
        await on_memory(payload["memory"])
    except Exception:  # noqa: BLE001
        logger.debug("memory: MEMORY_WRITTEN emit failed", exc_info=True)


# ---------------------------------------------------------------------------
# LangChain (V1) — the target harness
# ---------------------------------------------------------------------------

def build_memory_tools_lc(
    project_id: UUID | None,
    *,
    user_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    scope: str = SCOPE_PROJECT,
    on_memory: Callable[[dict], Any] | None = None,
) -> list:
    """RememberFact / SearchMemory / GetMemory as LangChain ``StructuredTool``s."""
    from langchain_core.tools import StructuredTool

    if project_id is None and scope != SCOPE_USER:
        return []

    async def remember_fact(**args: Any) -> str:
        payload = await _run(
            _remember_sync, args,
            project_id=project_id, user_id=user_id, conversation_id=conversation_id,
            agent_type=agent_type, scope=scope,
            source_type=SOURCE_USER if scope == SCOPE_USER else SOURCE_AGENT,
        )
        await _notify(on_memory, payload)
        return json.dumps(payload)

    async def search_memory(**args: Any) -> str:
        return json.dumps(
            await _run(_search_sync, args, project_id=project_id, user_id=user_id, scope=scope),
            indent=2,
        )

    async def get_memory_tool(memory_id: str) -> str:
        return json.dumps(
            await _run(_get_sync, memory_id, project_id=project_id, user_id=user_id), indent=2
        )

    return [
        StructuredTool.from_function(
            coroutine=remember_fact,
            name="RememberFact",
            description=REMEMBER_DESCRIPTION,
            args_schema=RememberFactArgs,
        ),
        StructuredTool.from_function(
            coroutine=search_memory,
            name="SearchMemory",
            description=SEARCH_DESCRIPTION,
            args_schema=SearchMemoryArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_memory_tool,
            name="GetMemory",
            description=GET_DESCRIPTION,
            args_schema=GetMemoryArgs,
        ),
    ]


# ---------------------------------------------------------------------------
# Claude Agent SDK (V3) — maintained until V1 earns full confidence
# ---------------------------------------------------------------------------

def build_memory_tools_sdk(
    project_id: UUID | None,
    *,
    user_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    scope: str = SCOPE_PROJECT,
    on_memory: Callable[[dict], Any] | None = None,
) -> list:
    """The same three tools as in-process MCP tools for the Claude Agent SDK."""
    from claude_agent_sdk import tool

    if project_id is None and scope != SCOPE_USER:
        return []

    def _text(payload: dict) -> dict:
        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}

    @tool(
        name="RememberFact",
        description=REMEMBER_DESCRIPTION,
        input_schema=RememberFactArgs.model_json_schema(),
    )
    async def remember_fact(args: dict) -> dict:
        payload = await _run(
            _remember_sync, args,
            project_id=project_id, user_id=user_id, conversation_id=conversation_id,
            agent_type=agent_type, scope=scope,
            source_type=SOURCE_USER if scope == SCOPE_USER else SOURCE_AGENT,
        )
        await _notify(on_memory, payload)
        return _text(payload)

    @tool(
        name="SearchMemory",
        description=SEARCH_DESCRIPTION,
        input_schema=SearchMemoryArgs.model_json_schema(),
    )
    async def search_memory(args: dict) -> dict:
        return _text(await _run(_search_sync, args, project_id=project_id, user_id=user_id, scope=scope))

    @tool(
        name="GetMemory",
        description=GET_DESCRIPTION,
        input_schema={"memory_id": Annotated[str, "The entry id, e.g. 'm_a1b2c3d4'."]},
    )
    async def get_memory_tool(args: dict) -> dict:
        return _text(
            await _run(
                _get_sync, str(args.get("memory_id") or ""),
                project_id=project_id, user_id=user_id,
            )
        )

    return [remember_fact, search_memory, get_memory_tool]
