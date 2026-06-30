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
    build_post_user_prompt,
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
    sys_a = build_orchestrator_system_prompt(_brand("BrandA"), "draft_post")
    sys_b = build_orchestrator_system_prompt(_brand("BrandB"), "draft_post")
    assert sys_a == sys_b, "system prompt drifts between projects — cache will miss"
    # And the brand-stanza content must instead appear in the user message.
    user = build_post_user_prompt(_brand("BrandA"), None, topic="face shapes", pillar="face_shape")
    assert "BrandA" in user


def test_system_prompt_advertises_essential_capabilities():
    """If the operating-loop / dispatch-policy / artifact contract is
    accidentally stripped, the model won't know what to do. One coarse
    assertion is enough — the prompt content is reviewed in PR diffs."""
    sys = build_orchestrator_system_prompt(_brand(), "draft_post")
    for must_have in ("<duct_artifact>", "submit_post_draft",
                      "research_pillar", "draft_post", "STRUCTURED SLIDES",
                      "MODE: draft_post"):
        assert must_have in sys, f"system prompt missing critical phrase: {must_have!r}"


# ---------------------------------------------------------------------------
# In-process MCP server — single smoke test for SDK + tool registration
# ---------------------------------------------------------------------------


def test_mcp_server_builds_and_exposes_writer_tools():
    """Catches: SDK version mismatch, @tool decorator misuse, broken
    closure capture of project_id/emit/session."""
    session = make_session("t", uuid4(), "draft_post")
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
        close_session,
        create_draft_session,
        get_session,
    )

    sid = "lifecycle-test"
    pid = uuid4()
    s = create_draft_session(sid, pid)
    assert get_session(sid) is s
    close_session(sid)
    assert get_session(sid) is None

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


def test_unified_agents_route_creates_contentsession():
    """The unified session factory must build a ContentSession (not the default
    AuditSession) for tiktok_studio draft_post, build a PlannerSession for
    content_planner, reject plan_month on tiktok_studio (planning moved to the
    planner), and 422 on a missing project_id."""
    from uuid import uuid4

    import pytest
    from fastapi import HTTPException

    from agents.content.schema import ContentSession
    from agents.content.v3.runner import close_session, get_session
    from agents.planner.schema import PlannerSession
    from agents.registry import AgentType
    from routes.agents import _create_session_for

    pid = uuid4()
    plan_id = uuid4()
    s2 = _create_session_for(
        AgentType.TIKTOK_STUDIO,
        "ufold-draft",
        {"mode": "draft_post", "project_id": str(pid), "plan_id": str(plan_id)},
    )
    assert isinstance(s2, ContentSession) and s2.mode == "draft_post" and s2.plan_id == plan_id
    assert s2.agent_type == "tiktok_studio"
    assert get_session("ufold-draft") is s2
    close_session("ufold-draft")

    # Content Studio no longer plans — plan_month is rejected.
    with pytest.raises(HTTPException):
        _create_session_for(
            AgentType.TIKTOK_STUDIO, "ufold-plan", {"mode": "plan_month", "project_id": str(pid)}
        )

    # The Content Planner owns plans (mode=update_plan → PlannerSession).
    sp = _create_session_for(
        AgentType.CONTENT_PLANNER, "ufold-planner", {"mode": "update_plan", "project_id": str(pid)}
    )
    assert isinstance(sp, PlannerSession)
    assert sp.mode == "update_plan" and sp.project_id == pid
    assert sp.agent_type == "content_planner"
    assert get_session("ufold-planner") is sp
    close_session("ufold-planner")

    with pytest.raises(HTTPException):
        _create_session_for(AgentType.TIKTOK_STUDIO, "ufold-bad", {"mode": "draft_post"})


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
# Writer-tool upfront validators — defends the new pattern's value prop
# ---------------------------------------------------------------------------


def test_writer_validator_accepts_both_wrapper_shapes_and_denies_with_corrective_text():
    """The two things this validator must do that aren't already Pydantic's job:
       1. Unwrap both `{"post": {...}}` and `{...}` directly (the model
          uses both shapes depending on how it interprets input_schema).
       2. When it denies, the message must tell the model what to do next
          ('call submit_post_draft again'). Without that hint the model
          retries blindly. This is the entire value prop of borrowing the
          audit branch's validate-and-deny pattern.

    The planner's submit_plan validator shares this same validate-and-deny
    pattern (just a different schema), so one test covers the shape.
    """
    from agents.content.v3.runner import _validate_submit_post_draft

    pid = uuid4()
    valid = {
        "type": "post",
        "project_id": str(pid),
        "post_dir_slug": "2026-06-01-001",
        "pillar": "face_shape",
        "topic": "x",
        "slides_html": "<html/>",
        "caption": "c",
    }
    # Both wrapper shapes pass.
    assert _validate_submit_post_draft({"post": valid}, pid) is None
    assert _validate_submit_post_draft(valid, pid)            is None

    # Invalid payload denies with corrective text.
    deny = _validate_submit_post_draft(
        {"type": "post", "project_id": str(pid)},  # missing required fields
        pid,
    )
    assert deny is not None
    assert "call submit_post_draft again" in deny.message


def test_writer_validator_blocks_cross_project_writes():
    """Multi-tenant safety: a payload carrying someone else's project_id
    must be rejected. Without this guard the agent could persist a draft
    into the wrong project's content_posts row."""
    from agents.content.v3.runner import _validate_submit_post_draft

    session_pid = uuid4()
    wrong = {
        "type": "post",
        "project_id": str(uuid4()),  # not session_pid
        "post_dir_slug": "x",
        "pillar": "p",
        "topic": "t",
        "slides_html": "<html/>",
        "caption": "c",
    }
    deny = _validate_submit_post_draft(wrong, session_pid)
    assert deny is not None
    assert "project_id mismatch" in deny.message
    assert str(session_pid)      in deny.message


def test_generate_image_validator_coalesces_legacy_and_multi_ref_keys():
    """The @tool accepts BOTH `input_asset_id` (single, legacy) and
    `input_asset_ids` (list, new). The validator must coalesce them into
    the Pydantic shape's single list field before validating — otherwise
    `extra=forbid` rejects the legacy key and the deny-path fires for
    every existing caller. Catches that regression class."""
    from agents.content.v3.runner import _validate_generate_image
    from uuid import uuid4

    # Legacy single-id only — must pass.
    assert _validate_generate_image({
        "prompt": "a red apple", "input_asset_id": str(uuid4()),
    }) is None

    # New list only — must pass.
    assert _validate_generate_image({
        "prompt": "a red apple", "input_asset_ids": [str(uuid4()), str(uuid4())],
    }) is None

    # Both keys with overlap — should not duplicate, should not deny.
    shared = str(uuid4())
    assert _validate_generate_image({
        "prompt": "a red apple", "input_asset_id": shared,
        "input_asset_ids": [shared, str(uuid4())],
    }) is None

    # Over the cap of 3 refs — must deny with actionable text.
    deny = _validate_generate_image({
        "prompt": "x",
        "input_asset_ids": [str(uuid4()) for _ in range(4)],
    })
    assert deny is not None
    assert "max 3" in deny.message


