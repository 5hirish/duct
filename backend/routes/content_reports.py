"""The Analytics tab's report: one agent run, stored for a day, refreshed on ask.

``GET /content/analytics/report`` answers three questions at once — which
templates exist, which of this project's sources can feed the chosen one,
and what the latest report says (with whether it is stale, or being written
right now). ``POST`` starts a run on the sources the person ticked. Nothing
regenerates on its own: a report is a model run on the person's own key, so
the day-old copy is served with ``stale: true`` and the Refresh button is
the only thing that spends again.

The run is the insights agent (``AutonomousInsightsRunner.run_report``),
unattended, writing the ``GrowthReport`` the app draws
(``agents/insights/report.py``). It stores through ``ArtifactPersister`` as
one artifact group per project and template, so a refresh is the next
version and the library keeps the history.

In process, one API worker: a live run is a task in ``_runs``; a second
request for the same project and template while it runs joins it rather
than starting another. A failure stays on the entry until the next start,
so the tab can say what went wrong after the page it happened on is gone.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import Session

from agents.core.errors import error_payload
from agents.insights.report import ARTIFACT_KIND, report_artifact_version
from agents.insights.report_templates import (
    DEFAULT_TEMPLATE,
    KIND_MCP,
    ReportTemplate,
    SourceState,
    choose_sources,
    source_states,
    template as template_for,
    templates_as_dicts,
)
from agents.registry import AgentType
from db.session import get_session as db_session
from models.artifact import Artifact
from models.auth import User
from models.project import Project
from service.analytics import capture_event
from service.auth import get_current_user, get_user_provider_keys
from service.membership import get_project_for_user
from utils.dates import last_n_days, now_iso, utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["content"], dependencies=[Depends(get_current_user)])

# A report older than this is served, flagged stale; the tab offers Refresh
# and never regenerates by itself.
REPORT_TTL = timedelta(hours=24)
# The window a report covers, ending yesterday like every insights pull.
REPORT_WINDOW_DAYS = 30
# How many stored reports to look through for the template's latest. One
# project writes a handful of templates; the JSON column is not indexed by
# template, so this is a bounded scan rather than a filter.
_RECENT_REPORTS = 60

REPORT_INVALID = "report_invalid"
NO_SOURCES = (
    "Nothing to read from yet. Connect Search Console, Google Analytics, a scheduler or an "
    "analytics MCP server, then pick the sources to include."
)


@dataclass
class _Run:
    started_at: str
    sources: list[str]
    task: asyncio.Task | None = None
    error: dict | None = None
    artifact_id: str = ""
    # Set by the task itself as it ends, success or failure. Not derived from
    # the task object: a process that loses its loop (a test client, a
    # shutdown) leaves a task "done" without having finished anything.
    finished: bool = False

    @property
    def live(self) -> bool:
        return self.task is not None and not self.finished


_runs: dict[tuple[UUID, str], _Run] = {}


class ReportRequest(BaseModel):
    project_id: UUID
    template: str = DEFAULT_TEMPLATE
    #: Source ids to include; empty means every ready source the template takes.
    sources: list[str] = Field(default_factory=list)


def _template_or_422(template_id: str) -> ReportTemplate:
    tmpl = template_for(template_id)
    if tmpl is None:
        known = ", ".join(t["id"] for t in templates_as_dicts())
        raise HTTPException(422, f"Unknown report template {template_id!r}. One of: {known}.")
    return tmpl


def _latest_report(db: Session, project_id: UUID, template_id: str) -> Artifact | None:
    rows = db.execute(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.kind == ARTIFACT_KIND)
        .order_by(Artifact.created_at.desc())
        .limit(_RECENT_REPORTS)
    ).scalars().all()
    return next((r for r in rows if (r.meta or {}).get("template") == template_id), None)


def _is_stale(row: Artifact) -> bool:
    return utcnow() - row.created_at > REPORT_TTL


def _report_out(row: Artifact | None) -> dict | None:
    if row is None:
        return None
    return {
        "artifact_id": str(row.id),
        "group_id": str(row.group_id),
        "version": row.version,
        "title": row.title,
        "generated_at": row.created_at.isoformat(),
        "stale": _is_stale(row),
        "stale_after": (row.created_at + REPORT_TTL).isoformat(),
        "template": (row.meta or {}).get("template", ""),
        "report": row.structured_json or {},
    }


def _state(db: Session, *, user_id: UUID, proj: Project, tmpl: ReportTemplate) -> dict[str, Any]:
    states = source_states(db, user_id=user_id, project=proj)
    run = _runs.get((proj.id, tmpl.id))
    return {
        "template": tmpl.as_dict(),
        "templates": templates_as_dicts(),
        "sources": [s.as_dict() for s in states if s.source.id in tmpl.sources],
        "report": _report_out(_latest_report(db, proj.id, tmpl.id)),
        "generating": bool(run and run.live),
        "started_at": run.started_at if run and run.live else None,
        "run_sources": run.sources if run else [],
        "error": None if run is None or run.live else run.error,
        "ttl_hours": int(REPORT_TTL.total_seconds() // 3600),
    }


@router.get("/content/analytics/report")
def get_analytics_report(
    project_id: UUID,
    template: str = DEFAULT_TEMPLATE,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    """The latest report for the template, the sources that can feed it, and
    whether a run is under way. Never starts one: that is the POST, and the
    difference is who pays for a model run and when."""
    proj = get_project_for_user(project_id, user, db)
    tmpl = _template_or_422(template)
    return _state(db, user_id=user.id, proj=proj, tmpl=tmpl)


@router.post("/content/analytics/report", status_code=202)
async def generate_analytics_report(
    body: ReportRequest,
    user: User = Depends(get_current_user),
    user_keys: dict = Depends(get_user_provider_keys),
    db: Session = Depends(db_session),
) -> dict:
    """Start writing the report on the sources chosen, or join the run that
    is already writing it. The model and key resolve here, in the request,
    so a missing provider key is the 402 the browser knows how to act on
    rather than a failure the tab learns about later."""
    from agents.insights.setup import InsightsSetupError, resolve_run

    proj = get_project_for_user(body.project_id, user, db)
    tmpl = _template_or_422(body.template)
    key = (proj.id, tmpl.id)
    existing = _runs.get(key)
    if existing is not None and existing.live:
        return _state(db, user_id=user.id, proj=proj, tmpl=tmpl)

    states = source_states(db, user_id=user.id, project=proj)
    chosen = choose_sources(tmpl, states, body.sources)
    if not chosen:
        raise HTTPException(400, NO_SOURCES)

    try:
        run = resolve_run(user_id=user.id, project_id=proj.id, user_keys=user_keys)
    except InsightsSetupError as exc:
        raise HTTPException(500, str(exc)) from exc
    if run.project_id is None:
        raise HTTPException(404, "Project not found")

    latest = _latest_report(db, proj.id, tmpl.id)
    entry = _Run(started_at=now_iso(), sources=[s.source.id for s in chosen])
    entry.task = asyncio.create_task(
        _finishing(
            entry,
            run=run,
            user_id=user.id,
            user_keys=user_keys,
            proj_id=proj.id,
            tmpl=tmpl,
            chosen=chosen,
            group_id=latest.group_id if latest is not None else None,
            start_version=latest.version if latest is not None else 0,
        )
    )
    _runs[key] = entry
    capture_event("analytics_report_requested", {
        "template": tmpl.id, "sources": entry.sources, "refresh": latest is not None,
    })
    return _state(db, user_id=user.id, proj=proj, tmpl=tmpl)


async def _finishing(entry: _Run, **kwargs: Any) -> None:
    """Run the report and mark the entry finished however it ends."""
    try:
        await _generate(entry, **kwargs)
    finally:
        entry.finished = True


async def _generate(
    entry: _Run,
    *,
    run: Any,
    user_id: UUID,
    user_keys: dict,
    proj_id: UUID,
    tmpl: ReportTemplate,
    chosen: list[SourceState],
    group_id: UUID | None,
    start_version: int,
) -> None:
    """The run itself, off the request. Everything per-project is assembled
    here and rides in the user turn, the same blocks the chat session gets."""
    from agents.core.context import business_context_from_project, format_business_context
    from agents.core.voice import user_context_block
    from agents.insights.prompts.autonomous import report_plan_block
    from agents.insights.setup import data_sources_block, memory_blocks
    from agents.insights.v1.runner import AutonomousInsightsRunner
    from service.artifact_store import ArtifactPersister
    from service.profile import get_profile

    date_from, date_to = last_n_days(REPORT_WINDOW_DAYS)
    try:
        with next(db_session()) as db:
            proj = db.get(Project, proj_id)
            business = format_business_context(business_context_from_project(proj)) if proj else ""
        persister = ArtifactPersister(
            project_id=proj_id,
            user_id=user_id,
            agent_type=str(AgentType.INSIGHTS),
            kind=ARTIFACT_KIND,
            api_key=run.summary_key,
            provider=run.provider,
            model=run.model,
            group_id=group_id,
            adapt=report_artifact_version,
            lent_keys=user_keys,
        )

        async def _silent(_event: dict) -> None:
            return None

        emit = persister.wrap_emit(_silent)
        memory = await memory_blocks(run, user_id=user_id, query=tmpl.question, emit=emit)
        runner = AutonomousInsightsRunner(
            api_key=run.api_key,
            provider=run.provider,
            model=run.model,
            verify_provider=run.verify_provider,
            verify_model=run.verify_model,
            verify_api_key=run.verify_api_key,
        )
        result = await runner.run_report(
            emit,
            prompt=(
                f"Write the {tmpl.label} report for {date_from} to {date_to}: {tmpl.question}"
            ),
            report_plan=report_plan_block(tmpl, chosen, date_from=date_from, date_to=date_to),
            template=tmpl.id,
            business_context=business,
            user_context=user_context_block(get_profile(user_id)),
            memory=memory,
            data_sources=data_sources_block(run, user_id=user_id),
            project_id=proj_id,
            user_id=user_id,
            connected_tools=any(s.source.kind == KIND_MCP for s in chosen),
            start_version=start_version,
        )
        if result.report is None:
            entry.error = {
                "code": REPORT_INVALID,
                "retryable": True,
                "error": "The agent could not write a report the tab can draw. Try again.",
                "problems": result.problems[:6],
            }
            logger.warning("analytics report: no valid report for %s/%s — %s", proj_id, tmpl.id, result.problems[:3])
        else:
            entry.artifact_id = str(persister.last_artifact_id or "")
        capture_event("analytics_report_generated", {
            "template": tmpl.id,
            "ok": result.report is not None,
            "repaired": result.repaired,
            "blocks": len((result.report or {}).get("blocks", [])),
            "provider": getattr(run.provider, "value", str(run.provider)),
        })
    except Exception as exc:  # noqa: BLE001 — the task's failure is the tab's error, never a crash
        logger.exception("analytics report: run failed for %s/%s", proj_id, tmpl.id)
        entry.error = error_payload(exc)


def _reset_runs_for_tests() -> None:
    _runs.clear()


__all__ = ["REPORT_TTL", "REPORT_WINDOW_DAYS", "ReportRequest", "router"]

