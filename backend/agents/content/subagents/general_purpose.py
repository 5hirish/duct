"""general-purpose sub-agent — the harness's default, made read-only.

``deepagents`` mounts a sub-agent named ``general-purpose`` on every deep agent
unless the caller supplies one by that name, and its default carries EVERY
tool of the parent. For the content orchestrator that would mean a sub-agent
holding submit_post_draft, generate_image and publish_post — the exact set the
dispatch policy says sub-agents never touch. Supplying this spec keeps the
name (and the model's expectation that a general helper exists) while
choosing its tools: the readers, the scratch of the open web, nothing that
writes a row or spends a Gemini call.
"""

from __future__ import annotations

from typing import Any

from agents.content.schema import ContentTool
from agents.core.web_tools import WEB_FETCH_TOOL

# deepagents' own name for its default sub-agent; supplying this name is what
# stops the harness from adding its every-tool default.
GENERAL_PURPOSE_SUBAGENT = "general-purpose"

GENERAL_PURPOSE_TOOLS: tuple[str, ...] = (
    ContentTool.FETCH_BRAND_CONTEXT.value,
    ContentTool.FETCH_TOPIC_BANK.value,
    ContentTool.FETCH_FORMAT_LIBRARY.value,
    ContentTool.FETCH_AVATAR_LIBRARY.value,
    ContentTool.FETCH_CONTENT_HISTORY.value,
    ContentTool.FETCH_CONTENT_ASSETS.value,
    ContentTool.FETCH_DISCOVERED_REFERENCES.value,
    ContentTool.FETCH_POST.value,
    WEB_FETCH_TOOL,
)


def build_general_purpose_subagent(tools: list[Any], model: Any) -> dict[str, Any]:
    """The ``SubAgent`` spec, with the tool objects and model the runner chose."""
    return {
        "name": GENERAL_PURPOSE_SUBAGENT,
        "description": (
            "General-purpose research helper for a multi-step read-only task: "
            "gathering context across the brand, the libraries, the post history "
            "and the open web, then reporting back. It cannot write, generate "
            "images or publish — the orchestrator does those."
        ),
        "system_prompt": (
            "You are a research helper for a content strategist. Do the task you "
            "were given using only the read tools you have, and return a concise, "
            "factual report the strategist can act on. Do not draft deliverables, "
            "do not invent data you could not read, and do not address the user."
        ),
        "tools": list(tools),
        "model": model,
    }
