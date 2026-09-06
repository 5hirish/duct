"""Content sub-agent specs, as plain dicts the runner hands to ``deepagents``.

Each builder returns a ``SubAgent``-shaped mapping — ``name``, ``description``,
``system_prompt``, ``tools``, ``model`` — which is the harness's declarative
spec and needs no import from it, so this package stays framework-free. The
runner picks which tool objects each sub-agent gets (by ``ContentTool`` name)
and which model it runs on; the spec says what the sub-agent is for.

The orchestrator dispatches them through the harness's ``task`` tool and reads
their final message as the tool result. Neither writes to the DB and neither
generates images — the orchestrator persists through the writer tools.

build_slides_html was retired when slide HTML moved to a deterministic Python
renderer (agents/content/templates.py); the orchestrator now authors
structured slides and never writes HTML.
"""

from agents.content.subagents.draft_post import (
    DRAFT_POST_SUBAGENT,
    DRAFT_POST_TOOLS,
    build_draft_post_subagent,
)
from agents.content.subagents.general_purpose import (
    GENERAL_PURPOSE_SUBAGENT,
    GENERAL_PURPOSE_TOOLS,
    build_general_purpose_subagent,
)
from agents.content.subagents.research_pillar import (
    RESEARCH_PILLAR_SUBAGENT,
    RESEARCH_PILLAR_TOOLS,
    build_research_pillar_subagent,
)

__all__ = [
    "DRAFT_POST_SUBAGENT",
    "DRAFT_POST_TOOLS",
    "GENERAL_PURPOSE_SUBAGENT",
    "GENERAL_PURPOSE_TOOLS",
    "RESEARCH_PILLAR_SUBAGENT",
    "RESEARCH_PILLAR_TOOLS",
    "build_draft_post_subagent",
    "build_general_purpose_subagent",
    "build_research_pillar_subagent",
]
