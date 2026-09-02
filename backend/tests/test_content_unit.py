"""Unit-level tests for agents/content/.

Scope kept tight: only tests that catch real regressions live here.
Pure Pydantic round-trips, enum shape checks, and constructor smoke
tests have been removed — Pydantic + Python tests itself. Real-data
behaviour lives in tests/test_content_e2e.py.

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
    for must_have in ("<duct_artifact>", "submit_plan", "submit_post_draft",
                      "research_pillar", "draft_post", "STRUCTURED SLIDES",
                      "MODE: plan_month"):
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
    """Folding /api/content/* into /api/agents/*: the unified session factory
    must build a ContentSession (not the default AuditSession) with the right
    mode/project_id, and 422 on a missing project_id."""
    from uuid import uuid4

    import pytest
    from fastapi import HTTPException

    from agents.content.schema import ContentSession
    from agents.content.v3.runner import close_session, get_session
    from agents.registry import AgentType
    from routes.agents import _create_session_for

    pid = uuid4()
    s = _create_session_for(
        AgentType.TIKTOK_STUDIO, "ufold-plan", {"mode": "plan_month", "project_id": str(pid)}
    )
    assert isinstance(s, ContentSession)
    assert s.mode == "plan_month" and s.project_id == pid
    assert s.agent_type == "tiktok_studio"
    assert get_session("ufold-plan") is s
    close_session("ufold-plan")

    plan_id = uuid4()
    s2 = _create_session_for(
        AgentType.TIKTOK_STUDIO,
        "ufold-draft",
        {"mode": "draft_post", "project_id": str(pid), "plan_id": str(plan_id)},
    )
    assert isinstance(s2, ContentSession) and s2.mode == "draft_post" and s2.plan_id == plan_id
    close_session("ufold-draft")

    with pytest.raises(HTTPException):
        _create_session_for(AgentType.TIKTOK_STUDIO, "ufold-bad", {"mode": "plan_month"})


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

    Symmetry: submit_plan shares the same code path (just a different
    schema). One test is enough — if the pattern breaks here, it breaks
    there too.
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
    # LEGACY_* keys deliberately name wire values the backend no longer emits —
    # they exist so an app deployed ahead of the backend still renders. Exempt
    # them; every other key must resolve to a live backend value.
    pairs = re.findall(r'([A-Z_0-9]+):\s*"([a-z_0-9]+)"', js)
    referenced = {v for k, v in pairs if not k.startswith("LEGACY_")}
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
# DRAFT_POST_PROMPT regression guard — borrowed patterns from nomadapps PR #37
# ---------------------------------------------------------------------------


def test_draft_post_prompt_contains_critical_quality_rules():
    """The TikTok content patterns (PR #37 borrow) — mystery architecture,
    5 emotional triggers, save_cta specific-payoff rule, AI→app
    terminology, visual-content alignment — are quality anchors. Each
    one is here because the source skill's experimentation showed
    measurable retention/engagement lift from it.

    If a future prompt edit accidentally deletes any of these, the model
    silently regresses. This test fails loudly so PRs surface the
    deletion before it ships.

    One test, six asserts. Cheap (<10ms). Catches the bug class that
    matters: silent prompt drift."""
    from agents.content.prompts import DRAFT_POST_PROMPT

    # 1. Mystery architecture (replaces list architecture)
    assert "Mystery" in DRAFT_POST_PROMPT or "MYSTERY" in DRAFT_POST_PROMPT, \
        "DRAFT_POST_PROMPT lost the mystery-architecture rule"
    assert "Open loop" in DRAFT_POST_PROMPT or "open loop" in DRAFT_POST_PROMPT.lower(), \
        "DRAFT_POST_PROMPT lost the open-loop instruction"

    # 2. Five emotional triggers — all five must be present
    for emotion in ("frustration", "shock", "disbelief", "anger", "sadness"):
        assert emotion in DRAFT_POST_PROMPT, f"DRAFT_POST_PROMPT lost the '{emotion}' emotion trigger"

    # 3. Save CTA rule — must enforce naming a specific payoff slide
    assert "save this — the" in DRAFT_POST_PROMPT.lower() or "save_cta" in DRAFT_POST_PROMPT, \
        "DRAFT_POST_PROMPT lost the save_cta specific-payoff rule"

    # 4. AI → app terminology rule
    assert 'never say "AI"' in DRAFT_POST_PROMPT or 'never say \"AI\"' in DRAFT_POST_PROMPT, \
        "DRAFT_POST_PROMPT lost the AI→app terminology rule"

    # 5. Visual-content alignment (image-prompt discipline)
    assert "Visual-Content Alignment" in DRAFT_POST_PROMPT or "VISUAL-CONTENT ALIGNMENT" in DRAFT_POST_PROMPT, \
        "DRAFT_POST_PROMPT lost the visual-content alignment check"

    # 6. Dual CTA on slide 7
    assert "Comment driver" in DRAFT_POST_PROMPT or "comment driver" in DRAFT_POST_PROMPT.lower(), \
        "DRAFT_POST_PROMPT lost the slide-7 dual-CTA rule"
    assert "Follow driver" in DRAFT_POST_PROMPT or "follow driver" in DRAFT_POST_PROMPT.lower(), \
        "DRAFT_POST_PROMPT lost the slide-7 follow-driver rule"

    # 7. Reference study session — the visual-brief discipline that drives
    #    copy voice and image prompts (Phase 8.5 borrow from skill.md
    #    Step 3). If a future edit deletes it, drafts go back to
    #    template-generic AI-looking output.
    lower = DRAFT_POST_PROMPT.lower()
    assert "reference study" in lower or "visual brief" in lower, \
        "DRAFT_POST_PROMPT lost the reference-study session"
    assert "copy from references" in lower or "never copy from references" in lower, \
        "DRAFT_POST_PROMPT lost the COPY-vs-NEVER-COPY reference rule"

    # 8. Emotional arc — 5-slide energy map prevents flatlined drafts
    assert "emotional arc" in lower or "emotional_arc" in lower, \
        "DRAFT_POST_PROMPT lost the emotional-arc discipline"

    # 9. Attractiveness anchor — order matters (beauty first, texture after)
    assert "attractiveness" in lower, \
        "DRAFT_POST_PROMPT lost the character-attractiveness anchor"
    assert "order matters" in lower or "lead with" in lower, \
        "DRAFT_POST_PROMPT lost the attractiveness-then-texture ordering"

    # 10. Gesture-arc repetition prevention — same gesture twice = flat
    assert "gesture arc" in lower or "not [gesture" in lower, \
        "DRAFT_POST_PROMPT lost the gesture-arc repetition prevention"


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
        mode="plan_month",
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
    assert "enum" in ei["properties"]["edit_mode"]

    # optional-as-required fixes: these take either/neither id, nothing forced
    assert schemas["fetch_post"]["required"] == []
    assert schemas["mark_posted"]["required"] == ["post_id"]


# ---------------------------------------------------------------------------
# Channel labels — _LABELS used to be a hand-kept mirror of a Platform enum
# that lived in another module, so the two could drift silently. They now sit
# together; this keeps the map total so a new channel can't ship label-less
# and fall back to titleize() ("Google_business").
# ---------------------------------------------------------------------------


def test_every_platform_has_a_display_label():
    from agents.content.channels import Platform, _LABELS, resolve

    assert set(_LABELS) == set(Platform), (
        "every Platform needs a label in agents/content/channels._LABELS — "
        f"missing: {set(Platform) - set(_LABELS)}"
    )
    # resolve() indexes the map with a bare string, which only works because
    # Platform is a StrEnum. Guard that, not just the key set.
    for p in Platform:
        assert resolve(p.value).label == _LABELS[p]
    # Unknown channels still degrade to the TikTok playbook, not an error.
    unknown = resolve("mastodon")
    assert unknown.label == "Mastodon"
    assert unknown.supported is False
    assert unknown.playbook == "tiktok"
