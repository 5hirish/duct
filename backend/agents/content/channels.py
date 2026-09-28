"""Channel seam for the Content agent.

A post is one row whatever it is bound for: ``caption`` is its words,
``slides`` its pictures (optional for a text post), ``replies`` the author's
own follow-ups under it. What differs between platforms is rules, not shape,
and the rules live here, in one table, so the agent's writer, the publish path
and the app read the same numbers: how long the words may be, where the feed
folds them, whether the platform takes a post with no media, and how many of
the replies go out with it.

A post's *primary channel* (platforms[0]) picks the playbook the agent drafts
with. Three have one: TikTok (visual), and X and LinkedIn (text). Any other
channel falls back to the TikTok playbook with ``supported=False`` so the UI
and the prompt can say no dedicated agent exists yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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


class Playbook(StrEnum):
    """The prompt families the agent can draft with. Each supported channel
    maps to one; a channel without one borrows TikTok's."""

    TIKTOK   = "tiktok"
    TWITTER  = "twitter"
    LINKEDIN = "linkedin"


@dataclass(frozen=True)
class ChannelRules:
    """What a platform accepts, as far as drafting and publishing care.

    ``max_chars`` is the platform's own ceiling on one post's words — X's is
    for a standard account, the one every account has. Counted as Python
    ``len`` (code points), which is exact for the Latin text these playbooks
    write; X weighs CJK and most emoji double and every URL as 23, and a
    playbook that keeps links out of the post (PostBridge strips them from a
    tweet anyway) never meets the URL case.

    ``fold_chars`` is where the feed cuts to "see more" (0: it does not), so
    the preview can show the reader's first screen. ``publishable_replies`` is
    how many of ``replies`` PostBridge posts with it: one on X and Threads,
    as a ``first_comment``; none elsewhere, where a reply is for the author
    to paste. ``requires_media`` is PostBridge's own list of platforms that
    reject a post without a picture or video, and ``synced_metrics`` its list
    of those it reports views and likes for (TikTok, YouTube, Instagram,
    Facebook); anywhere else the numbers are typed in from the platform.
    """

    label:               str
    max_chars:           int
    fold_chars:          int = 0
    publishable_replies: int = 0
    requires_media:      bool = False
    hashtags:            bool = True    # does the playbook expect them at all
    synced_metrics:      bool = False   # PostBridge reports this platform's numbers


# Keyed by the enum so a Platform without rules is a visible hole (the unit
# test asserts the table is total). Labels are spelled out because "TikTok"
# and "Twitter / X" don't fall out of titleize. StrEnum keys match plain
# strings, so rules_for() can index it with a bare channel id.
RULES: dict[Platform, ChannelRules] = {
    Platform.TIKTOK:          ChannelRules("TikTok", 4000, requires_media=True, synced_metrics=True),
    Platform.INSTAGRAM:       ChannelRules("Instagram", 2200, fold_chars=125, requires_media=True, synced_metrics=True),
    Platform.YOUTUBE:         ChannelRules("YouTube", 5000, requires_media=True, synced_metrics=True),
    Platform.LINKEDIN:        ChannelRules("LinkedIn", 3000, fold_chars=210, hashtags=False),
    Platform.TWITTER:         ChannelRules("Twitter / X", 280, publishable_replies=1, hashtags=False),
    Platform.FACEBOOK:        ChannelRules("Facebook", 63206, synced_metrics=True),
    Platform.THREADS:         ChannelRules("Threads", 500, publishable_replies=1),
    Platform.BLUESKY:         ChannelRules("Bluesky", 300),
    Platform.PINTEREST:       ChannelRules("Pinterest", 500, requires_media=True),
    Platform.GOOGLE_BUSINESS: ChannelRules("Google Business", 1500),
}

# Channels with a dedicated, tuned playbook today, and which one each uses.
PLAYBOOKS: dict[str, Playbook] = {
    Platform.TIKTOK:   Playbook.TIKTOK,
    Platform.TWITTER:  Playbook.TWITTER,
    Platform.LINKEDIN: Playbook.LINKEDIN,
}
SUPPORTED: set[str] = {str(p) for p in PLAYBOOKS}

