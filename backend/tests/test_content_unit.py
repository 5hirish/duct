"""Unit-level tests for agents/content/.

Scope kept tight: only tests that catch real regressions live here.
Pure Pydantic round-trips, enum shape checks, and constructor smoke
tests have been removed — Pydantic + Python tests itself. Real-data
behaviour lives in tests/test_content_e2e.py.

What earns a place here:
  - Cache-stability of the orchestrator system prompt (huge cost lever)
  - Sub-agent JSON output → orchestrator persistence (the only path
    from sub-agent text → DB row, easy to break silently)
  - Tool binding (single construction smoke + the schemas the model sees)
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
from agents.content.tools import build_content_tools_lc


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
# Tool binding — single smoke test for registration + closure capture
# ---------------------------------------------------------------------------


def test_content_tools_bind_and_expose_writer_tools():
    """Catches: a harness API change, a binder misuse, broken closure capture
    of project_id/emit/session, and a tool registered under a name the
    ContentTool enum (and the prompts) do not know."""
    from agents.content.schema import ContentTool

    session = make_session("t", uuid4(), "plan_month")
    tools = build_content_tools_lc(session.project_id, _noop, session)
    names = {t.name for t in tools}
    assert {"submit_plan", "submit_post_draft", "edit_slide", "generate_image"} <= names
    assert names == {t.value for t in ContentTool}


def test_unremembered_session_binds_no_memory_tools():
    """"Don't remember this" is enforced by absence, not by instruction."""
    session = make_session("t", uuid4(), "plan_month")
    names = {t.name for t in build_content_tools_lc(session.project_id, _noop, session, remember=False)}
    assert not names & {"RememberFact", "SearchMemory", "GetMemory"}


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
    from agents.content.v1.runner import (
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
    from agents.content.v1.runner import close_session, get_session
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
# Writer + image tools validate before they touch anything — the corrective
# text is what stops the model retrying blindly.
# ---------------------------------------------------------------------------


def _tools_for(session) -> dict:
    return {t.name: t for t in build_content_tools_lc(session.project_id, _noop, session)}


def test_writer_tool_denies_with_corrective_text_before_any_db_work():
    """Two things Pydantic does not do on its own: the error names the
    schema that failed so the model knows what to fix, and it arrives
    BEFORE a DB session is opened — there is no DATABASE_URL here, and the
    result must still be the validation message, not a connection error.
    submit_plan shares the path; one test covers the pattern."""
    import json

    session = make_session("t", uuid4(), "draft_post")
    tool = _tools_for(session)["submit_post_draft"]
    result = json.loads(asyncio.run(tool.ainvoke({"post": {"type": "post", "project_id": str(session.project_id)}})))
    assert result["status"] == "error"
    assert "PostDraft validation failed" in result["message"]


def test_writer_tool_blocks_cross_project_writes():
    """Multi-tenant safety: a payload carrying someone else's project_id must
    be rejected. Without this guard the agent could persist a draft into the
    wrong project's content_posts row."""
    import json

    session = make_session("t", uuid4(), "draft_post")
    wrong = {
        "type": "post",
        "project_id": str(uuid4()),  # not the session's
        "post_dir_slug": "x",
        "pillar": "p",
        "topic": "t",
        "slides_html": "<html/>",
        "caption": "c",
    }
    result = json.loads(asyncio.run(_tools_for(session)["submit_post_draft"].ainvoke({"post": wrong})))
    assert result["status"] == "error"
    assert "project_id mismatch" in result["message"]
    assert str(session.project_id) in result["message"]


def test_generate_image_refuses_more_than_three_references_before_paying():
    """The legacy single `input_asset_id` and the multi `input_asset_ids` are
    coalesced (deduplicated) before the cap is checked, and the cap fires
    before any Gemini call — so a run with a key and four refs gets the
    corrective text, never a bill."""
    import json

    session = make_session("t", uuid4(), "draft_post")
    session.gemini_api_key = "AIza-test"
    tool = _tools_for(session)["generate_image"]
    shared = str(uuid4())
    result = json.loads(asyncio.run(tool.ainvoke({
        "prompt": "x",
        "input_asset_id": shared,
        "input_asset_ids": [shared, str(uuid4()), str(uuid4()), str(uuid4())],
    })))
    assert result["status"] == "error"
    assert "max 3" in result["message"]


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
    """Graceful degradation: empty api_key skips the research pass and
    returns local signals only. This is the path that fires when no provider
    key is configured (dev / unit env)."""
    import asyncio
    from unittest.mock import patch
    from agents.content.enrichment import enrich_content_context
    from agents.content.schema import ContentBrandContext

    brand = ContentBrandContext(project_id=uuid4(), project_name="X")
    with patch("agents.content.enrichment.get_engine", return_value=None):
        ctx = asyncio.run(enrich_content_context(brand, api_key=""))
    # Empty but well-formed — the research pass was correctly skipped
    assert ctx.trending_sounds == []
    assert ctx.trending_hashtags == []


