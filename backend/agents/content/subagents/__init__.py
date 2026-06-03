"""Content sub-agent definitions consumed by ClaudeAgentOptions(agents=...)."""

from agents.content.subagents.build_slides_html import BUILD_SLIDES_AGENT
from agents.content.subagents.draft_post import DRAFT_POST_AGENT
from agents.content.subagents.research_pillar import RESEARCH_PILLAR_AGENT

__all__ = [
    "BUILD_SLIDES_AGENT",
    "DRAFT_POST_AGENT",
    "RESEARCH_PILLAR_AGENT",
]
