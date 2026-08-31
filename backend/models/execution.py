"""Staged-execution persistence models (change sets + per-account guardrails).

Execution follows a two-phase commit: an agent (or the API caller) *proposes*
a change set, each change is previewed and checked against the account's
guardrail invariants, a human approves, and only then is it applied — with
per-change results and rollback handles recorded. See
docs/strategy/gads-learnings-ads-intelligence.md §5.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String
from models.columns import json_column, utc_datetime
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


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


# Who proposed the set and who (if anyone) applied it.
CHANGE_SET_SOURCES = {"user", "agent"}
APPLIED_BY_VALUES = {"", "user", "auto"}

# Project execution autonomy (projects.autonomy_level) — a Claude-Code-shaped
# ladder governing THREE things together: how freely an agent asks clarifying
# questions, whether it proposes change sets, and whether any of them apply
# without a click.
#
# The critical property, and the reason this is safe to ship: **`auto` does not
# widen what may auto-apply.** It reduces interruption, not oversight.
# AUTO_APPLY_ALLOWLIST and the absolute destructive gate in
# service/execution/policy.py are identical at `assisted` and at `auto`.
AUTONOMY_ASK = "ask"            # asks freely; proposes; nothing ever auto-applies
AUTONOMY_ASSISTED = "assisted"  # asks when it changes the conclusion; reversible,
                                # guardrail-clean, allowlisted agent sets auto-apply
AUTONOMY_AUTO = "auto"          # asks minimally, records assumptions instead;
                                # the SAME allowlist applies, unchanged
AUTONOMY_LEVELS = {AUTONOMY_ASK, AUTONOMY_ASSISTED, AUTONOMY_AUTO}

# Levels at which an eligible agent-proposed set may apply without a click.
AUTO_APPLY_LEVELS = {AUTONOMY_ASSISTED, AUTONOMY_AUTO}

# "manual" was the original spelling of `ask`, and it named only the apply
# half of a level that now also governs questions. Stored rows, the column's
# server_default and older clients still say it, so it stays an accepted alias
# rather than a data migration: normalize_autonomy() is the single funnel, and
# rewriting rows to rename a free-text string would be risk for no behaviour.
AUTONOMY_MANUAL = "manual"
_AUTONOMY_ALIASES = {AUTONOMY_MANUAL: AUTONOMY_ASK}


def is_writable_autonomy(value: str | None) -> bool:
    """True when a client-supplied level may be stored.

    Distinct from ``normalize_autonomy``, which falls back to ``ask`` for
    anything it does not recognise. That is right when *reading* a stored row
    and wrong when *writing*: a typo must be a 422, not a silent write of a
    level nobody asked for. Aliases pass, so an older client still works.
    """
    level = (value or "").strip().lower()
    return level in AUTONOMY_LEVELS or level in _AUTONOMY_ALIASES


def normalize_autonomy(value: str | None) -> str:
    """A stored or client-supplied level as one of AUTONOMY_LEVELS.

    Unknown values fall back to `ask` — the level that applies nothing. A
    typo must never be read as more autonomy than was granted.
    """
    level = (value or "").strip().lower()
    level = _AUTONOMY_ALIASES.get(level, level)
    return level if level in AUTONOMY_LEVELS else AUTONOMY_ASK


class ExecutionChangeSet(SQLModel, table=True):
    __tablename__ = "execution_change_sets"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # Provenance: which project/conversation/agent proposed this set. Nullable —
    # browser-proposed sets from /execute predate projects and carry none.
    project_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    # Polymorphic link to agent_conversations — no FK (artifacts convention).
    conversation_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, index=True),
    )
    agent_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    source: str = Field(default="user", sa_column=Column(String, nullable=False, server_default="user"))
    # "" until applied; then "user" (explicit approval) or "auto" (assisted autonomy).
    applied_by: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Policy verdict computed at propose time: every change reversible,
    # allowlisted, guardrail-clean, non-destructive, preview-clean.
    auto_apply_eligible: bool = Field(
        default=False, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.false())
    )
    connector_type: str = Field(sa_column=Column(String, nullable=False))  # 'google_ads' | 'ga4' | 'gtm'
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
        sa_column=Column(json_column(), nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
    approved_at: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))
    applied_at: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))


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
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    active: bool = Field(default=True, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.true()))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
