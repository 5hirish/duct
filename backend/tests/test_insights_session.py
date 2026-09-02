"""Autonomous insights session — assembly, event contract, and the chat loop.

Phase 1 of `docs/engineering/autonomous-insights-agent-plan.md`: insights stops
being a request-shaped pipeline and becomes a session like audit and content.
What matters, and what these pin:

  * the frontend cannot tell which agent or harness served a run — only the
    shared `AgentEvent` vocabulary reaches the stream;
  * `deepagents` mounts a VIRTUAL filesystem, not the real one, so an
    autonomous loop cannot reach Duct's source or the host;
  * an unremembered session gets no memory tools at all — the agent cannot
    write what it cannot reach;
  * the session stays open after the opening turn and each follow-up continues
    the SAME thread rather than restarting one.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agents.core.events import AgentEvent
from agents.core.lc import _dispatch_updates
from agents.insights.prompts.autonomous import (
    build_insights_system_prompt,
    build_insights_user_prompt,
)
from agents.insights.schema import InsightsRequest, InsightsSession, create_insights_session
from agents.insights.v1.runner import AutonomousInsightsRunner


class ToolCallingFake(FakeMessagesListChatModel):
    """A fake that accepts bind_tools, so it can drive a real agent loop.

    `FakeMessagesListChatModel` cycles its responses rather than exhausting
    them, so a two-turn test needs two entries and a *failing* turn needs
    `RaisingFake` instead.
    """

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


class RaisingFake(ToolCallingFake):
    """Answers the first turn, then fails — the "one bad turn" case."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if getattr(self, "_used", False):
            raise RuntimeError("provider blew up")
        self._used = True
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.fixture
def session() -> InsightsSession:
    return create_insights_session(str(uuid.uuid4()))


@pytest.fixture
def emitted():
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    emit.events = events  # type: ignore[attr-defined]
    return emit


def _fake(*responses: str, cls=ToolCallingFake):
    return cls(responses=[AIMessage(content=r) for r in responses])


RUNNER = AutonomousInsightsRunner(api_key="unused-no-network")


def _tool_names(agent) -> set[str]:
    """Tool names bound into a compiled agent graph."""
    for node in agent.nodes.values():
        seq = getattr(getattr(node, "bound", None), "steps", None) or []
        for step in seq:
            if hasattr(step, "tools_by_name"):
                return set(step.tools_by_name)
    tool_node = agent.nodes.get("tools")
    inner = getattr(tool_node, "bound", tool_node)
    return set(getattr(inner, "tools_by_name", {}))


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

def test_a_project_and_a_sentence_is_a_complete_request():
    """The whole point of the rewrite: no connectors, accounts, goal or dates.

    If this ever needs more fields to validate, the wizard is growing back.
    """
    req = InsightsRequest.model_validate({"project_id": "p1", "prompt": "why did CPA jump?"})

    assert req.prompt == "why did CPA jump?"
    assert req.remember is True
    assert req.focus == ""  # an optional steer, never a required mode


def test_request_rejects_unknown_fields():
    with pytest.raises(Exception):
        InsightsRequest.model_validate({"project_id": "p1", "customer_id": "123-456"})


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def test_system_prompt_is_byte_identical_across_sessions():
    """The cached prefix must not vary per customer — per-project data belongs
    in the user turn (service/memory.py, and the same rule audit and content
    follow)."""
    assert build_insights_system_prompt() == build_insights_system_prompt()


def test_system_prompt_describes_the_tools_actually_mounted():
    """The capability stanza tracks what is really mounted, phase by phase. An
    agent that believes it can fetch data it cannot produces a confident, wrong
    brief — the exact failure this agent exists to eliminate."""
    prompt = build_insights_system_prompt()

    assert "Prove the number before you use it" in prompt
    for tool in ("FetchData", "ReadConnectorNotes", "ListDataSources", "SelectAccount"):
        assert tool in prompt