def test_enrich_skips_research_on_a_provider_with_no_verified_web_search():
    """A research pass with no search tool could only invent trends. Local
    signals come through and the model is never called — a fake that
    explodes is the proof."""
    import asyncio
    from unittest.mock import patch

    from langchain_core.messages import AIMessage

    from agents.content.enrichment import enrich_content_context
    from agents.content.schema import ContentBrandContext
    from agents.models import ModelName, Provider
    from tests.fakes import ToolCallingFake

    class _Explodes(ToolCallingFake):
        def _generate(self, *a, **k):
            raise AssertionError("no search, no research pass")

    brand = ContentBrandContext(project_id=uuid4(), project_name="X")
    with patch("agents.content.enrichment.get_engine", return_value=None):
        ctx = asyncio.run(enrich_content_context(
            brand, api_key="k", provider=Provider.OPENROUTER, model=ModelName.OR_DEEPSEEK_V4_FLASH,
            llm=_Explodes(responses=[AIMessage(content="x")]),
        ))
    assert ctx.trending_hooks == [] and ctx.total_posts_to_date == 0


def test_enrich_layers_the_research_pass_over_local_signals(monkeypatch):
    """The pass returns its findings through the structured-output contract;
    they land on the trend fields and the local signals are carried through
    untouched. Driven by a fake that answers the structured tool call."""
    import asyncio
    from unittest.mock import patch

    from langchain_core.messages import AIMessage

    import agents.content.enrichment as enrichment
    from agents.content.schema import ContentBrandContext, ContentResearchContext, PillarHistorySignal
    from agents.models import Provider
    from tests.fakes import ToolCallingFake

    monkeypatch.setattr(enrichment, "provider_web_search_tool", lambda _p: {"type": "web_search_fake"})
    found = {
        "trending_hooks": [{"kind": "hook", "label": "POV: you found out", "why_it_works": "curiosity"}],
        "audience_insights": ["saves spike on self-tests"],
    }
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "_RawTrendingResult", "args": found, "id": "s1"}]),
    ])
    base = ContentResearchContext(
        pillar_history=[PillarHistorySignal(pillar="face_shape", posts_count=3)], total_posts_to_date=3,
    )
    brand = ContentBrandContext(project_id=uuid4(), project_name="X")
    with patch("agents.content.enrichment.get_engine", return_value=None):
        ctx = asyncio.run(enrichment.enrich_content_context(
            brand, api_key="k", provider=Provider.ANTHROPIC, llm=llm, base_context=base,
        ))
    assert [h.label for h in ctx.trending_hooks] == ["POV: you found out"]
    assert ctx.audience_insights == ["saves spike on self-tests"]
    assert ctx.total_posts_to_date == 3 and ctx.pillar_history[0].pillar == "face_shape"


# ---------------------------------------------------------------------------
# DRAFT_POST_PROMPT regression guard — borrowed patterns from nomadapps PR #37
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CLI startup-failure diagnosis + retry (agents/core/claude_sdk.py)
#
# Written for the content runner when it ran on the Claude Agent SDK; the
# helpers now serve the audit v3 runner alone. The `claude` subprocess can
# exit 1 during initialize() — most often a transient subscription usage/rate
# limit on the OAuth path — and the SDK surfaces this opaquely. These tests
# pin the diagnosis helpers that turn that into an actionable, correctly-
# grouped signal — the bit that's easy to silently break.
# ---------------------------------------------------------------------------


# NB: the stderr-capture / failure-message / rate-limit classification logic is
# tested directly in tests/test_agent_core.py. Here we only cover the per-agent
# Sentry wiring (agent="content" tags, as the content runner used to pass).


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
    only the truly-required params required. Asserts the argument schema the
    model actually receives, guarding both the free-string `model` bug and an
    'every key required' regression."""
    from agents.content.schema import make_session

    session = make_session("t", uuid4(), "draft_post")
    schemas = {t.name: t.args_schema.model_json_schema() for t in build_content_tools_lc(uuid4(), _noop, session)}

    def _enum(schema: dict, field: str) -> list:
        """Pydantic emits an enum field as a $ref into $defs; follow it."""
        prop = schema["properties"][field]
        ref = prop.get("$ref") or next((a["$ref"] for a in prop.get("anyOf", []) if "$ref" in a), None)
        target = schema["$defs"][ref.rsplit("/", 1)[-1]] if ref else prop
        return target["enum"]

    gi = schemas["generate_image"]
    assert gi["required"] == ["prompt"]                                    # only prompt required
    assert "gemini-3.1-flash-image" in _enum(gi, "model")                  # valid id offered
    assert "gemini-3.1-flash-image-preview" not in _enum(gi, "model")      # the bad id can't be passed
    assert "9:16" in _enum(gi, "aspect_ratio")

    ei = schemas["edit_image"]
    assert set(ei["required"]) == {"prompt", "input_asset_id"}
    assert _enum(ei, "edit_mode")

    # optional-as-required fixes: these take either/neither id, nothing forced
    assert schemas["fetch_post"].get("required", []) == []
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
