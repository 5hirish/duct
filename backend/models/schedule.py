"""A run nobody starts by hand (issue #562): one row per schedule.

The schedule is the state the Scheduled page edits, pauses and reads, and the
state the loop in ``service/schedules.py`` fires from, so there is one source
of truth for both. What each run did is not here: it is an ``activity_logs``
row (category ``schedule``), linked to the conversation the run produced,
because "who did what to a project, when" already has a store.

A schedule executes only in the backend that owns its row: one made in a
self-hosted desktop app runs on that computer, one made in hosted Duct runs
in the cloud. ``host`` records which, for the page to say so.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

from models.columns import json_column, utc_datetime
from utils.dates import utcnow


class AgentSchedule(SQLModel, table=True):
    __tablename__ = "agent_schedules"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    # Who made it. A run acts as this person, and only while they are still a
    # member of the project: a creator who left disables the schedule.
    user_id: UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    # Which job fires (service/schedules.JobKind), and its own settings: a plan
    # from shipped work keeps its feed options and horizon here.
    job: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    config: dict = Field(default_factory=dict, sa_column=Column(json_column(), nullable=False, server_default="{}"))
    # When: a preset (hourly, daily, weekdays, weekly, on_release, manual) at a wall-clock
    # time in a named zone, so daylight saving moves with the person.
    cadence: str = Field(sa_column=Column(String, nullable=False))
    at_time: str = Field(default="09:00", sa_column=Column(String, nullable=False, server_default="09:00"))
    weekday: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))  # 0 = Monday
    timezone: str = Field(default="UTC", sa_column=Column(String, nullable=False, server_default="UTC"))
    enabled: bool = Field(default=True, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.true()))
    # cloud | local: the backend that owns, and therefore runs, this schedule.
    host: str = Field(default="cloud", sa_column=Column(String, nullable=False, server_default="cloud"))
    monthly_cap: int = Field(default=6, sa_column=Column(Integer, nullable=False, server_default="6"))

    # The loop's own state. ``next_run_at`` is the occurrence due next (jitter
    # included); the claim compares and sets it, so two processes cannot both
    # take one occurrence. A claimed run holds ``lease_until``, renewed while it
    # runs; a lapsed lease means a deploy or a quit app killed it.
    next_run_at: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True, index=True))
    lease_until: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))
    running_since: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))
    # The occurrence being run or retried, and how many tries it has had: a
    # transient failure retries once, and the key a retry checks first.
    occurrence: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))
    # The conversation the running run opened, so a run killed mid-way can
    # have its conversation closed as cancelled rather than left "Working".
    conversation_id: UUID | None = Field(default=None, sa_column=Column(sa.Uuid(), nullable=True))
    attempt: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    # What an event trigger last saw (#563): the release tag an on-release
    # schedule compares the repository's latest against. Empty until its first
    # check, which only records the tag, so a new schedule never plans from a
    # release that shipped before it existed.
    cursor: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # "Run now" on an event trigger: the next claim runs the job whether or not
    # the event happened, once.
    forced: bool = Field(default=False, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.false()))
    # What the page shows without reading history: the last run's outcome,
    # when it ended, and a reason a person must act on (needs_reason).
    last_run_at: datetime | None = Field(default=None, sa_column=Column(utc_datetime(), nullable=True))
    last_outcome: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    needs_reason: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False))
