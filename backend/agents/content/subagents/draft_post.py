"""draft_post sub-agent — produces one finished PostDraft per dispatch.

Invoked by the orchestrator via the built-in Agent tool. Runs in an isolated
context (~30K tokens), Sonnet-class for creative quality. Returns a strict
JSON payload matching agents.content.schema.PostDraft (slides_html, caption,
hashtags, hook, image_prompts). Does NOT write to the DB — the orchestrator
calls submit_post_draft to persist.

Tools allowed: WebSearch (light fact-check, max 3 queries) and the
mcp__duct_content__fetch_format_library reader (so the sub-agent can pull
the exact pixel/spec table for the chosen format without depending on the
orchestrator's brief to inline it).
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from agents.content.prompts import DRAFT_POST_PROMPT
from agents.models import AgentTool, ModelName

DRAFT_POST_AGENT = AgentDefinition(
    description=(
        "Draft a single finished post (slides_html, caption, hashtags, hook, "
        "image_prompts) for one Day. Returns strict JSON matching PostDraft. "
        "No DB writes; orchestrator persists via submit_post_draft."
    ),
    prompt=DRAFT_POST_PROMPT,
    model=ModelName.CLAUDE_SONNET.value,
    tools=[
        AgentTool.WEB_SEARCH.value,
        "mcp__duct_content__fetch_format_library",
    ],
)