def test_system_prompt_carries_the_catalog_and_the_notes_index():
    """Both are identical for every customer, so they belong in the cached
    prefix — and the agent cannot name an entity it has never been shown."""
    prompt = build_insights_system_prompt()

    assert "<entity_catalogs>" in prompt
    assert "search_terms" in prompt          # a catalog entity
    assert "ReadConnectorNotes" in prompt
    assert "`stripe`" in prompt              # a notes index entry


def test_verification_is_delegated_not_optional():
    prompt = build_insights_system_prompt()

    assert "Delegate the checking" in prompt
    assert "could not check" in prompt


def test_system_prompt_teaches_the_discovery_order():
    """ListDataSources before guessing, RequestConnection only when needed, and
    a decline is a normal answer — the three habits that replace the wizard."""
    prompt = build_insights_system_prompt()

    assert "ListDataSources" in prompt
    assert "SelectAccount" in prompt
    assert "Decline is a normal answer" in prompt


def test_user_turn_carries_the_per_project_blocks():
    out = build_insights_user_prompt(
        prompt="how is paid search doing?",
        business_context="<business_context>\nBusiness: Acme\n</business_context>",
        memory="<project_memory>\nTarget CPA is $45\n</project_memory>",
    )

    assert "Acme" in out
    assert "Target CPA is $45" in out
    assert "<request>" in out and "how is paid search doing?" in out


def test_empty_prompt_becomes_an_opening_instruction():
    """Opening a session without typing anything is a normal entry point."""
    out = build_insights_user_prompt(prompt="")

    assert "without saying what they want" in out


# ---------------------------------------------------------------------------
# Agent assembly
# ---------------------------------------------------------------------------

def test_filesystem_tools_are_virtual_not_the_real_disk():
    """deepagents' default backend is graph state, so `read_file` cannot reach
    Duct's source or the host. No Bash tool exists at all — the guarantee the
    product makes about agent isolation."""
    names = _tool_names(RUNNER.build_agent(llm=_fake("ok")))

    assert {"read_file", "write_file", "ls"} <= names
    assert "Bash" not in names and "bash" not in names


def test_planning_is_mounted():
    """Task planning became opt-in in deepagents 0.7 — assert it is actually on,
    since the todo stream is what makes a long autonomous run legible."""
    assert "write_todos" in _tool_names(RUNNER.build_agent(llm=_fake("ok")))


def test_memory_tools_need_a_project(session, emitted):
    unscoped = RUNNER.build_agent(llm=_fake("ok"), project_id=None)
    scoped = RUNNER.build_agent(llm=_fake("ok"), project_id=uuid.uuid4())

    assert "RememberFact" not in _tool_names(unscoped)
    assert {"RememberFact", "SearchMemory", "GetMemory"} <= _tool_names(scoped)


def test_unremembered_session_gets_no_memory_tools():
    """"Don't remember this" is enforced by absence, not by instruction: the
    agent cannot write what it cannot reach."""
    agent = RUNNER.build_agent(llm=_fake("ok"), project_id=uuid.uuid4(), remember=False)

    assert "RememberFact" not in _tool_names(agent)


def test_connector_discovery_is_mounted(session, emitted):
    """The tools that replace the wizard's first four steps."""
    agent = RUNNER.build_agent(
        llm=_fake("ok"), project_id=uuid.uuid4(), user_id=uuid.uuid4(),
        session=session, session_id=session.session_id, emit=emitted,
    )

    assert {"ListDataSources", "SelectAccount", "RequestConnection"} <= _tool_names(agent)


def test_tools_that_pause_need_a_session_and_a_project(session, emitted):
    """A tool that cannot serve its purpose should not be offered at all — a
    model calling SelectAccount with nowhere to persist the choice is worse than
    one that never sees it."""
    anonymous = RUNNER.build_agent(llm=_fake("ok"), user_id=uuid.uuid4())

    names = _tool_names(anonymous)
    assert "ListDataSources" in names          # read-only, still useful
    assert "SelectAccount" not in names
    assert "RequestConnection" not in names


