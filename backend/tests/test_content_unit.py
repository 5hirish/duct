"""Unit-level tests for agents/content/.

Scope kept tight: only tests that catch real regressions live here.
Pure Pydantic round-trips, enum shape checks, and constructor smoke
tests have been removed — Pydantic + Python tests itself. Real-data
behaviour lives in tests/test_content_e2e.py and
tests/test_seed_maxaura.py.

What earns a place here:
  - Cache-stability of the orchestrator system prompt (huge cost lever)
  - Sub-agent JSON output → orchestrator persistence (the only path
    from sub-agent text → DB row, easy to break silently)
  - In-process MCP server build (single import + construction smoke)
  - Session registry lifecycle (in-memory but real concurrency surface)
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from agents.content.prompts import (
    build_orchestrator_system_prompt,
    build_plan_user_prompt,
)
from agents.content.schema import (
    ContentBrandContext,
    ContentPillar,
    ContentVisualAssets,
    make_session,
)
from agents.content.tools import build_content_mcp_server


def _brand(name: str = "MaxAura") -> ContentBrandContext:
    return ContentBrandContext(
        project_id=uuid4(),
        project_name=name,
        url=f"https://{name.lower()}.example.com",
        audience="women 16-35 into beauty",
        brand_voice="confident, warm",
        value_prop="real AI analysis of your selfie",
        content_goal="drive trial signups via saveable beauty education",
        pillars=[
            ContentPillar(id="face_shape", name="Face Shape", description="cuts by face shape"),
        ],
        visual=ContentVisualAssets(primary_color="#8B1A4A", style="editorial"),
    )


# ---------------------------------------------------------------------------
# Prompt-cache stability — the single biggest cost lever
# ---------------------------------------------------------------------------


def test_system_prompt_excludes_brand_so_anthropic_cache_hits():
    """Brand stanza must NOT live in system_prompt — it goes in the first
    user message so the system-prompt prefix stays identical across all
    users and all sessions, hitting the 1-hour Anthropic prompt cache.

    If someone re-inlines brand into the system prompt this assertion
    fails and they pay full input-token price on every turn.
    """
    sys_a = build_orchestrator_system_prompt(_brand("BrandA"), "plan_month")
    sys_b = build_orchestrator_system_prompt(_brand("BrandB"), "plan_month")
    assert sys_a == sys_b, "system prompt drifts between projects — cache will miss"
    # And the brand-stanza content must instead appear in the user message.
    user = build_plan_user_prompt(_brand("BrandA"), history=[], formats=[], avatars=[])
    assert "BrandA" in user


def test_system_prompt_advertises_essential_capabilities():
    """If the operating-loop / dispatch-policy / artifact contract is
    accidentally stripped, the model won't know what to do. One coarse
    assertion is enough — the prompt content is reviewed in PR diffs."""
    sys = build_orchestrator_system_prompt(_brand(), "plan_month")
    for must_have in ("<duct_report>", "submit_plan", "research_pillar",
                      "draft_post", "build_slides_html", "MODE: plan_month"):
        assert must_have in sys, f"system prompt missing critical phrase: {must_have!r}"


# ---------------------------------------------------------------------------
# In-process MCP server — single smoke test for SDK + tool registration
# ---------------------------------------------------------------------------


def test_mcp_server_builds_and_exposes_writer_tools():
    """Catches: SDK version mismatch, @tool decorator misuse, broken
    closure capture of project_id/emit/session."""
    session = make_session("t", uuid4(), "plan_month")
    srv = build_content_mcp_server(session.project_id, _noop, session)
    assert isinstance(srv, dict)
    assert srv.get("name") == "duct_content"
    assert srv.get("type") == "sdk"
    assert srv.get("instance") is not None


async def _noop(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Session registry — actual concurrency surface (chat queue + answer future)
# ---------------------------------------------------------------------------


def test_session_registry_lifecycle_closes_and_drains():
    """A close_session call must:
       - remove the session from the in-memory registry
       - send a None sentinel into the chat queue so the message
         generator unblocks
    These two together are the only way a long-running SSE stream
    cleanly terminates when the user navigates away. If close_session
    forgets to push the sentinel, the stream hangs until chat_idle_timeout.
    """
    from agents.content.v3.runner import (
        _sessions,
        close_session,
        create_draft_session,
        create_plan_session,
        get_session,
    )

    sid = "lifecycle-test"
    pid = uuid4()
    s = create_plan_session(sid, pid)
    assert get_session(sid) is s
    close_session(sid)
    assert sid not in _sessions

    # Sentinel reached the queue:
    drained = asyncio.run(_drain_first(s.chat_queue))
    assert drained is None

    # Draft session carries plan_id through (so PostDraft inserts attach
    # to the right plan, which is structurally important).
    plan_id = uuid4()
    sid2 = "lifecycle-test-2"
    s2 = create_draft_session(sid2, pid, plan_id=plan_id)
    assert s2.plan_id == plan_id
    close_session(sid2)


async def _drain_first(q) -> object:
    return await asyncio.wait_for(q.get(), timeout=1.0)


# ---------------------------------------------------------------------------
# Sub-agent dispatch name resolution — defensive but covers the SDK's
# documented-as-fuzzy key naming for the Agent tool input.
# ---------------------------------------------------------------------------


def test_extract_subagent_name_covers_known_sdk_key_variants():
    """The Agent tool's input shape isn't pinned in claude_agent_sdk docs;
    we accept the four plausible keys. If a future SDK release lands a
    new key name our STEP_STARTED chips silently say 'unknown' until we
    add it here — this test documents the contract for that update."""
    from agents.content.v3.runner import _extract_subagent_name
    for key in ("subagent_type", "agent", "agent_type", "name"):
        assert _extract_subagent_name({key: "draft_post"}) == "draft_post", key
    assert _extract_subagent_name({}) == "unknown"


# ---------------------------------------------------------------------------
# Frontend ↔ backend event-enum mirror — guard against drift
# ---------------------------------------------------------------------------


def test_frontend_content_events_mirror_backend_enums():
    """If a new ContentEvent or ContentStep lands without updating
    app/src/lib/contentEvents.js the frontend silently ignores the new
    event. This test fails loudly so we catch the drift in CI."""
    import os
    from agents.content.events import ContentEvent, ContentStep

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    js_path = os.path.join(repo_root, "app", "src", "lib", "contentEvents.js")
    if not os.path.exists(js_path):
        pytest.skip("frontend contentEvents.js not in this checkout")
    with open(js_path) as fh:
        js = fh.read()
    for ev in ContentEvent:
        assert f'"{ev.value}"' in js, f"frontend missing event: {ev.value}"
    for step in ContentStep:
        assert f'"{step.value}"' in js, f"frontend missing step: {step.value}"
