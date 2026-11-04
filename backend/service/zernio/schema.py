"""The slice of Zernio's v1 API that Duct reads, as typed models.

Zernio documents some 760 endpoints (https://zernio.com/openapi.json); these
are the fields its accounts, posts, media and analytics answers carry that
Duct uses, spelled as the vendor spells them. Everything else in an answer is
ignored, so a field Zernio adds never fails a parse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ZernioError(_Model):
    """Zernio's error envelope. ``error`` is reworded freely; ``type`` and
    ``code`` are the stable parts."""

    error: str = ""
    type: str = ""
    code: str = ""


class ZernioAccount(_Model):
    id: str = Field(validation_alias=AliasChoices("_id", "id"))
    platform: str
    username: str = ""
    display_name: str = Field(default="", validation_alias=AliasChoices("displayName", "display_name"))
    profile_picture: str | None = Field(default=None, validation_alias=AliasChoices("profilePicture", "profile_picture"))
    is_active: bool = Field(default=True, validation_alias=AliasChoices("isActive", "is_active"))
    needs_reconnection: bool = Field(default=False, validation_alias=AliasChoices("needsReconnection", "needs_reconnection"))


class ZernioPresign(_Model):
    upload_url: str = Field(validation_alias=AliasChoices("uploadUrl", "upload_url"))
    public_url: str = Field(validation_alias=AliasChoices("publicUrl", "public_url"))


class ZernioTarget(_Model):
    """One platform entry on a post: where it went and what became of it."""

    platform: str
    account_id: str = Field(default="", validation_alias=AliasChoices("accountId", "account_id"))
    status: str = ""
    platform_post_url: str | None = Field(default=None, validation_alias=AliasChoices("platformPostUrl", "platform_post_url"))
    error_message: str | None = Field(default=None, validation_alias=AliasChoices("errorMessage", "error_message"))

    @field_validator("account_id", mode="before")
    @classmethod
    def _account_ref(cls, value: Any) -> str:
        # A post's accountId comes back as the id, or as the account itself
        # when Zernio populates it.
        if isinstance(value, dict):
            return str(value.get("_id") or value.get("id") or "")
        return str(value or "")


class ZernioPost(_Model):
    id: str = Field(validation_alias=AliasChoices("_id", "id"))
    content: str = ""
    status: str = ""
    scheduled_for: datetime | None = Field(default=None, validation_alias=AliasChoices("scheduledFor", "scheduled_for"))
    platforms: list[ZernioTarget] = Field(default_factory=list)
    media_items: list[dict] = Field(default_factory=list, validation_alias=AliasChoices("mediaItems", "media_items"))


class ZernioPostAnswer(_Model):
    """What create and update answer: the post, and notices about it."""

    post: ZernioPost
    warnings: list[str] = Field(default_factory=list)


class ZernioPostAnalytics(_Model):
    """A post's numbers. Zernio sends 0 for a metric the platform does not
    report, which ``service/zernio/publisher.py`` reads as unknown for every
    metric beyond the four counts all of them report."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    views: int = 0
    ig_reels_avg_watch_time: int = Field(default=0, validation_alias=AliasChoices("igReelsAvgWatchTime", "ig_reels_avg_watch_time"))  # ms
    completion_rate: float = Field(default=0, validation_alias=AliasChoices("completionRate", "completion_rate"))  # 0–1
    last_updated: str | None = Field(default=None, validation_alias=AliasChoices("lastUpdated", "last_updated"))


class ZernioAnalyticsPost(_Model):
    """One post in an analytics answer, single or listed."""

    id: str = Field(default="", validation_alias=AliasChoices("postId", "_id", "id"))
    late_post_id: str | None = Field(default=None, validation_alias=AliasChoices("latePostId", "late_post_id"))
    content: str = ""
    platform: str = ""
    platform_post_url: str | None = Field(default=None, validation_alias=AliasChoices("platformPostUrl", "platform_post_url"))
    thumbnail_url: str | None = Field(default=None, validation_alias=AliasChoices("thumbnailUrl", "thumbnail_url"))
    published_at: str | None = Field(default=None, validation_alias=AliasChoices("publishedAt", "published_at"))
    analytics: ZernioPostAnalytics = Field(default_factory=ZernioPostAnalytics)


class ZernioTimelineDay(_Model):
    date: str
    platform: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
