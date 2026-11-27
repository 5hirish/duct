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
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from agents.audit.events import AuditStep
from agents.audit.schema import CrawlPlan, CrawlResult
from agents.audit.v1.runner import build_audit_agent, mounts_connected_data
from agents.core.events import AgentEvent
from agents.core.lc import (
    MAX_QUESTIONS,
    build_ask_user_tool,
    split_chunk,
    stream_agent,
)
from agents.core.session import BaseAgentSession, close_session, register_session
from tests.fakes import RecordingFake, ToolCallingFake, fake_llm, tool_names as _tool_names


def _thread(name: str) -> dict:
    """The audit agent is checkpointed, so every run needs a thread to write to."""
    return {"configurable": {"thread_id": f"test-{name}"}}


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


def test_connected_data_is_mounted_only_for_an_in_depth_project_audit(crawl_result):
    """The audit ranked findings by crawl signals alone even with Search Console
    connected, because it had no FetchData. The in-depth audit of a project now
    gets it; the quick audit stays a crawl, because it exists to be fast."""
    llm = ToolCallingFake(responses=[AIMessage(content="ok")])
    project, user = uuid.uuid4(), uuid.uuid4()

    in_depth = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        project_id=project, user_id=user, remember=False, with_data=True,
    )
    quick = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        project_id=project, user_id=user, remember=False, with_data=False,
    )

    assert {"FetchData", "ReadConnectorNotes"} <= set(_tool_names(in_depth))
    assert "FetchData" not in _tool_names(quick)

    assert mounts_connected_data(project, lead_magnet=False, crawl_depth="deep")
    assert not mounts_connected_data(project, lead_magnet=False, crawl_depth="light")
    assert not mounts_connected_data(project, lead_magnet=True, crawl_depth="deep")
    assert not mounts_connected_data(None, lead_magnet=False, crawl_depth="deep")


# ---------------------------------------------------------------------------
# Streaming contract
# ---------------------------------------------------------------------------

async def test_stream_emits_the_shared_event_vocabulary(crawl_result, emitted):
    llm = ToolCallingFake(responses=[AIMessage(content="Audit looks healthy.")])
    agent = build_audit_agent(crawl_result=crawl_result, llm=llm, system_prompt="audit")

    async def on_close(_raw: str, _turn: str) -> None:
        pass

    await stream_agent(
        agent, "audit getduct.ai", emitted, on_artifact_close=on_close, config=_thread("vocab"),
    )

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

    await stream_agent(
        agent, "audit", emitted, on_artifact_close=on_close, config=_thread("artifact"),
    )

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
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1

    async def offline_crawl(_url, **_kwargs):
        return crawl_result

    monkeypatch.setattr(audit_crawl, "run_crawl", offline_crawl)
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
        (AuditStep.CRAWL_PAGES, "running"), (AuditStep.CRAWL_PAGES, "success"),
        # The business context names a company, so the research pass runs. It
        # degrades to the crawl's own signals here — the fake model has no web.
        (AuditStep.ENRICHING, "running"), (AuditStep.ENRICHING, "success"),
        (AuditStep.SYNTHESIZE_AUDIT, "running"),
        # One progress tick per category the model adds.
        (AuditStep.SYNTHESIZE_AUDIT, "running"),
        (AuditStep.SYNTHESIZE_AUDIT, "success"),
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


class _DraftingFake(ToolCallingFake):
    """The report-building fake, plus the structured answer the draft
    classifier asks the same model for."""

    def with_structured_output(self, _schema, **_kwargs):
        from agents.audit.draft import DraftInference
        from agents.audit.schema import DraftPersona

        class _Once:
            async def ainvoke(self, _prompt):
                return DraftInference(
                    industry="SaaS & Software",
                    business_model="B2B",
                    brand_voice="Technical",
                    personas=[DraftPersona(name="Marketing lead", description="wants signups")],
                )

        return _Once()


