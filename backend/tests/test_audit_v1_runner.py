"""Audit V1 runner — SSE event contract and the mid-run question bridge.

V1 runs alongside V3, so the frontend must not be able to tell them apart. These
assert the shared `AgentEvent` vocabulary is what reaches the stream, and that
AskUserQuestion still pauses the agent on an asyncio.Future resolved by the
messages route (`agents/core/session.py`) rather than needing new plumbing.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessage

from agents.audit.events import AuditStep
from agents.audit.schema import CrawlPlan, CrawlResult
from agents.audit.v1.runner import build_audit_agent
from agents.core.events import AgentEvent
from agents.core.lc import (
    MAX_QUESTIONS,
    build_ask_user_tool,
    split_chunk,
    stream_agent,
)
from agents.core.session import BaseAgentSession, register_session
from tests.fakes import ToolCallingFake, tool_names as _tool_names


@pytest.fixture
def crawl_result():
    return CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai"))


@pytest.fixture
def session():
    return register_session(
        BaseAgentSession(
            session_id=str(uuid.uuid4()),
            agent_type="audit_seo",
            event_queue=asyncio.Queue(),
            chat_queue=asyncio.Queue(),
        )
    )


async def _wait_for_event(events: list, timeout: float = 2.0) -> dict:
    """Wait until the tool has emitted, rather than guessing a tick count.

    `tool.ainvoke` goes through LangChain's callback machinery before reaching
    our coroutine, so a single `sleep(0)` is not enough.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while not events:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("tool never emitted an event")
        await asyncio.sleep(0.01)
    return events[-1]


# ---------------------------------------------------------------------------
# Mid-run questions
# ---------------------------------------------------------------------------

async def test_ask_user_emits_questions_and_waits_for_the_answer(session, emitted):
    tool = build_ask_user_tool(session, session.session_id, emitted)
    questions = [{"question": "What is the primary conversion goal?", "header": "Goal"}]

    task = asyncio.create_task(tool.ainvoke({"questions": questions}))
    event = await _wait_for_event(emitted.events)

    # The agent is parked until the route resolves the future.
    assert not task.done()
    assert event["event"] == AgentEvent.QUESTIONS_REQUIRED
    assert event["session_id"] == session.session_id
    assert event["questions"] == questions

    session.answer_future.set_result({"Goal": "Demo bookings"})
    result = await task

    assert "Demo bookings" in result


async def test_ask_user_caps_the_number_of_questions(session, emitted):
    tool = build_ask_user_tool(session, session.session_id, emitted)
    many = [{"question": f"q{i}", "header": f"h{i}"} for i in range(10)]

    task = asyncio.create_task(tool.ainvoke({"questions": many}))
    event = await _wait_for_event(emitted.events)

    assert len(event["questions"]) == MAX_QUESTIONS
    session.answer_future.set_result({})
    await task


async def test_ask_user_timeout_tells_the_model_to_continue(session, emitted):
    """An unanswered question must not strand the audit.

    The timeout is injected, not monkeypatched: `bridge_ask_user_question` binds
    ASK_USER_TIMEOUT as a default argument at import time, so patching the module
    attribute has no effect and the test would really wait two minutes.
    """
    tool = build_ask_user_tool(session, session.session_id, emitted, timeout=0.01)

    result = await tool.ainvoke({"questions": [{"question": "q", "header": "h"}]})

    assert "did not answer" in result
    assert "do not ask again" in result


# ---------------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------------

def test_ask_user_tool_only_present_with_a_session(crawl_result, session, emitted):
    llm = ToolCallingFake(responses=[AIMessage(content="ok")])

    without = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit"
    )
    with_session = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        session=session, session_id=session.session_id, emit=emitted,
    )

    assert "AskUserQuestion" not in _tool_names(without)
    assert "AskUserQuestion" in _tool_names(with_session)


# ---------------------------------------------------------------------------
# Streaming contract
# ---------------------------------------------------------------------------

async def test_stream_emits_the_shared_event_vocabulary(crawl_result, emitted):
    llm = ToolCallingFake(responses=[AIMessage(content="Audit looks healthy.")])
    agent = build_audit_agent(crawl_result=crawl_result, llm=llm, system_prompt="audit")

    async def on_close(_raw: str, _turn: str) -> None:
        pass

    await stream_agent(agent, "audit getduct.ai", emitted, on_artifact_close=on_close)

    kinds = [e["event"] for e in emitted.events]
    assert AgentEvent.MESSAGE_STOP in kinds
    assert AgentEvent.AGENT_MESSAGE_CHUNK in kinds
    # Only the shared vocabulary reaches the frontend.
    assert set(kinds) <= set(AgentEvent)