def test_generate_image_validator_accepts_global_library_url_refs():
    """A reference id may be a repo-bundled global library URL
    ('/static/references/...') instead of a DB UUID — the tool resolves it
    from disk. The validator must NOT reject it through the UUID-typed
    request model, but it MUST still count toward the max-3 cap. Catches
    the regression where every camera-ref call gets denied."""
    from uuid import uuid4

    from agents.content.v3.runner import _validate_generate_image

    lib = "/static/references/camera/selfie-talking/IMG_5885.jpeg"

    # Single global library ref — must pass.
    assert _validate_generate_image({
        "prompt": "p", "input_asset_ids": [lib],
    }) is None

    # Mixed [character UUID, camera library URL] — the slide 2-5 pattern.
    assert _validate_generate_image({
        "prompt": "p", "input_asset_ids": [str(uuid4()), lib],
    }) is None

    # Globals still count toward the cap: 4 distinct refs (mixed) must deny.
    deny = _validate_generate_image({
        "prompt": "p",
        "input_asset_ids": [str(uuid4()), str(uuid4()), lib, lib + "x"],
    })
    assert deny is not None
    assert "max 3" in deny.message


# ---------------------------------------------------------------------------
# Frontend ↔ backend event-enum mirror — guard against drift
# ---------------------------------------------------------------------------


def test_frontend_content_events_are_valid_backend_events():
    """Every event/step the content frontend references must be a real, shared
    backend value. Event names now live once in agents/core/events.py as a
    superset shared across all agents (AgentEvent/AgentStep); each frontend file
    mirrors the subset its agent uses. This guards against the frontend
    referencing an unknown or typo'd event/step."""
    import os
    import re

    from agents.content.events import ContentEvent, ContentStep

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    js_path = os.path.join(repo_root, "app", "src", "lib", "contentEvents.js")
    if not os.path.exists(js_path):
        pytest.skip("frontend contentEvents.js not in this checkout")
    with open(js_path) as fh:
        js = fh.read()
    valid = {e.value for e in ContentEvent} | {s.value for s in ContentStep}
    referenced = set(re.findall(r':\s*"([a-z_0-9]+)"', js))
    unknown = referenced - valid
    assert not unknown, f"contentEvents.js references unknown events/steps: {unknown}"


# ---------------------------------------------------------------------------
# Pre-flight enrichment — local scan + prompt stanza
# ---------------------------------------------------------------------------


def test_research_stanza_omits_empty_context_keeps_prompt_clean():
    """First-run projects (no posts, no enrichment) must not get a
    pollution-y empty <content_research> block in their kickoff prompt.
    Otherwise the orchestrator wastes tokens on noise."""
    from agents.content.prompts import _research_stanza
    from agents.content.schema import ContentResearchContext

    assert _research_stanza(None) == ""
    assert _research_stanza(ContentResearchContext()) == ""


def test_research_stanza_renders_pillar_history_and_trends():
    """When the enrichment ran, the kickoff prompt must include the
    fields the orchestrator's prompt instructs it to consult: pillar
    history (with days_since + recent topics) and the four trend
    categories. If any of these go missing the orchestrator quietly
    falls back to dispatching research_pillar sub-agents unnecessarily."""
    from agents.content.prompts import _research_stanza
    from agents.content.schema import (
        ContentResearchContext,
        PillarHistorySignal,
        TrendSignal,
    )

    ctx = ContentResearchContext(
        total_posts_to_date=12,
        days_since_last_post=3,
        pillar_history=[
            PillarHistorySignal(
                pillar="face_shape",
                posts_count=4,
                days_since_last_post=2,
                recent_topics=["wolf cut for oval", "side parts"],
                recent_hook_types=["identity_challenge", "curiosity_gap"],
                median_save_rate=0.062,
            ),
            PillarHistorySignal(
                pillar="color_aura",
                posts_count=1,
                days_since_last_post=45,
                recent_topics=["winter palette intro"],
            ),
        ],
        trending_sounds=[TrendSignal(kind="sound", label="aesthetic lofi 2026",
                                     why_it_works="calm vocals fit beauty content",
                                     evidence_url="https://tiktok.com/discover/lofi")],
        trending_hashtags=[TrendSignal(kind="hashtag", label="#auramaxxing",
                                       why_it_works="audience self-identifier")],
        trending_hooks=[TrendSignal(kind="hook", label="things nobody tells you about [X]",
                                    why_it_works="curiosity gap drives saves")],
        trending_styles=[TrendSignal(kind="style", label="POV-text overlay frame 1")],
        audience_insights=["audience prefers slideshows posted 8-10am local"],
        enrichment_notes=["competitor X is leaning hard on Format A"],
    )
    out = _research_stanza(ctx)
    # Block opens + closes properly
    assert out.startswith("<content_research>")
    assert out.endswith("</content_research>")
    # Pillar history surfaces days_since and recent topics so the
    # orchestrator can balance pillar distribution
    assert "face_shape" in out
    assert "color_aura" in out
    assert "45d ago" in out
    assert "wolf cut for oval" in out
    # Each trend category renders
    assert "trending_sounds" in out and "lofi 2026" in out
    assert "trending_hashtags" in out and "auramaxxing" in out
    assert "trending_hooks" in out and "things nobody tells you" in out
    assert "trending_styles" in out and "POV-text overlay" in out
    # Notes + audience insights surface
    assert "audience_insights" in out
    assert "notes" in out


def test_local_signals_handles_empty_db_gracefully():
    """When the project has no posts (first-run), local scan must not
    raise and must return an empty-but-valid ContentResearchContext.

    No mocking-Pydantic; we run against a real call with no DB
    connection, which exercises the early-return path."""
    from unittest.mock import patch
    from agents.content.enrichment import _local_content_signals

    with patch("agents.content.enrichment.get_engine", return_value=None):
        ctx = _local_content_signals(uuid4())
    assert ctx.pillar_history == []
    assert ctx.total_posts_to_date == 0
    assert ctx.days_since_last_post is None


