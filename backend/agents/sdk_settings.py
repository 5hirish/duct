"""Duct-specific Claude Agent SDK subprocess settings.

Each agent type declares its base network allowlist here. Runners call
sdk_sandbox() to get a SandboxSettings to pass as ClaudeAgentOptions.sandbox,
combined with setting_sources=[] to skip the user's ~/.claude/settings.json.

Adding a new agent type:
  1. Add an entry to _AGENT_EXTRA_DOMAINS with its required non-Anthropic domains.
  2. Call sdk_sandbox(AgentType.<TYPE>, extra_domains=[...]) in the runner.
"""

from __future__ import annotations

from urllib.parse import urlparse

from claude_agent_sdk.types import SandboxSettings

from agents.registry import AgentType

# Every SDK subprocess needs the Anthropic API regardless of agent type.
_ANTHROPIC_DOMAINS = ["api.anthropic.com"]

# Per-agent static domains added on top of Anthropic.
# Request-scoped domains (e.g. the audit target URL) are passed at call time.
_AGENT_EXTRA_DOMAINS: dict[str, list[str]] = {
    AgentType.SEO_AUDIT:   [],   # target domain injected dynamically per request
    AgentType.INSIGHTS:    [],
    AgentType.BLOG_WRITER: [],   # extend when web-search tools are added
    AgentType.RESEARCH:    [],   # extend when web-search tools are added
}


def sdk_sandbox(
    agent_type: str,
    extra_domains: list[str] | None = None,
) -> SandboxSettings:
    """Return a SandboxSettings scoped to what agent_type actually needs.

    agent_type:    one of the AgentType enum values
    extra_domains: request-scoped additions (e.g. the audit target hostname)
    """
    base = _AGENT_EXTRA_DOMAINS.get(agent_type, [])
    combined = [*_ANTHROPIC_DOMAINS, *base, *(extra_domains or [])]
    # Deduplicate while preserving order
    seen: set[str] = set()
    allowed = [d for d in combined if d not in seen and not seen.add(d)]  # type: ignore[func-returns-value]
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "network": {"allowedDomains": allowed},
    }


def domain_from_url(url: str) -> str | None:
    """Extract the registrable hostname from a URL, stripping www. prefix."""
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.") or None
