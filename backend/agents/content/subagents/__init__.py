"""Content sub-agent definitions consumed by ClaudeAgentOptions(agents=...).

build_slides_html was retired when slide HTML moved to a deterministic Python
renderer (agents/content/templates.py); the orchestrator now authors
structured slides and never writes HTML.
"""

from agents.content.subagents.draft_post import DRAFT_POST_AGENT
from agents.content.subagents.research_pillar import RESEARCH_PILLAR_AGENT
from agents.content.subagents.review_post import REVIEW_POST_AGENT

__all__ = [
    "DRAFT_POST_AGENT",
    "RESEARCH_PILLAR_AGENT",
    "REVIEW_POST_AGENT",
]
