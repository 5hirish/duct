"""Lead magnet capture model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class LeadMagnet(SQLModel, table=True):
    __tablename__ = "lead_magnets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str
    website_url: str
    magnet_type: str = Field(default="seo_audit")
    access_token: str = Field(unique=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Populated after audit completes — nullable until then
    report_json: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=True),
    )
    report_generated_at: Optional[datetime] = Field(default=None)
