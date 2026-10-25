"""Insights subagents — delegated work that deserves its own context."""

from agents.insights.subagents.general_purpose import (
    GENERAL_PURPOSE_SUBAGENT,
    GENERAL_PURPOSE_TOOLS,
    build_general_purpose_subagent,
    pick_read_tools,
)
from agents.insights.subagents.verify import VERIFY_SUBAGENT_NAME, build_verify_subagent

__all__ = [
    "GENERAL_PURPOSE_SUBAGENT",
    "GENERAL_PURPOSE_TOOLS",
    "VERIFY_SUBAGENT_NAME",
    "build_general_purpose_subagent",
    "build_verify_subagent",
    "pick_read_tools",
]
