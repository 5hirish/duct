"""The jobs a schedule can run (service/schedules.JobKind), as the loop calls them.

They live beside the routes because a scheduled run is a session like any
other and reuses the routes' own helpers to make one: the conversation and
its recorder (``routes.agents._create_session_for``), and the model on the
owner's saved keys (``routes.content._runner_for``). A second copy of either
is the copy that eventually spends the wrong key or loses the transcript.

A scheduled run leaves a conversation behind, with its proposal held on it,
so the person reopens it later and accepts or rejects there: the same
proposal, the same buttons, nothing written until they say so.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from agents.engines import ProviderKeyRequired
from service.lent_keys import borrowed
from service.schedules import (
    ACTIVITY_CATEGORY, Claim, JobKind, JobResult, Outcome, Probe, Reason, note_conversation,
)
from utils.dates import utcnow

logger = logging.getLogger(__name__)

GITHUB = "github"
# The cursor of a repository with no published release yet: its first release
# is then new, where an empty cursor means "never checked" and only records.
NO_RELEASE = "-"

# A scheduled plan's chat turn has nobody to wait for: once the opening turn
# ends, the session closes.
UNATTENDED_IDLE_SECONDS = 1.0
DEFAULT_HORIZON_DAYS = 7


async def content_plan_from_work(claim: Claim) -> JobResult:
    """A plan from shipped work (#561), unattended: the read, the gate, and a
    proposal waiting on its conversation for the person to answer."""
    from agents.content.feed import FeedOptions
    from agents.content.plan_period import requested_period
    from agents.content.v1.runner import close_session
    from agents.core.events import AgentEvent
    from agents.registry import AgentType
    from routes.agents import _create_session_for
    from routes.content import _runner_for

    config = claim.config or {}
    feed = FeedOptions.model_validate(config.get("feed") or {})
    horizon = int(config.get("horizon") or DEFAULT_HORIZON_DAYS)
    session_id = f"schedule-{uuid4().hex}"
    session = _create_session_for(AgentType.TIKTOK_STUDIO, session_id, {
        "mode": "plan_month", "project_id": str(claim.project_id),
    })
    session.user_id = claim.user_id
    session.unattended = True
    events: list[dict] = []

    async def collect(body: dict) -> None:
        events.append(body)

    recorder = getattr(session, "recorder", None)
    emit = recorder.wrap_emit(collect) if recorder is not None else collect
    conversation_id = getattr(session, "conversation_id", None)
    await asyncio.to_thread(_note, claim.schedule_id, conversation_id)
    try:
        try:
            # Saved keys first; else the keys this person's open app lent.
            runner = _runner_for(session_id, borrowed(claim.user_id))
        except ProviderKeyRequired:
            return JobResult(Outcome.SKIPPED, Reason.NO_KEY, conversation_id=conversation_id, retryable=True)
        await runner.run_plan(
            session_id, claim.project_id, emit,
            period=requested_period(utcnow().date(), horizon), feed=feed,
            chat_idle_timeout=UNATTENDED_IDLE_SECONDS,
        )
    finally:
        close_session(session_id)

    cost = sum(float(e.get("cost_usd") or 0) for e in events if e.get("event") == AgentEvent.TOKEN_USAGE)
    failed = next((e for e in events if e.get("event") == AgentEvent.PIPELINE_FAILED), None)
    if failed is not None:
        return JobResult(Outcome.FAILED, str(failed.get("code") or Reason.ERROR), conversation_id=conversation_id,
                         cost_usd=cost, retryable=bool(failed.get("retryable", True)))
    if any(e.get("event") == AgentEvent.PIPELINE_FINISHED and e.get("outcome") == "nothing_new" for e in events):
        return JobResult(Outcome.NOTHING_NEW, conversation_id=conversation_id, cost_usd=cost)
    proposal = getattr(session, "proposal", None)
    if proposal is None:
        return JobResult(Outcome.NO_PROPOSAL, conversation_id=conversation_id, cost_usd=cost)
    feed_days = sum(1 for d in (proposal.days or []) if (d or {}).get("sources"))
    await asyncio.to_thread(_supersede, claim.schedule_id, conversation_id)
    return JobResult(Outcome.PROPOSED, conversation_id=conversation_id, cost_usd=cost,
                     detail={"feed_days": feed_days, "proposal_id": proposal.proposal_id})


async def release_landed(claim: Claim) -> Probe:
    """The on-release check (#563): one GitHub request for the newest release
    of the project's repository, compared with the tag the schedule last saw.
    The first check only records the tag, so a new schedule never plans from
    a release that shipped before it existed."""
    tag = await asyncio.to_thread(_latest_tag, claim.user_id, claim.project_id)
    if tag is None:
        return Probe(fire=False, needs_reason=Reason.NO_REPOSITORY)
    if not claim.cursor:
        return Probe(fire=False, cursor=tag)
    return Probe(fire=tag != claim.cursor and tag != NO_RELEASE, cursor=tag)


def _latest_tag(user_id, project_id) -> str | None:
    """The newest release tag, NO_RELEASE when the repository has none, or None
    when no repository is bound for this project. GitHub refusing raises, and
    the loop counts that as a quiet hour."""
    from db.session import get_session as db_session
    from service.connector_access import STATUS_BOUND, get_data_source, resolve_read_credentials
    from service.github.fetch import latest_release_tag

    with next(db_session()) as db:
        source = get_data_source(db, GITHUB, user_id=user_id, project_id=project_id)
        if source is None or source.status != STATUS_BOUND or not source.account_id:
            return None
        creds = resolve_read_credentials(
            db, user_id=user_id, project_id=project_id, connector_type=GITHUB, account_id=source.account_id,
        )
    if not creds:
        return None
    return latest_release_tag({**creds, "repo": source.account_id}) or NO_RELEASE


def _supersede(schedule_id, conversation_id) -> None:
    """One open proposal per schedule: the run before this one, if its
    proposal is still unanswered, is released and its thread told why. Kept
    quiet on failure; a second open proposal is a nuisance, not a loss."""
    if conversation_id is None:
        return
    from sqlmodel import select

    from agents.content.persistence import append_event
    from agents.content.plan_proposal import SUPERSEDED, held_proposal, hold_proposal
    from agents.core.events import EventKind
    from db.session import get_session as db_session
    from models.activity import ActivityLog

    try:
        with next(db_session()) as db:
            rows = db.exec(
                select(ActivityLog)
                .where(ActivityLog.category == ACTIVITY_CATEGORY, ActivityLog.target_id == str(schedule_id),
                       ActivityLog.conversation_id.is_not(None))
                .order_by(ActivityLog.created_at.desc())
                .limit(20)
            ).all()
            previous = next((r for r in rows if (r.data or {}).get("outcome") == Outcome.PROPOSED
                             and r.conversation_id != conversation_id), None)
            if previous is None:
                return
            held = held_proposal(db, previous.conversation_id)
            if held is None:
                return
            hold_proposal(db, previous.conversation_id, None)
            append_event(db, previous.conversation_id, EventKind.PLAN_DECISION, {
                "decision": SUPERSEDED,
                "proposal_id": held.proposal_id,
                "plan_id": None,
                "name": held.name,
                "superseded_by": str(conversation_id),
            })
    except Exception:  # noqa: BLE001
        logger.warning("schedules: could not supersede the last proposal of %s", schedule_id, exc_info=True)


def _note(schedule_id, conversation_id) -> None:
    if conversation_id is None:
        return
    from db.session import get_session as db_session

    with next(db_session()) as db:
        note_conversation(db, schedule_id, conversation_id)


JOBS = {
    JobKind.CONTENT_PLAN_FROM_WORK: content_plan_from_work,
}

# Each job's event check, for a schedule on an event cadence (on_release).
PROBES = {
    JobKind.CONTENT_PLAN_FROM_WORK: release_landed,
}