def test_enrich_returns_local_signals_when_no_api_key():
    """Graceful degradation: empty api_key skips the sub-agent and
    returns local signals only. This is the path that fires when
    ANTHROPIC_API_KEY isn't set (dev / unit env)."""
    import asyncio
    from unittest.mock import patch
    from agents.content.enrichment import enrich_content_context
    from agents.content.schema import ContentBrandContext

    brand = ContentBrandContext(project_id=uuid4(), project_name="X")
    with patch("agents.content.enrichment.get_engine", return_value=None):
        ctx = asyncio.run(enrich_content_context(brand, api_key=""))
    # Empty but well-formed — sub-agent was correctly skipped
    assert ctx.trending_sounds == []
    assert ctx.trending_hashtags == []


# ---------------------------------------------------------------------------
# CLI startup-failure diagnosis + retry (agents/content/v3/runner.py)
#
# The `claude` subprocess can exit 1 during initialize() — most often a
# transient subscription usage/rate limit on the OAuth path. The SDK surfaces
# this opaquely ("Command failed with exit code 1 / Check stderr output for
# details"). These tests pin the diagnosis helpers that turn that into an
# actionable, correctly-grouped signal — the bit that's easy to silently break.
# ---------------------------------------------------------------------------


# NB: the stderr-capture / failure-message / rate-limit classification logic is
# tested directly in tests/test_agent_core.py (it now lives in core/claude_sdk.py).
# Here we only cover the content-specific Sentry wiring (agent="content" tags).


def test_sentry_startup_report_fingerprints_by_kind_and_never_raises(monkeypatch):
    from agents.core import claude_sdk

    scopes: list = []

    class _Scope:
        def __init__(self):
            self.tags, self.ctx, self.fingerprint, self.level = {}, {}, None, None

        def set_tag(self, k, v):
            self.tags[k] = v

        def set_context(self, k, v):
            self.ctx[k] = v

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured: dict = {}

    class _FakeSentry:
        def push_scope(self):
            sc = _Scope()
            scopes.append(sc)
            return sc

        def capture_exception(self, exc):
            captured["exc"] = exc

        def capture_message(self, msg, level=None):
            captured["msg"] = (msg, level)

    import sys

    monkeypatch.setitem(sys.modules, "sentry_sdk", _FakeSentry())

    claude_sdk.report_startup_failure_to_sentry(
        RuntimeError("boom"),
        agent="content",
        session_id="s1",
        mode="draft_post",
        attempts=3,
        exit_code=1,
        stderr="429 usage limit reached",
        rate_limited=True,
    )
    sc = scopes[-1]
    assert captured["exc"].args == ("boom",)
    assert sc.tags["content.failure_kind"] == "rate_limit"
    assert sc.level == "warning"
    assert sc.fingerprint == ["content-cli-startup", "rate_limit"]
    assert sc.ctx["content_startup"]["exit_code"] == 1

    # A hard crash groups separately and reports at error level.
    claude_sdk.report_startup_failure_to_sentry(
        RuntimeError("segfault"),
        agent="content",
        session_id="s2",
        mode="draft_post",
        attempts=3,
        exit_code=139,
        stderr="Segmentation fault",
        rate_limited=False,
    )
    sc2 = scopes[-1]
    assert sc2.fingerprint == ["content-cli-startup", "startup_crash"]
    assert sc2.level == "error"


def test_isolated_config_dir_separates_state_but_shares_oauth_login(tmp_path, monkeypatch):
    # A backend worker must not share ~/.claude (sessions, locks, plugin/security
    # bootstrap) with an interactive Claude Code on the same box — that shared
    # state is the leading suspect for intermittent CLI exit-1 at startup.
    import os

    from agents.core import claude_sdk

    fake_home = tmp_path / ".claude"
    fake_home.mkdir()
    (fake_home / ".credentials.json").write_text("{}")
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.delenv("DUCT_CONTENT_CLAUDE_CONFIG_DIR", raising=False)

    kw = dict(env_var="DUCT_CONTENT_CLAUDE_CONFIG_DIR", suffix="duct-content", log_prefix="content")

    # OAuth path (no api key): isolated dir created, live creds symlinked in.
    iso = claude_sdk.isolated_config_dir("", **kw)
    assert iso is not None and iso != str(fake_home)
    link = os.path.join(iso, ".credentials.json")
    assert os.path.islink(link)
    assert os.readlink(link) == str(fake_home / ".credentials.json")

    # API-key path: dir still isolated, but no credential symlink is needed.
    iso2 = tmp_path / "viakey"
    monkeypatch.setenv("DUCT_CONTENT_CLAUDE_CONFIG_DIR", str(iso2))
    assert claude_sdk.isolated_config_dir("sk-test", **kw) == str(iso2)
    assert not os.path.exists(os.path.join(str(iso2), ".credentials.json"))

    # Explicit opt-out falls back to the default ~/.claude.
    monkeypatch.setenv("DUCT_CONTENT_CLAUDE_CONFIG_DIR", "0")
    assert claude_sdk.isolated_config_dir("", **kw) is None


def test_jsonable_coerces_db_unsafe_types_and_caps_pathological_payloads():
    """Tool inputs/outputs land in a JSONB column. _jsonable must coerce
    non-JSON types (UUID, datetime) so the write can't fail, and truncate a
    runaway blob so one tool call can't bloat the conversation log."""
    from datetime import datetime
    from agents.content.persistence import _jsonable, _MAX_TOOL_PAYLOAD

    coerced = _jsonable({"post_id": uuid4(), "when": datetime(2026, 6, 14), "slides": [{"i": 1}]})
    assert isinstance(coerced["post_id"], str)     # UUID → str, write-safe
    assert isinstance(coerced["when"], str)        # datetime → str
    assert coerced["slides"] == [{"i": 1}]         # plain JSON preserved

    big = _jsonable({"blob": "x" * (_MAX_TOOL_PAYLOAD + 1)})
    assert big["_truncated"] is True and "preview" in big

    # A non-serializable object must degrade to its string form, never raise.
    class _Weird:
        def __repr__(self):
            return "WEIRD"
    assert _jsonable(_Weird()) == "WEIRD"