async def test_stream_routes_report_payload_to_the_parser(crawl_result, emitted):
    """Text inside <duct_artifact> is ARTIFACT_CHUNK, prose outside is a message."""
    llm = ToolCallingFake(
        responses=[AIMessage(content="Summary first.<duct_artifact>{\"a\":1}</duct_artifact>")]
    )
    agent = build_audit_agent(crawl_result=crawl_result, llm=llm, system_prompt="audit")

    closed: list[tuple[str, str]] = []

    async def on_close(raw: str, turn: str) -> None:
        closed.append((raw, turn))

    await stream_agent(agent, "audit", emitted, on_artifact_close=on_close)

    assert closed, "the report tag should have closed"
    raw, _turn = closed[0]
    assert "\"a\":1" in raw
    prose = "".join(
        e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "Summary first." in prose
    assert "duct_report" not in prose, "the tag must not leak into user-facing prose"


# ---------------------------------------------------------------------------
# The pipeline the route runs by default
# ---------------------------------------------------------------------------

def _model_that_builds_a_template_report() -> ToolCallingFake:
    """Start, one category, finalize, then a sentence — the sequence the
    prompt asks for, as canned tool calls."""
    header = {"overall_score": 72, "score_band": "good", "pages_crawled": 1, "total_sitemap_urls": 1}
    category = {
        "id": "on_page_seo", "label": "On-page SEO", "score": 8, "tooltip": "on-page health",
        "findings": [{
            "id": "h1-missing", "severity": "fail", "title": "No H1 on the homepage",
            "description": "The root page has no H1.", "tooltip": "Headline tag",
        }],
    }
    finalize = {"top_priorities": [], "wins": [], "roadmap": []}
    return ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "StartAuditReport", "args": header, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "AddAuditCategory", "args": category, "id": "c2"}]),
        AIMessage(content="", tool_calls=[{"name": "FinalizeAuditReport", "args": finalize, "id": "c3"}]),
        AIMessage(content="Report published."),
    ])


async def test_run_pipeline_crawls_then_publishes_the_report_the_tools_built(
    crawl_result, emitted, acme_business_context, monkeypatch
):
    """`routes/audit.py` runs this by default, and until now only the live
    suite exercised it. The crawl and the model are replaced at their seams;
    everything between them is real: the step events bracket the work, the
    report the tools assembled reaches the stream as version 1, and the same
    report is what the route gets back to persist."""
    import agents.audit.v1.runner as v1
    import agents.audit.v3.runner as v3

    async def offline_crawl(_url, **_kwargs):
        return crawl_result

    monkeypatch.setattr(v3, "run_crawl", offline_crawl)
    monkeypatch.setattr(v1, "resolve_chat_model", lambda *_a, **_k: _model_that_builds_a_template_report())

    report = await v1.LangChainAuditRunner(api_key="unused-no-network").run_pipeline(
        session_id="offline-audit", url="https://getduct.ai",
        business_context=acme_business_context, emit=emitted, report_mode="template",
    )

    steps = [
        (e["step_id"], e["status"]) for e in emitted.events
        if e["event"] in (AgentEvent.STEP_STARTED, AgentEvent.STEP_FINISHED)
    ]
    assert steps == [
        (AuditStep.FETCH_SITEMAP, "running"), (AuditStep.FETCH_SITEMAP, "success"),
        (AuditStep.SYNTHESIZE_AUDIT, "running"), (AuditStep.SYNTHESIZE_AUDIT, "success"),
    ]
    version = next(e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION)
    assert version["version_id"] == 1
    # The model claimed 72; one FAIL in the 20-point tier is what the findings support.
    assert version["payload"]["structured_data"]["overall_score"] == 80
    assert version["payload"]["structured_data"]["score_band"] == "good"
    assert report is not None
    assert [c.id for c in report.structured_data.categories] == ["on_page_seo"]
    assert report.structured_data.categories[0].score == 80
    assert set(e["event"] for e in emitted.events) <= set(AgentEvent)


# ---------------------------------------------------------------------------
# Provider content shapes
# ---------------------------------------------------------------------------

