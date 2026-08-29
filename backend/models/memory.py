"""Agent memory — one typed, bi-temporal, sourced entry per remembered fact.

Design: `docs/engineering/agent-memory-research.html` §06–07 (the model) and
`docs/engineering/agent-memory-on-deepagents.md` (the harness wiring).

Layer 1 of four. Layer 0 is the evidence that already exists (``agent_events``,
``activity_logs``, ``artifacts`` versions) and stays append-only; this table is
the layer between raw events and the prompt — what an agent can write, a job can
consolidate, a query can retrieve and the timeline can show.

Three scopes live in one table:

* ``user``     — who is operating Duct (method, communication, tooling, process).
                 Keyed by ``user_id``, crosses projects, private to that user.
* ``project``  — what is true about the account (status, goal, incident, metric,
                 decision, action, watch…). Keyed by ``project_id``, shared by
                 every member, never visible to another project.
* ``artifact`` — what we produced and where it says so. One entry per artifact
                 version, so reports appear on the timeline and in the digest.

**Bi-temporal.** ``observed_at`` is when the thing happened, ``valid_from`` /
``valid_to`` the period the statement holds, ``recorded_at`` when we learned it.
A new observation for the same *state key* (``entity_key`` + ``attribute`` +
``period``) closes the previous row rather than overwriting it: the old row keeps
its validity range and gains ``superseded_by``. Nothing is deleted by the system,
so "we thought X, then learned Y" reads as history. That rule runs in
``service/memory.py`` — never as an LLM judgement.

House style: ``kind`` is a free string (validated against the sets below, not a
DB enum, so a new kind needs no migration), ``source_refs`` is polymorphic JSON,
and every JSON column goes through ``json_column()`` for the SQLite desktop build.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlmodel import Field, SQLModel

from models.columns import json_column, utc_datetime
from utils.dates import utcnow

# --- Scopes ----------------------------------------------------------------

SCOPE_USER = "user"
SCOPE_PROJECT = "project"
SCOPE_ARTIFACT = "artifact"
MEMORY_SCOPES = {SCOPE_USER, SCOPE_PROJECT, SCOPE_ARTIFACT}

# --- Kinds -----------------------------------------------------------------
# Free strings on the column; these sets are the vocabulary the tools and the
# digest renderer understand. An unknown kind is stored, not rejected.

PROJECT_KINDS = {
    "status",      # current state of an area or entity        (key: entity + status)
    "goal",        # targets and KPIs in force                 (key: kpi + target)
    "milestone",   # dated achievement or planned date         (event, no key)
    "event",       # launches, budget changes, redirects       (event, no key)
    "incident",    # anomaly/problem with detected + resolved  (key: entity + issue)
    "metric",      # dated observation of a KPI for a period   (key: entity + attr + period)
    "decision",    # what was decided and why                  (event, no key)
    "conclusion",  # agent finding or hypothesis               (key: entity + topic)
    "action",      # commitments and change sets with state    (key: action id)
    "watch",       # open question / something to monitor      (key: entity + watch)
    "entity",      # durable fact about a campaign, page, competitor
}

USER_KINDS = {
    "identity",       # role, seniority, team, accountability
    "communication",  # depth, format, tone, language
    "method",         # how they like analysis done
    "tooling",        # which integrations and outputs they trust
    "process",        # cadence and approval habits
    "feedback",       # a correction or confirmation, with the rule it implies
}

ARTIFACT_KINDS = {"artifact"}

MEMORY_KINDS = PROJECT_KINDS | USER_KINDS | ARTIFACT_KINDS

# Kinds that describe a moment rather than a state — they never supersede
# anything, even when an entity_key is supplied. ``artifact`` is deliberately
# absent: v2 of a report supersedes v1, so the digest carries the current
# version while the timeline keeps every one.
EVENT_KINDS = {"milestone", "event", "decision"}

# --- Status / provenance ---------------------------------------------------

STATUS_PROPOSED = "proposed"      # agent wrote it; awaiting the user's eye
STATUS_CONFIRMED = "confirmed"    # user said it, or confirmed a proposal
STATUS_SUPERSEDED = "superseded"  # closed by a newer observation of the same state
STATUS_ARCHIVED = "archived"      # user dismissed it; kept, never recalled
MEMORY_STATUSES = {STATUS_PROPOSED, STATUS_CONFIRMED, STATUS_SUPERSEDED, STATUS_ARCHIVED}

# Statuses that still reach the digest and search.
ACTIVE_STATUSES = (STATUS_CONFIRMED, STATUS_PROPOSED)

SOURCE_AGENT = "agent"
SOURCE_USER = "user"
SOURCE_CONNECTOR = "connector"
SOURCE_ARTIFACT = "artifact"
SOURCE_SYSTEM = "system"
MEMORY_SOURCES = {SOURCE_AGENT, SOURCE_USER, SOURCE_CONNECTOR, SOURCE_ARTIFACT, SOURCE_SYSTEM}

CONFIDENCE_LEVELS = {"low", "medium", "high"}

# The state-key predicate, shared by the model's safety-net index and the
# supersession query in service/memory.py. Keep the two in step.
_STATE_KEY_PREDICATE = (
    "status IN ('confirmed', 'proposed') AND superseded_by IS NULL AND state_key <> ''"
)


class ProjectMemory(SQLModel, table=True):
    """One remembered fact, observation, decision or pointer."""

    __tablename__ = "project_memories"
    __table_args__ = (
        Index("ix_project_memories_project_observed", "project_id", "observed_at"),
        Index("ix_project_memories_project_kind", "project_id", "kind"),
        Index("ix_project_memories_user_scope", "user_id", "scope"),
        Index("ix_project_memories_hash", "project_id", "content_hash"),
        # Safety net that makes supersession atomic: at most one active row per
        # project state key. Partial indexes work on both Postgres and SQLite,
        # so both dialects need the predicate spelled out. User-scope rows have
        # a NULL project_id (distinct under both dialects), so their
        # supersession relies on the service query alone.
        Index(
            "uq_project_memories_state",
            "project_id", "state_key",
            unique=True,
            postgresql_where=sa.text(_STATE_KEY_PREDICATE),
            sqlite_where=sa.text(_STATE_KEY_PREDICATE),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)

    # 'user' | 'project' | 'artifact'
    scope: str = Field(
        default="project",
        sa_column=Column(String, nullable=False, server_default="project", index=True),
    )
    # Set for project + artifact scope; NULL for user scope.
    project_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True),
    )
    # The author for project scope, the subject for user scope.
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
    )

    kind: str = Field(sa_column=Column(String, nullable=False))
    title: str = Field(sa_column=Column(String, nullable=False))
    # The fact itself. Agent-written entries follow the Claude Code discipline:
    # the statement, then "Why:" and "How to apply:".
    body: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))

    # --- State key (supersession) -----------------------------------------
    # e.g. entity_key='page:/pricing' attribute='clicks_wow' period='2026-08-01..14'
    entity_key: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    attribute: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    period: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # The three fields above joined, and EMPTY when this entry does not
    # participate in supersession (an event, or a fact with no entity). One
    # column so the "is this a state?" decision lives in Python — where
    # EVENT_KINDS lives — instead of being frozen into an index predicate that
    # a new kind would have to migrate. See service/memory.py::state_key.
    state_key: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Typed payload for metric/goal entries: {"value": 71, "unit": "USD", "delta": 0.38}
    value: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )

    # --- Bi-temporal ------------------------------------------------------
    observed_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
    valid_from: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
    # NULL = still true.
    valid_to: datetime | None = Field(
        default=None, sa_column=Column(utc_datetime(), nullable=True)
    )
    recorded_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
    # The entry that closed this one (same table, no FK — a self-FK would block
    # the CASCADE delete ordering on project removal).
    superseded_by: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    # --- Provenance -------------------------------------------------------
    source_type: str = Field(
        default=SOURCE_AGENT, sa_column=Column(String, nullable=False, server_default=SOURCE_AGENT)
    )
    # Polymorphic evidence pointers (artifacts convention — no FK):
    # [{"conversation_id": "…", "seq": [41, 58]},
    #  {"artifact_id": "…", "slug": "acme-seo-audit", "section": "3"},
    #  {"change_set_id": "…"}, {"connector": "google_ads"}]
    source_refs: list = Field(
        default_factory=list,
        sa_column=Column(json_column(), nullable=False, server_default="[]"),
    )
    agent_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # Polymorphic link to agent_conversations — no FK (artifacts convention).
    conversation_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, index=True),
    )

    # --- Ranking / lifecycle ----------------------------------------------
    confidence: str = Field(
        default="medium", sa_column=Column(String, nullable=False, server_default="medium")
    )
    importance: int = Field(
        default=5, sa_column=Column(Integer, nullable=False, server_default="5")
    )
    status: str = Field(
        default=STATUS_PROPOSED,
        sa_column=Column(String, nullable=False, server_default=STATUS_PROPOSED, index=True),
    )
    # Always in the digest, regardless of recency or importance.
    pinned: bool = Field(
        default=False, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.false())
    )
    recall_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    last_recalled_at: datetime | None = Field(
        default=None, sa_column=Column(utc_datetime(), nullable=True)
    )

    # Dedupe key over the identity fields — see service/memory.py::content_hash.
    content_hash: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
