"""Lead magnet capture model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa
from models.columns import json_column
from sqlmodel import Column, Field, SQLModel


class LeadMagnet(SQLModel, table=True):
    __tablename__ = "lead_magnets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str
    website_url: str
    magnet_type: str = Field(default="seo_audit")
    access_token: str = Field(unique=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )

    # Populated after audit completes — nullable until then
    report_json: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(json_column(), nullable=True),
    )
    report_generated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )
    email_sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )


class ExecutionInterest(SQLModel, table=True):
    """A lead's expressed interest in having Duct execute fixes for them.

    Demand-validation signal — captured from the audit report's execution upsell.
    Auditing stays free; this records which paid execution service(s) a lead wants
    so we can prioritise which to build first. No execution is performed yet.
    """

    __tablename__ = "execution_interest"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    lead_magnet_id: uuid.UUID = Field(foreign_key="lead_magnets.id", index=True)
    email: str
    website_url: str
    # Service keys, e.g. ["ai_ready_fixes", "translation", "content_rewrites"]
    services: list[str] = Field(
        default_factory=list,
        sa_column=Column(json_column(), nullable=False),
    )
    # Optional finding ids the lead wants fixed (nullable — block-level interest needs none)
    finding_ids: Optional[list[str]] = Field(
        default=None,
        sa_column=Column(json_column(), nullable=True),
    )
    note: Optional[str] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