def test_reprime_block_excludes_tool_events():
    """tool_use / tool_result are persisted for forensics + restore, but must
    NOT leak into the re-prime transcript — otherwise stale tool I/O gets
    re-injected into the model's context on resume (token bloat + confusion)."""
    from agents.content.persistence import build_reprime_block
    from models.content import AgentConversation, AgentEvent as AgentEventRow

    conv = AgentConversation(agent_type="tiktok_studio", project_id=uuid4(), summary="")
    events = [
        AgentEventRow(conversation_id=conv.id, seq=1, kind="user", data={"content": "draft it"}),
        AgentEventRow(conversation_id=conv.id, seq=2, kind="tool_use",
                      data={"name": "submit_post_draft", "input": {"post_dir_slug": "2026-06-14-001"}}),
        AgentEventRow(conversation_id=conv.id, seq=3, kind="tool_result",
                      data={"name": "submit_post_draft", "result": {"ok": True}}),
        AgentEventRow(conversation_id=conv.id, seq=4, kind="assistant", data={"text": "done"}),
    ]
    block = build_reprime_block(conv, events)
    assert "draft it" in block and "done" in block        # conversational turns kept
    assert "submit_post_draft" not in block               # tool events excluded
    assert "2026-06-14-001" not in block


def test_generated_slide_image_prompt_is_locked_on_bulk_reemit():
    """The bulk re-emit (submit_post_draft) must never rewrite a GENERATED
    slide's image_prompt — that is how a 2170-char realism prompt silently
    collapsed to a 75-char stub and produced plastic output. The lock is
    structural (image present), not a length heuristic: even a *longer* incoming
    prompt is ignored on this path; deliberate changes go through edit_slide.
    A slide with no image yet is still being drafted, so refinements pass."""
    from types import SimpleNamespace
    from agents.content.tools import _merge_slide_images, _resolved_image_prompt
    from agents.content.schema import Slide

    RICH = "detailed realism prompt: visible pores, asymmetry, film grain, no plastic skin"
    generated = SimpleNamespace(slides=[{
        "slide_id": "slide-01", "image_prompt": RICH, "image_url": "https://cdn/x.png",
        "image_asset_id": None, "image_prompt_used": RICH,
    }])

    # generated slide: a shorter incoming prompt is IGNORED, image carried forward
    short = _merge_slide_images([Slide(slide_id="slide-01", image_prompt="round face selfie")], generated)
    assert short[0].image_prompt == RICH
    assert short[0].image_url == "https://cdn/x.png"
    # generated slide: even a LONGER incoming is locked (use edit_slide instead)
    longer = _merge_slide_images([Slide(slide_id="slide-01", image_prompt=RICH + " extra detail")], generated)
    assert longer[0].image_prompt == RICH
    # generated slide: omitted (empty) prompt never deletes the stored one
    omitted = _merge_slide_images([Slide(slide_id="slide-01", image_prompt="")], generated)
    assert omitted[0].image_prompt == RICH

    # un-generated slide (no image): drafting refinements pass through, shorter or not
    draft = SimpleNamespace(slides=[{"slide_id": "slide-02", "image_prompt": RICH, "image_url": ""}])
    refined = _merge_slide_images([Slide(slide_id="slide-02", image_prompt="tighter v2")], draft)
    assert refined[0].image_prompt == "tighter v2"
    # ...but an omitted prompt still doesn't wipe a stored one even while drafting
    kept = _merge_slide_images([Slide(slide_id="slide-02", image_prompt="")], draft)
    assert kept[0].image_prompt == RICH

    # helper: no length math anywhere
    assert _resolved_image_prompt("short", RICH, True) == RICH          # locked
    assert _resolved_image_prompt("short", RICH, False) == "short"      # drafting
    assert _resolved_image_prompt("", RICH, False) == RICH              # omission
    assert _resolved_image_prompt("anything", "", True) == "anything"   # nothing stored


def test_attach_image_syncs_prompt_and_provenance_no_false_stale():
    """When generate_image attaches an image (prompt_used given), the slide's
    image_prompt AND image_prompt_used are both set to the generating prompt — so
    the slide is NOT falsely 'stale' right after a (re)generation. Keystone for
    the staleness lifecycle: generating an image is a deliberate act that defines
    what the slide depicts."""
    from agents.content.tools import _attach_image_to_slide
    from agents.content.schema import Slide
    from models.content import ContentPost

    class _FakeDB:
        def add(self, _row):
            pass

    row = ContentPost(
        project_id=uuid4(), post_dir_slug="x", layout="full-bleed",
        slides=[{"slide_id": "slide-01", "kind": "photo", "image_prompt": "old short stub"}],
    )
    NEW = "24yo woman, heart face, real skin with visible pores, natural asymmetry, warm window light, candid"
    ok = _attach_image_to_slide(
        _FakeDB(), row, "slide-01",
        asset_id=str(uuid4()), url="https://cdn/x.png", prompt_used=NEW,
    )
    assert ok
    s = row.slides[0]
    assert s["image_url"] == "https://cdn/x.png"
    assert s["image_prompt"] == NEW and s["image_prompt_used"] == NEW   # in sync
    assert Slide.model_validate(s).is_image_stale() is False            # not falsely stale


def test_arc_line_for_slide_extracts_this_slides_beat():
    """fetch_slide_context hands the model THIS slide's emotional_arc beat (the
    arc is one "01: ...\\n02: ..." blob). Matches by the slide's trailing number,
    tolerates non-zero-padded lines, and falls back to the idx-th line."""
    from agents.content.tools import _arc_line_for_slide

    arc = "01: quiet wry smile\n02: leaning in, brow tightening\n03: pointing at jaw"
    assert _arc_line_for_slide(arc, "slide-02", 1) == "02: leaning in, brow tightening"
    assert _arc_line_for_slide(arc, "slide-03", 2) == "03: pointing at jaw"
    # non-zero-padded arc lines still match
    assert _arc_line_for_slide("1: a\n2: b", "slide-01", 0) == "1: a"
    # empty arc → empty; unmatched number → idx-th line fallback
    assert _arc_line_for_slide("", "slide-01", 0) == ""
    assert _arc_line_for_slide("01: a\n02: b", "slide-09", 1) == "02: b"


