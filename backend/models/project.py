"""Project persistence model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String
from models.columns import json_column, utc_datetime
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class Project(SQLModel, table=True):
    __tablename__ = "projects"

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
