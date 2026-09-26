"""The account-history signals a content plan is written from (#224).

What earns a place here is the arithmetic a wrong answer would hide in: which
type is crowned, which is left to test, what an unrecorded metric counts as,
and whether a bet is graded against the post it produced. The prompt prose is
not asserted beyond what the model must be told (unknown is not zero).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agents.content.performance import (
    PROVEN,
    UNPROVEN,
    UNTESTED,
    PostSample,
    best_posting_times,
    load_account_performance,
    planned_bets,
    read_metric,
    summarise,
)


def _post(post_type: str, *, at: datetime | None = None, hook: str = "", bet: dict | None = None, **perf) -> PostSample:
    return PostSample(post_type=post_type, perf=perf, posted_at=at, hook_type=hook, bet=bet or {})


def _at(day: int, hour: int) -> datetime:
    # 2026-09-07 is a Monday, so day 0 is Mon, 1 is Tue, ...
    return datetime(2026, 9, 7 + day, hour, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Reading a metric
# ---------------------------------------------------------------------------


def test_each_key_convention_reads_the_same_metric():
    assert read_metric({"view_count": 900}, "views") == 900
    assert read_metric({"views": 900}, "views") == 900
    assert read_metric({"save_count": 12}, "saves") == 12
    assert read_metric({"saves": 12}, "saves") == 12
    # The app's manual form records completion as a percentage; the Perf
    # schema as a fraction. Both must land on one scale to be compared.
    assert read_metric({"completion_rate": 0.42}, "completion_rate") == pytest.approx(0.42)
    assert read_metric({"completionRate": 42}, "completion_rate") == pytest.approx(0.42)


def test_an_unrecorded_metric_is_unknown_not_zero():
    assert read_metric({}, "saves") is None
    assert read_metric({"saves": None}, "saves") is None
    assert read_metric({"saves": "12"}, "saves") is None
    assert read_metric({"saves": True}, "saves") is None
    assert read_metric(None, "saves") is None
    # A recorded zero is a real zero.
    assert read_metric({"saves": 0}, "saves") == 0


# ---------------------------------------------------------------------------
# Explore / exploit
# ---------------------------------------------------------------------------


def test_the_proven_leader_is_exploited_and_the_untested_type_is_explored():
    samples = (
        [_post("video", completion_rate=c, like_count=10) for c in (0.5, 0.4, 0.45)]
        # Slideshow has the likes; likes are not a signal.
        + [_post("slideshow", completion_rate=c, like_count=5000) for c in (0.2, 0.1, 0.15, 0.3)]
    )
    perf = summarise(samples)

    assert perf.ranked_by == "completion_rate"
    assert perf.exploit == "video"
    assert perf.explore == ["image"]
    assert [(g.key, g.verdict) for g in perf.types] == [
        ("video", PROVEN), ("slideshow", PROVEN), ("image", UNTESTED),
    ]


def test_a_type_nobody_measured_is_left_to_test_not_ranked_as_zero():
    """Video has three hand-logged completion rates; slideshow has more posts
    and none. Read as 0%, slideshow would look like a proven failure."""
    samples = [_post("video", completion_rate=0.3) for _ in range(3)] + [
        _post("slideshow", view_count=5000) for _ in range(6)
    ]
    perf = summarise(samples)

    slideshow = next(g for g in perf.types if g.key == "slideshow")
    assert slideshow.verdict == UNPROVEN
    assert slideshow.measures["completion_rate"].median is None
    assert slideshow.measures["completion_rate"].measured == 0
    assert perf.exploit == "video"
    # Untested before thin: no data at all is the bigger blind spot.
    assert perf.explore == ["image", "slideshow"]


def test_shares_rank_an_account_that_never_logs_metrics_by_hand():
    """PostBridge syncs views, likes, comments and shares — nothing else."""
    samples = [_post("slideshow", share_count=s, view_count=1000) for s in (40, 50, 60)] + [
        _post("video", share_count=s, view_count=1000) for s in (5, 6, 7)
    ]
    perf = summarise(samples)
    assert perf.ranked_by == "shares"
    assert perf.exploit == "slideshow"


def test_history_with_no_ranking_signal_crowns_nothing():
    samples = [_post("slideshow", like_count=100, view_count=1000) for _ in range(5)]
    perf = summarise(samples)
    assert perf.ranked_by is None
    assert perf.exploit is None
    assert perf.explore == ["video", "image", "slideshow"]


def test_no_history_explores_every_type():
    perf = summarise([])
    assert not perf.has_history
    assert perf.exploit is None
    assert perf.explore == ["slideshow", "video", "image"]


# ---------------------------------------------------------------------------
# Graded bets
# ---------------------------------------------------------------------------


def test_past_bets_are_graded_on_what_the_posts_earned():
    question = {"hook_type": "question", "funnel_stage": "Awareness", "objective": "saves"}
    curiosity = {"hook_type": "curiosity_gap", "funnel_stage": "conversion", "objective": "clicks"}
    samples = (
        [_post("video", bet=question, completion_rate=c) for c in (0.5, 0.55, 0.6)]
        + [_post("video", bet=curiosity, completion_rate=c) for c in (0.1, 0.2)]
        # Drafted outside any plan: its own hook still counts.
        + [_post("video", hook="authority_claim", completion_rate=0.3)]
    )
    perf = summarise(samples)

    hooks = perf.bets["hook_type"]
    assert [g.key for g in hooks] == ["question", "authority_claim", "curiosity_gap"]
    assert hooks[0].posts == 3
    assert hooks[0].measures["completion_rate"].median == pytest.approx(0.55)
    # Funnel stage and objective exist only on the plan; values normalise.
    assert [g.key for g in perf.bets["funnel_stage"]] == ["awareness", "conversion"]
    assert [g.key for g in perf.bets["objective"]] == ["saves", "clicks"]


def test_the_published_hook_wins_over_the_planned_one():
    samples = [_post("video", hook="pattern_interrupt", bet={"hook_type": "question"}, completion_rate=0.4)] * 3
    assert [g.key for g in summarise(samples).bets["hook_type"]] == ["pattern_interrupt"]


def test_planned_bets_follow_the_post_id_and_the_latest_plan_wins():
    post = str(uuid4())
    older = [{"topic": "t", "post_id": post, "hook_type": "question", "funnel_stage": "awareness"}]
    newer = [
        {"topic": "t", "post_id": post, "hook_type": "curiosity_gap", "objective": "saves"},
        {"topic": "unlinked", "hook_type": "question"},
        "not a day",
    ]
    assert planned_bets([older, newer]) == {
        post: {"hook_type": "curiosity_gap", "funnel_stage": "", "objective": "saves"},
    }


# ---------------------------------------------------------------------------
# Best posting times
# ---------------------------------------------------------------------------


def test_best_times_rank_hours_and_weekdays_by_median_views():
    samples = [
        _post("video", at=_at(1, 18), view_count=9000),
        _post("video", at=_at(3, 18), view_count=11000),
        _post("video", at=_at(1, 9), view_count=1000),
        _post("video", at=_at(4, 9), view_count=1500),
        # One viral post alone does not name the best hour.
        _post("video", at=_at(5, 3), view_count=900000),
        # No views recorded: not evidence about timing.
        _post("video", at=_at(1, 18)),
    ]
    hours, weekdays, timed = best_posting_times(samples)

    assert timed == 5
    assert [(w.label, w.posts, w.median_views) for w in hours] == [("18:00", 2, 10000), ("09:00", 2, 1250)]
    # Tuesday is the only weekday with two posts that recorded views.
    assert [(w.label, w.posts, w.median_views) for w in weekdays] == [("Tue", 2, 5000)]


def test_best_times_wait_for_enough_posts():
    samples = [_post("video", at=_at(1, 18), view_count=100) for _ in range(4)]
    assert best_posting_times(samples) == ([], [], 4)


# ---------------------------------------------------------------------------
# The prompt block
# ---------------------------------------------------------------------------


def test_the_block_says_unknown_in_words_and_names_both_choices():
    from agents.content.prompts import _performance_stanza

    samples = [_post("video", completion_rate=0.3, view_count=1000) for _ in range(3)] + [
        _post("slideshow", view_count=5000) for _ in range(2)
    ]
    block = _performance_stanza(summarise(samples))

    assert block.startswith("<account_performance>") and block.endswith("</account_performance>")
    assert "completion 30.0% (3)" in block
    assert "completion not recorded" in block
    assert "exploit: video" in block
    assert "explore: image, slideshow" in block


def test_the_block_for_no_history_and_for_an_unreadable_one():
    from agents.content.prompts import _performance_stanza

    assert "No published posts yet" in _performance_stanza(summarise([]))
    assert "could not be read" in _performance_stanza(None)


def test_the_block_rides_in_the_plan_turn_not_the_system_prompt():
    from agents.content.prompts import build_orchestrator_system_prompt, build_plan_user_prompt
    from agents.content.schema import ContentBrandContext

    brand = ContentBrandContext(project_id=uuid4(), project_name="Solo")
    turn = build_plan_user_prompt(brand, history=[], formats=[], avatars=[], performance=summarise([]))
    assert "<account_performance>" in turn
    assert "<account_performance>\n" not in build_orchestrator_system_prompt(brand, "plan_month")


# ---------------------------------------------------------------------------
# The stored side: loading history, recording the strategy
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch):
    from tests.conftest import make_sqlite_engine

    import agents.content.tools as content_tools
    import db.session as db_session

    eng = make_sqlite_engine()
    monkeypatch.setattr(db_session, "get_engine", lambda: eng)
    monkeypatch.setattr(content_tools, "get_engine", lambda: eng)
    return eng


def test_history_is_loaded_from_published_posts_and_their_plans(engine):
    from sqlmodel import Session

    from models.content import ContentPlan, ContentPost

    project = uuid4()
    posted = [
        ContentPost(project_id=project, post_dir_slug=f"p{i}", post_type="video",
                    posted_at=_at(i, 18), perf={"completionRate": 50}, hook_type="")
        for i in range(3)
    ]
    unposted = ContentPost(project_id=project, post_dir_slug="draft", post_type="image", perf={"saves": 99})
    other_project = ContentPost(project_id=uuid4(), post_dir_slug="x", post_type="image",
                                posted_at=_at(0, 1), perf={"saves": 99})
    plan = ContentPlan(project_id=project, days=[
        {"topic": "t", "pillar": "p", "post_id": str(p.id), "hook_type": "question", "funnel_stage": "awareness"}
        for p in posted
    ])
    with Session(engine) as db:
        db.add_all([*posted, unposted, other_project, plan])
        db.commit()

    perf = load_account_performance(project)

    assert perf.posts == 3
    assert perf.exploit == "video"
    assert perf.explore == ["slideshow", "image"]
    assert [g.key for g in perf.bets["hook_type"]] == ["question"]
    assert perf.bets["hook_type"][0].measures["completion_rate"].median == pytest.approx(0.5)


def test_submit_plan_records_the_strategy_it_chose(engine):
    from sqlmodel import Session

    from agents.content.schema import make_session
    from agents.content.tools import build_content_tools_lc
    from models.content import ContentPlan

    events: list[dict] = []

    async def emit(body: dict) -> None:
        events.append(body)

    session = make_session("s", uuid4(), "plan_month")
    tool = {t.name: t for t in build_content_tools_lc(session.project_id, emit, session)}["submit_plan"]
    strategy = {
        "exploit": "Video",
        "exploit_evidence": "median completion 50% over 3 posts",
        "explore": "image",
        "explore_evidence": "no image posts yet",
    }
    plan = {
        "type": "plan",
        "project_id": str(session.project_id),
        "strategy": strategy,
        "days": [{"topic": "t", "pillar": "p", "post_type": "image", "hook_type": "question",
                  "funnel_stage": "awareness", "objective": "saves"}],
    }
    result = json.loads(asyncio.run(tool.ainvoke({"plan": plan})))
    assert result.get("status") != "error", result

    with Session(engine) as db:
        row = db.get(ContentPlan, session.plan_id)
    assert row.strategy["exploit"] == "video"  # normalised
    assert row.strategy["explore"] == "image"
    assert row.days[0]["hook_type"] == "question" and row.days[0]["objective"] == "saves"
    generated = next(e for e in events if e.get("plan_id"))
    assert generated["payload"]["strategy"]["explore_evidence"] == "no image posts yet"


def test_a_strategy_naming_an_unknown_type_is_refused():
    from pydantic import ValidationError

    from agents.content.schema import PlanDraft

    base = {"type": "plan", "project_id": str(uuid4()), "days": [{"topic": "t", "pillar": "p"}]}
    PlanDraft.model_validate({**base, "strategy": {"exploit": "", "explore": ""}})
    with pytest.raises(ValidationError):
        PlanDraft.model_validate({**base, "strategy": {"exploit": "reels"}})