def test_image_tool_schemas_constrain_model_and_required_params():
    """The image tools must expose ENUM-constrained model/aspect_ratio (so an
    invalid id like 'gemini-3.1-flash-image-preview' can't be passed) and mark
    only the truly-required params required. Asserts the schema the model actually
    receives (via the MCP server's list_tools), guarding both the free-string
    `model` bug and the dict-form 'every key required' default."""
    import mcp.types as mt
    from agents.content.tools import build_content_mcp_server
    from agents.content.schema import make_session

    async def _emit(_body):
        return None

    cfg = build_content_mcp_server(uuid4(), _emit, make_session("t", uuid4(), "draft_post"))
    inst = cfg["instance"]

    async def _list():
        handler = inst.request_handlers[mt.ListToolsRequest]
        res = await handler(mt.ListToolsRequest(method="tools/list"))
        return {t.name: t.inputSchema for t in res.root.tools}

    schemas = asyncio.run(_list())

    gi = schemas["generate_image"]
    assert gi["required"] == ["prompt"]                                  # only prompt required
    assert "gemini-3.1-flash-image" in gi["properties"]["model"]["enum"]  # valid id offered
    assert "gemini-3.1-flash-image-preview" not in gi["properties"]["model"]["enum"]  # the bad id can't be passed
    assert "9:16" in gi["properties"]["aspect_ratio"]["enum"]

    ei = schemas["edit_image"]
    assert set(ei["required"]) == {"prompt", "input_asset_id"}
    assert "gemini-3.1-flash-image" in ei["properties"]["model"]["enum"]  # enum-constrained model

    # optional-as-required fixes: these take either/neither id, nothing forced
    assert schemas["fetch_post"]["required"] == []
    assert schemas["render_slide"]["required"] == ["slide_id"]


def test_merge_manual_metrics_maps_keys_preserves_postbridge_and_tracks_manual():
    """Manual-entry merge: form fields map to the canonical perf keys (the same
    keys metricsOf/PostCard already read), PostBridge's *_count fields are left
    untouched, and every touched key is recorded under manual_keys so a later
    sync won't be assumed to own them. Nested retention/audience pass through."""
    from routes.content import _merge_manual_metrics

    perf = {"view_count": 825, "like_count": 5, "comment_count": 0, "share_count": 1}
    provided = {
        "saves": 12,
        "reach": 1200,
        "profile_views": 40,
        "new_followers": 6,
        "avg_watch_time": 3.6,
        "completion_rate": 15.0,
        "retention": {"slide1": 100, "slide2": 62},
        "audience_age": {"18-24": 53, "25-34": 22},
    }
    out = _merge_manual_metrics(perf, provided, at="2026-06-18T00:00:00+00:00")

    # snake_case field → canonical perf key
    assert out["saves"] == 12
    assert out["reach"] == 1200
    assert out["profileViews"] == 40
    assert out["newFollowers"] == 6
    assert out["avgWatchTime"] == 3.6
    assert out["completionRate"] == 15.0
    assert out["retention"] == {"slide1": 100, "slide2": 62}
    assert out["audienceAge"] == {"18-24": 53, "25-34": 22}

    # PostBridge-owned counts are never clobbered by a manual entry
    assert out["view_count"] == 825 and out["share_count"] == 1

    assert set(out["manual_keys"]) == {
        "saves", "reach", "profileViews", "newFollowers",
        "avgWatchTime", "completionRate", "retention", "audienceAge",
    }
    assert out["manual_updated_at"] == "2026-06-18T00:00:00+00:00"
    # input perf dict is not mutated in place
    assert "saves" not in perf


def test_merge_manual_metrics_maps_new_dimensions():
    """The expanded manual metrics (video avg-watched, slideshow photos-viewed,
    and the gender / locations / traffic / search-query breakdowns) map to their
    canonical camelCase perf keys and are recorded as manual."""
    from routes.content import _merge_manual_metrics

    provided = {
        "retention_rate": 29.0,
        "photos_viewed": 2.3,
        "gender": {"Male": 18, "Female": 82},
        "locations": {"Spain": 50.6, "Nigeria": 11.8},
        "traffic_sources": {"For You": 59.2, "Search": 40.8},
        "search_queries": {"heart face shape": 47.3},
    }
    out = _merge_manual_metrics({}, provided, at="2026-06-29T00:00:00+00:00")

    assert out["retentionRate"] == 29.0
    assert out["photosViewed"] == 2.3
    assert out["gender"] == {"Male": 18, "Female": 82}
    assert out["locations"] == {"Spain": 50.6, "Nigeria": 11.8}
    assert out["trafficSources"] == {"For You": 59.2, "Search": 40.8}
    assert out["searchQueries"] == {"heart face shape": 47.3}
    assert set(out["manual_keys"]) == {
        "retentionRate", "photosViewed", "gender",
        "locations", "trafficSources", "searchQueries",
    }


def test_merge_manual_metrics_unions_manual_keys_across_calls():
    """A second manual edit adds to (not replaces) the recorded manual_keys, so
    the set reflects every hand-entered field over time."""
    from routes.content import _merge_manual_metrics

    first = _merge_manual_metrics({}, {"saves": 3}, at="2026-06-18T00:00:00+00:00")
    second = _merge_manual_metrics(first, {"reach": 900}, at="2026-06-18T01:00:00+00:00")
    assert second["saves"] == 3 and second["reach"] == 900
    assert set(second["manual_keys"]) == {"saves", "reach"}


# ---------------------------------------------------------------------------
# Video posts (Higgsfield) — prompt branch + token resolver are real logic
# ---------------------------------------------------------------------------


def test_video_kickoff_prompt_uses_higgsfield_flow_not_slides():
    """A video post must steer the model to the Higgsfield image-to-video flow
    (keyframe → animate → poll → attach_post_video), while a slideshow post must
    stay on the slides path. If the post_type branch breaks, a video post would
    silently draft slides and never call Higgsfield."""
    from agents.content.prompts import build_post_user_prompt

    brand = _brand()
    video = build_post_user_prompt(brand, None, topic="x", post_type="video")
    slides = build_post_user_prompt(brand, None, topic="x", post_type="slideshow")

    assert "mcp__higgsfield__" in video and "attach_post_video" in video
    assert "VIDEO post" in video
    assert "higgsfield" not in slides.lower()
    assert "slide_count" in slides


def _clone_reference(*, is_slideshow: bool, video_analysis: str = "") -> dict:
    """Minimal ingest result (service.discovery.ingest_reference shape) for a
    clone kickoff — a video reference vs a photo carousel."""
    return {
        "tiktok_url": "https://www.tiktok.com/@ref/video/123",
        "scraped_post": {
            "is_slideshow": is_slideshow,
            "text": "ref caption",
            "hashtags": ["beauty"],
            "author_meta": {"name": "ref"},
            "music_meta": {"music_name": "some sound"},
        },
        "media": {"cover": "https://cdn/cover.jpg", "slides": []},
        "diagnostic": {"lever": "saves", "confidence": "high", "summary": "won on saves"},
        "video_analysis": video_analysis,
    }


