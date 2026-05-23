"""Phase 2 smoke tests for agents/content/.

Covers what we can test without a live Anthropic API key:
  - imports + module structure
  - sub-agent definitions match SDK shape
  - MCP server constructs
  - PlanDraft / PostDraft Pydantic round-trip
  - prompt assembly produces non-empty, well-formed output
  - <duct_report> JSON parser (happy + fenced-markdown paths)

Live end-to-end coverage lands in Phase 6 (e2e tests against the routes).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from claude_agent_sdk import AgentDefinition

from agents.content.events import ContentEvent, ContentStep
from agents.content.prompts import (
    DRAFT_POST_PROMPT,
    ORCHESTRATOR_BASE_PROMPT,
    RESEARCH_PILLAR_PROMPT,
    build_orchestrator_system_prompt,
    build_plan_user_prompt,
    build_post_user_prompt,
)
from agents.content.schema import (
    Character,
    ContentBrandContext,
    ContentPillar,
    ContentVisualAssets,
    Day,
    ImagePrompt,
    PlanDraft,
    PostDraft,
    make_session,
)
from agents.content.subagents import DRAFT_POST_AGENT, RESEARCH_PILLAR_AGENT
from agents.content.tools import build_content_mcp_server
from agents.content.v3.runner import (
    ClaudeContentRunner,
    _parse_report_json,
    create_draft_session,
    create_plan_session,
)
from agents.models import Platform


def _brand() -> ContentBrandContext:
    return ContentBrandContext(
        project_id=uuid4(),
        project_name="MaxAura",
        url="https://maxauralab.com",
        tagline="AI style analysis",
        audience="women 16-35 into beauty",
        brand_voice="friendly expert",
        value_prop="find your face shape, color season, ideal hairstyles",
        content_goal="drive sign-ups via saveable beauty education",
        pillars=[
            ContentPillar(id="face_shape", name="Face Shape", description="cuts by face shape"),
            ContentPillar(id="color_aura", name="Color Aura", description="seasonal color analysis"),
        ],
        visual=ContentVisualAssets(primary_color="#8B1A4A", style="editorial"),
    )


# ---------------------------------------------------------------------------
# Event + step enums
# ---------------------------------------------------------------------------


def test_content_event_covers_plan_and_post_payloads():
    assert ContentEvent.PLAN_GENERATED.value     == "plan_generated"
    assert ContentEvent.POST_DRAFT_UPDATED.value == "post_draft_updated"
    assert ContentEvent.STEP_STARTED.value       == "step_started"
    assert ContentEvent.REPORT_CHUNK.value       == "report_chunk"


def test_content_step_includes_dispatch_subagent():
    assert ContentStep.DISPATCH_SUBAGENT.value == "dispatch_subagent"


# ---------------------------------------------------------------------------
# Sub-agent definitions
# ---------------------------------------------------------------------------


def test_research_pillar_agent_definition_shape():
    assert isinstance(RESEARCH_PILLAR_AGENT, AgentDefinition)
    assert RESEARCH_PILLAR_AGENT.description
    assert RESEARCH_PILLAR_AGENT.prompt is RESEARCH_PILLAR_PROMPT
    assert RESEARCH_PILLAR_AGENT.model == "claude-haiku-4-5-20251001"
    assert "WebSearch" in (RESEARCH_PILLAR_AGENT.tools or [])
    assert "WebFetch"  in (RESEARCH_PILLAR_AGENT.tools or [])


def test_draft_post_agent_definition_shape():
    assert isinstance(DRAFT_POST_AGENT, AgentDefinition)
    assert DRAFT_POST_AGENT.description
    assert DRAFT_POST_AGENT.prompt is DRAFT_POST_PROMPT
    assert DRAFT_POST_AGENT.model == "claude-sonnet-4-6"
    assert "mcp__duct_content__fetch_format_library" in (DRAFT_POST_AGENT.tools or [])


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


def test_mcp_server_builds_with_expected_shape():
    session = make_session("t", uuid4(), "plan_month")

    async def _emit(_event: dict) -> None:
        return None

    srv = build_content_mcp_server(session.project_id, _emit, session)
    assert isinstance(srv, dict)
    assert srv.get("name") == "duct_content"
    assert srv.get("type") == "sdk"
    assert srv.get("instance") is not None


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


def test_plan_draft_round_trip():
    pid = uuid4()
    plan = PlanDraft(
        type="plan",
        project_id=pid,
        name="Q2 Plan",
        days=[
            Day(day=1, topic="face shape basics", pillar="face_shape", status="pending"),
            Day(day=2, topic="color season intro", pillar="color_aura", status="pending"),
        ],
        character=Character(name="Aura", voice="friendly expert"),
    )
    plan2 = PlanDraft.model_validate_json(plan.model_dump_json())
    assert plan2.project_id == pid
    assert len(plan2.days) == 2
    assert plan2.days[0].pillar == "face_shape"
    assert plan2.type == "plan"


def test_post_draft_round_trip():
    pid = uuid4()
    post = PostDraft(
        type="post",
        project_id=pid,
        post_dir_slug="2026-04-01-001",
        pillar="face_shape",
        topic="wolf cut for oval",
        slide_count=7,
        slides_html="<html><body><div class='slide'>x</div></body></html>",
        caption="If you have an oval face…",
        hashtags=["#faceshape", "#wolfcut"],
        hook_type="identity_challenge",
        hook_text="You've been styling wrong",
        image_prompts=[ImagePrompt(slide_id="slide-01", prompt="young woman, oval, soft window light")],
        platforms=[Platform.TIKTOK, Platform.INSTAGRAM],
    )
    post2 = PostDraft.model_validate_json(post.model_dump_json())
    assert post2.project_id == pid
    assert post2.slide_count == 7
    assert Platform.INSTAGRAM in post2.platforms
    assert post2.image_prompts[0].slide_id == "slide-01"
    assert post2.type == "post"


def test_post_draft_rejects_extra_fields():
    pid = uuid4()
    # extra='forbid' on PostDraft — surface model errors instead of silently
    # swallowing typos in the orchestrator's payload.
    with pytest.raises(Exception):
        PostDraft.model_validate({
            "type": "post",
            "project_id": str(pid),
            "post_dir_slug": "x",
            "pillar": "p",
            "topic": "t",
            "slides_html": "<html/>",
            "unknown_field": "should fail",
        })


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_orchestrator_prompt_embeds_brand_context():
    sys = build_orchestrator_system_prompt(_brand(), "plan_month")
    assert "MaxAura" in sys
    assert "face_shape" in sys
    assert "<duct_report>" in sys
    assert "submit_plan" in sys
    assert "research_pillar" in sys
    assert "draft_post"     in sys
    # mode-specific tail
    assert "MODE: plan_month" in sys
    # base preamble is included
    assert ORCHESTRATOR_BASE_PROMPT.split("\n", 1)[0] in sys


def test_plan_user_prompt_lists_history():
    p = build_plan_user_prompt(
        _brand(),
        history=[{"day_index": 1, "topic": "face shapes", "pillar": "face_shape", "status": "posted"}],
        formats=[{"slug": "format-d", "name": "Default UGC"}],
        avatars=[],
    )
    assert "face_shape" in p
    assert "format-d"  in p


def test_post_user_prompt_uses_day_or_freeform():
    day_prompt = build_post_user_prompt(
        _brand(),
        Day(day=5, topic="wolf cut", pillar="face_shape", format_style="D"),
        recent_posts=[{"topic": "X", "pillar": "Y", "hook_type": "curiosity_gap"}],
    )
    assert "Day 5" in day_prompt
    assert "wolf cut" in day_prompt

    free = build_post_user_prompt(
        _brand(),
        None,
        topic="color season basics",
        pillar="color_aura",
        format_style="A",
    )
    assert "Standalone draft" in free
    assert "color season basics" in free


# ---------------------------------------------------------------------------
# <duct_report> JSON parser
# ---------------------------------------------------------------------------


def test_parse_report_json_happy_path():
    raw = '{"type":"plan","project_id":"00000000-0000-0000-0000-000000000000","days":[]}'
    payload = _parse_report_json(raw)
    assert payload is not None
    assert payload["type"] == "plan"


def test_parse_report_json_strips_markdown_fences():
    raw = """```json
{"type":"post","project_id":"00000000-0000-0000-0000-000000000000","post_dir_slug":"x","pillar":"p","topic":"t","slides_html":"<html/>","caption":"c"}
```"""
    payload = _parse_report_json(raw)
    assert payload is not None
    assert payload["type"] == "post"
    assert payload["pillar"] == "p"


def test_parse_report_json_returns_none_on_garbage():
    assert _parse_report_json("this is not JSON at all") is None


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------


def test_session_registry_create_and_close():
    from agents.content.v3.runner import _sessions, close_session, get_session

    sid = "test-session-1"
    pid = uuid4()
    s = create_plan_session(sid, pid)
    assert s.session_id == sid
    assert s.mode == "plan_month"
    assert get_session(sid) is s

    close_session(sid)
    assert get_session(sid) is None
    assert sid not in _sessions


def test_create_draft_session_carries_plan_id():
    sid = "test-session-2"
    pid = uuid4()
    plan_id = uuid4()
    s = create_draft_session(sid, pid, plan_id=plan_id)
    try:
        assert s.mode == "draft_post"
        assert s.plan_id == plan_id
    finally:
        from agents.content.v3.runner import close_session
        close_session(sid)


# ---------------------------------------------------------------------------
# Runner constructor
# ---------------------------------------------------------------------------


def test_runner_requires_api_key():
    with pytest.raises(ValueError):
        ClaudeContentRunner(api_key="")


def test_runner_constructs_with_defaults():
    r = ClaudeContentRunner(api_key="sk-fake")
    assert r._api_key == "sk-fake"


# ---------------------------------------------------------------------------
# make_session — async queue wiring
# ---------------------------------------------------------------------------


def test_make_session_initialises_queues():
    async def _run():
        s = make_session("x", uuid4(), "plan_month")
        await s.chat_queue.put({"hello": "world"})
        await s.event_queue.put({"event": "test"})
        got_msg = await s.chat_queue.get()
        got_ev = await s.event_queue.get()
        assert got_msg["hello"] == "world"
        assert got_ev["event"]  == "test"

    asyncio.run(_run())