def test_signed_out_sessions_get_no_connector_tools():
    """No user, no connectors: there is nothing to enumerate and no owner to
    attribute a binding to."""
    assert not {"ListDataSources", "SelectAccount", "RequestConnection"} & _tool_names(
        RUNNER.build_agent(llm=_fake("ok"), project_id=uuid.uuid4(), user_id=None)
    )


def test_ask_user_tool_only_present_with_a_session(session, emitted):
    without = RUNNER.build_agent(llm=_fake("ok"))
    with_session = RUNNER.build_agent(llm=_fake("ok"), 
        session=session, session_id=session.session_id, emit=emitted
    )

    assert "AskUserQuestion" not in _tool_names(without)
    assert "AskUserQuestion" in _tool_names(with_session)


# ---------------------------------------------------------------------------
# Streaming contract
# ---------------------------------------------------------------------------

async def test_only_the_shared_event_vocabulary_reaches_the_stream(session, emitted):
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("Your CPA rose because of one campaign."),
        session=session, prompt="why did CPA jump?",
        chat_idle_timeout=0.01,
    )

    kinds = [e["event"] for e in emitted.events]
    assert set(kinds) <= set(AgentEvent), "an insights-only event would break the shared UI"
    assert AgentEvent.AGENT_MESSAGE_CHUNK in kinds
    assert AgentEvent.MESSAGE_STOP in kinds


async def test_opening_turn_finishes_before_the_chat_loop(session, emitted):
    """PIPELINE_FINISHED is what moves the UI out of "working" and into chat, so
    it must land after the first turn — not when the session eventually ends."""
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("Here is the read."),
        session=session, prompt="status?",
        chat_idle_timeout=0.01,
    )

    kinds = [e["event"] for e in emitted.events]
    assert AgentEvent.PIPELINE_FINISHED in kinds
    assert kinds.index(AgentEvent.MESSAGE_STOP) < kinds.index(AgentEvent.PIPELINE_FINISHED)


async def test_follow_up_continues_the_same_session(session, emitted):
    """The session stays open: a queued message drives a second turn, and the
    sentinel from close_session ends the loop."""
    await session.chat_queue.put("and what about mobile?")
    await session.chat_queue.put(None)  # sentinel — close_session's stop signal

    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("First answer.", "Second answer."),
        session=session, prompt="status?",
        chat_idle_timeout=2.0,
    )

    prose = "".join(
        e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert "First answer." in prose and "Second answer." in prose
    # Two turns, so two turn boundaries.
    assert sum(1 for e in emitted.events if e["event"] == AgentEvent.MESSAGE_STOP) == 2


async def test_a_failed_turn_does_not_end_the_session(session, emitted):
    """One bad turn must leave the user able to rephrase."""
    await session.chat_queue.put("follow up")
    await session.chat_queue.put(None)

    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("First answer.", cls=RaisingFake),
        session=session, prompt="status?",
        chat_idle_timeout=2.0,
    )

    kinds = [e["event"] for e in emitted.events]
    assert AgentEvent.STEP_FAILED in kinds
    assert AgentEvent.PIPELINE_FAILED not in kinds  # the session survived


async def test_short_replies_are_not_truncated(session, emitted):
    """Regression: the parser holds back the tail of every chunk in case it is a
    split `<duct_artifact>` open tag, so a turn only completes on flush. V1 never
    flushed, which swallowed any reply shorter than the tag — the common case for
    a chat agent. Both V3 runners already flushed; V1 does now too.
    """
    await RUNNER.run_session(
        session.session_id, emitted, llm=_fake("Up 12%."),
        session=session, prompt="cpa?", chat_idle_timeout=0.01,
    )

    prose = "".join(
        e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK
    )
    assert prose == "Up 12%."


