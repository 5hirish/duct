"""A content plan is proposed, then accepted — never saved by the agent alone.

Until 2026-11-08 ``submit_plan`` wrote the plan the moment the model called
it: a person opened a planning session and, a minute later, thirty days were
on the board with no step between the agent's draft and their calendar. The
plan is now a *proposal*, held on the session and shown in the viewport with
Accept / Modify / Reject; only Accept writes.

What Accept writes is decided here, in one place the tool (preview) and the
route (write) share, so what the person saw is what lands:

* a plan already covering the period keeps every day **before today** as it
  was (that is history, not a plan) and every day with a drafted post
  (``post_id``: the board finds the draft through it);
* every other day takes the proposal;
* a period with no plan yet takes the proposal whole.

No DB session is opened here except in :func:`apply_proposal`; the merge is
plain data so it can be previewed and tested without one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from agents.content.plan_period import PlanPeriod, default_period, keep_drafted_days

PROPOSED = "proposed"
ACCEPTED = "accepted"
REJECTED = "rejected"


@dataclass
class PlanProposal:
    """What the agent put forward, as the viewport shows it and Accept writes it."""

    proposal_id: str
    project_id: UUID
    name: str
    start_date: date
    character: dict
    strategy: dict
    days: list[dict]          # already merged: what Accept would store
    kept_days: list[int]      # indexes kept from the live plan (drafted or past)
    replaces_plan_id: UUID | None
    created: date = field(default_factory=date.today)

    def payload(self, status: str = PROPOSED) -> dict[str, Any]:
        """The PLAN_GENERATED payload: the plan as the viewport renders it,
        plus the decision state. ``id`` is the live plan's once accepted and
        null before, so nothing downstream mistakes a proposal for a row."""
        return {
            "id": None,
            "status": status,
            "proposal_id": self.proposal_id,
            "replaces_plan_id": str(self.replaces_plan_id) if self.replaces_plan_id else None,
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "days": self.days,
            "character": self.character,
            "strategy": self.strategy,
            "kept_days": self.kept_days,
        }


def merge_proposal(
    old_days: list | None,
    new_days: list[dict],
    *,
    start: date,
    today: date,
) -> tuple[list[dict], list[int]]:
    """The days Accept stores: the proposal, except where the live plan wins.

    The live plan wins on a day before ``today`` (already happened; a plan
    does not rewrite the past) and on a drafted day (``post_id``). Positions
    are dates: index ``i`` is ``start + i`` days, the same rule the calendar
    lays days out by, so "before today" is an index cutoff.
    """
    merged, kept = keep_drafted_days(list(old_days or []), list(new_days))
    if not old_days:
        return merged, kept
    past = max(0, min(len(merged), (today - start).days))
    for i in range(past):
        if i < len(old_days) and isinstance(old_days[i], dict) and i not in kept:
            merged[i] = old_days[i]
            kept.append(i)
    kept.sort()
    return merged, kept


def build_proposal(
    *,
    project_id: UUID,
    draft_name: str,
    character: dict,
    strategy: dict,
    new_days: list[dict],
    live_days: list | None,
    live_plan_id: UUID | None,
    period: PlanPeriod | None,
    today: date,
) -> PlanProposal:
    """A proposal for ``period`` against the live plan (or none)."""
    period = period or default_period(today)
    days, kept = merge_proposal(live_days, new_days, start=period.start, today=today)
    return PlanProposal(
        proposal_id=uuid4().hex,
        project_id=project_id,
        name=draft_name or f"{period.label()} plan",
        start_date=period.start,
        character=character,
        strategy=strategy,
        days=days,
        kept_days=kept,
        replaces_plan_id=live_plan_id,
    )


def apply_proposal(db: Any, proposal: PlanProposal, *, now: Any):
    """Write an accepted proposal: update the plan it replaces, else insert.

    ``db`` is a SQLModel session the route opened; ``now`` its timestamp.
    Returns the row, refreshed. Imports the model lazily so this module stays
    importable without the ORM in tests of the merge alone.
    """
    from models.content import ContentPlan

    row = db.get(ContentPlan, proposal.replaces_plan_id) if proposal.replaces_plan_id else None
    if row is not None and row.project_id != proposal.project_id:
        row = None
    if row is None:
        row = ContentPlan(
            project_id=proposal.project_id,
            name=proposal.name,
            start_date=proposal.start_date,
            status="draft",
        )
    else:
        if proposal.name:
            row.name = proposal.name
        row.updated_at = now
    row.character = proposal.character
    row.strategy = proposal.strategy
    row.days = proposal.days
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def day_date(start: date | None, index: int) -> date | None:
    """The calendar date of day ``index`` in a plan that starts on ``start``."""
    return None if start is None else start + timedelta(days=index)


__all__ = [
    "ACCEPTED",
    "PROPOSED",
    "REJECTED",
    "PlanProposal",
    "apply_proposal",
    "build_proposal",
    "day_date",
    "merge_proposal",
]
