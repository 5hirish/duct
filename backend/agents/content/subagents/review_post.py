"""review_post sub-agent — scores the current post before publishing.

Invoked by the orchestrator via the built-in Agent tool when the user asks to
review or publish a post. Runs in an isolated context, Sonnet-class — this is
multimodal subjective critique (hook / virality / resonance + caption legibility
read off the rendered slides), the review counterpart of draft_post (also
Sonnet). research_pillar/audit use Haiku only because they do structured
fact-extraction; judgement quality is the whole value here.

It finalises its own review by calling submit_assessment (which re-runs the
sanity checks, computes the overall score, persists last_assessment, and emits
PUBLISH_ASSESSMENT to the panel), then returns a one-line summary. This is the
single narrow exception to "sub-agents don't write the DB" — the write is
self-contained and idempotent (no orchestrator-side merge), and calling it here
(rather than handing markers back for the orchestrator to re-submit) removes a
hop where the panel could silently never paint.

Tools allowed: fetch_post + check_post_sanity (read the post + its completeness),
render_slide (SEE the composed frames for a CAROUSEL's visual_quality marker),
understand_video (WATCH a VIDEO post's own generated clip — target='generated' — to
score it on what it ACTUALLY contains), and submit_assessment (finalise). It shares
the session's MCP server, so render_slide resolves through the same
ContentSession.render_futures round-trip and submit_assessment emits through the
same SSE queue the orchestrator uses.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from agents.content.prompts import REVIEW_POST_PROMPT
from agents.content.schema import ContentTool
from agents.models import ModelName

REVIEW_POST_AGENT = AgentDefinition(
    description=(
        "Score the current post before publishing on six quality markers "
        "(hook, momentum, save-worthiness, shareability, visual, CTA). For a CAROUSEL "
        "it views the rendered slides; for a VIDEO it WATCHES the generated clip "
        "(understand_video). Finalises via submit_assessment (emits the review panel) "
        "and returns a one-line summary."
    ),
    prompt=REVIEW_POST_PROMPT,
    model=ModelName.CLAUDE_SONNET_4_6.value,
    tools=[
        ContentTool.FETCH_POST.value,
        ContentTool.CHECK_POST_SANITY.value,
        ContentTool.RENDER_SLIDE.value,
        ContentTool.UNDERSTAND_VIDEO.value,
        ContentTool.SUBMIT_ASSESSMENT.value,
    ],
)