async def test_todos_reach_the_frontend_shape(session, emitted):
    """The deepagents/LangChain Todo is {content, status} — exactly what
    AuditTodos.jsx renders, so no mapping layer should creep in."""
    captured: list[list] = []

    async def on_todo(todos):
        captured.append(todos)

    await _dispatch_updates(
        {"tools": {"todos": [{"content": "Pull search terms", "status": "in_progress"}]}},
        on_todo=on_todo, on_tool_use=None, on_tool_result=None,
    )

    assert captured == [[{"content": "Pull search terms", "status": "in_progress"}]]


async def test_update_dispatch_survives_unexpected_shapes():
    """LangGraph puts control keys beside the nodes and middleware may deliver a
    list of deltas. A stream translator must never be what ends a run."""
    calls: list = []

    async def on_todo(todos):
        calls.append(todos)

    for chunk in (None, "junk", {"__interrupt__": ("x",)}, {"n": None}, {"n": [{"todos": []}]}):
        await _dispatch_updates(chunk, on_todo=on_todo, on_tool_use=None, on_tool_result=None)

    assert calls == []  # nothing raised, nothing spurious emitted


# ---------------------------------------------------------------------------
# Route wiring
# ---------------------------------------------------------------------------

async def test_route_creates_an_insights_session_not_an_audit_one():
    """Insights used to borrow AuditSession because it had no session of its own.
    It has one now, and the route must hand back that type — the runner reads
    fields (artifact_project_id, memory_off) that only it declares."""
    from routes.agents import _create_session_for

    created = _create_session_for("insights", str(uuid.uuid4()), {"prompt": "hi"})

    assert isinstance(created, InsightsSession)
    assert created.agent_type == "insights"


async def test_route_rejects_a_wizard_shaped_body():
    """The old pipeline's fields must not quietly work — a caller still sending
    connectors and a customer_id should hear that the contract changed."""
    from fastapi import HTTPException
    from routes.agents import _create_session_for, _dispatch_start

    session_id = str(uuid.uuid4())
    _create_session_for("insights", session_id, {})

    async def emit(_e):
        pass

    with pytest.raises(HTTPException) as exc:
        await _dispatch_start(
            "insights", session_id,
            {"connections": ["google_ads"], "customer_id": "123", "goal": "maximize_roas"},
            emit,
        )
    assert exc.value.status_code == 422


def test_agent_spec_advertises_the_session_capabilities():
    """Discovery drives what the frontend offers, so the spec has to say the
    agent asks questions and holds a chat — it claimed neither before."""
    from agents.registry import AgentCapability, AgentType, get_spec

    spec = get_spec(AgentType.INSIGHTS)

    assert spec.active
    assert AgentCapability.INTERACTIVE_QUESTIONS in spec.capabilities
    assert AgentCapability.CHAT in spec.capabilities
    # The config schema is what a client validates against — it must be the
    # session request, not an empty dict.
    assert "prompt" in spec.config_schema.get("properties", {})


# ---------------------------------------------------------------------------
# Unattended runs — the scheduled brief, which can never block on a human
# ---------------------------------------------------------------------------

UNATTENDED_BRIEF = """<duct_artifact>
---
title: Weekly paid search
---
# Weekly paid search

Spend held. GSC was never connected, so organic overlap is unverified.
</duct_artifact>"""


