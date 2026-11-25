"""The audience panel's check against the brand's own results
(agents/content/panel.py): which past posts it is tested on, what it is
shown, and how its order is scored."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from agents.content.panel import (
    PANEL_MAX_POSTS,
    PANEL_MIN_POSTS,
    PanelPost,
    opening_line,
    panel_check,
    panel_posts,
    short_id,
)
from agents.content.performance import INTENT

NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


@dataclass
class Row:
    days_ago: int
    saves: int | None = 10
    platforms: list = field(default_factory=lambda: ["tiktok"])
    headline: str = "An opening"
    caption: str = ""
    id: UUID = field(default_factory=uuid4)

    @property
    def posted_at(self):
        return NOW - timedelta(days=self.days_ago)

    @property
    def slides(self):
        return [{"slide_id": "slide-01", "headline": self.headline}] if self.headline else []

    @property
    def perf(self):
        return {} if self.saves is None else {"saves": self.saves}


def test_the_opening_is_what_a_feed_shows_first():
    assert opening_line([{"headline": "Your ads leak", "subtext": "here's where"}], "ignored") == "Your ads leak here's where"
    assert opening_line([], "\n  Is it working?\nThe rest of the post") == "Is it working?"
    assert opening_line(None, None) == ""


def test_the_panel_is_tested_on_its_own_channel_when_that_has_enough_posts():
    tiktok = [Row(i) for i in range(1, PANEL_MIN_POSTS + 1)]
    linkedin = [Row(0, platforms=["linkedin"])]

    chosen = panel_posts([*linkedin, *tiktok], channel="tiktok", metric=INTENT)

    assert [p.id for p in chosen] == [short_id(r.id) for r in tiktok]   # newest first, the other channel left out


def test_too_few_on_the_channel_widens_to_all_and_too_few_anywhere_is_no_test():
    mixed = [Row(1, platforms=["linkedin"]), *[Row(i) for i in range(2, PANEL_MIN_POSTS + 1)]]
    assert len(panel_posts(mixed, channel="tiktok", metric=INTENT)) == PANEL_MIN_POSTS

    unmeasured = [Row(i, saves=None) for i in range(1, 10)]
    assert panel_posts(unmeasured, channel="tiktok", metric=INTENT) == []


def test_the_post_under_review_and_wordless_posts_are_never_in_the_test():
    rows = [Row(i) for i in range(1, PANEL_MAX_POSTS + 4)]
    rows.append(Row(0, headline=""))

    chosen = panel_posts(rows, channel="tiktok", metric=INTENT, exclude=rows[0].id)

    assert len(chosen) == PANEL_MAX_POSTS and short_id(rows[0].id) not in {p.id for p in chosen}


def _posts(values):
    return [PanelPost(id=f"p{i}", opening=f"o{i}", value=v) for i, v in enumerate(values)]


def test_an_order_is_scored_on_the_pairs_it_puts_the_right_way_round():
    posts = _posts([50, 40, 30, 20, 10])

    perfect = panel_check(["p0", "p1", "p2", "p3", "p4"], posts, INTENT)
    swapped = panel_check(["p1", "p0", "p2", "p3", "p4"], posts, INTENT)
    backwards = panel_check(["p4", "p3", "p2", "p1", "p0"], posts, INTENT)

    assert (perfect.agreed, perfect.pairs, perfect.fit) == (10, 10, "tracks")
    assert (swapped.agreed, swapped.fit) == (9, "tracks")
    assert (backwards.agreed, backwards.fit) == (0, "chance")


def test_ties_unknown_ids_and_repeats_tell_nothing():
    posts = _posts([30, 30, 20, 10, 5])

    check = panel_check(["P0", "p1", "nope", "p1", "p2", "p3", "p4"], posts, INTENT)

    assert (check.posts, check.pairs, check.agreed) == (5, 9, 9)   # the tie p0/p1 is not a pair


def test_fewer_ranked_than_the_minimum_is_no_check():
    assert panel_check(["p0", "p1"], _posts([5, 4, 3, 2, 1]), INTENT) is None
    assert panel_check([f"p{i}" for i in range(5)], _posts([7] * 5), INTENT) is None
