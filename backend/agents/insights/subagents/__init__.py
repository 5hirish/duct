"""Insights subagents — delegated work that deserves its own context."""

from agents.insights.subagents.verify import VERIFY_SUBAGENT_NAME, build_verify_subagent

__all__ = ["VERIFY_SUBAGENT_NAME", "build_verify_subagent"]
