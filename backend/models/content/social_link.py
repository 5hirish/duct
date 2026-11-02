"""Per-project linked social account, at the scheduler that holds it."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel
from models.columns import utc_datetime
from utils.dates import utcnow


class ContentSocialLink(SQLModel, table=True):
    __tablename__ = "content_social_links"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "publisher", "external_account_id",
            name="uq_content_social_links_project_publisher_account",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # The scheduler that holds the account (PublisherSpec.id), and the
    # account's id there, as text: PostBridge's are numbers, Zernio's are not.
    # A project can link LinkedIn at one scheduler and TikTok at another, and
    # a post goes out through the one holding its platform's account.
    publisher: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    external_account_id: str = Field(sa_column=Column(String, nullable=False))
    platform: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    username: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False),
    )
