"""build_slides_html sub-agent — stage 2 of the two-stage drafting flow.

Stage 1 (draft_post) returns post metadata WITHOUT slides_html — fast,
parallel-batchable for the whole 30-day plan.

Stage 2 (this) takes an existing post's metadata and produces the
slides_html field on demand. Runs only when the user clicks "Build
slides" on a card, so most plans never pay this cost.

Tools: WebSearch only — slide HTML doesn't need WebFetch or MCP readers,
the metadata brief carries everything the agent needs.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from agents.content.prompts import BUILD_SLIDES_PROMPT
from agents.models import AgentTool, ModelName

BUILD_SLIDES_AGENT = AgentDefinition(
    description=(
        "Build slides_html for an existing post. Returns the same "
        "PostDraft shape received in the brief, with slides_html "
        "populated. No DB writes — orchestrator persists via "
        "submit_post_draft."
    ),
    prompt=BUILD_SLIDES_PROMPT,
    model=ModelName.CLAUDE_SONNET.value,
    tools=[AgentTool.WEB_SEARCH.value],
)