def test_an_unattended_run_cannot_ask_a_question():
    """`backend/CLAUDE.md` is explicit that the scheduled brief is the product
    and can never block on a person. Blocking is made impossible rather than
    discouraged: the tools that pause are simply not mounted."""
    interactive = RUNNER.build_agent(
        llm=_fake("x"), session=create_insights_session("s"), session_id="s",
        emit=lambda body: None, project_id=uuid.uuid4(), user_id=uuid.uuid4(),
    )
    unattended = RUNNER.build_agent(
        llm=_fake("x"), session=create_insights_session("s"), session_id="s",
        emit=lambda body: None, project_id=uuid.uuid4(), user_id=uuid.uuid4(),
        interactive=False,
    )

    assert "AskUserQuestion" in _tool_names(interactive)
    assert "AskUserQuestion" not in _tool_names(unattended)
    # The connector tools that pause go too — but the read-only one stays, or
    # the agent cannot even tell the reader what it could not reach.
    for pausing in ("RequestConnection", "SelectAccount"):
        assert pausing in _tool_names(interactive)
        assert pausing not in _tool_names(unattended)
    assert "ListDataSources" in _tool_names(unattended)
    assert "FetchData" in _tool_names(unattended)


def test_an_unattended_run_is_told_there_is_nobody_to_ask():
    """A prompt that still describes an interactive session would have the
    agent plan around a question it will never get to ask — which produces a
    brief with a hole in it instead of a stated assumption."""
    from agents.insights.prompts.autonomous import (
        CAPABILITIES_PHASE_3,
        CAPABILITIES_UNATTENDED,
    )

    assert "There is nobody to ask" in CAPABILITIES_UNATTENDED
    assert "state the assumption in the brief" in CAPABILITIES_UNATTENDED
    assert "AskUserQuestion" not in CAPABILITIES_UNATTENDED
    # The interactive stanza must NOT say that — it has the tool.
    assert "There is nobody to ask" not in CAPABILITIES_PHASE_3


async def test_run_once_returns_the_brief_it_wrote(emitted):
    brief = await RUNNER.run_once(emitted, llm=_fake(UNATTENDED_BRIEF), prompt="weekly brief")

    assert brief["title"] == "Weekly paid search"
    assert brief["format"] == "markdown"
    assert "Spend held" in brief["content"]

    kinds = [e["event"] for e in emitted.events]
    assert AgentEvent.ARTIFACT_VERSION in kinds
    assert AgentEvent.PIPELINE_FINISHED in kinds
    # No chat loop: one turn, one boundary, and the call returns.
    assert kinds.count(AgentEvent.MESSAGE_STOP) == 1


async def test_a_run_that_wrote_nothing_says_so(emitted):
    """An unattended run that reached no conclusion worth keeping must be
    distinguishable from one that produced a brief — a caller logging "ok" for
    an empty result is how a broken schedule stays invisible for a month."""
    brief = await RUNNER.run_once(emitted, llm=_fake("I could not reach any data."), prompt="?")

    assert brief == {}
    assert AgentEvent.ARTIFACT_VERSION not in [e["event"] for e in emitted.events]


def test_the_wizards_request_contract_is_gone_not_merely_unused():
    """Phase 6. `GenerateRequest` was the six-step form's output — connectors,
    accounts, goal, date range — and `UnifiedInsight` the envelope it produced.
    Leaving them importable is how a deleted path grows a second caller."""
    import routes.schemas as schemas

    for name in ("GenerateRequest", "ReportRequest", "UnifiedInsight", "InsightMetadata"):
        assert not hasattr(schemas, name), f"{name} outlived the wizard"


def test_the_unattended_endpoint_takes_a_project_and_a_sentence():
    """The URL survives; its contract does not. /api/insights/generate now
    validates the same body as a session."""
    import inspect

    import routes.generate as generate_routes

    assert hasattr(generate_routes, "generate_insight")
    # The wizard's streaming twin had no caller once the form went.
    assert not hasattr(generate_routes, "generate_insight_stream")
    assert not hasattr(generate_routes, "_run_generate_pipeline")
    # The modes catalogue stays — the organic-growth page still renders it.
    assert hasattr(generate_routes, "list_insight_modes")

    params = inspect.signature(generate_routes.generate_insight).parameters
    assert "user_keys" in params, "bring-your-own provider keys must survive the rewire"