# The playbooks whose deliverable is words first: a text post, no slides.
TEXT_PLAYBOOKS: frozenset[str] = frozenset({Playbook.TWITTER, Playbook.LINKEDIN})

DEFAULT_CHANNEL = "tiktok"

# The ceiling for a channel id the table does not know — a stored row from a
# vendor that added a platform first reads, rather than crashing.
_UNKNOWN_MAX_CHARS = 2200


@dataclass(frozen=True)
class Channel:
    """Resolved channel for a drafting session."""

    id: str                # requested channel, e.g. "youtube"
    label: str             # display label, e.g. "YouTube"
    supported: bool        # True only when a dedicated playbook exists
    playbook: str          # the playbook whose prompt rules we actually apply
    rules: ChannelRules

    @property
    def text_first(self) -> bool:
        return self.playbook in TEXT_PLAYBOOKS


def _normalise(channel: str | None) -> str:
    return (str(channel or "") or DEFAULT_CHANNEL).strip().lower() or DEFAULT_CHANNEL


def primary_channel(platforms: list | None) -> str:
    """The post's primary channel — first platform, or the default."""
    if isinstance(platforms, list) and platforms:
        first = platforms[0]
        return getattr(first, "value", first) or DEFAULT_CHANNEL
    return DEFAULT_CHANNEL


# The site crawl names channels by the host it found a profile on
# (agents/audit/draft._SOCIAL_HOSTS), which calls X "x"; posts use
# PostBridge's wire names, which call it "twitter".
_ALIASES: dict[str, str] = {"x": Platform.TWITTER}


def brand_platforms(active_channels: list | None) -> list[str]:
    """The brand's active channels as Platform values, in their order, minus
    anything Duct cannot post to. Where a plan or a draft looks for "the
    brand's channels" — the crawl found the profiles, so start from those."""
    out: list[str] = []
    for raw in active_channels or []:
        if not isinstance(raw, str):
            continue
        cid = _ALIASES.get(raw.strip().lower(), raw.strip().lower())
        if cid in RULES and cid not in out:
            out.append(str(Platform(cid)))
    return out


def rules_for(channel: str | None) -> ChannelRules:
    cid = _normalise(channel)
    return RULES.get(cid) or ChannelRules(titleize(cid), _UNKNOWN_MAX_CHARS)


def resolve(channel: str | None) -> Channel:
    """Resolve a requested channel to its playbook and rules.

    Unknown / not-yet-supported channels fall back to the TikTok playbook with
    supported=False (callers surface a "no dedicated agent yet" note).
    """
    cid = _normalise(channel)
    rules = rules_for(cid)
    return Channel(
        id=cid,
        label=rules.label,
        supported=cid in SUPPORTED,
        playbook=str(PLAYBOOKS.get(cid, Playbook.TIKTOK)),
        rules=rules,
    )


def channel_payload(channel: str | None) -> dict:
    """The channel as the app reads it: id, playbook, and the rules the
    preview counts against. Sent with every post so the app never keeps its
    own copy of a character limit."""
    ch = resolve(channel)
    return {
        "id": ch.id, "supported": ch.supported, "playbook": ch.playbook,
        "text_first": ch.text_first, **asdict(ch.rules),
    }


def copy_problems(channel: str | None, caption: str, replies: list[str] | None = None) -> list[str]:
    """What is wrong with a post's words for its channel, as sentences a model
    or a person can act on. Empty when it fits. The limits are the platform's
    own, so an over-length post is not a style note: it does not publish."""
    rules = rules_for(channel)
    out: list[str] = []
    caption = caption or ""
    if len(caption) > rules.max_chars:
        out.append(f"The post is {len(caption)} characters; {rules.label} allows {rules.max_chars}.")
    for i, reply in enumerate(replies or [], start=1):
        reply = reply or ""
        if not reply.strip():
            out.append(f"Reply {i} is empty.")
        elif len(reply) > rules.max_chars:
            out.append(f"Reply {i} is {len(reply)} characters; {rules.label} allows {rules.max_chars}.")
    return out
