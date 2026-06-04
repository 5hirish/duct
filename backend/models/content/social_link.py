"""Per-project linked social account (selected from PostBridge accounts)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentSocialLink(SQLModel, table=True):
    __tablename__ = "content_social_links"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "external_account_id",
            name="uq_content_social_links_project_account",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # PostBridge social-account id (numeric upstream) stored as text.
    external_account_id: str = Field(sa_column=Column(String, nullable=False))
    platform: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    username: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