def test_clone_kickoff_video_embeds_gemini_deconstruction_then_higgsfield_generates():
    """Cloning a VIDEO reference must embed the Gemini DECONSTRUCTION (watched at
    ingest) in the kickoff, steer the model to rebuild the structure + on-screen
    text, and generate via the keyframe → Higgsfield image-to-video →
    attach_post_video flow — NOT a slideshow, and NOT the Higgsfield analyser.
    Cloning a photo carousel must stay on the slides path with no deconstruction."""
    from agents.content.prompts import build_clone_user_prompt

    brand = _brand()
    decon = "1. BEAT-BY-BEAT: straight hair -> bangs. 3. ON-SCREEN TEXT: 'me without bangs'."
    video = build_clone_user_prompt(
        brand,
        reference=_clone_reference(is_slideshow=False, video_analysis=decon),
        post_dir_slug="d01-x",
    )
    carousel = build_clone_user_prompt(
        brand, reference=_clone_reference(is_slideshow=True), post_dir_slug="d01-x"
    )

    # Video clone: the watched deconstruction is embedded; analysis is Gemini (the
    # understand_video tool), generation is Higgsfield; on-screen text is recreated.
    assert "DECONSTRUCTION" in video and decon in video
    assert "understand_video" in video
    assert "on-screen text" in video.lower()
    assert 'post_type="video"' in video
    assert "attach_post_video" in video and "mcp__higgsfield__" in video  # generation only
    # Carousel clone: slides path, no Higgsfield, no deconstruction block.
    assert "higgsfield" not in carousel.lower()
    assert "structured slides" in carousel
    assert "DECONSTRUCTION" not in carousel
    # Both target the SAME pending card (pending → draft), never a duplicate.
    assert "post_dir_slug=d01-x" in video and "post_dir_slug=d01-x" in carousel


def test_clone_discipline_maps_to_closest_pillar_and_stays_content_first():
    """The clone discipline must steer the agent to (a) map the reference to its
    CLOSEST brand pillar by subject — a hair reference stays a hair post, it does
    NOT drift to face-shape — and (b) stay content-first / soft-sell by default,
    not name-dropping the product unless it's a product-demo pillar or the user
    asked. Guards the reported regression (hair ref → face-shape post that promoted
    'MaxAura said heart face')."""
    from agents.content import prompts as p

    disc = p._CLONE_DISCIPLINE.lower()
    # Closest-pillar mapping (topical fit over reach).
    assert "pick the closest pillar" in disc
    assert "topical fit beats reach" in disc
    assert "does not become a face-shape post" in disc
    # Content-first / soft-sell default.
    assert "content-first / soft-sell" in disc
    assert "do not name the brand/product" in disc
    # The video clone tail must not push an unconditional product moment.
    assert "no product placement" in p._VIDEO_CLONE_INSTRUCTIONS.lower()
    # Strategist fit × proof: clone a proven in-niche winner closely; out-of-niche
    # is a structure-only transfer mapped to the best-fit pillar.
    assert "judge fit × proof" in disc
    assert "in-niche + proven" in disc and "clone close" in disc
    assert "out-of-niche" in disc and "structure-only transfer" in disc
    # Research-grounded hook principle (first 3s is the ranking signal).
    assert "first 3 seconds" in disc
    assert "identity call" in disc and "open loop" in disc
    # Character authenticity: an in-niche clone mirrors the reference creator's
    # demographic (gender/ethnicity/look), reusing the UGC image discipline.
    assert "clone the creator" in disc
    assert "demographic" in disc and "ethnicity" in disc


def test_video_reuses_slide_image_discipline_and_keeps_motion_video_only():
    """The keyframe is a still, so it REUSES the same proven image discipline the
    slide drafter uses (_IMAGE_PROMPT_DISCIPLINE_BRIEF) — not a thinner parallel
    block. The VIDEO-ONLY motion/structure bits (guardrails, clip spec, storyboard)
    must still never leak into the slideshow instruction blocks."""
    from agents.content import prompts as p

    video = p._VIDEO_PHASE_INSTRUCTIONS + p._VIDEO_CLONE_INSTRUCTIONS
    slideshow = p._SLIDESHOW_PHASE_INSTRUCTIONS + p._SLIDESHOW_CLONE_INSTRUCTIONS
    # Shared image discipline: the keyframe gets the SAME brief as the slide drafter.
    for shared in ("FOUR ANCHOR RULES", "PROMPT SKELETON"):
        assert shared in video, f"{shared} missing from the video keyframe standards"
        assert shared in p.DRAFT_POST_PROMPT, f"{shared} missing from the slide drafter"
    # Video-only motion/structure must NOT leak into the slideshow tails.
    for marker in ("HARD CONSTRAINTS", "CLIP DIRECTION", "video_storyboard", "beat_id",
                   "SHOT SIZE", "CAMERA MOVE"):
        assert marker in video, f"{marker} missing from the video blocks"
        assert marker not in slideshow, f"LEAK: {marker} reached the slideshow blocks"
    assert "higgsfield" not in slideshow.lower()
    # Keyframe character consistency: beats 2+ MUST reference beat 1's keyframe as
    # an input asset (same mechanism slides use), so the same person carries across.
    assert "LOCK THE CHARACTER" in video
    assert "BEAT 1's keyframe" in video and "input_asset_id" in video
    # Multi-character: describe each person distinctly + a per-character reference
    # scheme so two interacting subjects each stay consistent across beats.
    assert "MULTIPLE PEOPLE" in video
    assert "Person A" in video and "Person B" in video
    # Honest keyframe review (anti-sycophancy) + hand-defect handling: hands near the
    # face are flagged as the #1 defect, and a broken frame is regenerated/rejected,
    # not rationalised.
    assert "HANDS ARE THE #1 DEFECT" in video
    assert "critical art director" in video and "REJECT" in video


def test_clone_kickoff_video_without_analysis_falls_back_to_understand_video_tool():
    """If the ingest-time analysis is unavailable (no key / fetch failed), the
    video kickoff must NOT embed an empty deconstruction block and must tell the
    model to call understand_video (or deconstruct from the cover) — never silently
    proceed as if it had watched the clip."""
    from agents.content.prompts import build_clone_user_prompt

    video = build_clone_user_prompt(
        _brand(), reference=_clone_reference(is_slideshow=False), post_dir_slug="d01-x"
    )
    assert "DECONSTRUCTION (Gemini watched the clip)" not in video
    assert "understand_video" in video


