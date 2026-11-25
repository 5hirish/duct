"""MCP prompts: Duct's playbooks, served to the person's own agent.

A prompt is the same text as a tool (``start_run``), offered where a client
shows prompts as slash commands (Claude Code, Gemini CLI). A client that lists
no prompts loses nothing: the tool reaches the same playbook.
"""

from __future__ import annotations

from uuid import UUID

from service.mcp_server import scopes as mcp_scopes
from service.mcp_server.playbook import build_playbook
from service.mcp_server.protocol import Caller, Prompt, PromptArgument, ToolError


def _insights_brief(args: dict[str, str], caller: Caller) -> str:
    try:
        project_id = UUID(args.get("project_id", "").strip())
    except ValueError:
        raise ToolError("project_id is not an id. Call list_projects for one.", code="validation")
    return build_playbook(caller, project_id, args.get("goal", ""))["playbook"]


PROMPTS: dict[str, Prompt] = {
    prompt.name: prompt
    for prompt in (
        Prompt(
            name="insights_brief",
            title="Duct brief",
            description="Write a growth brief for one Duct project with Duct's playbook, on your own model.",
            arguments=(
                PromptArgument("project_id", "The Duct project, from list_projects.", required=True),
                PromptArgument("goal", "What the brief should answer. Empty for this week's growth brief."),
            ),
            render=_insights_brief,
            scope=mcp_scopes.REPORTS,
        ),
    )
}
