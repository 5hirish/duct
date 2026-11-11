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
from service.schedules import Claim, JobKind, JobResult, Outcome, Reason, note_conversation
from utils.dates import utcnow

logger = logging.getLogger(__name__)

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
    return JobResult(Outcome.PROPOSED, conversation_id=conversation_id, cost_usd=cost,
                     detail={"feed_days": feed_days, "proposal_id": proposal.proposal_id})


def _note(schedule_id, conversation_id) -> None:
    if conversation_id is None:
        return
    from db.session import get_session as db_session

    with next(db_session()) as db:
        note_conversation(db, schedule_id, conversation_id)


JOBS = {
    JobKind.CONTENT_PLAN_FROM_WORK: content_plan_from_work,
}