def test_video_understanding_knobs_map_to_sdk():
    """The documented video-understanding levers must map to real google.genai
    types: fps + start/end offset → VideoMetadata; media_resolution → the enum,
    with 'default'/unknown ⇒ None (API default). If the SDK renames these, this
    fails loudly instead of silently dropping the knob at runtime."""
    from google.genai import types

    import service.gemini.video as gv

    vm = gv._video_metadata(types, 3, "30s", "80s")
    assert vm.fps == 3 and vm.start_offset == "30s" and vm.end_offset == "80s"
    assert gv._video_metadata(types, None, None, None) is None

    cfg = gv._gen_config(types, "low")
    assert cfg.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert gv._gen_config(types, "default") is None  # not a real member → API default
    assert gv._gen_config(types, None) is None


def test_is_youtube_url_routes_youtube_to_filedata():
    """YouTube URLs must be detected so they go to Gemini as fileData (no local
    download); any other URL is fetched as bytes. Host-based, so a substring
    bypass is rejected."""
    from agents.content.tools import _is_youtube_url

    assert _is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert _is_youtube_url("https://youtu.be/abc")
    assert not _is_youtube_url("https://cdn.example.com/clip.mp4")
    assert not _is_youtube_url("https://api.apify.com/v2/key-value-stores/x/records/y")
    # SSRF/spoof: substring 'youtube.com/' in the path must NOT count as YouTube.
    assert not _is_youtube_url("https://evil.com/?x=youtube.com/watch")


def test_url_safety_blocks_ssrf_and_substring_token_leak():
    """is_public_http_url must reject private/loopback/link-local + non-http; and
    host_in must be an EXACT host check (no substring) so the Apify token is never
    appended to an attacker host like 'https://evil.com/?x=api.apify.com'."""
    from service.url_safety import host_in, is_public_http_url

    # SSRF: cloud-metadata, loopback, private, link-local, non-http → blocked.
    assert not is_public_http_url("http://169.254.169.254/latest/meta-data/")
    assert not is_public_http_url("http://127.0.0.1/")
    assert not is_public_http_url("http://10.0.0.1/x")
    assert not is_public_http_url("http://192.168.1.1/x")
    assert not is_public_http_url("file:///etc/passwd")
    assert not is_public_http_url("ftp://example.com/x")
    assert not is_public_http_url("")
    # Public IP literal + normal https host → allowed.
    assert is_public_http_url("https://8.8.8.8/x")
    assert is_public_http_url("https://api.apify.com/v2/key-value-stores/x/records/y")

    # Secret-leak gate: exact host only.
    apify = {"api.apify.com", "storage.apify.com"}
    assert host_in("https://api.apify.com/v2/x?token=t", apify)
    assert not host_in("https://evil.com/?x=api.apify.com", apify)
    assert not host_in("https://api.apify.com.evil.com/x", apify)


def test_safe_get_bytes_revalidates_redirect_hops(monkeypatch):
    """safe_get_bytes must NOT follow a redirect to an internal host — closing the
    follow_redirects bypass where a validated URL 302s straight to 127.0.0.1."""
    import httpx

    import service.url_safety as us

    class _Resp:
        def __init__(self, *, redirect_to=None, content=b""):
            self._loc = redirect_to
            self.content = content
            self.headers = {"location": redirect_to} if redirect_to else {}

        @property
        def is_redirect(self):
            return self._loc is not None

        def raise_for_status(self):
            return None

    def _fake_get(url, **kw):
        # The first (public) host 302s to an internal address; a direct public host 200s.
        if "8.8.8.8" in url:
            return _Resp(content=b"OK")
        return _Resp(redirect_to="http://127.0.0.1/secret")

    monkeypatch.setattr(httpx, "get", _fake_get)
    # Redirect target (127.0.0.1) is re-validated and rejected → None.
    assert us.safe_get_bytes("https://cdn-public.example/x") is None
    # Direct 200 from a public IP literal → bytes.
    assert us.safe_get_bytes("https://8.8.8.8/clip.mp4") == b"OK"


def test_video_storyboard_merge_carries_keyframes_and_beat_attach():
    """video_storyboard persistence mirrors slides: _merge_beat_images carries a
    generated keyframe forward across a copy-only re-emit (incoming omits the url),
    keeps an incoming url, and _attach_image_to_beat writes the first vs 'after'
    frame. _require_beat lists valid ids on a miss (hard error, not silent)."""
    import types

    from agents.content.schema import VideoBeat
    from agents.content.tools import (
        _attach_image_to_beat,
        _merge_beat_images,
        _require_beat,
    )

    existing = types.SimpleNamespace(video_storyboard=[{
        "beat_id": "beat-01", "image_prompt": "alley selfie",
        "image_url": "https://cdn/k1.png", "image_asset_id": "a1",
        "image_prompt_used": "alley selfie",
    }])
    # Copy-only re-emit (no url) → keyframe carried forward.
    merged = _merge_beat_images([VideoBeat(beat_id="beat-01", image_prompt="alley selfie")], existing)
    assert merged[0].image_url == "https://cdn/k1.png" and str(merged[0].image_asset_id) == "a1"
    # Incoming with its own url is left as-is.
    merged2 = _merge_beat_images(
        [VideoBeat(beat_id="beat-09", image_prompt="x", image_url="https://cdn/new.png")], existing
    )
    assert merged2[0].image_url == "https://cdn/new.png"

    class _DB:
        def add(self, *_):
            pass

    row = types.SimpleNamespace(
        video_storyboard=[{"beat_id": "beat-01", "image_prompt": "before", "end_image_prompt": "after"}],
        updated_at=None,
    )
    assert _attach_image_to_beat(_DB(), row, "beat-01", asset_id="a2", url="https://cdn/first.png", frame="first")
    assert row.video_storyboard[0]["image_url"] == "https://cdn/first.png"
    # Transformation 'after' frame attaches to the end_* fields, leaving the first intact.
    assert _attach_image_to_beat(_DB(), row, "beat-01", asset_id="a3", url="https://cdn/after.png", frame="last")
    assert row.video_storyboard[0]["end_image_url"] == "https://cdn/after.png"
    assert row.video_storyboard[0]["image_url"] == "https://cdn/first.png"
    # Unknown beat → no attach, and the guard lists the valid ids.
    assert not _attach_image_to_beat(_DB(), row, "beat-99", asset_id="x", url="y")
    _b, _i, err = _require_beat(types.SimpleNamespace(video_storyboard=row.video_storyboard), "beat-99")
    assert err is not None and "beat-01" in err["content"][0]["text"]


