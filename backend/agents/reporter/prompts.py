"""Prompt strings and builders for the generate agent and Gemini synthesis."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from agents.reporter.goals import GOAL_DIRECTIVES, ReportGenerationGoal, goal_heading_text

# Google Ads weekly brief — system instructions (shared by LangChain + Gemini paths).
GOOGLE_ADS_WEEKLY_BRIEF_SYSTEM = """# Google Ads Weekly Brief Template

Use this template after the raw Google Ads data has already been normalized into
the `GoogleAdsBrief` schema contract.

## Job

Turn the structured Google Ads payload into a concise operator report.

The report must answer:

1. What changed?
2. Why does it matter?
3. What should the operator do next?

## Rules

- Use only the normalized payload provided.
- Do not invent platform data.
- Prefer concrete operator language over abstract marketing language.
- Make recommendations specific: scale, pause, monitor, refresh, refine (narrow audience/queries/themes), or investigate.
- Focus on campaign-level decisions, not generic PPC advice.
- If evidence is weak, say so with lower confidence.

## Finding Style

Each finding should include:

- a short title
- 1-3 pieces of evidence from the data
- why it matters commercially
- a clear recommended action
- a confidence level

## Example Tone

Good:

- Brand search is carrying efficiency while two non-brand campaigns are burning spend without enough conversion value to justify their budget.
- Pause Campaign X this week unless conversion quality improves after targeting cleanup.
- CTR is falling, which points to likely creative fatigue rather than a bidding issue alone.

Bad:

- Performance was mixed overall.
- Consider optimizing campaigns.
- Some campaigns may need improvement.
"""

def get_system_prompt(
    *,
    goal: ReportGenerationGoal | None = None,
    custom_goal: str = "",
    context: str = "",
) -> str:
    """System instruction: weekly brief contract + optional goal/context + directives."""
    sections: list[str] = []
    if goal is not None:
        heading = goal_heading_text(goal, custom_goal=custom_goal)
        sections.append(f"## User Goal\n{heading}")
    if context:
        sections.append(f"## Additional Context\n{context}")
    if goal is not None:
        directive = GOAL_DIRECTIVES.get(goal, "")
        if directive:
            sections.append(directive)

    sections.append(GOOGLE_ADS_WEEKLY_BRIEF_SYSTEM)
    return "\n\n".join(sections)


def get_synthesis_user_prompt(
    brief_dict: Dict[str, Any],
    raw_payload: Dict[str, Any],
    *,
    supplementary: Optional[Dict[str, Any]] = None,
) -> str:
    """User message with compact JSON payloads for synthesis.

    When supplementary data is available (from goal-driven tool calls),
    it's included as additional context for richer analysis.
    """
    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]

    parts = [
        "Use only data from the payloads; do not invent metrics.\n",
        f"Deterministic brief JSON:\n{compact_brief}\n",
        f"Raw campaign payload:\n{compact_raw}",
    ]

    if supplementary:
        parts.append(
            "\n\n--- Supplementary Data (goal-specific) ---\n"
            "The following additional data was fetched based on the user's goal. "
            "Use it to provide deeper, more actionable insights. Reference specific "
            "data points from these reports in your evidence fields.\n"
        )
        for tool_name, data in supplementary.items():
            compact = json.dumps(data, separators=(",", ":"), default=str)[:60_000]
            report_type = data.get("report_type", tool_name)
            row_count = data.get("row_count", "?")
            parts.append(f"\n{report_type} ({row_count} rows):\n{compact}")

    return "\n".join(parts)
