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
    fans: int = 0
    verified: bool = False


class ScrapedPostMusic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    music_name: str = Field(default="", validation_alias="musicName")
    music_author: str = Field(default="", validation_alias="musicAuthor")
    music_id: str = Field(default="", validation_alias="musicId")


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
    hashtags:          list[str] = Field(default_factory=list)
    slideshow_image_links: list[str] = Field(default_factory=list, validation_alias="slideshowImageLinks")


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
