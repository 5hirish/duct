"""Where a plan's posts go, channel by channel (agents/content/channel_mix.py).

What earns a place here is the arithmetic a wrong answer would hide in: which
goal the brand's words name, what a goal counts per post, how far one plan
may move a channel's days, that every channel stays tested, and that one
channel's numbers never rank another's posts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agents.content.channel_mix import (
    HOLDS,
    LEADS,
    MAX_SHIFT,
    TRAILS,
    UNTESTED,
    Goal,
    GoalKind,
    allocate,
    build_mix,
    floor_days,
    goal_from,
    load_channel_mix,
    mix_snapshot,
    overreaching_hooks,
)
from agents.content.performance import INTENT, REACHED, PostSample, read_metric

INTENT_GOAL = Goal(GoalKind.INTENT)


def _post(channel: str, *, post_type: str = "slideshow", pillar: str = "", topic: str = "", **perf) -> PostSample:
    return PostSample(post_type=post_type, perf=perf, channel=channel, pillar=pillar, topic=topic)


# ---------------------------------------------------------------------------
# The goal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("words", "kind"), [
    ("Drive app downloads from TikTok", GoalKind.INTENT),
    ("Grow brand awareness", GoalKind.REACH),
    ("Build a community around the product", GoalKind.ENGAGEMENT),
    # A business outcome beats attention when both are named.
    ("Awareness that turns into signups", GoalKind.INTENT),
    ("", GoalKind.INTENT),
])
def test_the_goal_is_read_off_the_brands_words(words, kind):
    goal = goal_from(words)
    assert goal.kind == kind
    assert goal.source == words


def test_a_goal_counts_people_who_acted_and_unknown_stays_unknown():
    assert read_metric({"saves": 4, "share_count": 6}, INTENT) == 10
    # X reports no saves: its intent is its shares, not None and not zero-padded.
    assert read_metric({"share_count": 3, "view_count": 900}, INTENT) == 3
    assert read_metric({"view_count": 900}, INTENT) is None
    assert read_metric({"reach": 700, "view_count": 900}, REACHED) == 700
    assert read_metric({"view_count": 900}, REACHED) == 900


# ---------------------------------------------------------------------------
# Moving effort between channels
# ---------------------------------------------------------------------------


def test_with_nothing_to_compare_the_last_plans_split_holds():
    counts, standing = allocate(["tiktok", "linkedin"], 30, {"tiktok": 20, "linkedin": 10}, {})
    assert counts == {"tiktok": 20, "linkedin": 10}
    assert standing == {"tiktok": UNTESTED, "linkedin": UNTESTED}


def test_one_measured_channel_has_nothing_to_beat():
    counts, standing = allocate(["tiktok", "linkedin"], 30, {"tiktok": 15, "linkedin": 15}, {"tiktok": 40.0})
    assert counts == {"tiktok": 15, "linkedin": 15}
    assert standing == {"tiktok": HOLDS, "linkedin": UNTESTED}


def test_the_channel_that_earns_more_gains_days_but_at_most_a_quarter():
    counts, standing = allocate(
        ["tiktok", "instagram"], 30, {"tiktok": 15, "instagram": 15}, {"tiktok": 10.0, "instagram": 90.0},
    )
    assert standing == {"tiktok": TRAILS, "instagram": LEADS}
    assert counts["instagram"] > 15 > counts["tiktok"]
    # A ninefold gap still moves a quarter, not the whole plan; a day of rounding.
    assert counts["instagram"] <= round(15 * (1 + MAX_SHIFT)) + 1
    assert counts["tiktok"] >= round(15 * (1 - MAX_SHIFT)) - 1
    assert sum(counts.values()) == 30


def test_close_numbers_hold_their_share():
    counts, standing = allocate(
        ["tiktok", "instagram"], 30, {"tiktok": 15, "instagram": 15}, {"tiktok": 20.0, "instagram": 21.0},
    )
    assert standing == {"tiktok": HOLDS, "instagram": HOLDS}
    assert abs(counts["tiktok"] - counts["instagram"]) <= 1


def test_every_channel_keeps_a_post_a_week_however_it_did():
    counts, _ = allocate(
        ["tiktok", "linkedin", "blog"], 28, {"tiktok": 27, "linkedin": 1}, {"tiktok": 500.0, "linkedin": 1.0},
    )
    floor = floor_days(28, 3)
    assert floor == 4
    assert counts["linkedin"] >= floor and counts["blog"] >= floor  # the new channel too
    assert sum(counts.values()) == 28


def test_a_plan_too_short_for_every_floor_still_adds_up():
    channels = ["tiktok", "instagram", "youtube", "facebook", "twitter", "linkedin", "blog", "wordpress"]
    counts, _ = allocate(channels, 5, {}, {})
    assert sum(counts.values()) == 5
    assert floor_days(5, 8) == 0


def test_the_split_is_the_same_every_run():
    args = (["a", "b", "c"], 23, {"a": 8, "b": 8, "c": 7}, {"a": 3.0, "b": 9.0, "c": 5.0})
    assert allocate(*args) == allocate(*args)


# ---------------------------------------------------------------------------
# Each channel on its own history
# ---------------------------------------------------------------------------


def test_each_channel_is_ranked_on_its_own_posts():
    samples = [
        *[_post("tiktok", post_type="video", saves=40, share_count=10, view_count=9000) for _ in range(3)],
        *[_post("tiktok", post_type="slideshow", saves=5, share_count=1, view_count=4000) for _ in range(3)],
        *[_post("linkedin", post_type="text", pillar="build", share_count=2, view_count=300) for _ in range(3)],
        _post("pinterest", post_type="image", saves=999),  # not a channel the brand posts on
    ]
    mix = build_mix(samples, ["tiktok", "linkedin"], INTENT_GOAL, 30, None)
    tiktok, linkedin = mix.channels

    assert tiktok.performance.exploit == "video"
    assert tiktok.performance.ranked_by == INTENT
    # A text channel is judged as one: no visual type is named untested there.
    assert [g.key for g in linkedin.performance.types] == ["text"]
    assert linkedin.performance.posts == 3
    assert tiktok.goal_per_post.median == pytest.approx(28.0)  # median of 50, 50, 50, 6, 6, 6
    assert tiktok.standing == LEADS and linkedin.standing == TRAILS
    assert sum(c.days for c in mix.channels) == 30


def test_a_brand_that_named_no_channel_keeps_its_history():
    samples = [_post("tiktok", saves=5) for _ in range(3)] + [_post("instagram", saves=9) for _ in range(3)]
    assert [c.channel for c in build_mix(samples, [], INTENT_GOAL, 30, None).channels] == ["tiktok", "instagram"]
    assert [c.channel for c in build_mix([], [], INTENT_GOAL, 30, None).channels] == ["tiktok"]


def test_the_best_and_weakest_posts_are_named_by_topic():
    samples = [
        _post("tiktok", topic=f"topic {n}", pillar="face", saves=n, share_count=0) for n in (50, 3, 20, 1, 9)
    ]
    perf = build_mix(samples, ["tiktok"], INTENT_GOAL, 30, None).channels[0].performance
    assert [x.topic for x in perf.best] == ["topic 50", "topic 20"]
    assert [x.topic for x in perf.weakest] == ["topic 1", "topic 3"]


def test_the_last_plan_counts_days_by_the_channel_each_was_made_for():
    last_plan = [
        {"topic": "a", "platforms": ["tiktok", "instagram"]},
        {"topic": "b", "platforms": ["tiktok"]},
        {"topic": "c", "platforms": ["linkedin"]},
        {"topic": "d", "platforms": []},  # an old day with no platform was TikTok
    ]
    mix = build_mix([], ["tiktok", "instagram", "linkedin"], INTENT_GOAL, 8, last_plan)
    by = {c.channel: c for c in mix.channels}
    assert (by["tiktok"].last_days, by["linkedin"].last_days) == (3, 1)
    assert by["instagram"].last_days is None  # it rode along, it was not planned for
    assert mix.last_plan_days == 4


def test_a_plan_keeps_each_channels_facts_for_the_board():
    """The board says per channel what the plan scales and tests and how its
    share moved; those facts are code's, never the strategy's one sentence."""
    samples = [
        *[_post("tiktok", post_type="video", saves=40, share_count=10) for _ in range(3)],
        *[_post("tiktok", post_type="slideshow", saves=5, share_count=1) for _ in range(3)],
        *[_post("linkedin", post_type="text", share_count=2) for _ in range(3)],
    ]
    last_plan = [{"platforms": ["tiktok"]}] * 20 + [{"platforms": ["linkedin"]}] * 10
    snap = mix_snapshot(build_mix(samples, ["tiktok", "linkedin"], INTENT_GOAL, 30, last_plan))

    assert snap["goal"] == "intent"
    tiktok, linkedin = snap["channels"]
    assert (tiktok["channel"], tiktok["last_days"], tiktok["standing"]) == ("tiktok", 20, LEADS)
    assert tiktok["scaling"] == "video" and "image" in tiktok["testing"]
    assert (linkedin["last_days"], linkedin["standing"]) == (10, TRAILS)


def test_a_hook_the_history_has_not_proven_takes_at_most_a_quarter_of_a_channel():
    """One post tried transformation_reveal and a plan gave it 9 of 23 days."""
    samples = [
        PostSample(post_type="video", perf={"saves": 2}, channel="tiktok", hook_type="transformation_reveal"),
        *[PostSample(post_type="slideshow", perf={"saves": 5}, channel="tiktok", hook_type="myth_bust") for _ in range(3)],
    ]
    mix = build_mix(samples, ["tiktok"], INTENT_GOAL, 22, None)
    day = lambda hook: {"platforms": ["tiktok"], "hook_type": hook}  # noqa: E731
    days = [day("transformation_reveal")] * 9 + [day("myth_bust")] * 10 + [day("")] * 3

    (over,) = overreaching_hooks(mix, days)
    assert (over.hook, over.days, over.cap, over.channel_days) == ("transformation_reveal", 9, 6, 22)
    assert over.record == "1 measured post"
    assert overreaching_hooks(mix, [day("transformation_reveal")] * 6 + [day("x")] * 16)[0].hook == "x", (
        "a hook no post tried is held to the same cap, and a proven one is not"
    )


def test_the_block_tells_the_model_the_goal_the_days_and_each_channel():
    from agents.content.prompts import _channel_mix_stanza

    samples = [_post("tiktok", post_type="video", saves=10, share_count=2, view_count=1000) for _ in range(3)]
    block = _channel_mix_stanza(build_mix(samples, ["tiktok", "linkedin"], goal_from("More signups"), 14, None))

    assert block.startswith("<account_performance>") and block.endswith("</account_performance>")
    assert "conversions themselves are not measured" in block
    assert "- tiktok: " in block and "- linkedin: " in block
    assert "linkedin:\n" in block and "No published posts yet" in block


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch):
    from tests.conftest import make_sqlite_engine

    import db.session as db_session

    eng = make_sqlite_engine()
    monkeypatch.setattr(db_session, "get_engine", lambda: eng)
    return eng


def test_the_mix_is_loaded_from_published_posts_and_the_latest_plan(engine):
    from sqlmodel import Session

    from models.content import ContentPlan, ContentPost

    project = uuid4()
    at = datetime(2026, 10, 1, 18, tzinfo=timezone.utc)
    posted = [
        ContentPost(project_id=project, post_dir_slug=f"t{i}", post_type="video", platforms=["tiktok"],
                    pillar="face", topic=f"tiktok {i}", posted_at=at, perf={"saves": 10 + i})
        for i in range(3)
    ] + [
        ContentPost(project_id=project, post_dir_slug=f"l{i}", post_type="text", platforms=["linkedin"],
                    pillar="build", topic=f"linkedin {i}", posted_at=at, perf={"share_count": 2})
        for i in range(3)
    ]
    draft = ContentPost(project_id=project, post_dir_slug="d", post_type="video", platforms=["tiktok"],
                        perf={"saves": 999})
    older = ContentPlan(project_id=project, created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                        days=[{"topic": "x", "pillar": "p", "platforms": ["linkedin"]}] * 10)
    latest = ContentPlan(project_id=project, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc), days=[
        {"topic": "x", "pillar": "p", "platforms": ["tiktok"], "post_id": str(posted[0].id), "hook_type": "question"},
        {"topic": "y", "pillar": "p", "platforms": ["linkedin"]},
    ])
    with Session(engine) as db:
        db.add_all([*posted, draft, older, latest])
        db.commit()

    mix = load_channel_mix(project, ["tiktok", "linkedin"], INTENT_GOAL, 10)
    by = {c.channel: c for c in mix.channels}

    assert by["tiktok"].performance.posts == 3 and by["linkedin"].performance.posts == 3
    assert by["tiktok"].goal_per_post.median == 11  # the unpublished draft's 999 never counts
    assert (by["tiktok"].last_days, by["linkedin"].last_days, mix.last_plan_days) == (1, 1, 2)
    assert by["tiktok"].performance.bets["pillar"][0].key == "face"
    assert by["tiktok"].performance.bets["hook_type"][0].key == "question"
    assert sum(c.days for c in mix.channels) == 10
