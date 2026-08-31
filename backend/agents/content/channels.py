"""Channel seam for the Content agent.

The content agent is currently a TikTok specialist — its prompts, hooks, slide
architecture and visual rules are all TikTok-native. This module makes that
identity explicit and selectable by a post's *primary channel* (platforms[0]),
so other channel agents can be added later without touching call sites.

For now only "tiktok" is a fully supported channel. Any other channel resolves
to the TikTok playbook with `supported=False` so the UI/prompt can note that no
dedicated agent exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from utils.strings import titleize


class Platform(StrEnum):
    """Publishing channels a post can target.

    Values are PostBridge v1 wire names — which is why it reads 'twitter'
    rather than 'x'. Deliberately not the same object as
    service.post_bridge.schema.PostBridgePlatform: that one is the vendor's
    contract and moves when PostBridge moves, this is Duct's own list. They
    happen to agree today. Mirrored for the UI in app/src/lib/contentEnums.js.

    Lives here rather than in agents/models.py because a publishing channel is
    not a model — and because the label map below is the thing that consumes it.
    """

    TIKTOK          = "tiktok"
    INSTAGRAM       = "instagram"
    YOUTUBE         = "youtube"
    LINKEDIN        = "linkedin"
    TWITTER         = "twitter"
    FACEBOOK        = "facebook"
    THREADS         = "threads"
    BLUESKY         = "bluesky"
    PINTEREST       = "pinterest"
    GOOGLE_BUSINESS = "google_business"


# Channels with a dedicated, tuned playbook today.
SUPPORTED: set[str] = {"tiktok"}

# Display labels. Keyed by the enum, so adding a Platform without a label is a
# visible hole rather than a silent titleize() fallback (test_content_unit
# asserts the map is total). Spelled out because "TikTok" and "Twitter / X"
# don't fall out of titleize. StrEnum keys match plain-string lookups, so
# resolve() below can still index it with a bare channel id.
_LABELS: dict[Platform, str] = {
    Platform.TIKTOK: "TikTok",
    Platform.INSTAGRAM: "Instagram",
    Platform.YOUTUBE: "YouTube",
    Platform.LINKEDIN: "LinkedIn",
    Platform.TWITTER: "Twitter / X",
    Platform.FACEBOOK: "Facebook",
    Platform.THREADS: "Threads",
    Platform.BLUESKY: "Bluesky",
    Platform.PINTEREST: "Pinterest",
    Platform.GOOGLE_BUSINESS: "Google Business",
}

DEFAULT_CHANNEL = "tiktok"


@dataclass(frozen=True)
class Channel:
    """Resolved channel for a drafting session."""

    id: str            # requested channel, e.g. "youtube"
    label: str         # display label, e.g. "YouTube"
    supported: bool    # True only when a dedicated playbook exists
    playbook: str      # the channel whose prompt rules we actually apply


def primary_channel(platforms: list | None) -> str:
    """The post's primary channel — first platform, or the default."""
    if isinstance(platforms, list) and platforms:
        first = platforms[0]
        return getattr(first, "value", first) or DEFAULT_CHANNEL
    return DEFAULT_CHANNEL


def resolve(channel: str | None) -> Channel:
    """Resolve a requested channel to its playbook.

    Unknown / not-yet-supported channels fall back to the TikTok playbook with
    supported=False (callers surface a "no dedicated agent yet" note).
    """
    cid = (channel or DEFAULT_CHANNEL).strip().lower() or DEFAULT_CHANNEL
    supported = cid in SUPPORTED
    return Channel(
        id=cid,
        label=_LABELS.get(cid, titleize(cid)),
        supported=supported,
        playbook=cid if supported else DEFAULT_CHANNEL,
    )
