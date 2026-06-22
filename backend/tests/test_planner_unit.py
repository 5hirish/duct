"""Unit tests for the Content Planner agent (content_planner).

Pure unit — no DB / network. Covers the registry spec, config validation,
the reused PlanDraft/Day shape extensions, and the runner's chat helpers.
"""

from __future__ import annotations

from uuid import uuid4


def test_content_planner_registered_and_active():
    from agents.registry import AGENT_REGISTRY, AgentType, get_spec

    assert AgentType.CONTENT_PLANNER in AGENT_REGISTRY
    spec = get_spec("content_planner")
    assert spec is not None and spec.active


def test_planner_config_caps_geographies_and_completeness():
    from agents.planner.schema import PlannerConfig

    cfg = PlannerConfig(
        platforms=["tiktok", "instagram"],
        posts_per_day=2,
        geographies=["United States", "India", "UK", "Canada"],
        primary_objective="trial_signups",
    )
    assert cfg.geographies == ["United States", "India", "UK"]  # capped to 3
    assert cfg.is_complete()

    # Missing platforms, geographies, OR primary_objective → incomplete (gate fires).
    assert not PlannerConfig(platforms=[], geographies=["US"], primary_objective="sales").is_complete()
    assert not PlannerConfig(platforms=["tiktok"], geographies=[], primary_objective="sales").is_complete()
    assert not PlannerConfig(platforms=["tiktok"], geographies=["US"]).is_complete()


def test_plandraft_carries_strategy_and_day_planner_fields():
    from datetime import datetime

    from agents.content.schema import Day, PlanDraft

    day = Day(
        topic="hook",
        pillar="education",
        post_type="video",
        scheduled_at=datetime(2026, 6, 18, 19, 10),
        best_time_note="7:10pm IST — peak",
        angle="What nobody tells you…",
        rationale="rides trend X; hits pain point Y",
    )
    draft = PlanDraft(
        project_id=uuid4(),
        name="week of Jun 18",
        days=[day],
        strategy={
            "narrative_arc": "build authority then convert",
            "sequencing_rationale": "value first, offer last",
            "content_mix": {"video": 4, "slideshow": 2, "image": 1},
            "weekly_theme": "myth-busting week",
        },
    )
    assert draft.strategy.weekly_theme == "myth-busting week"
    assert draft.strategy.content_mix["video"] == 4
    d0 = draft.days[0]
    assert d0.post_type == "video" and d0.angle and d0.rationale and d0.scheduled_at is not None


def test_chat_text_flattens_content():
    # _chat_text drives the /refresh-posts interception: a chat turn's content
    # may be a string or a content-block list; only text blocks count.
    from agents.planner.v3.runner import _chat_text

    assert _chat_text("hello") == "hello"
    assert _chat_text([{"type": "text", "text": "a"}, {"type": "image", "x": 1}]) == "a"
    assert _chat_text(None) == ""


# ---------------------------------------------------------------------------
# Content-type performance ranking — drives performance-weighted content_mix
# (explore + exploit). Pure function, no DB.
# ---------------------------------------------------------------------------


def test_rank_content_types_crowns_proven_leader_and_seeds_untested():
    """Video has the best completion+saves with enough posts → it's the proven
    `leader`. A type with NO history (image) is `untested` and must be surfaced
    for an exploration slot."""
    from agents.planner.data import _rank_content_types

    tp = _rank_content_types({
        "video":     {"posts": 5, "median_completion": 0.42, "median_saves": 30, "median_views": 1200},
        "slideshow": {"posts": 8, "median_completion": 0.21, "median_saves": 12, "median_views": 3000},
    })
    assert tp["leader"] == "video"                       # exploit the proven winner
    assert tp["untested_types"] == ["image"]             # explore what has no data
    assert [r["type"] for r in tp["ranked"]] == ["video", "slideshow"]


def test_rank_content_types_cold_start_for_video_seeds_exploration():
    """Only slideshow history → video+image are untested. The planner must still
    be told to test them (so a brand-new format like video isn't starved)."""
    from agents.planner.data import _rank_content_types

    tp = _rank_content_types({
        "slideshow": {"posts": 6, "median_completion": 0.3, "median_saves": 20, "median_views": 2000},
    })
    assert tp["leader"] == "slideshow"
    assert "video" in tp["untested_types"] and "image" in tp["untested_types"]


def test_rank_content_types_does_not_crown_a_single_lucky_post():
    """A type with 1 high post is `unproven`, not the leader — we don't scale a
    format off one lucky clip; we flag it for more testing."""
    from agents.planner.data import _rank_content_types

    tp = _rank_content_types({
        "slideshow": {"posts": 10, "median_completion": 0.25, "median_saves": 15, "median_views": 2500},
        "video":     {"posts": 1,  "median_completion": 0.50, "median_saves": 40, "median_views": 1500},
    })
    assert tp["leader"] == "slideshow"                   # proven, despite lower medians
    assert tp["unproven_types"] == ["video"]
