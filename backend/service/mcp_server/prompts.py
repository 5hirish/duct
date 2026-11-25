"""MCP prompts: Duct's playbooks, served to the person's own agent.

Filled in by the reports work. ``PROMPTS`` maps a prompt name to its
``protocol.Prompt``.
"""

from __future__ import annotations

from service.mcp_server.protocol import Prompt

PROMPTS: dict[str, Prompt] = {}
