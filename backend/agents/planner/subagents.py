"""Sub-agent definitions for the Content Planner orchestrator.

Dispatched via the built-in Agent tool. Each runs in an isolated context on a
Haiku-class model with only WebSearch/WebFetch, and returns strict JSON the
orchestrator folds into the plan. No DB writes — the orchestrator persists.

NOTE: AskUserQuestion is not available inside sub-agents spawned via the Agent
tool (per the Agent SDK), so the config gate stays at the orchestrator level.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from agents.models import AgentTool, ModelName
from agents.planner.prompts import COMPETITOR_ANALYST_PROMPT, TREND_SCOUT_PROMPT
from agents.planner.schema import PlannerTool

TREND_SCOUT_AGENT = AgentDefinition(
    description=(
        "Research current platform trends (sounds, hooks, formats, hashtags, "
        "angles) for the brand's audience + geographies. Returns strict JSON of "
        "trend signals. No DB writes."
    ),
    prompt=TREND_SCOUT_PROMPT,
    model=ModelName.CLAUDE_HAIKU_4_5.value,
    tools=[
        AgentTool.WEB_SEARCH.value,
        AgentTool.WEB_FETCH.value,
        # Read-only: grounds trends in the real high-performing TikTok posts the
        # user saved from the Discover feature — stronger signal than web search
        # alone, and the source of the plan's evidence citations.
        PlannerTool.FETCH_DISCOVERED_REFERENCES.value,
    ],
)

COMPETITOR_ANALYST_AGENT = AgentDefinition(
    description=(
        "Map competitors + market and surface white-space opportunities the "
        "brand can own. Returns strict JSON of competitors/market/opportunities. "
        "No DB writes."
    ),
    prompt=COMPETITOR_ANALYST_PROMPT,
    model=ModelName.CLAUDE_HAIKU_4_5.value,
    tools=[AgentTool.WEB_SEARCH.value, AgentTool.WEB_FETCH.value],
)

__all__ = ["COMPETITOR_ANALYST_AGENT", "TREND_SCOUT_AGENT"]
