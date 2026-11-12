"""Which channels a project posts on, and what it says about each.

Stored in ``Project.brand_channels`` beside the crawl's ``active_channels``,
so no migration: the crawl found where the brand already posts, and the
person decides here which of those (and which others) Duct plans for. A
channel is on when the person switched it on, or, before anyone touched the
list, when the crawl found it. A channel can be on with no scheduler account
behind it: the person posts there by hand, and the plan still covers it.

Shape of ``brand_channels``::

    {
      "active_channels": ["tiktok", "x"],          # the crawl's list (legacy, kept)
      "primary_publisher": "zernio",               # the scheduler posts go out through
      "channels": {
        "tiktok": {"enabled": true, "username": "real_glowupdaily", "display_name": "",
                   "bio": "...", "notes": "...", "target_media": ["video", "slideshow"]},
        "blog":   {"enabled": true, "username": "", "notes": "Hugo site, publish by hand"}
      }
    }
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from agents.content.channels import OFFERED, Platform, brand_platforms
from agents.content.platform_guides import MEDIA_KINDS

CHANNELS_KEY = "channels"
PRIMARY_KEY = "primary_publisher"
LEGACY_KEY = "active_channels"


@dataclass
class ChannelProfile:
    enabled: bool = False
    username: str = ""
    display_name: str = ""
    bio: str = ""
    notes: str = ""
    # Empty means every kind of media the channel takes.
    target_media: list[str] = field(default_factory=list)

    def words(self) -> dict:
        """The profile as the prompt reads it (platform_guides._profile_lines)."""
        return asdict(self)


@dataclass
class ChannelConfig:
    primary_publisher: str = ""
    channels: dict[str, ChannelProfile] = field(default_factory=dict)
    # True once the person has saved the list; before that the crawl's
    # channels stand in for it.
    chosen: bool = False

    def enabled(self) -> list[str]:
        """The channels Duct plans for, in the offered order."""
        return [cid for cid in OFFERED if self.channels.get(cid, ChannelProfile()).enabled]

    def profiles(self) -> dict[str, dict]:
        return {cid: p.words() for cid, p in self.channels.items() if p.enabled}


def _profile_from(raw: object) -> ChannelProfile:
    if not isinstance(raw, dict):
        return ChannelProfile()
    media = raw.get("target_media")
    return ChannelProfile(
        enabled=bool(raw.get("enabled")),
        username=str(raw.get("username") or "").strip().lstrip("@"),
        display_name=str(raw.get("display_name") or "").strip(),
        bio=str(raw.get("bio") or "").strip(),
        notes=str(raw.get("notes") or "").strip(),
        target_media=[m for m in media if m in MEDIA_KINDS] if isinstance(media, list) else [],
    )


def load_channel_config(
    brand_channels: dict | None, linked: Iterable[tuple[str, str]] = (),
) -> ChannelConfig:
    """The project's channel choices, with the crawl's channels standing in
    until the person has made any.

    ``linked`` is ``(platform, username)`` for each account the project linked
    at a scheduler. A linked account is the strongest evidence a channel is on,
    so before the person has chosen it switches the channel on, and its handle
    stands in for one they have not typed. On 2026-11-08 the tab showed
    LinkedIn "Off" over a linked LinkedIn account with an empty handle field."""
    blob = brand_channels or {}
    raw = blob.get(CHANNELS_KEY)
    chosen = isinstance(raw, dict) and bool(raw)
    channels: dict[str, ChannelProfile] = {}
    if chosen:
        for cid, prof in raw.items():
            if cid in OFFERED:
                channels[cid] = _profile_from(prof)
    else:
        for cid in brand_platforms(blob.get(LEGACY_KEY)):
            if cid in OFFERED:
                channels[cid] = ChannelProfile(enabled=True)
    for platform, username in linked:
        if platform not in OFFERED:
            continue
        prof = channels.setdefault(platform, ChannelProfile())
        if not chosen:
            prof.enabled = True
        if not prof.username and username:
            prof.username = str(username).strip().lstrip("@")
    return ChannelConfig(
        primary_publisher=str(blob.get(PRIMARY_KEY) or "").strip(),
        channels=channels,
        chosen=chosen,
    )


def active_platforms(brand_channels: dict | None, linked: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Where the brand posts, as Platform values: the person's list once they
    made one, the crawl's and the linked accounts' before. The one answer
    every 'Posts on' reads."""
    return load_channel_config(brand_channels, linked).enabled()


def linked_pairs(links: Iterable[object]) -> list[tuple[str, str]]:
    """``(platform, username)`` from linked-account rows, whatever their class."""
    return [
        (str(getattr(link, "platform", "") or ""), str(getattr(link, "username", "") or ""))
        for link in links
    ]


def save_channel_config(brand_channels: dict | None, config: ChannelConfig) -> dict:
    """``brand_channels`` with the choices written in and everything else kept."""
    blob = dict(brand_channels or {})
    blob[PRIMARY_KEY] = config.primary_publisher
    blob[CHANNELS_KEY] = {
        cid: asdict(prof) for cid, prof in config.channels.items() if cid in OFFERED
    }
    # The legacy list follows the choice, so an older reader agrees with a newer one.
    blob[LEGACY_KEY] = [str(Platform(cid)) for cid in config.enabled()]
    return blob
