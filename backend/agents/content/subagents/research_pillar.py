"""research_pillar sub-agent — fan-out topic research for one pillar.

Invoked by the orchestrator through the ``task`` tool. Runs in an isolated
context on the cheaper sibling of the run's model where one exists (the same
step the fallback chain takes — see ``agents/models.MODEL_FALLBACK``) and
returns a strict JSON payload matching ``agents.content.schema.TopicCandidates``.
Does NOT write to the DB — the orchestrator persists results via submit_plan.

Tools: ``fetch_discovered_references`` (read-only: real high-performing posts
the user or a prior discovery run saved — cheaper and higher-signal than
search, because it bypasses ranking noise) and ``WebFetch``. Web search
rides along too — the runner appends whichever one this provider can use.
"""

from __future__ import annotations

from typing import Any

from agents.content.prompts import RESEARCH_PILLAR_PROMPT
from agents.content.schema import ContentTool
from agents.core.web_tools import WEB_FETCH_TOOL

RESEARCH_PILLAR_SUBAGENT = "research_pillar"

# Tool names this sub-agent may use, resolved to tool objects by the runner.
RESEARCH_PILLAR_TOOLS: tuple[str, ...] = (
    ContentTool.FETCH_DISCOVERED_REFERENCES.value,
    WEB_FETCH_TOOL,
)


def build_research_pillar_subagent(tools: list[Any], model: Any) -> dict[str, Any]:
    """The ``SubAgent`` spec, with the tool objects and model the runner chose."""
    return {
        "name": RESEARCH_PILLAR_SUBAGENT,
        "description": (
            "Research candidate topics for a single content pillar. Returns a "
            "ranked JSON list of {topic_id, title, angle, sources, confidence}. "
            "No DB writes; the orchestrator persists the result."
        ),
        "system_prompt": RESEARCH_PILLAR_PROMPT,
        "tools": list(tools),
        "model": model,
    }
