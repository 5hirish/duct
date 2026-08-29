"""Shared prompt-assembly scaffolding used by every agent.

The actual analysis protocols / quality briefs stay per-agent (and per-engine
where they legitimately differ) — this module only standardizes the *wrapping*
conventions every agent already converged on: XML-tagged context blocks and the
JSON-output / ``<duct_report>`` instructions.
"""

from __future__ import annotations

# The streaming report tag every Claude-SDK agent wraps its final structured
# payload in (parsed by agents/core/stream.py).
DUCT_REPORT_OPEN = "<duct_report>"
DUCT_REPORT_CLOSE = "</duct_report>"


def xml_block(tag: str, content: str, attrs: dict[str, str] | None = None) -> str:
    """Wrap ``content`` in a labelled XML block, or return '' when empty.

    Standardizes the ``<business_context>`` / ``<data>`` / ``<user_preferences>``
    / ``<content_research>`` convention used across agents so blocks render and
    parse consistently. ``attrs`` adds opening-tag attributes for blocks that
    carry metadata the model should read — ``<project_memory as_of="…">``.
    """
    body = (content or "").strip()
    if not body:
        return ""
    rendered = "".join(
        f' {name}="{str(value).replace(chr(34), "")}"'
        for name, value in (attrs or {}).items()
        if value
    )
    return f"<{tag}{rendered}>\n{body}\n</{tag}>"