async def test_a_drafting_run_uses_the_prefetched_crawl_and_emits_two_draft_layers(
    emitted, monkeypatch
):
    """Onboarding: the crawl ran while the user connected a provider, the run
    picks it up instead of crawling again, and the project arrives as two
    PROJECT_DRAFT events — the crawl's own facts before enrichment, the
    classified fields after — with provenance on every field."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.prefetch as prefetch
    import agents.audit.v1.runner as v1
    from agents.audit.schema import PageSignals
    from agents.core.context import BusinessContext

    # An audit session, not the bare base one: the report tools write
    # versions onto it, and a draft run publishes a report like any other.
    session = audit_crawl.create_audit_session(str(uuid.uuid4()))

    root = PageSignals(
        url="https://getduct.ai", page_type="landing_page", title="Duct | The channel for your data",
        meta_description="Duct checks a number before it trusts it.", favicon="https://getduct.ai/favicon.ico",
    )
    crawled = CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai", landing_pages=[root.url]), pages=[root])

    async def must_not_crawl(_url, **_kwargs):
        raise AssertionError("the prefetched crawl should have been used")

    async def prefetched(_crawl_id, **_kwargs):
        return crawled

    monkeypatch.setattr(audit_crawl, "run_crawl", must_not_crawl)
    monkeypatch.setattr(prefetch, "take_crawl", prefetched)
    monkeypatch.setattr(
        v1, "resolve_chat_model",
        lambda *_a, **_k: _DraftingFake(responses=_model_that_builds_a_template_report().responses),
    )

    await v1.LangChainAuditRunner(api_key="unused-no-network").run_pipeline(
        session_id=session.session_id, url="https://getduct.ai",
        business_context=BusinessContext(), emit=emitted, report_mode="template",
        crawl_id="prefetched-1", draft_project=True,
        # A registered session stays open for follow-ups after the report;
        # nobody is going to ask one here.
        chat_idle_timeout=0.1,
    )

    drafts = [e for e in emitted.events if e["event"] == AgentEvent.PROJECT_DRAFT]
    assert [d["layer"] for d in drafts] == ["crawl", "inferred"]
    crawl_fields = drafts[0]["fields"]
    assert crawl_fields["name"] == {"value": "Duct", "provenance": "crawl"}
    assert crawl_fields["pitch"]["value"] == "Duct checks a number before it trusts it."
    inferred_fields = drafts[1]["fields"]
    assert inferred_fields["industry"] == {"value": "SaaS & Software", "provenance": "inferred"}
    assert inferred_fields["personas"]["value"][0]["name"] == "Marketing lead"

    steps = [(e["step_id"], e["status"]) for e in emitted.events if e["event"] == AgentEvent.STEP_FINISHED]
    assert (AuditStep.FETCH_SITEMAP, "success") in steps, "the ladder reads the same with a prefetched crawl"
    # An empty business context would have skipped research; drafting turns it on.
    assert (AuditStep.ENRICHING, "success") in steps
    # The draft is emitted before synthesis starts, so the app has a project
    # while the report is still being written.
    order = [e["event"] for e in emitted.events]
    assert order.index(AgentEvent.PROJECT_DRAFT) < order.index(AgentEvent.ARTIFACT_VERSION)


class _ReadsDocumentsFake(_DraftingFake):
    """The drafting fake, answering the documents call with its own schema."""

    def with_structured_output(self, schema, **kwargs):
        from agents.audit.draft import DocumentCompetitor, DocumentInference

        if schema is not DocumentInference:
            return super().with_structured_output(schema, **kwargs)

        class _Once:
            async def ainvoke(self, _prompt):
                return DocumentInference(
                    name="Duct", industry="Marketing & Advertising",
                    competitors=[DocumentCompetitor(name="Supermetrics", differentiator="checks the numbers")],
                )

        return _Once()


async def test_documents_are_read_before_research_and_draft_between_the_site_and_the_guess(
    emitted, monkeypatch
):
    """The files the user added beside the site become their own draft layer,
    after the crawl's and before the classifier's, and the step that reads
    them runs before competitor research so the research hears the names."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.documents as documents
    import agents.audit.prefetch as prefetch
    import agents.audit.v1.runner as v1
    from agents.audit.schema import PageSignals
    from agents.core.context import BusinessContext
    from service.documents import DocumentKind, Extracted

    session = audit_crawl.create_audit_session(str(uuid.uuid4()))
    root = PageSignals(url="https://getduct.ai", page_type="landing_page", title="Duct")
    crawled = CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai", landing_pages=[root.url]), pages=[root])

    async def prefetched(_crawl_id, **_kwargs):
        return crawled

    asked: list[list[str]] = []

    def take(ids, **_kwargs):
        asked.append(ids)
        return [Extracted(name="deck.pdf", kind=DocumentKind.PDF, text="Duct vs Supermetrics", pages=8, truncated=False)]

    monkeypatch.setattr(prefetch, "take_crawl", prefetched)
    monkeypatch.setattr(documents, "take_documents", take)
    monkeypatch.setattr(
        v1, "resolve_chat_model",
        lambda *_a, **_k: _ReadsDocumentsFake(responses=_model_that_builds_a_template_report().responses),
    )

    await v1.LangChainAuditRunner(api_key="unused-no-network").run_pipeline(
        session_id=session.session_id, url="https://getduct.ai",
        business_context=BusinessContext(), emit=emitted, report_mode="template",
        crawl_id="prefetched-1", draft_project=True, document_ids=["doc-1"],
        chat_idle_timeout=0.1,
    )

    assert asked == [["doc-1"]]
    drafts = [e for e in emitted.events if e["event"] == AgentEvent.PROJECT_DRAFT]
    assert [d["layer"] for d in drafts] == ["crawl", "documents", "inferred"]
    from_documents = drafts[1]["fields"]
    assert from_documents["industry"] == {"value": "Marketing & Advertising", "provenance": "document"}
    assert from_documents["competitors"]["value"][0]["name"] == "Supermetrics"

    finished = [e for e in emitted.events if e["event"] == AgentEvent.STEP_FINISHED]
    steps = [e["step_id"] for e in finished]
    assert steps.index(AuditStep.READ_DOCUMENTS) < steps.index(AuditStep.ENRICHING)
    read = next(e for e in finished if e["step_id"] == AuditStep.READ_DOCUMENTS)
    assert read["payload"] == {"documents": 1, "drafted": True}


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

