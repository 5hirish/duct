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

A proposal is also **held on the conversation** (``agent_conversations.meta``),
because the session is only in the server's memory: a deploy or a reload used
to lose a plan the person had not decided on yet, and the board went on
showing the old one while the chat said the new one was made. A resumed
session takes it back (the runner's resume hook) and shows it again; Accept
and Reject release it. Accept merges against the plan **as it stands then**,
not as it stood when the agent proposed: a day drafted, or gone by, while the
proposal waited is kept like any other.

No DB session is opened here: the merge is plain data so it can be previewed
and tested without one, and the writers below take the caller's session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from agents.content.plan_period import PlanPeriod, default_period, keep_drafted_days

PROPOSED = "proposed"
ACCEPTED = "accepted"
REJECTED = "rejected"

# Where a conversation holds the proposal waiting on the person
# (``AgentConversation.meta``, the catch-all that needs no migration).
HELD_PROPOSAL_KEY = "plan_proposal"


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
    # The agent's own days, before the merge: Accept merges them again
    # against the plan as it is by then.
    proposed_days: list[dict] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out.update(
            project_id=str(self.project_id),
            start_date=self.start_date.isoformat(),
            created=self.created.isoformat(),
            replaces_plan_id=str(self.replaces_plan_id) if self.replaces_plan_id else None,
        )
        return out

    @classmethod
    def from_json(cls, raw: Any) -> "PlanProposal | None":
        """The proposal a conversation holds, or None for anything that is not one."""
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                proposal_id=str(raw["proposal_id"]),
                project_id=UUID(str(raw["project_id"])),
                name=str(raw.get("name") or ""),
                start_date=date.fromisoformat(str(raw["start_date"])),
                character=dict(raw.get("character") or {}),
                strategy=dict(raw.get("strategy") or {}),
                days=list(raw.get("days") or []),
                kept_days=[int(i) for i in raw.get("kept_days") or []],
                replaces_plan_id=UUID(str(raw["replaces_plan_id"])) if raw.get("replaces_plan_id") else None,
                created=date.fromisoformat(str(raw.get("created") or raw["start_date"])),
                proposed_days=list(raw.get("proposed_days") or []),
            )
        except (KeyError, TypeError, ValueError):
            return None

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
        created=today,
        proposed_days=list(new_days),
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
    days = proposal.days
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
        if proposal.proposed_days:
            days, _ = merge_proposal(
                row.days, proposal.proposed_days, start=row.start_date or proposal.start_date, today=now.date()
            )
    row.character = proposal.character
    row.strategy = proposal.strategy
    row.days = days
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def hold_proposal(db: Any, conversation_id: UUID | None, proposal: PlanProposal | None) -> None:
    """Keep ``proposal`` on its conversation until the person decides, or
    release it (``None``). A newer proposal replaces an older one, as on the
    session. No-op without a conversation; the caller commits nothing else."""
    if conversation_id is None:
        return
    from models.content.conversation import AgentConversation

    conv = db.get(AgentConversation, conversation_id)
    if conv is None:
        return
    meta = {k: v for k, v in (conv.meta or {}).items() if k != HELD_PROPOSAL_KEY}
    if proposal is not None:
        meta[HELD_PROPOSAL_KEY] = proposal.to_json()
    conv.meta = meta
    db.add(conv)
    db.commit()


def held_proposal(db: Any, conversation_id: UUID | None) -> PlanProposal | None:
    """The proposal a conversation is waiting on the person for, if any."""
    if conversation_id is None:
        return None
    from models.content.conversation import AgentConversation

    conv = db.get(AgentConversation, conversation_id)
    return PlanProposal.from_json((conv.meta or {}).get(HELD_PROPOSAL_KEY)) if conv is not None else None


def day_date(start: date | None, index: int) -> date | None:
    """The calendar date of day ``index`` in a plan that starts on ``start``."""
    return None if start is None else start + timedelta(days=index)


__all__ = [
    "ACCEPTED",
    "HELD_PROPOSAL_KEY",
    "PROPOSED",
    "REJECTED",
    "PlanProposal",
    "apply_proposal",
    "build_proposal",
    "day_date",
    "held_proposal",
    "hold_proposal",
    "merge_proposal",
]
