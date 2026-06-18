"""Pydantic models for Apify TikTok scraper integration.

Source: nomadapps/marketing/app/src/types.ts ScrapedPost/DiscoveredRef
+ Apify v2 actor-runs API. Field names follow the actor's output
verbatim (the TikTok scraper actor returns camelCase) — we keep that
shape so the frontend doesn't need a remap layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApifyRunStatus(str, Enum):
    """Lifecycle states from Apify's /actor-runs/{id} status field.

    Source: https://docs.apify.com/api/v2#tag/Actor-runs
    """

    READY     = "READY"
    RUNNING   = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED    = "FAILED"
    ABORTING  = "ABORTING"
    ABORTED   = "ABORTED"
    TIMING_OUT = "TIMING-OUT"
    TIMED_OUT = "TIMED-OUT"


class ApifyRun(BaseModel):
    """Subset of Apify's actor-run object we care about."""

    model_config = ConfigDict(extra="ignore")

    id:               str
    actor_id:         str = Field(default="", validation_alias="actId")
    status:           ApifyRunStatus = ApifyRunStatus.READY
    started_at:       datetime | None = Field(default=None, validation_alias="startedAt")
    finished_at:      datetime | None = Field(default=None, validation_alias="finishedAt")
    default_dataset_id: str = Field(default="", validation_alias="defaultDatasetId")
    default_key_value_store_id: str = Field(default="", validation_alias="defaultKeyValueStoreId")


class ScrapedPostAuthor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    nick_name: str = Field(default="", validation_alias="nickName")
    fans: int = 0
    verified: bool = False
    # Richer fields used by the profile/competitor discovery mode — avatar + bio
    # power the profile header card; heart/following round out the snapshot.
    avatar: str = ""
    signature: str = ""  # the profile bio
    bio_link: str = Field(default="", validation_alias="bioLink")
    profile_url: str = Field(default="", validation_alias="profileUrl")
    following: int = 0
    heart: int = 0


class ScrapedComment(BaseModel):
    """One comment on a scraped post — best-effort passthrough.

    The actor only returns comments when ``commentsPerPost`` is set (profile
    mode). Field names follow the actor's output; extra='ignore' tolerates
    shape drift so a key rename can't break the discovery flow.
    """

    model_config = ConfigDict(extra="ignore")

    text: str = ""
    digg_count: int = Field(default=0, validation_alias="diggCount")
    author: str = Field(default="", validation_alias="uniqueId")


class ScrapedPostMusic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    music_name: str = Field(default="", validation_alias="musicName")
    music_author: str = Field(default="", validation_alias="musicAuthor")
    music_id: str = Field(default="", validation_alias="musicId")
    # `music_original` flags an original sound (rideable trend); play_url is the
    # audio so a future "trending sounds" view can preview / analyse it.
    music_original: bool = Field(default=False, validation_alias="musicOriginal")
    play_url: str = Field(default="", validation_alias="playUrl")


class ScrapedPostVideo(BaseModel):
    """Video metadata — notably the cover image used as the card thumbnail.

    `cover_url` is the still frame; the actor also returns a higher-res
    `originalCoverUrl`. Both are TikTok CDN URLs with signed, time-limited
    query params, so they can expire (relevant once we cache results).
    """

    model_config = ConfigDict(extra="ignore")

    cover_url:          str = Field(default="", validation_alias="coverUrl")
    original_cover_url: str = Field(default="", validation_alias="originalCoverUrl")
    duration:           int = 0
    width:              int = 0
    height:             int = 0


class ScrapedPost(BaseModel):
    """One TikTok post returned by the scraper actor.

    extra='ignore' lets the actor evolve without breaking us — fields
    we don't model just get dropped. The frontend gets the raw post
    via the route layer's pass-through `raw` field if it needs them.
    """

    model_config = ConfigDict(extra="ignore")

    id:                str
    text:              str = ""
    web_video_url:     str = Field(default="", validation_alias="webVideoUrl")
    is_slideshow:      bool = Field(default=False, validation_alias="isSlideshow")
    create_time_iso:   datetime | None = Field(default=None, validation_alias="createTimeISO")
    digg_count:        int = Field(default=0, validation_alias="diggCount")
    play_count:        int = Field(default=0, validation_alias="playCount")
    collect_count:     int = Field(default=0, validation_alias="collectCount")
    comment_count:     int = Field(default=0, validation_alias="commentCount")
    share_count:       int = Field(default=0, validation_alias="shareCount")
    music_meta:        ScrapedPostMusic | None = Field(default=None, validation_alias="musicMeta")
    author_meta:       ScrapedPostAuthor | None = Field(default=None, validation_alias="authorMeta")
    video_meta:        ScrapedPostVideo | None = Field(default=None, validation_alias="videoMeta")
    hashtags:          list[str] = Field(default_factory=list)
    slideshow_image_links: list[str] = Field(default_factory=list, validation_alias="slideshowImageLinks")
    # Populated only when the run requested comments (profile/competitor mode) —
    # the audience's own words: questions + objections to mine for hooks.
    comments:          list[ScrapedComment] = Field(default_factory=list)
    # Richer signal kept for analysis/filtering (mostly free passthrough). Most
    # are always returned; subtitle_links only when transcription is requested.
    mentions:          list[str] = Field(default_factory=list)
    effect_stickers:   list[dict] = Field(default_factory=list, validation_alias="effectStickers")
    subtitle_links:    list[dict] = Field(default_factory=list, validation_alias="subtitleLinks")
    text_language:     str = Field(default="", validation_alias="textLanguage")
    location_created:  str = Field(default="", validation_alias="locationCreated")
    is_ad:             bool = Field(default=False, validation_alias="isAd")
    is_sponsored:      bool = Field(default=False, validation_alias="isSponsored")


class DiscoveredReferenceRecord(BaseModel):
    """One saved discovered reference — what we persist into ContentAsset
    when the user clicks Save on a scraped post.

    Goes into ContentAsset.params as a JSON blob so we don't need a new
    table; ContentAsset.asset_type='discovered_reference', source='apify',
    url='' (no on-disk bytes yet; we just track the URL + metadata).
    """

    model_config = ConfigDict(extra="forbid")

    actor:        str            # Apify actor id used to find this post
    run_id:       str            # Apify run id (for re-fetching dataset)
    dataset_id:   str            # Apify dataset id holding the run's items
    request:      dict[str, Any] = Field(default_factory=dict)  # actor input echoed back
    post:         ScrapedPost
    saved_at:     datetime
    downloaded_images: list[str] = Field(default_factory=list)  # local paths (future)