def test_every_audit_route_builds_the_one_runner():
    """Both entry points used to pick an engine; the Claude Agent SDK one is
    gone. The engine parameter survives because `agents/engines.py` is still
    where a second harness would be declared if there is ever another."""
    from agents.audit.v1.runner import LangChainAuditRunner
    from agents.engines import Engine
    from agents.models import ModelName, Provider
    from routes.audit import _build_runner, _resolve_agent_config

    _provider, _model, engine = _resolve_agent_config("")
    assert engine == Engine.V1

    runner = _build_runner("k", Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH, Engine.V1)
    assert isinstance(runner, LangChainAuditRunner)


def test_the_runner_still_answers_the_call_the_routes_make():
    """The routes pass these by keyword; a rename here is a 500 at run time."""
    import inspect

    from agents.audit.v1.runner import LangChainAuditRunner

    pipeline = inspect.signature(LangChainAuditRunner.run_pipeline).parameters
    assert {"session_id", "url", "business_context", "emit", "report_mode",
            "template_id", "chat_idle_timeout", "lead_magnet"} <= set(pipeline)

    resume = inspect.signature(LangChainAuditRunner.run_resume).parameters
    assert {"session_id", "url", "emit", "chat_idle_timeout", "report_mode"} <= set(resume)


# ---------------------------------------------------------------------------
# A site that never answers is not audited
# ---------------------------------------------------------------------------

async def test_an_unreachable_site_closes_the_crawl_step_as_an_error_and_never_reaches_the_model(
    emitted, acme_business_context, monkeypatch
):
    """Two live runs scored a homepage that returned no response 84 "good".
    The crawl now raises instead; the runner closes the step as an error so the
    UI stops spinning, and re-raises so the route reports the failure."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1
    from service.crawl.fetcher import SiteUnreachableError

    async def dead_site(url, **_kwargs):
        raise SiteUnreachableError(url)

    def no_model(*_a, **_k):
        raise AssertionError("synthesis must not start for a site that never answered")

    monkeypatch.setattr(audit_crawl, "run_crawl", dead_site)
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


# ---------------------------------------------------------------------------
# The session stays open — follow-up chat and resume
# ---------------------------------------------------------------------------

async def _drain(session, events, *, wait_for: str, timeout: float = 3.0) -> dict:
    """Wait for one event kind to show up on the emitted list."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        for event in events:
            if event["event"] == wait_for:
                return event
        await asyncio.sleep(0.02)
    raise AssertionError(f"{wait_for} never arrived; got {[e['event'] for e in events]}")


