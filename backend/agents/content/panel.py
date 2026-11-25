"""The audience panel's check against the brand's own results.

The pre-publish review role-plays the brand's personas. Research on these
"digital twins" (Columbia's 2026 mega-study, Stanford's 1,052 interviews)
says a twin's verdict on one post is mostly the model's own average opinion,
leaning kind, while its *order* of several options carries some signal. So
the panel is checked on the one thing that can be checked: it ranks the
openings of posts the brand already published, without their numbers, and
this module scores that ranking against what the posts actually earned on
the brand's content goal.

The model never sees a number: ``panel_posts`` hands it short ids and
openings, the ranking comes back as ids, and ``panel_check`` scores it here.
A reviewer cannot argue its way to "tracks".

No database and no model call: the tools pass rows in.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from agents.content.channels import primary_channel
from agents.content.performance import read_metric
from agents.content.schema import HOOK_MAX, PanelCheck, PanelFit

# Fewer measured posts than this and an order means nothing: five posts are
# ten pairs, the least that separates a panel from a coin with any margin.
PANEL_MIN_POSTS = 5
# More than this and the openings crowd the reviewer's context for little
# gain; recent posts are also the audience as it is now.
PANEL_MAX_POSTS = 8
# Share of pairs put the right way round. A coin gets half; 0.7 of ten pairs
# happens by luck about one time in six, which is why "tracks" still reads
# as a lean, not a guarantee, in the app's words.
TRACKS_AT = 0.7
LOOSE_AT = 0.55
# Enough of a UUID to tell eight posts apart, short enough not to look like
# something to look up.
SHORT_ID_LEN = 8


@dataclass(frozen=True)
class PanelPost:
    """One past post the panel ranks: what it is shown, and what it earned."""

    id: str
    opening: str
    value: float


def short_id(post_id: Any) -> str:
    return str(post_id).replace("-", "")[:SHORT_ID_LEN]


def opening_line(slides: Sequence[Any] | None, caption: str | None) -> str:
    """What a feed shows first: slide 1's words on a visual post, else the
    caption's first line. The panel judges openings only, as a scroller does."""
    first = next((s for s in slides or [] if isinstance(s, dict)), None)
    if first:
        words = " ".join(
            t for t in ((first.get("headline") or "").strip(), (first.get("subtext") or "").strip()) if t
        )
        if words:
            return words[:HOOK_MAX]
    line = next((ln.strip() for ln in (caption or "").splitlines() if ln.strip()), "")
    return line[:HOOK_MAX]


def panel_posts(rows: Iterable[Any], *, channel: str | None, metric: str, exclude: Any = None) -> list[PanelPost]:
    """The posts to test the panel on: published, measured on ``metric``,
    with an opening to show, newest first. The post's own channel when it has
    enough of them, since a LinkedIn audience is not a TikTok one; otherwise
    every channel, which is a weaker test but a test. Empty when even that
    is too few."""
    usable: list[tuple[Any, PanelPost]] = []
    for row in rows:
        if exclude is not None and row.id == exclude:
            continue
        value = read_metric(row.perf, metric)
        opening = opening_line(row.slides, row.caption)
        if value is None or not opening or row.posted_at is None:
            continue
        usable.append((row, PanelPost(short_id(row.id), opening, value)))
    usable.sort(key=lambda pair: pair[0].posted_at, reverse=True)
    same = [p for row, p in usable if channel and primary_channel(row.platforms) == channel]
    chosen = same if len(same) >= PANEL_MIN_POSTS else [p for _, p in usable]
    return chosen[:PANEL_MAX_POSTS] if len(chosen) >= PANEL_MIN_POSTS else []


def shuffled(posts: Sequence[PanelPost], seed: Any = None) -> list[PanelPost]:
    """The order the reviewer sees: newest-first would hint at nothing, but a
    stable shuffle keeps any order from being read as a ranking."""
    out = list(posts)
    random.Random(str(seed)).shuffle(out)
    return out


def panel_check(order: Iterable[str], posts: Sequence[PanelPost], metric: str) -> PanelCheck | None:
    """Score the panel's order (most likely to earn first) against what the
    posts earned. Unknown and repeated ids are ignored; None when fewer than
    PANEL_MIN_POSTS were ranked, or every pair tied."""
    known = {p.id: p.value for p in posts}
    ranked: list[str] = []
    for raw in order or []:
        pid = str(raw).strip().lower()
        if pid in known and pid not in ranked:
            ranked.append(pid)
    if len(ranked) < PANEL_MIN_POSTS:
        return None
    pairs = agreed = 0
    for i, higher in enumerate(ranked):
        for lower in ranked[i + 1:]:
            a, b = known[higher], known[lower]
            if a == b:
                continue
            pairs += 1
            agreed += a > b
    if not pairs:
        return None
    share = agreed / pairs
    fit = PanelFit.TRACKS if share >= TRACKS_AT else PanelFit.LOOSE if share >= LOOSE_AT else PanelFit.CHANCE
    return PanelCheck(metric=metric, posts=len(ranked), pairs=pairs, agreed=agreed, fit=fit)


__all__ = [
    "PANEL_MAX_POSTS",
    "PANEL_MIN_POSTS",
    "PanelPost",
    "opening_line",
    "panel_check",
    "panel_posts",
    "short_id",
    "shuffled",
]
