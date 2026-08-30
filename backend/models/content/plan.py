"""30-day content plan persistence model."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, ForeignKey, String
from models.columns import json_column, utc_datetime
from sqlmodel import Field, SQLModel
from utils.dates import utcnow


class ContentPlan(SQLModel, table=True):
    __tablename__ = "content_plans"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    name: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    start_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    character: dict = Field(
        default_factory=dict,
        sa_column=Column(json_column(), nullable=False, server_default="{}"),
    )
    days: list = Field(
        default_factory=list,
        sa_column=Column(json_column(), nullable=False, server_default="[]"),
    )
    status: str = Field(default="draft", sa_column=Column(String, nullable=False, server_default="draft"))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