async def test_the_audit_answers_a_follow_up_on_the_same_thread(
    crawl_result, emitted, acme_business_context, monkeypatch
):
    """V1 used to stream one turn and return, so every message after the report
    hit a closed session. The run now stays open until the user goes quiet."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1

    async def offline_crawl(_url, **_kwargs):
        return crawl_result

    monkeypatch.setattr(audit_crawl, "run_crawl", offline_crawl)
    monkeypatch.setattr(
        v1, "resolve_chat_model", lambda *_a, **_k: _model_that_builds_a_template_report()
    )
    session = register_session(BaseAgentSession(
        session_id="audit-followup", agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    ))

    pipeline = asyncio.create_task(
        v1.LangChainAuditRunner(api_key="unused-no-network").run_pipeline(
            session_id="audit-followup", url="https://getduct.ai",
            business_context=acme_business_context, emit=emitted,
            report_mode="template", chat_idle_timeout=2.0,
        )
    )
    # The bare PIPELINE_FINISHED is what moves the UI out of "working"; the
    # chat loop is running behind it.
    await _drain(session, emitted.events, wait_for=AgentEvent.PIPELINE_FINISHED)
    await session.chat_queue.put("which page is worst?")
    report = await asyncio.wait_for(pipeline, timeout=10)

    assert report is not None, "the follow-up must not lose the report"
    prose = "".join(
        e.get("text", "") for e in emitted.events
        if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "Report published." in prose
    close_session("audit-followup")


async def test_resume_continues_the_thread_without_crawling_again(
    emitted, monkeypatch
):
    """The project-scoped audit resumes a stored conversation. V1 had no
    run_resume at all, so this path only ever worked on the Claude Agent SDK."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1

    async def must_not_crawl(*_a, **_k):
        raise AssertionError("resume must not re-crawl the site")

    monkeypatch.setattr(audit_crawl, "run_crawl", must_not_crawl)
    monkeypatch.setattr(
        v1, "resolve_chat_model",
        lambda *_a, **_k: ToolCallingFake(responses=[AIMessage(content="Still the pricing page.")]),
    )
    session = register_session(BaseAgentSession(
        session_id="audit-resume", agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    ))

    resumed = asyncio.create_task(
        v1.LangChainAuditRunner(api_key="unused-no-network").run_resume(
            session_id="audit-resume", url="https://getduct.ai",
            emit=emitted, chat_idle_timeout=2.0, report_mode="template",
        )
    )
    await _drain(session, emitted.events, wait_for=AgentEvent.PIPELINE_FINISHED)
    await session.chat_queue.put("what should I fix first?")
    await asyncio.wait_for(resumed, timeout=10)

    prose = "".join(
        e.get("text", "") for e in emitted.events
        if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "Still the pricing page." in prose
    close_session("audit-resume")

def test_the_project_scoped_audit_builds_the_one_runner_too():
    """The session path — artifacts, memory, execution tools, resume — ran V3
    unconditionally, which is what actually kept the Agent SDK in production."""
    import inspect

    import routes.agents as agents_route
    from agents.audit.v1.runner import LangChainAuditRunner
    from agents.engines import Engine, resolve_engine

    source = inspect.getsource(agents_route)
    assert "ClaudeAuditRunner" not in source, "the Agent SDK runner is gone"
    assert resolve_engine("") == Engine.V1
    assert agents_route.LangChainAuditRunner is LangChainAuditRunner


def test_v1_reads_its_project_scope_from_the_session_not_the_caller():
    """routes/agents.py stamps artifact_project_id only after checking
    membership, so its presence is the authorisation. A session without one
    mounts no library, no memory and no execution tools."""
    from uuid import uuid4

    from agents.audit.v1.runner import LangChainAuditRunner

    runner = LangChainAuditRunner(api_key="k")

    async def emit(_event: dict) -> None:
        pass

    scoped = SimpleNamespace(
        artifact_project_id=uuid4(), user_id=uuid4(), conversation_id=uuid4(), memory_off=False
    )
    ephemeral = SimpleNamespace(artifact_project_id=None, user_id=None, conversation_id=None)

    assert runner._project_wiring(scoped, emit)["remember"] is True
    assert runner._project_wiring(ephemeral, emit)["project_id"] is None

    # "Don't remember this session" keeps the project but drops the memory tools.
    quiet = SimpleNamespace(
        artifact_project_id=uuid4(), user_id=uuid4(), conversation_id=None, memory_off=True
    )
    assert runner._project_wiring(quiet, emit)["remember"] is False


async def test_each_published_report_is_a_new_numbered_version(crawl_result):
    """The next version number is read off the session's list, so a run that
    never records one numbers every revision 1. That was invisible until V1
    could revise a report at all."""
    from agents.audit.schema import AuditSession
    from agents.audit.v1.runner import _record_version

    session = AuditSession(
        session_id="versions", agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    )
    first = SimpleNamespace(update_label="Initial audit", generated_at="t1")
    second = SimpleNamespace(update_label="Update 2", generated_at="t2")

    _record_version(session, first, 1)
    _record_version(session, second, 2)

    assert [v.version_id for v in session.report_versions] == [1, 2]
    assert [v.label for v in session.report_versions] == ["Initial audit", "Update 2"]
    # A runner with no session (the eval harness, a script) must not blow up.
    _record_version(None, first, 1)


# ---------------------------------------------------------------------------
# Context pruning — what an in-depth audit read stays readable
# ---------------------------------------------------------------------------

def _audit_messages(*, data_chars: int, follow_ups: int = 0) -> list:
    """An in-depth audit's opening run as the pruner sees it: six data reads,
    StartAuditReport, nine categories and the finish — then, optionally, chat
    turns that each fetch a batch of pages."""
    from langchain_core.messages import HumanMessage, ToolMessage

    calls = [
        ("ListDataSources", 2_000), ("ReadConnectorNotes", 3_000), ("ReadConnectorNotes", 3_000),
        ("FetchData", data_chars), ("FetchData", data_chars), ("FetchData", data_chars),
        ("StartAuditReport", 40), *[("AddAuditCategory", 40)] * 9, ("FinalizeAuditReport", 40),
        *[("FetchPages", 50_000)] * follow_ups,
    ]
    messages: list = [HumanMessage(content="crawl " * 8_000)]
    for i, (name, size) in enumerate(calls):
        call_id = f"call_{i}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": call_id}]))
        messages.append(ToolMessage(content=f"{name}:" + "x" * size, tool_call_id=call_id, name=name))
    return messages


