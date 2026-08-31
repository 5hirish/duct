"""LangChain binder for the insights data tools.

Two tools, both thin over framework-free logic:

  ``FetchData``          — one catalog entity for this project
                           (``agents/insights/fetchers.py``).
  ``ReadConnectorNotes`` — the gotcha pack for one connector
                           (``agents/knowledge/``).

Why the notes are a tool and not a skill
----------------------------------------
The phase plan said to move ``agents/knowledge/*.md`` behind ``deepagents``'
``SkillsMiddleware``. That middleware requires a ``FilesystemBackend`` — a
**real** filesystem rooted somewhere on disk — and mounting one would hand the
agent's ``read_file`` a live path into the host. The isolation guarantee that
the agent cannot reach Duct's source is held today by construction (the default
``StateBackend`` is graph state, and there is no Bash tool), and it is asserted
in ``tests/test_insights_session.py``. Trading it for a prompt optimisation
would be a bad exchange, and confining a real backend to one directory is a
path-traversal question this codebase should not have to answer.

A tool gives the same progressive disclosure — an index in the cached system
prompt, bodies on demand — with no filesystem at all, in about thirty lines.
If ``deepagents`` ever ships a virtual skills backend, this becomes the shim.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field

from agents.core.telemetry import tool_span
from agents.insights.fetchers import (
    MAX_RESPONSE_CHARS,
    fetch_entity,
    known_entities,
)
from agents.knowledge import load_knowledge_pack

logger = logging.getLogger(__name__)

# Packs that exist under agents/knowledge/, with the one-line summary that goes
# in the cached system prompt. Names match connector ids where one exists, so
# the agent can go straight from a data source to its notes.
KNOWLEDGE_INDEX: dict[str, str] = {
    "google_ads": "Google Ads — attribution windows, conversion double-counting, shared-account contamination.",
    "ga4": "GA4 — key events vs conversions, internal traffic, and what the UI silently samples.",
    "gsc": "Search Console — anonymised queries, position averaging, and the 16-month limit.",
    "gtm": "Tag Manager — tags that fire but fail at runtime, and publish-as-deploy.",
    "stripe": "Stripe — incomplete subscriptions, expansion vs acquisition, involuntary churn.",
    "apple_ads": "Apple Search Ads — org-scoped endpoints, string money fields, v5 field renames.",
    "meta": "Meta Ads — cents vs dollars, one purchase under three action types.",
    "openai_ads": "OpenAI ads — minor-unit amounts against decimal spend.",
    "revenuecat": "RevenueCat — sandbox vs production, and trial accounting.",
    "reconciliation": "Cross-platform reconciliation — comparing numbers that are not comparable.",
}


class FetchDataArgs(BaseModel):
    entity_id: str = Field(
        description=(
            "Which catalog entity to fetch, exactly as named in <entity_catalogs>. "
            f"One of: {', '.join(known_entities())}."
        )
    )
    date_from: str = Field(
        default="",
        description="Start date, YYYY-MM-DD. Leave both dates empty for the last 30 days ending yesterday.",
    )
    date_to: str = Field(default="", description="End date, YYYY-MM-DD.")


class ConnectorNotesArgs(BaseModel):
    connector_id: str = Field(
        description=f"Which connector's notes to read. One of: {', '.join(sorted(KNOWLEDGE_INDEX))}."
    )


FETCH_DESCRIPTION = (
    "Fetch one entity of live data for this project. The account, property or site and "
    "the credentials are resolved server-side from the project's connections — you name "
    "the entity and the window, nothing else. Returns the data plus the exact window it "
    "covers; cite that window whenever you cite a number from it. A non-'ok' status is an "
    "instruction: 'needs_account' means call SelectAccount first, 'not_connected' means "
    "the project lacks that source, 'fetch_failed' means say what you could not read "
    "rather than retrying the same call."
)

NOTES_DESCRIPTION = (
    "Read Duct's hard-won notes on one connector before you interpret its numbers: the "
    "specific ways that platform reports something plausible and wrong. Read the notes "
    "for every connector you fetch from, BEFORE drawing a conclusion from it — each entry "
    "exists because the naive reading produced a believable wrong number in a real account."
)


def build_data_tools_lc(
    project_id: UUID | None,
    *,
    user_id: UUID | None = None,
    log_prefix: str = "agent",
    on_fetch: Callable[[str, dict], Any] | None = None,
) -> list:
    """FetchData + ReadConnectorNotes as LangChain tools.

    Without a user there is nothing to resolve credentials from, so only the
    notes tool is mounted — reading them is still useful, and a fetch tool that
    can only fail is worse than no fetch tool.
    """
    from langchain_core.tools import StructuredTool

    async def read_connector_notes(connector_id: str) -> str:
        with tool_span(tool_name="ReadConnectorNotes", agent_name=log_prefix):
            body = load_knowledge_pack(connector_id.strip().lower())
            if not body:
                return json.dumps({
                    "status": "no_notes",
                    "connector_id": connector_id,
                    "available": sorted(KNOWLEDGE_INDEX),
                })
            return body

    tools = [
        StructuredTool.from_function(
            coroutine=read_connector_notes,
            name="ReadConnectorNotes",
            description=NOTES_DESCRIPTION,
            args_schema=ConnectorNotesArgs,
        )
    ]
    if user_id is None:
        return tools

    async def fetch_data(entity_id: str, date_from: str = "", date_to: str = "") -> str:
        import asyncio

        with tool_span(tool_name="FetchData", agent_name=log_prefix):
            try:
                result = await asyncio.to_thread(
                    fetch_entity,
                    entity_id.strip(),
                    user_id=user_id,
                    project_id=project_id,
                    date_from=date_from.strip(),
                    date_to=date_to.strip(),
                )
            except Exception as exc:  # noqa: BLE001 — a payload, never a raise
                logger.exception("insights: FetchData(%s) failed", entity_id)
                result = {"status": "fetch_failed", "entity_id": entity_id, "message": str(exc)[:300]}

            if on_fetch is not None:
                try:
                    await _maybe_await(on_fetch(entity_id, result))
                except Exception:  # noqa: BLE001 — UI sugar, never fatal
                    logger.debug("insights: on_fetch hook failed", exc_info=True)

            return _truncate(result)

    tools.append(
        StructuredTool.from_function(
            coroutine=fetch_data,
            name="FetchData",
            description=FETCH_DESCRIPTION,
            args_schema=FetchDataArgs,
        )
    )
    return tools


def knowledge_index_block() -> str:
    """The pack index for the cached system prompt — names and one-liners only.

    Cache-stable: the same for every customer. The bodies stay behind
    ReadConnectorNotes so the prefix does not carry ten files nobody read.
    """
    lines = [f"- `{name}` — {summary}" for name, summary in sorted(KNOWLEDGE_INDEX.items())]
    return "\n".join(lines)


async def _maybe_await(value: Any) -> Any:
    import inspect

    return await value if inspect.isawaitable(value) else value


def _truncate(result: dict[str, Any]) -> str:
    """Serialise, and cut the payload rather than the envelope when it is large.

    Dropping rows off the end of a JSON blob would corrupt it, so an oversized
    response keeps its status/window fields and replaces the data with a
    truncated string plus a note — the agent can then narrow the window instead
    of wondering why the numbers stopped.
    """
    body = json.dumps(result, default=str)
    if len(body) <= MAX_RESPONSE_CHARS:
        return body
    data = json.dumps(result.get("data"), default=str)[: MAX_RESPONSE_CHARS - 2_000]
    trimmed = {k: v for k, v in result.items() if k != "data"}
    trimmed["data_truncated"] = data
    trimmed["note"] = (
        "This response was too large to return whole and has been cut mid-structure. "
        "Narrow the date range or analyse a more specific entity rather than relying "
        "on the tail of this payload."
    )
    return json.dumps(trimmed, default=str)
