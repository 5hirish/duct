"""Insight generation goals — unified re-exports for backward compatibility.

Import from the mode-specific modules for new code:
  from agents.insights.goals.paid_ads import InsightGenerationGoal
  from agents.insights.goals.organic_growth import OrganicGrowthGoal

This __init__ re-exports the paid ads goal for backward compatibility with
existing code that imports from agents.insights.goals directly.
"""

from __future__ import annotations

from agents.insights.goals.paid_ads import (
    GOAL_DIRECTIVES,
    GOAL_LABELS,
    GOAL_TOOL_PRIORITIES,
    InsightGenerationGoal,
    goal_heading_text,
    parse_goal_value,
)

__all__ = [
    "InsightGenerationGoal",
    "GOAL_LABELS",
    "GOAL_DIRECTIVES",
    "GOAL_TOOL_PRIORITIES",
    "goal_heading_text",
    "parse_goal_value",
]
