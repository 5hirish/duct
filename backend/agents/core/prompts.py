"""Shared prompt-assembly scaffolding used by every agent.

The actual analysis protocols / quality briefs stay per-agent (and per-engine
where they legitimately differ) — this module only standardizes the *wrapping*
conventions every agent already converged on: XML-tagged context blocks and the
JSON-output / ``<duct_report>`` instructions.
"""

from __future__ import annotations

# The streaming report tag every Claude-SDK agent wraps its final structured
# payload in (parsed by agents/core/report_stream.py).
DUCT_REPORT_OPEN = "<duct_report>"
DUCT_REPORT_CLOSE = "</duct_report>"

JSON_OUTPUT_INSTRUCTION = (
    "Output ONLY a single valid JSON object — no markdown fences, no preamble, "
    "no trailing text."
)

DUCT_REPORT_CONVENTION = (
    f"When your result is ready, emit it as a single JSON object wrapped in "
    f"{DUCT_REPORT_OPEN} … {DUCT_REPORT_CLOSE} tags. Put nothing else inside the "
    f"tags — no fences, no commentary."
)


def xml_block(tag: str, content: str) -> str:
    """Wrap ``content`` in a labelled XML block, or return '' when empty.

    Standardizes the ``<business_context>`` / ``<data>`` / ``<user_preferences>``
    / ``<content_research>`` convention used across agents so blocks render and
    parse consistently.
    """
    body = (content or "").strip()
    if not body:
        return ""
    return f"<{tag}>\n{body}\n</{tag}>"
