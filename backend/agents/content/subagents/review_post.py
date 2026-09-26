"""review_post sub-agent — scores the current post before it is published.

Invoked by the orchestrator through the ``task`` tool when the user asks for a
review, or is about to publish. It exists as a sub-agent rather than a step
the orchestrator does itself for one reason: the orchestrator wrote the post,
and a critic grading its own draft is the inflated score this review is meant
to replace. A fresh context reads only what shipped.

Returns strict JSON — the six marker scores — and writes nothing: the
orchestrator persists them through ``submit_assessment``, the same hand-back
draft_post uses, so "sub-agents cannot write" stays structural. That also
means no ``render_slide`` (it saves a render asset); the orchestrator puts
what it saw on the rendered slides into the brief instead, and the reviewer
judges visuals from that plus the image prompts.

Runs on the run's own model: judgement is the whole value here, the same
argument that keeps draft_post off the cheaper sibling.
"""

from __future__ import annotations

from typing import Any

from agents.content.prompts import REVIEW_POST_PROMPT
from agents.content.schema import ContentTool

REVIEW_POST_SUBAGENT = "review_post"

# Tool names this sub-agent may use, resolved to tool objects by the runner.
REVIEW_POST_TOOLS: tuple[str, ...] = (
    ContentTool.FETCH_POST.value,
    ContentTool.FETCH_BRAND_CONTEXT.value,
)


def build_review_post_subagent(tools: list[Any], model: Any) -> dict[str, Any]:
    """The ``SubAgent`` spec, with the tool objects and model the runner chose."""
    return {
        "name": REVIEW_POST_SUBAGENT,
        "description": (
            "Score the current post before publishing on six quality markers "
            "(hook, momentum, save-worthiness, shareability, visuals, call to "
            "action). Put what you saw on the rendered slides in the brief. "
            "Returns strict JSON of the scores; no DB writes — persist them "
            "with submit_assessment."
        ),
        "system_prompt": REVIEW_POST_PROMPT,
        "tools": list(tools),
        "model": model,
    }
