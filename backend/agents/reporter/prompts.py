"""Dynamic prompt builders for the generate agent.

Follows the nomadtools messages.py pattern: functions accept parameters
and return formatted prompt strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_BRIEF_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "briefs" / "templates" / "google_ads_weekly_brief.md"
)


def get_system_prompt(goal: str = "", context: str = "") -> str:
    """Build the system instruction from the brief template + goal/context.

    Goal and context are prepended so the LLM weights its analysis
    toward the user's intent.
    """
    try:
        base_template = _BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        base_template = (
            "You are a paid-ads analyst. Turn the provided Google Ads data "
            "into a concise operator report with narrative, highlights, risks, "
            "and recommended actions."
        )

    sections: list[str] = []
    if goal:
        sections.append(f"## User Goal\n{goal}")
    if context:
        sections.append(f"## Additional Context\n{context}")
    sections.append(base_template)
    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    brief_dict: Dict[str, Any],
    raw_payload: Dict[str, Any],
) -> str:
    """Build the user message containing the data payloads for synthesis."""
    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]
    return (
        "You output ONLY fields: narrative (verdict, summary, operator_takeaway), "
        "highlights, risks, recommended_actions. Match the JSON schema exactly. "
        "Use only data from the payloads; do not invent metrics.\n\n"
        f"Deterministic brief JSON:\n{compact_brief}\n\n"
        f"Raw campaign payload:\n{compact_raw}"
    )
