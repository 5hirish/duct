"""Content asset (generated images, uploads, references)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetType(StrEnum):
    """What a content_assets row IS — stored as a plain String column (values
    match these members); use this enum in code instead of bare strings.

    GENERATED / SLIDE_RENDER are system-produced; the rest (REFERENCE, UPLOAD,
    LOGO, BACKGROUND, DISCOVERED_REFERENCE) come from uploads or discovery. The
    uploadable subset is UPLOADABLE_ASSET_TYPES below.
    """

    GENERATED            = "generated"
    SLIDE_RENDER         = "slide_render"
    REFERENCE            = "reference"
    UPLOAD               = "upload"
    LOGO                 = "logo"
    BACKGROUND           = "background"
    DISCOVERED_REFERENCE = "discovered_reference"


class AssetSource(StrEnum):
    """Where a content_assets row's bytes came from — stored as a plain String
    column. (Not to be confused with Day.source, which is plan-slot provenance.)
    """

    GEMINI     = "gemini"      # Gemini image generation
    HIGGSFIELD = "higgsfield"  # Higgsfield video generation
    RENDER     = "render"      # client-side slide rasterisation
    UPLOAD     = "upload"      # user upload
    APIFY      = "apify"       # scraped via Apify (discovery)


# The asset types a user is allowed to UPLOAD (excludes system-produced
# generated/slide_render). Used by the upload route to validate the request.
UPLOADABLE_ASSET_TYPES = frozenset({
    AssetType.REFERENCE,
    AssetType.UPLOAD,
    AssetType.LOGO,
    AssetType.BACKGROUND,
    AssetType.DISCOVERED_REFERENCE,
})


class ContentAsset(SQLModel, table=True):
    __tablename__ = "content_assets"
    __table_args__ = (
        Index("ix_content_assets_project_type", "project_id", "asset_type"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    project_id: UUID = Field(
        sa_column=Column(
            ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    post_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("content_posts.id", ondelete="SET NULL"), nullable=True),
    )
    asset_type: str = Field(sa_column=Column(String, nullable=False))
    source: str = Field(default=AssetSource.UPLOAD, sa_column=Column(String, nullable=False, server_default="upload"))
    url: str = Field(sa_column=Column(String, nullable=False))
    filename: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    mime_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    prompt: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    model: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    params: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
