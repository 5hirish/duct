"""research_pillar sub-agent — fan-out topic research for one pillar.

Invoked by the orchestrator via the built-in Agent tool. Runs in an isolated
context (~30K tokens), uses Haiku-class speed, and returns a strict JSON
payload matching agents.content.schema.TopicCandidates. Does NOT write to
the DB — the orchestrator persists results via submit_plan.

Tools allowed: WebSearch, WebFetch, FetchPages (the audit's existing crawl
MCP server is in-process and same-origin-safe).
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from agents.content.prompts import RESEARCH_PILLAR_PROMPT
from agents.models import AgentTool, ModelName

# NOTE: saved TikTok discoveries are consumed by the Content Planner's
# trend_scout sub-agent, not here — planning owns the discovery signal.
RESEARCH_PILLAR_AGENT = AgentDefinition(
    description=(
        "Research candidate topics for a single content pillar. "
        "Returns ranked JSON list of {topic_id, title, angle, sources, "
        "confidence}. No DB writes; orchestrator persists the result."
    ),
    prompt=RESEARCH_PILLAR_PROMPT,
    model=ModelName.CLAUDE_HAIKU_4_5.value,
    tools=[
        AgentTool.WEB_SEARCH.value,
        AgentTool.WEB_FETCH.value,
    ],
)
