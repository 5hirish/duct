"""Pydantic models for the PostBridge v1 API.

Mirrors the OpenAPI spec at https://api.post-bridge.com — every method
returns a typed Pydantic model so route handlers never see raw dicts.
Non-2xx responses parse into PostBridgeError and surface as
PostBridgeAPIError.

Wire shapes match the OpenAPI exactly:
  - social account IDs are NUMERIC
  - post body keys: `caption`, `social_accounts` (numeric list), `media`
    (string media-id list), `scheduled_at`, `platform_configurations`
  - hashtags belong inside `caption` (PostBridge has no separate field)
  - analytics chain: post -> post_result -> analytics; daily snapshots
    come from /v1/analytics/{analytics_id}/daily
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PostBridgePostStatus(StrEnum):
    """Actual statuses returned by /v1/posts."""

    POSTED     = "posted"
    SCHEDULED  = "scheduled"
    PROCESSING = "processing"
    FAILED     = "failed"


class PostBridgePlatform(StrEnum):
    """Platforms PostBridge officially supports.

    Note: PostBridge uses 'twitter' (not 'x'). This is the vendor's wire
    contract; Duct's own channel list is agents.content.channels.Platform and
    the user-facing mirror is app/src/lib/contentEnums.js. All three agree
    today — if PostBridge diverges, this enum is the one that follows them.
    """

    BLUESKY         = "bluesky"
    FACEBOOK        = "facebook"
    GOOGLE_BUSINESS = "google_business"
    INSTAGRAM       = "instagram"
    LINKEDIN        = "linkedin"
    PINTEREST       = "pinterest"
    THREADS         = "threads"
    TIKTOK          = "tiktok"
    TWITTER         = "twitter"
    YOUTUBE         = "youtube"


class PostBridgeMimeType(StrEnum):
    """Allowed media MIME types per CreateUploadUrlDto."""

    IMAGE_PNG      = "image/png"
    IMAGE_JPEG     = "image/jpeg"
    VIDEO_MP4      = "video/mp4"
    VIDEO_QUICKTIME = "video/quicktime"
    APPLICATION_PDF = "application/pdf"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PostBridgeError(BaseModel):
    """Body of a non-2xx PostBridge response."""

    model_config = ConfigDict(extra="allow")

    code:    str  = ""
    message: str  = ""
    details: dict | None = None


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------


class PaginatedMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total:  int
    offset: int
    limit:  int
    next:   str | None = None


# ---------------------------------------------------------------------------
# Social accounts
# ---------------------------------------------------------------------------


class PostBridgeSocialAccount(BaseModel):
    """SocialAccountDto — note `id` is NUMERIC."""

    model_config = ConfigDict(extra="ignore")

    id:       int
    platform: PostBridgePlatform
    username: str


# ---------------------------------------------------------------------------
# Media upload
# ---------------------------------------------------------------------------


class CreateUploadUrlRequest(BaseModel):
    """Request body for POST /v1/media/create-upload-url."""

    model_config = ConfigDict(extra="forbid")

    name:       str
    mime_type:  PostBridgeMimeType
    size_bytes: int = Field(ge=1)


class PostBridgeUploadUrl(BaseModel):
    """CreateUploadUrlResponseDto — return shape from create-upload-url."""

    model_config = ConfigDict(extra="ignore")

    media_id:    str
    upload_url:  str
    name:        str


class PostBridgeMediaObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    isDeleted:  bool = False
    url:        str | None = None
    size_bytes: int | None = None
    name:       str | None = None


class PostBridgeMedia(BaseModel):
    """MediaDto — one media record."""

    model_config = ConfigDict(extra="ignore")

    id:        str
    mime_type: str | None = None
    object:    PostBridgeMediaObject | None = None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


class PostBridgeCreatePostRequest(BaseModel):
    """CreatePostDto. Note: hashtags are part of `caption`, not separate.

    Either `media` (preferred, media_id list from create-upload-url) or
    `media_urls` (publicly-accessible URL list) must be provided, not both.
    `media` wins if both are supplied.
    """

    model_config = ConfigDict(extra="forbid")

    caption:                  str
    social_accounts:          list[int]
    media:                    list[str] | None = None
    media_urls:               list[str] | None = None
    scheduled_at:             datetime | None = None
    platform_configurations:  dict[str, Any] | None = None
    account_configurations:   dict[str, Any] | None = None
    is_draft:                 bool | None = None
    processing_enabled:       bool | None = None


class PostBridgePost(BaseModel):
    """PostDto — single post record."""

    model_config = ConfigDict(extra="ignore")

    id:                       str
    caption:                  str = ""
    status:                   PostBridgePostStatus
    scheduled_at:             datetime | None = None
    platform_configurations:  dict[str, Any] | None = None
    social_accounts:          list[int] = Field(default_factory=list)
    account_configurations:   dict[str, Any] | None = None
    media:                    list[Any] | None = None
    created_at:               datetime | None = None
    updated_at:               datetime | None = None
    is_draft:                 bool = False
    warnings:                 list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Post results (the link between a Post and platform-specific outcomes)
# ---------------------------------------------------------------------------


class PostBridgePostResultPlatformData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id:       str | None = None
    url:      str | None = None
    username: str | None = None


class PostBridgePostResult(BaseModel):
    """PostResultDto — one post → many post_results, one per platform."""

    model_config = ConfigDict(extra="ignore")

    id:                str
    post_id:           str
    success:           bool
    social_account_id: int
    error:             Any | None = None
    platform_data:     PostBridgePostResultPlatformData | None = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class PostBridgeAnalytics(BaseModel):
    """AnalyticsDto — lifetime per-platform analytics, keyed by post_result_id."""

    model_config = ConfigDict(extra="ignore")

    id:                str
    post_result_id:    str
    platform:          str
    platform_post_id:  Any | None = None
    view_count:        int | None = None
    like_count:        int | None = None
    comment_count:     int | None = None
    share_count:       int | None = None
    cover_image_url:   Any | None = None
    share_url:         Any | None = None
    video_description: Any | None = None
    duration:          Any | None = None
    platform_created_at: Any | None = None
    last_synced_at:    datetime | None = None
    match_confidence:  Any | None = None


class PostBridgeDailySnapshot(BaseModel):
    """AnalyticsDailySnapshotDto — cumulative totals for one day."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    snapshot_date: date  = Field(validation_alias="date")
    view_count:    int   = 0
    like_count:    int   = 0
    comment_count: int   = 0
    share_count:   int   = 0


class PostBridgeDailyDelta(BaseModel):
    """AnalyticsDailyDeltaDto — per-day deltas (excludes first day)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    snapshot_date: date = Field(validation_alias="date")
    views:    int = 0
    likes:    int = 0
    comments: int = 0
    shares:   int = 0


class PostBridgeAnalyticsDaily(BaseModel):
    """AnalyticsDailyDto — wrapper returned by /v1/analytics/{id}/daily."""

    model_config = ConfigDict(extra="ignore")

    snapshots: list[PostBridgeDailySnapshot] = Field(default_factory=list)
    deltas:    list[PostBridgeDailyDelta]    = Field(default_factory=list)
