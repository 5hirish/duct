"""draft_post sub-agent — produces one finished PostDraft per dispatch.

Invoked by the orchestrator through the ``task`` tool. Runs in an isolated
context on the run's own model (creative quality is the point, so no step
down) and returns a strict JSON payload matching
``agents.content.schema.PostDraft`` (layout + structured slides, caption,
hashtags, hook). Does NOT write to the DB — the orchestrator calls
submit_post_draft to persist.

Tools: the ``fetch_format_library`` reader (so the sub-agent can pull the
exact spec table for the chosen format without depending on the
orchestrator's brief to inline it) plus ``WebFetch`` for a light fact-check
of a URL it already has. Web search rides along where the provider offers a
native one — the runner appends it.
"""

from __future__ import annotations

from typing import Any

from agents.content.prompts import DRAFT_POST_PROMPT
from agents.content.schema import ContentTool
from agents.core.web_tools import WEB_FETCH_TOOL

DRAFT_POST_SUBAGENT = "draft_post"

# Tool names this sub-agent may use, resolved to tool objects by the runner.
DRAFT_POST_TOOLS: tuple[str, ...] = (
    ContentTool.FETCH_FORMAT_LIBRARY.value,
    WEB_FETCH_TOOL,
)


def build_draft_post_subagent(tools: list[Any], model: Any) -> dict[str, Any]:
    """The ``SubAgent`` spec, with the tool objects and model the runner chose."""
    return {
        "name": DRAFT_POST_SUBAGENT,
        "description": (
            "Draft a single finished post (layout, structured slides, caption, "
            "hashtags, hook, image prompts) for one Day. Returns strict JSON "
            "matching PostDraft. No DB writes; the orchestrator persists via "
            "submit_post_draft."
        ),
        "system_prompt": DRAFT_POST_PROMPT,
        "tools": list(tools),
        "model": model,
    }