def test_split_chunk_handles_provider_variations():
    assert split_chunk(AIMessage(content="plain")) == ("plain", "")
    assert split_chunk(
        AIMessage(content=[{"type": "text", "text": "visible"}])
    ) == ("visible", "")
    # Anthropic-style reasoning blocks
    assert split_chunk(
        AIMessage(content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "out"}])
    ) == ("out", "hmm")
    # OpenAI-style reasoning blocks
    assert split_chunk(
        AIMessage(content=[{"type": "reasoning", "text": "why"}])
    ) == ("", "why")
    # Unknown block types are dropped, never leaked as report text
    assert split_chunk(AIMessage(content=[{"type": "image", "url": "x"}])) == ("", "")
    assert split_chunk(None) == ("", "")


# ---------------------------------------------------------------------------
# Route wiring — engine selection
# ---------------------------------------------------------------------------

def test_route_defaults_to_v1_and_opts_in_to_v3():
    """V1 is production; V3 is per-request opt-in.

    The flip is the first step of consolidating onto one harness. Audit is where
    it costs nothing — both runners exist with the same ``run_pipeline``
    signature and event vocabulary (asserted below) — and running V1 by default
    is how it earns the confidence the old default was waiting for.
    """
    from agents.audit.v3.runner import ClaudeAuditRunner
    from agents.engines import Engine
    from agents.models import ModelName, Provider
    from routes.audit import _build_runner, _resolve_agent_config
    from agents.audit.v1.runner import LangChainAuditRunner

    # An unset engine resolves to V1...
    _provider, _model, engine = _resolve_agent_config("")
    assert engine == Engine.V1

    # ...and V3 remains reachable by naming it.
    _provider, _model, engine_v3 = _resolve_agent_config("v3")
    assert engine_v3 == Engine.V3

    v3 = _build_runner("k", Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, Engine.V3)
    v1 = _build_runner("k", Provider.GOOGLE_GENAI, ModelName.GEMINI_2_5_FLASH, Engine.V1)

    assert isinstance(v3, ClaudeAuditRunner)
    assert isinstance(v1, LangChainAuditRunner)


def test_both_runners_share_the_run_pipeline_signature():
    """The route calls one signature; swapping engines must change nothing else."""
    import inspect

    from agents.audit.v1.runner import LangChainAuditRunner
    from agents.audit.v3.runner import ClaudeAuditRunner

    v1 = inspect.signature(LangChainAuditRunner.run_pipeline).parameters
    v3 = inspect.signature(ClaudeAuditRunner.run_pipeline).parameters
    assert list(v1) == list(v3)


# ---------------------------------------------------------------------------
# A site that never answers is not audited
# ---------------------------------------------------------------------------

async def test_an_unreachable_site_closes_the_crawl_step_as_an_error_and_never_reaches_the_model(
    emitted, acme_business_context, monkeypatch
):
    """Two live runs scored a homepage that returned no response 84 "good".
    The crawl now raises instead; the runner closes the step as an error so the
    UI stops spinning, and re-raises so the route reports the failure."""
    import agents.audit.v1.runner as v1
    import agents.audit.v3.runner as v3
    from service.crawl.fetcher import SiteUnreachableError

    async def dead_site(url, **_kwargs):
        raise SiteUnreachableError(url)

    def no_model(*_a, **_k):
        raise AssertionError("synthesis must not start for a site that never answered")

    monkeypatch.setattr(v3, "run_crawl", dead_site)
    monkeypatch.setattr(v1, "resolve_chat_model", no_model)

    with pytest.raises(SiteUnreachableError, match="Could not reach https://dead.example"):
        await v1.LangChainAuditRunner(api_key="unused-no-network").run_pipeline(
            session_id="offline-audit", url="https://dead.example",
            business_context=acme_business_context, emit=emitted, report_mode="template",
        )

    steps = [
        (e["step_id"], e["status"]) for e in emitted.events
        if e["event"] in (AgentEvent.STEP_STARTED, AgentEvent.STEP_FINISHED)
    ]
    assert steps == [(AuditStep.FETCH_SITEMAP, "running"), (AuditStep.FETCH_SITEMAP, "error")]
    failed = next(e for e in emitted.events if e.get("status") == "error")
    assert "no HTTP response" in failed["error"]
    assert not any(e["event"] == AgentEvent.ARTIFACT_VERSION for e in emitted.events)