def test_video_provider_resolution_routes_grok_vs_veo():
    """The video-gen dispatcher must route by model id: grok-* → Grok (xAI), every
    Veo id → Veo. A misroute would call the wrong client/key."""
    from agents.models import VideoModel, VideoProvider, video_provider_for

    assert video_provider_for(VideoModel.VEO_3_1.value) is VideoProvider.VEO
    assert video_provider_for(VideoModel.VEO_3_1_FAST.value) is VideoProvider.VEO
    assert video_provider_for(VideoModel.GROK_IMAGINE_VIDEO_1_5.value) is VideoProvider.GROK
    assert video_provider_for(VideoModel.SEEDANCE_2_0.value) is VideoProvider.SEEDANCE
    assert video_provider_for("dreamina-seedance-2-0-260128") is VideoProvider.SEEDANCE
    assert video_provider_for(None) is VideoProvider.VEO  # default
    # Each provider's client requires a key (no silent unauth'd calls).
    from service.byteplus.video_gen import SeedanceVideoClient
    from service.xai.video_gen import GrokVideoClient
    for cls in (GrokVideoClient, SeedanceVideoClient):
        try:
            cls("")
            raise AssertionError(f"{cls.__name__} allowed empty key")
        except ValueError:
            pass


def test_analyze_video_bytes_fails_soft(monkeypatch):
    """analyze_video_bytes must return '' (never raise) when there's no Gemini key
    or no bytes — so a clone degrades to cover+metadata instead of crashing. The
    function does `from config import get_configs` per call, so patch it on config."""
    import asyncio

    import config
    import service.discovery as disc

    class _NoKey:
        gemini_api_key = ""

    monkeypatch.setattr(config, "get_configs", lambda: _NoKey())
    # No key → "" before any SDK construction; empty bytes → "" too.
    assert asyncio.run(disc.analyze_video_bytes(b"\x00\x01\x02")) == ""
    assert asyncio.run(disc.analyze_video_bytes(b"")) == ""


def test_higgsfield_token_resolver_falls_back_to_env(monkeypatch):
    """With no per-user ConnectorCredential (user_id=None), the resolver returns
    the server-wide HIGGSFIELD_API_TOKEN — the dev/single-operator path. Empty
    config ⇒ '' (caller treats that as 'not connected' and skips the MCP)."""
    import service.higgsfield.auth as auth

    class _Cfg:
        higgsfield_api_token = "hf-test-token"

    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    assert auth.higgsfield_token_for_user(None, db=None) == "hf-test-token"

    class _Empty:
        higgsfield_api_token = ""

    monkeypatch.setattr(auth, "get_configs", lambda: _Empty())
    assert auth.higgsfield_token_for_user(None, db=None) == ""


def test_image_provider_for_routes_gemini_and_seedream():
    """generate_image dispatch hinges on this: seedream ids → Seedream client,
    everything else (incl. unknown) → Gemini. Mirrors video_provider_for."""
    from agents.models import ImageModel, ImageProvider, image_provider_for

    assert image_provider_for(ImageModel.SEEDREAM_5_0_LITE.value) is ImageProvider.SEEDREAM
    assert image_provider_for("seedream-5-0-260128") is ImageProvider.SEEDREAM
    assert image_provider_for(ImageModel.GEMINI_3_PRO_IMAGE.value) is ImageProvider.GEMINI
    assert image_provider_for(ImageModel.GEMINI_3_1_FLASH_IMAGE.value) is ImageProvider.GEMINI
    assert image_provider_for(None) is ImageProvider.GEMINI
    assert image_provider_for("") is ImageProvider.GEMINI


def test_seedream_aspect_to_size_clears_pixel_floor_and_keeps_ratio():
    """Seedream rejects images under 3,686,400 px, so aspect_to_size must map each
    ratio to an even WxH at-or-above the floor with the correct ratio. 9:16 → the
    canonical 1440x2560 (exactly the floor)."""
    from service.byteplus.image_gen import aspect_to_size

    FLOOR = 3_686_400
    assert aspect_to_size("9:16") == "1440x2560"
    assert aspect_to_size("16:9") == "2560x1440"
    for ratio, (a, b) in {"9:16": (9, 16), "16:9": (16, 9), "1:1": (1, 1), "3:4": (3, 4)}.items():
        w, h = (int(x) for x in aspect_to_size(ratio).split("x"))
        assert w * h >= FLOOR                      # clears the floor
        assert w % 2 == 0 and h % 2 == 0           # even dims
        assert abs(w / h - a / b) < 0.01           # ratio preserved
    # Unparseable ratio falls back to 9:16 portrait.
    assert aspect_to_size("garbage") == "1440x2560"


def test_media_vendor_models_maps_byteplus_and_google():
    """The config switch hinges on this: byteplus → Seedance+Seedream, google →
    Veo+Gemini, unknown/None → byteplus (the default combo)."""
    from agents.models import ImageModel, VideoModel, media_vendor_models

    assert media_vendor_models("byteplus") == (VideoModel.SEEDANCE_2_0, ImageModel.SEEDREAM_5_0_LITE)
    assert media_vendor_models("google") == (VideoModel.VEO_3_1, ImageModel.GEMINI_3_PRO_IMAGE)
    assert media_vendor_models("GOOGLE") == (VideoModel.VEO_3_1, ImageModel.GEMINI_3_PRO_IMAGE)
    # unknown / None / empty all fall back to byteplus
    for bad in ("nonsense", None, ""):
        assert media_vendor_models(bad) == (VideoModel.SEEDANCE_2_0, ImageModel.SEEDREAM_5_0_LITE)


def test_media_vendor_directive_reflects_configured_vendor():
    """The system prompt must tell the agent which video engines are active so it
    doesn't pass a model itself. byteplus → Seedance/Seedream; google → Veo/Gemini."""
    bp = build_orchestrator_system_prompt(_brand(), "draft_post", vendor="byteplus")
    assert "MEDIA VENDOR (video posts) = BytePlus" in bp
    assert "Seedream 5.0 Lite" in bp and "do NOT pass a `model`" in bp

    gg = build_orchestrator_system_prompt(_brand(), "draft_post", vendor="google")
    assert "MEDIA VENDOR (video posts) = Google" in gg
    assert "Veo 3.1" in gg and "Gemini 3 Pro Image" in gg
    # The google prompt must carry the Google directive, not the BytePlus one.
    assert "MEDIA VENDOR (video posts) = BytePlus" not in gg

    # Default (no vendor arg) follows config, which defaults to byteplus.
    assert "MEDIA VENDOR (video posts) = BytePlus" in build_orchestrator_system_prompt(_brand(), "draft_post")
