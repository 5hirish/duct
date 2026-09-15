"""Project persistence model."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from models.columns import json_column, utc_datetime
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A project's URL-safe name. Mirrors the backfill in f6fa9305fb03."""
    return _SLUG_RE.sub("-", (value or "").lower()).strip("-") or "project"


def unique_slug(db, user_id: UUID, wanted: str, *, exclude: UUID | None = None) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`... whichever is free for this user.

    `uq_projects_user_slug` has existed since f6fa9305fb03, which backfilled
    every slug from the project name with exactly this counter. Nothing has
    written the column since, so every project created after that migration
    kept the empty-string default -- which the constraint permits once per user
    and rejects on their second project. That is an IntegrityError on a plain
    "create project", so this is not tidiness. The content agent reads
    `proj.slug` too, and has been reading "" for every project.
    """
    from sqlalchemy import select as _select

    stmt = _select(Project.slug).where(Project.user_id == user_id)
    if exclude is not None:
        stmt = stmt.where(Project.id != exclude)
    taken = set(db.execute(stmt).scalars().all())

    base = slugify(wanted)
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    # A slug is unique per owner, not globally — two people may both have a
    # project called "growth". Created by f6fa9305fb03.
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_projects_user_slug"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    slug: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    tagline: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    description: str = Field(default="", sa_column=Column(sa.Text(), nullable=False, server_default=""))
    url: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    company_name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    industry: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    business_model: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    pitch: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    targets: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    audience: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    competition: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    brand_channels: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    content_brand: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    content_pillars: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    content_visual_assets: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    # Execution autonomy: 'ask' (default — the agent asks freely and every
    # change set waits for approval) | 'assisted' | 'auto'. Read it through
    # models.execution.normalize_autonomy, never raw: the server_default below
    # is still 'manual', the original spelling of 'ask', which that function
    # accepts as an alias. Destructive/publish ops always wait regardless, at
    # every level — see service/execution/policy.py.
    autonomy_level: str = Field(
        default="ask", sa_column=Column(String, nullable=False, server_default="manual")
    )
    # Memory off switch: agents and system writers stop remembering anything new
    # about this project. Reads are unaffected — what is already known stays
    # visible and usable; archive and delete are how you remove it.
    memory_paused: bool = Field(
        default=False, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.false())
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
