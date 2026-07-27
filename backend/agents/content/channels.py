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

# Channels with a dedicated, tuned playbook today.
SUPPORTED: set[str] = {"tiktok"}

# Friendly labels for known platforms (mirror agents.models.Platform).
_LABELS = {
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "twitter": "Twitter / X",
    "facebook": "Facebook",
    "threads": "Threads",
    "bluesky": "Bluesky",
    "pinterest": "Pinterest",
    "google_business": "Google Business",
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
        label=_LABELS.get(cid, cid.replace("_", " ").title()),
        supported=supported,
        playbook=cid if supported else DEFAULT_CHANNEL,
    )