def _prune(messages: list) -> list:
    from langchain.agents.middleware import ClearToolUsesEdit
    from langchain_core.messages.utils import count_tokens_approximately

    from agents.audit.v1.runner import LIMITS

    ClearToolUsesEdit(
        trigger=LIMITS.tool_result_prune_trigger, keep=LIMITS.tool_results_kept,
    ).apply(messages, count_tokens=count_tokens_approximately)
    return [m.name for m in messages if getattr(m, "content", "") == "[cleared]"]


def test_an_in_depth_audit_keeps_the_data_it_read_while_it_writes_the_report():
    """The trigger is in tokens. At 40 it pruned from the first call, and the
    Search Console reads were cleared before the summary that quotes them."""
    assert _prune(_audit_messages(data_chars=40_000)) == []


def test_a_long_follow_up_chat_is_still_pruned():
    cleared = _prune(_audit_messages(data_chars=40_000, follow_ups=10))
    assert cleared, "the trigger must still fire once a chat grows"


def test_the_audit_thread_is_keyed_on_the_conversation(emitted, monkeypatch):
    """A session id is minted per open. Keyed on it, every resume of a
    project-scoped audit started an empty checkpoint beside its own
    transcript — the failure the checkpointer was added to prevent. The
    conversation outlives the session, so it is the thread."""
    from uuid import uuid4

    import agents.audit.v1.runner as v1

    seen: dict = {}

    class _Loop:
        def __init__(self, agent, **kwargs):
            seen.update(kwargs)
            self.opened = False

    monkeypatch.setattr(v1, "DeepSession", _Loop)
    runner = v1.LangChainAuditRunner(api_key="unused-no-network")
    conversation_id = uuid4()

    with_conversation = BaseAgentSession(
        session_id="audit-open-2", agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    )
    with_conversation.conversation_id = conversation_id
    runner._session_loop(
        object(), object(), with_conversation, emitted, "audit-open-2",
        on_artifact_close=lambda *_a, **_k: None, announce_finish=True,
    )
    assert seen["thread_id"] == str(conversation_id)

    ephemeral = BaseAgentSession(
        session_id="audit-teaser", agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    )
    runner._session_loop(
        object(), object(), ephemeral, emitted, "audit-teaser",
        on_artifact_close=lambda *_a, **_k: None, announce_finish=True,
    )
    assert seen["thread_id"] == "audit-teaser"


# ---------------------------------------------------------------------------
# What the V3 runner did that V1 had lost (Sept 2026 port)
# ---------------------------------------------------------------------------

def _crawled() -> CrawlResult:
    """A two-page crawl with something on each page worth counting."""
    from agents.audit.schema import PageSignals

    return CrawlResult(
        plan=CrawlPlan(
            root_url="https://getduct.ai",
            sitemap_url="https://getduct.ai/sitemap.xml",
            landing_pages=["https://getduct.ai", "https://getduct.ai/pricing"],
            total_sitemap_urls=12,
        ),
        robots_txt="User-agent: *\nAllow: /",
        pages=[
            PageSignals(url="https://getduct.ai", title="Duct", h1s=["Duct"], ttfb_ms=200.0),
            PageSignals(
                url="https://getduct.ai/pricing", ttfb_ms=400.0, is_noindex=True,
                is_spa_suspected=True, redirect_chain=[{"url": "https://getduct.ai/price", "status": 301}],
            ),
        ],
        crawl_errors=["https://getduct.ai/blog: timed out"],
    )


def _template_responses() -> list:
    return list(_model_that_builds_a_template_report().responses)


