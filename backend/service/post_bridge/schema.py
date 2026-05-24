"""Pydantic response models for the PostBridge API.

The marketing app's TS code dealt in untyped JSON; the Python port
standardises on these models so callers never see a raw dict. Every
non-2xx response is parsed as PostBridgeError and raised as
PostBridgeAPIError (see service.post_bridge.client).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from agents.models import Platform


class PostBridgePostType(StrEnum):
    SLIDESHOW = "slideshow"
    VIDEO     = "video"
    IMAGE     = "image"


class PostBridgePostStatus(StrEnum):
    DRAFT     = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED    = "failed"


class PostBridgeError(BaseModel):
    """Body of a non-2xx PostBridge response. Raised as PostBridgeAPIError."""

    model_config = ConfigDict(extra="allow")  # PostBridge may add fields

    code:    str = ""
    message: str = ""
    details: dict | None = None


class PostBridgeUploadUrl(BaseModel):
    """Response from POST /v1/media/create-upload-url."""

    model_config = ConfigDict(extra="ignore")

    upload_url: HttpUrl
    asset_url:  HttpUrl
    expires_at: datetime | None = None


class PostBridgeSocialAccount(BaseModel):
    """One connected social account as returned by GET /v1/social-accounts."""

    model_config = ConfigDict(extra="ignore")

    id:                  str
    platform:            Platform
    username:            str
    display_name:        str | None = None
    profile_picture_url: HttpUrl | None = None
    connected_at:        datetime | None = None


class PostBridgeCreatePostRequest(BaseModel):
    """Body sent to POST /v1/posts."""

    model_config = ConfigDict(extra="forbid")

    account_ids:  list[str]
    caption:      str
    hashtags:     list[str] = Field(default_factory=list)
    media_urls:   list[HttpUrl]
    scheduled_at: datetime | None = None
    post_type:    PostBridgePostType = PostBridgePostType.SLIDESHOW


class PostBridgeCreatePostResponse(BaseModel):
    """Response from POST /v1/posts."""

    model_config = ConfigDict(extra="ignore")

    post_id:      str
    result_id:    str | None = None
    status:       PostBridgePostStatus
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    error:        str | None = None


class PostBridgeAnalytics(BaseModel):
    """Per-post lifetime metrics from GET /v1/posts/{id}/analytics.

    Note: save_count and save_rate are explicit fields here — the marketing
    app's `Perf` type conflated saves with comments, which broke save_rate.
    """

    model_config = ConfigDict(extra="ignore")

    post_id:          str
    view_count:       int | None = None
    like_count:       int | None = None
    comment_count:    int | None = None
    share_count:      int | None = None
    save_count:       int | None = None
    completion_rate:  float | None = None
    profile_visits:   int | None = None
    bio_link_clicks:  int | None = None
    comments_1h:      int | None = None
    save_rate:        float | None = None
    cover_image_url:  HttpUrl | None = None
    share_url:        HttpUrl | None = None
    last_synced_at:   datetime


class PostBridgeDailySnapshot(BaseModel):
    """One row from GET /v1/posts/{id}/analytics/daily."""

    model_config = ConfigDict(extra="ignore")

    snapshot_date: date = Field(validation_alias="date")
    view_count:    int | None = None
    like_count:    int | None = None
    comment_count: int | None = None
    share_count:   int | None = None
    save_count:    int | None = None


class PostBridgePost(BaseModel):
    """One post from GET /v1/posts list."""

    model_config = ConfigDict(extra="ignore")

    id:           str
    platform:     str
    status:       Literal["draft", "scheduled", "published", "failed"]
    scheduled_at: datetime | None = None
    posted_at:    datetime | None = None
    caption:      str | None = None
    hashtags:     list[str] = Field(default_factory=list)
    media_urls:   list[HttpUrl] = Field(default_factory=list)
    external_url: HttpUrl | None = None
    analytics:    PostBridgeAnalytics | None = None
