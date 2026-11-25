"""MCP tools for the ``reports`` scope: read the artifact library, start a
brief from Duct's playbook, and save the brief the agent wrote.

The agent writes the brief on its own model (``playbook.py``); Duct keeps it
in the same library as briefs its own agent writes (``kind="brief"``,
``service/artifact_store``), so it is versioned, listed on the desk, and
recorded in memory and the activity feed like any other.

An artifact addressed by its own id is checked through its row's project,
never a project id from the arguments: a caller must not vouch for itself.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from agents.insights.brief import ARTIFACT_KIND, CONTENT_TYPE, sniff_format
from agents.registry import AgentType
from models.artifact import Artifact
from service.mcp_server import scopes as mcp_scopes
from service.mcp_server.common import app_link, member_project, record_write
from service.mcp_server.playbook import AGENTS, build_playbook
from service.mcp_server.protocol import Caller, Tool, ToolError
from service.ratelimit import RateLimit

# What get_artifact returns of one version. A brief is a few thousand
# characters; an audit's HTML can be far more, and the model's context is the
# person's, not ours.
MAX_CONTENT_CHARS = 25_000
LIST_LIMIT_MAX = 50

TITLE_MAX_CHARS = 140
BODY_MIN_CHARS = 200
BODY_MAX_CHARS = 60_000
MAX_SOURCES = 20

# A brief is a deliberate act; dozens an hour is a loop.
_SUBMIT_LIMIT = RateLimit(limit=20, window_seconds=3600.0)

NOT_FOUND_ARTIFACT = "No artifact with that id among your projects. Call list_artifacts."


def _artifact_url(row: Artifact) -> str:
    return app_link(f"/artifacts/{row.id}")


def _summary(row: Artifact, versions: int | None = None) -> dict[str, Any]:
    out = {
        "artifact_id": str(row.id),
        "kind": row.kind,
        "title": row.title,
        "version": row.version,
        "content_type": row.content_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.summary or "",
        "url": _artifact_url(row),
    }
    if versions is not None:
        out["version_count"] = versions
    return out


# -- list_artifacts ------------------------------------------------------------

class ListArtifactsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID = Field(description="A project_id from list_projects.")
    kind: str = Field(default="", description="Only this kind: brief, growth-report or report (an audit). Empty for all.")
    limit: int = Field(default=20, ge=1, le=LIST_LIMIT_MAX)


def list_artifacts(args: ListArtifactsArgs, caller: Caller) -> dict[str, Any]:
    from service.artifact_store import latest_versions

    project = member_project(args.project_id, caller)
    stmt = select(Artifact).where(Artifact.project_id == project.id)
    if args.kind.strip():
        stmt = stmt.where(Artifact.kind == args.kind.strip())
    rows = list(caller.session.execute(stmt.order_by(Artifact.created_at.desc())).scalars())
    counts: dict[UUID, int] = {}
    for row in rows:
        counts[row.group_id] = counts.get(row.group_id, 0) + 1
    latest = latest_versions(rows)[: args.limit]
    return {
        "project_id": str(project.id),
        "artifacts": [_summary(row, counts[row.group_id]) for row in latest],
    }


# -- get_artifact --------------------------------------------------------------

class GetArtifactArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: UUID = Field(description="An artifact_id from list_artifacts.")
    version: int | None = Field(default=None, ge=1, description="A version number; the newest when left out.")


def _readable(artifact_id: UUID, caller: Caller) -> Artifact:
    row = caller.session.get(Artifact, artifact_id)
    if row is None:
        raise ToolError(NOT_FOUND_ARTIFACT, code="not_found")
    try:
        member_project(row.project_id, caller)
    except ToolError:
        raise ToolError(NOT_FOUND_ARTIFACT, code="not_found")
    return row


def get_artifact(args: GetArtifactArgs, caller: Caller) -> dict[str, Any]:
    from service.artifact_store import artifact_text_content

    row = _readable(args.artifact_id, caller)
    if args.version is not None and args.version != row.version:
        other = caller.session.execute(
            select(Artifact).where(Artifact.group_id == row.group_id, Artifact.version == args.version)
        ).scalars().first()
        if other is None:
            raise ToolError(f"This artifact has no version {args.version}.", code="not_found")
        row = other
    content = artifact_text_content(row)
    return {
        **_summary(row),
        "content": content[:MAX_CONTENT_CHARS],
        "truncated": len(content) > MAX_CONTENT_CHARS,
    }


# -- start_run -----------------------------------------------------------------

class StartRunArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID = Field(description="A project_id from list_projects.")
    goal: str = Field(
        default="",
        max_length=1000,
        description="What the person wants from the brief, in their words. Empty for a weekly growth brief.",
    )
    agent: str = Field(default="insights", description=f"Which playbook. One of: {', '.join(AGENTS)}.")


def start_run(args: StartRunArgs, caller: Caller) -> dict[str, Any]:
    return build_playbook(caller, args.project_id, args.goal, args.agent)


# -- submit_brief --------------------------------------------------------------

class SubmitBriefArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID = Field(description="The project the brief is about.")
    title: str = Field(description="What the brief concluded, not 'Growth brief'.")
    markdown: str = Field(description="The whole brief: markdown, or a complete HTML page.")
    period_start: str = Field(default="", description="First day the brief's numbers cover, YYYY-MM-DD.")
    period_end: str = Field(default="", description="Last day the brief's numbers cover, YYYY-MM-DD.")
    sources: list[str] = Field(
        default_factory=list,
        description="The connectors or entities the numbers came from, e.g. ga4, gsc, stripe.",
    )

    @field_validator("title", "markdown", "period_start", "period_end")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


def _problems(args: SubmitBriefArgs) -> list[str]:
    problems: list[str] = []
    if not args.title:
        problems.append("title is empty: give the brief a title that says what it concluded")
    elif len(args.title) > TITLE_MAX_CHARS:
        problems.append(f"title is {len(args.title)} characters; keep it under {TITLE_MAX_CHARS}")
    if len(args.markdown) < BODY_MIN_CHARS:
        problems.append(
            f"the brief is {len(args.markdown)} characters; a brief needs its decision, findings, actions "
            "and what could not be checked"
        )
    elif len(args.markdown) > BODY_MAX_CHARS:
        problems.append(f"the brief is {len(args.markdown)} characters; cut it under {BODY_MAX_CHARS}")
    dates: dict[str, date] = {}
    for name in ("period_start", "period_end"):
        value = getattr(args, name)
        if value:
            try:
                dates[name] = date.fromisoformat(value)
            except ValueError:
                problems.append(f"{name} {value!r} is not a date; use YYYY-MM-DD")
    if len(dates) == 2 and dates["period_start"] > dates["period_end"]:
        problems.append("period_start is after period_end")
    if len(args.sources) > MAX_SOURCES:
        problems.append(f"name at most {MAX_SOURCES} sources")
    return problems


def _existing_brief(caller: Caller, project_id: UUID, title: str, content_type: str) -> Artifact | None:
    """The brief this one revises: same project, same title, same format.
    Re-running a playbook on the same question then adds a version rather
    than a second card on the desk."""
    from service.artifact_store import latest_versions

    rows = list(caller.session.execute(
        select(Artifact).where(
            Artifact.project_id == project_id,
            Artifact.kind == ARTIFACT_KIND,
            Artifact.title == title,
        )
    ).scalars())
    heads = [r for r in latest_versions(rows) if r.content_type == content_type]
    return heads[0] if heads else None


def submit_brief(args: SubmitBriefArgs, caller: Caller) -> dict[str, Any]:
    from service.artifact_store import create_artifact_group, revise_artifact

    project = member_project(args.project_id, caller)
    problems = _problems(args)
    if problems:
        raise ToolError(
            "The brief was not saved. Fix and submit again: " + "; ".join(problems) + ".", code="validation"
        )
    allowed, retry_after = _SUBMIT_LIMIT.allow(str(caller.user.id))
    if not allowed:
        raise ToolError(
            f"Too many briefs in a short time. Try again in {int(retry_after) + 1} seconds.", code="rate_limited"
        )

    # The bytes decide the format, as for a brief Duct's own agent writes
    # (agents/insights/brief.py): an HTML page is never served as markdown.
    content_type = CONTENT_TYPE[sniff_format(args.markdown)]
    label = f"From {caller.token.name}"
    head = _existing_brief(caller, project.id, args.title, content_type)
    if head is not None:
        row = revise_artifact(caller.session, head, content=args.markdown, label=label, user_id=caller.user.id)
    else:
        row = create_artifact_group(
            caller.session,
            project_id=project.id,
            user_id=caller.user.id,
            agent_type=str(AgentType.INSIGHTS),
            kind=ARTIFACT_KIND,
            content_type=content_type,
            title=args.title,
            content=args.markdown,
            label=label,
        )
    record_write(
        caller,
        project_id=project.id,
        category="artifact",
        action="artifact.submitted",
        summary=f"Saved the brief “{args.title}” (v{row.version})",
        target_type="artifact",
        target_id=str(row.id),
        data={
            "group_id": str(row.group_id),
            "version": row.version,
            "period_start": args.period_start,
            "period_end": args.period_end,
            "sources": [s.strip()[:60] for s in args.sources if s.strip()],
        },
    )
    return {
        "artifact_id": str(row.id),
        "version": row.version,
        "title": row.title,
        "url": _artifact_url(row),
        "saved_as": "a new version of an earlier brief" if row.version > 1 else "a new brief",
    }


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="list_artifacts",
        title="List a project's briefs and reports",
        description=(
            "The project's library, newest first: briefs, growth reports and audits, each with its "
            "title, version count, summary and a link. Read an earlier one with get_artifact before "
            "repeating its analysis."
        ),
        args=ListArtifactsArgs,
        run=list_artifacts,
        read_only=True,
        scope=mcp_scopes.REPORTS,
    ),
    Tool(
        name="get_artifact",
        title="Read a brief or report",
        description="One artifact's content as stored (markdown, HTML or JSON), the newest version unless you name one.",
        args=GetArtifactArgs,
        run=get_artifact,
        read_only=True,
        scope=mcp_scopes.REPORTS,
    ),
    Tool(
        name="start_run",
        title="Start a Duct brief",
        description=(
            "Duct's playbook for an insights brief on this project: Duct's own instructions for the "
            "job, adapted to the tools you have here, and the project's context (business, profile, "
            "memory, connected sources). Call it first when the person asks for a brief or an "
            "analysis, then follow it. Duct runs no model for this; you do the reasoning."
        ),
        args=StartRunArgs,
        run=start_run,
        read_only=True,
        scope=mcp_scopes.REPORTS,
    ),
    Tool(
        name="submit_brief",
        title="Save a brief to Duct",
        description=(
            "Save the brief you wrote to the project's library in Duct, where the person reads, "
            "shares and compares it. A brief with the same title adds a version. If it comes back "
            "with problems, fix them and submit again. Returns the link to give the person."
        ),
        args=SubmitBriefArgs,
        run=submit_brief,
        read_only=False,
        scope=mcp_scopes.REPORTS,
    ),
)
