"""Staged-execution persistence models (change sets + per-account guardrails).

Execution follows a two-phase commit: an agent (or the API caller) *proposes*
a change set, each change is previewed and checked against the account's
guardrail invariants, a human approves, and only then is it applied — with
per-change results and rollback handles recorded. See
docs/strategy/gads-learnings-ads-intelligence.md §5.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Change-set lifecycle: proposed → approved → applying → applied | partial | failed
# Terminal alternatives: rejected (never applied), rolled_back (applied then reverted).
CHANGE_SET_STATUSES = {
    "proposed",
    "approved",
    "applying",
    "applied",
    "partial",
    "failed",
    "rejected",
    "rolled_back",
}

# Per-change lifecycle inside `changes` JSON:
# proposed → blocked (guardrail) | approved → applied | failed → rolled_back
CHANGE_STATUSES = {"proposed", "blocked", "approved", "applied", "failed", "rolled_back"}


class ExecutionChangeSet(SQLModel, table=True):
    __tablename__ = "execution_change_sets"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    connector_type: str = Field(sa_column=Column(String, nullable=False))  # 'google_ads' | 'ga4'
    account_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    account_name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    title: str = Field(sa_column=Column(String, nullable=False))
    # Narrative from the proposing agent: why these changes, expected impact.
    context: str = Field(default="", sa_column=Column(sa.Text(), nullable=False, server_default=""))
    status: str = Field(default="proposed", sa_column=Column(String, nullable=False, server_default="proposed"))
    # List of change dicts:
    # {id, op_type, summary, target: {...}, payload: {...}, current: {...},
    #  preview: {...}, status, guardrail_violations: [...], result: {...}, rollback: {...}}
    changes: list = Field(
        default_factory=list,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    approved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    applied_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ExecutionGuardrail(SQLModel, table=True):
    """A per-account learned invariant the executor must never violate.

    `rule` is the human-readable statement (also injected into agent prompts).
    `match` is the machine matcher enforced at preview/apply time:
      {"op_types": ["google_ads.pause_campaign", ...],   # ops this rule blocks
       "target_contains": "2074113222"}                   # optional substring
    A change violates the rule when its op_type is in op_types (empty = all ops)
    AND target_contains (if set) appears in the serialized target/payload.
    """

    __tablename__ = "execution_guardrails"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    connector_type: str = Field(sa_column=Column(String, nullable=False))
    account_id: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    rule: str = Field(sa_column=Column(sa.Text(), nullable=False))
    match: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    active: bool = Field(default=True, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.true()))
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