async def _offline_pipeline(monkeypatch, emitted, *, crawl=None, llm=None, runner=None, **kwargs):
    """run_pipeline with the crawl and the model replaced at their seams. No
    business context, so no research pass spends a canned response."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1
    from agents.audit.schema import AuditBusinessContext

    crawl = crawl or _crawled()

    async def offline_crawl(_url, **_kwargs):
        return crawl

    model = llm or _model_that_builds_a_template_report()
    monkeypatch.setattr(audit_crawl, "run_crawl", offline_crawl)
    monkeypatch.setattr(v1, "resolve_chat_model", lambda *_a, **_k: model)
    runner = runner or v1.LangChainAuditRunner(api_key="unused-no-network")
    return await runner.run_pipeline(
        session_id=kwargs.pop("session_id", f"offline-audit-{uuid.uuid4()}"), url="https://getduct.ai",
        business_context=AuditBusinessContext(), emit=emitted, report_mode="template",
        **kwargs,
    )


def _versions(events: list) -> list[dict]:
    return [e for e in events if e["event"] == AgentEvent.ARTIFACT_VERSION]


def _stored_report(**structured):
    from agents.audit.schema import AuditReport, CrawlSummary, StructuredAuditData, VersionedReport

    data = StructuredAuditData(
        url="https://getduct.ai", generated_at="2026-11-01T00:00:00+00:00",
        overall_score=80, score_band="good", pages_crawled=2, total_sitemap_urls=12,
        crawl_summary=CrawlSummary(avg_ttfb_ms=300.0, pages_noindex=1),
        **structured,
    )
    report = AuditReport(
        url="https://getduct.ai", generated_at=data.generated_at, update_label="Initial audit",
        report_mode="template", template_id="seo_v1", structured_data=data,
    )
    return VersionedReport(version_id=1, label="Initial audit", report=report, created_at=data.generated_at)


def _audit_session(session_id: str, versions: list | None = None):
    from agents.audit.schema import AuditSession

    session = AuditSession(
        session_id=session_id, agent_type="audit_seo",
        event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
    )
    session.report_versions = list(versions or [])
    return register_session(session)


async def test_a_resumed_audit_shows_its_stored_report_again(emitted, monkeypatch):
    """Reopening an audit showed "AI synthesis finished but no report was
    generated": the resume sent PIPELINE_FINISHED with nothing before it. The
    stored version comes back first, flagged replay so nothing stores it twice."""
    import agents.audit.v1.runner as v1

    monkeypatch.setattr(v1, "resolve_chat_model", lambda *_a, **_k: fake_llm("ok"))
    session = _audit_session("audit-resume-replay", [_stored_report()])

    resumed = asyncio.create_task(
        v1.LangChainAuditRunner(api_key="unused-no-network").run_resume(
            session_id=session.session_id, url="https://getduct.ai",
            emit=emitted, chat_idle_timeout=0.2, report_mode="template",
        )
    )
    await _drain(session, emitted.events, wait_for=AgentEvent.PIPELINE_FINISHED)
    close_session(session.session_id)
    await asyncio.wait_for(resumed, timeout=5)

    kinds = [e["event"] for e in emitted.events]
    replay = next(e for e in _versions(emitted.events))
    assert kinds.index(AgentEvent.ARTIFACT_VERSION) < kinds.index(AgentEvent.PIPELINE_FINISHED)
    assert replay["replay"] is True
    assert replay["version_id"] == 1
    assert replay["label"] == "Initial audit"
    assert replay["payload"]["structured_data"]["overall_score"] == 80


async def test_a_revision_in_a_resumed_chat_keeps_the_crawl_strip(emitted, monkeypatch):
    """A resumed chat runs on a crawl stub with no pages, so the strip it
    publishes is the stored one carried forward, not an empty one."""
    import agents.audit.v1.runner as v1

    revised = _stored_report().report.structured_data.model_dump(exclude={"crawl_summary"})
    model = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "SubmitAuditReport", "args": revised, "id": "r1"}]),
        AIMessage(content="Revised."),
    ])
    monkeypatch.setattr(v1, "resolve_chat_model", lambda *_a, **_k: model)
    session = _audit_session("audit-resume-revise", [_stored_report()])

    resumed = asyncio.create_task(
        v1.LangChainAuditRunner(api_key="unused-no-network").run_resume(
            session_id=session.session_id, url="https://getduct.ai",
            emit=emitted, chat_idle_timeout=1.0, report_mode="template",
        )
    )
    await _drain(session, emitted.events, wait_for=AgentEvent.PIPELINE_FINISHED)
    await session.chat_queue.put("drop the pricing finding")
    await asyncio.wait_for(resumed, timeout=10)
    close_session(session.session_id)

    fresh = [v for v in _versions(emitted.events) if not v.get("replay")]
    assert [v["version_id"] for v in fresh] == [2]
    assert fresh[0]["label"] == "Update 2"
    strip = fresh[0]["payload"]["structured_data"]["crawl_summary"]
    assert strip["avg_ttfb_ms"] == 300.0 and strip["pages_noindex"] == 1


async def test_the_report_carries_the_crawl_strip_counted_from_the_pages(emitted, monkeypatch):
    """The report's speed/redirect/noindex strip only draws when the field is
    set, and V1 never set it."""
    await _offline_pipeline(monkeypatch, emitted)

    version = _versions(emitted.events)[0]
    assert version["label"] == "Initial audit"
    assert version["payload"]["structured_data"]["crawl_summary"] == {
        "avg_ttfb_ms": 300.0, "pages_with_redirects": 1, "spa_pages_count": 1,
        "pages_noindex": 1, "pages_missing_title": 1, "pages_missing_h1": 1,
    }


async def test_each_category_added_moves_the_synthesis_progress(emitted, monkeypatch):
    """The progress row reads "N/9 categories" off SYNTHESIZE_AUDIT; with no
    callback wired it showed only a clock for the whole build."""
    await _offline_pipeline(monkeypatch, emitted)

    progress = [
        e["payload"] for e in emitted.events
        if e["event"] == AgentEvent.STEP_STARTED
        and e["step_id"] == AuditStep.SYNTHESIZE_AUDIT and e.get("payload")
    ]
    assert progress == [{"categories_done": 1, "categories_total": 9, "last_category": "On-page SEO"}]


async def test_the_crawl_steps_carry_what_the_crawl_found(emitted, monkeypatch):
    """The sitemap and crawl rows expand to the files and pages the crawl
    read; V1 closed the first with no payload and never sent the second."""
    await _offline_pipeline(monkeypatch, emitted)

    finished = {
        e["step_id"]: e for e in emitted.events if e["event"] == AgentEvent.STEP_FINISHED
    }
    sitemap = finished[AuditStep.FETCH_SITEMAP]["payload"]
    assert sitemap["sitemap_url"] == "https://getduct.ai/sitemap.xml"
    assert sitemap["landing_page_urls"] == ["https://getduct.ai", "https://getduct.ai/pricing"]
    assert sitemap["robots_txt_found"] and sitemap["robots_txt_lines"] == 2
    assert not sitemap["llms_txt_found"]

    pages = finished[AuditStep.CRAWL_PAGES]["payload"]
    assert [p["url"] for p in pages["pages"]] == ["https://getduct.ai", "https://getduct.ai/pricing"]
    assert pages["pages"][1]["is_noindex"] is True
    assert pages["errors"] == ["https://getduct.ai/blog: timed out"]


def _tools_by_name(agent) -> dict:
    tool_node = agent.nodes.get("tools")
    inner = getattr(tool_node, "bound", tool_node)
    return dict(getattr(inner, "tools_by_name", {}))


async def test_the_audit_chat_can_read_and_search_the_web(crawl_result):
    """V3's chat had WebSearch and WebFetch; V1 mounted neither, so "what do
    competitors rank for?" had nothing to answer with. A page of the audited
    site still goes to FetchPages, which keeps the SEO signals."""
    from agents.models import ModelName, Provider

    llm = ToolCallingFake(responses=[AIMessage(content="ok")])
    agent = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        provider=Provider.OPENAI, model=ModelName.GPT_6_1_SOL, gemini_api_key="search-key",
    )
    tools = _tools_by_name(agent)
    assert {"WebFetch", "WebSearch", "FetchPages"} <= set(tools)

    own_site = await tools["WebFetch"].ainvoke({"url": "https://www.getduct.ai/pricing"})
    assert "FetchPages" in own_site

    # No key for Duct's search on a provider with no built-in: fetch only.
    no_search = build_audit_agent(
        crawl_result=crawl_result, llm=llm, system_prompt="audit",
        provider=Provider.OPENAI, model=ModelName.GPT_6_1_SOL,
    )
    assert "WebFetch" in _tool_names(no_search)
    assert "WebSearch" not in _tool_names(no_search)


def test_the_audit_form_s_effort_is_read_as_a_thinking_level():
    from agents.audit.schema import AuditRequest
    from agents.preferences import UserPreferences

    assert AuditRequest(url="getduct.ai").thinking_level() == ""  # nothing chosen
    assert AuditRequest(url="getduct.ai", effort="low").thinking_level() == "quick"
    assert AuditRequest(url="getduct.ai", effort="high").thinking_level() == "deep"
    saved = AuditRequest(
        url="getduct.ai", effort="low", user_preferences=UserPreferences(thinking="exhaustive"),
    )
    assert saved.thinking_level() == "exhaustive"


async def test_the_requested_thinking_reaches_the_model(emitted, monkeypatch):
    """The form's effort and the saved dial reached no model call: the runner
    took no thinking and never passed one to resolve_chat_model."""
    import agents.audit.crawl as audit_crawl
    import agents.audit.v1.runner as v1
    from agents.audit.schema import AuditBusinessContext

    asked: list[dict] = []

    def resolve(*_a, **kwargs):
        asked.append(kwargs)
        return _model_that_builds_a_template_report()

    async def offline_crawl(_url, **_kwargs):
        return _crawled()

    monkeypatch.setattr(audit_crawl, "run_crawl", offline_crawl)
    monkeypatch.setattr(v1, "resolve_chat_model", resolve)
    await v1.LangChainAuditRunner(api_key="unused-no-network", thinking="deep").run_pipeline(
        session_id=f"offline-audit-{uuid.uuid4()}", url="https://getduct.ai",
        business_context=AuditBusinessContext(), emit=emitted, report_mode="template",
    )
    assert asked and all(k.get("thinking") == "deep" for k in asked)

    # The public audit route builds its runner with the level too.
    from agents.engines import Engine
    from agents.models import ModelName, Provider
    from routes.audit import _build_runner

    runner = _build_runner("k", Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, Engine.V1, thinking="quick")
    assert runner.thinking == "quick"


async def test_synthesis_says_whether_the_model_reasoned(emitted, monkeypatch):
    """The finished synthesis row shows "reasoned" when the model thought."""
    responses = _template_responses()
    responses[-1] = AIMessage(content=[
        {"type": "thinking", "thinking": "Weighing the noindex page."},
        {"type": "text", "text": "Report published."},
    ])
    await _offline_pipeline(monkeypatch, emitted, llm=ToolCallingFake(responses=responses))

    finished = next(
        e for e in emitted.events
        if e["event"] == AgentEvent.STEP_FINISHED and e["step_id"] == AuditStep.SYNTHESIZE_AUDIT
    )
    assert finished["payload"]["reasoned"] is True


async def test_an_opening_turn_without_a_report_gets_one_recovery_nudge(emitted, monkeypatch):
    """A model that analyses the whole turn and stops before publishing used
    to end the run with no report. One nudge, then the report."""
    from langchain_core.messages import HumanMessage

    llm = RecordingFake(responses=[AIMessage(content="The site looks fine overall."), *_template_responses()])
    report = await _offline_pipeline(monkeypatch, emitted, llm=llm)

    assert report is not None
    assert [v["version_id"] for v in _versions(emitted.events)] == [1]
    assert AgentEvent.PIPELINE_FINISHED in [e["event"] for e in emitted.events]
    humans = [m for m in llm.requests[-1]["messages"] if isinstance(m, HumanMessage)]
    assert len(humans) == 2, "the opening turn, then exactly one nudge"


async def test_a_turn_that_publishes_is_never_nudged(emitted, monkeypatch):
    from langchain_core.messages import HumanMessage

    llm = RecordingFake(responses=_template_responses())
    await _offline_pipeline(monkeypatch, emitted, llm=llm)

    humans = [m for m in llm.requests[-1]["messages"] if isinstance(m, HumanMessage)]
    assert len(humans) == 1


async def test_the_system_prompt_carries_the_connector_knowledge(emitted, monkeypatch):
    """V3 always gave the audit the Search Console pack, and the Ads, GA4 and
    GTM packs once it could propose changes there. Static per configuration,
    so the prefix still caches."""
    from langchain_core.messages import SystemMessage

    from agents.audit.v1.runner import system_prompt_for
    from agents.knowledge import knowledge_block

    llm = RecordingFake(responses=_template_responses())
    await _offline_pipeline(monkeypatch, emitted, llm=llm)

    system = next(m for m in llm.requests[0]["messages"] if isinstance(m, SystemMessage))
    assert knowledge_block(("gsc",)) in system.content
    assert knowledge_block(("gsc",)) in system_prompt_for("template", "seo_v1", with_data=False, execution=False)
    with_execution = system_prompt_for("template", "seo_v1", with_data=True, execution=True)
    assert knowledge_block(("gsc", "google_ads", "ga4", "gtm")) in with_execution
    # One variant per configuration: no run's own text in it.
    assert with_execution == system_prompt_for("template", "seo_v1", with_data=True, execution=True)
