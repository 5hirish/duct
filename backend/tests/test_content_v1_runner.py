"""Content Studio on deepagents — assembly, event contract, and the chat loop.

The port of the content agent off the Claude Agent SDK. What matters, and
what these pin:

  * the frontend cannot tell which harness served a run — only the shared
    `AgentEvent` vocabulary reaches the stream, and the content-specific
    events (PLAN_GENERATED / POST_DRAFT_UPDATED, the sub-agent dispatch chips)
    keep the shapes the workspace already renders;
  * the writer tools are the orchestrator's alone — a sub-agent cannot reach
    them, so "sub-agents never write" is structural;
  * the filesystem is virtual and there is no shell;
  * a session stays open after the opening turn, each follow-up continues the
    same thread, and a turn that ends with nothing persisted gets one nudge.

Fake chat model throughout — no API key, no network, no database.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from langchain_core.messages import AIMessage

from agents.content.artifacts import parse_artifact_json
from agents.content.schema import ContentSession, ContentTool
from agents.content.subagents import DRAFT_POST_TOOLS, GENERAL_PURPOSE_TOOLS, RESEARCH_PILLAR_TOOLS
from agents.content.v1.runner import (
    ContentRunner,
    close_session,
    create_draft_session,
    create_plan_session,
)
from agents.core.events import AgentEvent, AgentStep
from agents.models import ModelName, Provider
from tests.fakes import ToolCallingFake, fake_llm, tool_names

RUNNER = ContentRunner(api_key="unused-no-network")
PROJECT = uuid.uuid4()


@pytest.fixture
def plan_session() -> ContentSession:
    session = create_plan_session(str(uuid.uuid4()), PROJECT)
    yield session
    close_session(session.session_id)


@pytest.fixture
def draft_session() -> ContentSession:
    session = create_draft_session(str(uuid.uuid4()), PROJECT)
    yield session
    close_session(session.session_id)


def _agent(session: ContentSession, emit, **kw):
    return RUNNER.build_agent(
        llm=kw.pop("llm", fake_llm("ok")),
        session=session,
        session_id=session.session_id,
        emit=emit,
        project_id=session.project_id,
        mode=session.mode,
        **kw,
    )


def _kinds(emitted) -> list[str]:
    return [e["event"] for e in emitted.events]


def _plan_payload() -> dict:
    return {"type": "plan", "project_id": str(PROJECT), "days": [{"topic": "t", "pillar": "p"}]}


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def test_the_orchestrator_gets_every_content_tool_and_the_scaffolding(plan_session, emitted):
    names = tool_names(_agent(plan_session, emitted))

    assert {t.value for t in ContentTool} <= names
    assert {"task", "write_todos", "AskUserQuestion", "WebFetch"} <= names


def test_filesystem_is_virtual_and_there_is_no_shell(plan_session, emitted):
    names = tool_names(_agent(plan_session, emitted))

    assert {"ls", "read_file", "write_file"} <= names
    assert "execute" not in names and "Bash" not in names and "bash" not in names


def test_sub_agents_never_get_the_writer_tools():
    """Enforced by which tools are on their lists, not by the prompt — the
    harness's general-purpose default (every tool of the parent) included."""
    writers = {ContentTool.SUBMIT_PLAN, ContentTool.SUBMIT_POST_DRAFT, ContentTool.EDIT_SLIDE,
               ContentTool.GENERATE_IMAGE, ContentTool.EDIT_IMAGE, ContentTool.PUBLISH_POST,
               ContentTool.MARK_POSTED, ContentTool.RENDER_SLIDE}

    for tools in (RESEARCH_PILLAR_TOOLS, DRAFT_POST_TOOLS, GENERAL_PURPOSE_TOOLS):
        assert not writers & set(tools)


def test_unremembered_session_gets_no_memory_tools(plan_session, emitted):
    names = tool_names(_agent(plan_session, emitted, remember=False))

    assert not names & {"RememberFact", "SearchMemory", "GetMemory"}


def test_no_session_means_no_content_tools_and_no_questions():
    """The shape `thread_state` builds: a compiled graph to read a checkpoint
    with, and nothing that could act on a project."""
    names = tool_names(RUNNER.build_agent(llm=fake_llm("ok"), interactive=False))

    assert "AskUserQuestion" not in names
    assert not {t.value for t in ContentTool} & names


def test_native_web_search_rides_only_on_a_verified_provider():
    from agents.core.web_tools import provider_web_search_tool

    assert provider_web_search_tool(Provider.ANTHROPIC)["name"] == "web_search"
    assert provider_web_search_tool(Provider.OPENROUTER) is None
    assert provider_web_search_tool(None) is None


def test_vision_follows_the_provider():
    """Only a provider whose API takes image blocks in a tool result can run
    the look-and-critique loop; the prompt says so for the others."""
    from agents.content.prompts import NO_VISION_DIRECTIVE, build_orchestrator_system_prompt

    assert ContentRunner(api_key="", provider=Provider.ANTHROPIC).vision is True
    assert ContentRunner(api_key="", provider=Provider.OPENAI, model=ModelName.GPT_5_MINI).vision is False
    assert NO_VISION_DIRECTIVE in build_orchestrator_system_prompt(None, "draft_post", vision=False)
    assert NO_VISION_DIRECTIVE not in build_orchestrator_system_prompt(None, "draft_post", vision=True)


# ---------------------------------------------------------------------------
# Streaming contract
# ---------------------------------------------------------------------------

async def _drive(session, emitted, llm, *, resume=False, chat=None):
    """One session: opening turn, then optional chat turns, then idle-out.

    A resume carries no opening prompt — that is what `_run_mode` passes, and
    what makes reload/refresh silent: a prompt on a resumed idle thread would
    be a follow-up turn."""
    task = asyncio.create_task(RUNNER._run_session(
        session, emitted,
        system_prompt="sys", opening_prompt="" if resume else "plan it",
        llm=llm, chat_idle_timeout=0.2, resume=resume,
    ))
    for message in chat or []:
        await asyncio.sleep(0.05)
        await session.chat_queue.put(message)
    await task


async def test_only_the_shared_vocabulary_reaches_the_stream(plan_session, emitted):
    await _drive(plan_session, emitted, fake_llm("Here is your plan."))

    kinds = _kinds(emitted)
    assert set(kinds) <= set(AgentEvent), "a content-only event would break the shared UI"
    assert AgentEvent.AGENT_MESSAGE_CHUNK in kinds
    assert AgentEvent.MESSAGE_STOP in kinds
    assert AgentEvent.PIPELINE_FINISHED in kinds


async def test_a_streamed_plan_artifact_becomes_the_preview_event(plan_session, emitted):
    payload = _plan_payload()
    llm = fake_llm(f"Drafted.\n<duct_artifact>{json.dumps(payload)}</duct_artifact>")

    await _drive(plan_session, emitted, llm)

    generated = [e for e in emitted.events if e["event"] == AgentEvent.PLAN_GENERATED]
    assert generated and generated[0]["payload"] == payload
    assert generated[0]["source"] == "duct_artifact"
    # The tag's contents never leak into the chat as prose.
    prose = "".join(e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK)
    assert "duct_artifact" not in prose and json.dumps(payload) not in prose


async def test_a_post_artifact_routes_to_the_post_event(draft_session, emitted):
    payload = {"type": "post", "project_id": str(PROJECT), "post_dir_slug": "x", "pillar": "p", "topic": "t"}
    await _drive(draft_session, emitted, fake_llm(f"<duct_artifact>{json.dumps(payload)}</duct_artifact>"))

    kinds = _kinds(emitted)
    assert AgentEvent.POST_DRAFT_UPDATED in kinds and AgentEvent.PLAN_GENERATED not in kinds


async def test_an_opening_turn_with_nothing_persisted_gets_exactly_one_nudge(plan_session, emitted):
    """The model analysed everything and saved nothing. One nudge, then the
    user takes over — never a loop, and never a hollow success either: the
    finish event says there is no plan id yet."""
    llm = fake_llm("Thinking about it.", "Still thinking.", "Chat reply.")

    await _drive(plan_session, emitted, llm)

    stops = _kinds(emitted).count(AgentEvent.MESSAGE_STOP)
    assert stops == 2, "opening turn + one nudge, no more"
    finished = next(e for e in emitted.events if e["event"] == AgentEvent.PIPELINE_FINISHED)
    assert finished["mode"] == "plan_month" and finished["plan_id"] is None


async def test_a_persisted_plan_is_not_nudged_and_rides_on_the_finish_event(plan_session, emitted):
    plan_session.plan_id = uuid.uuid4()  # what submit_plan stashes
    await _drive(plan_session, emitted, fake_llm("Done.", "never sent"))

    assert _kinds(emitted).count(AgentEvent.MESSAGE_STOP) == 1
    finished = next(e for e in emitted.events if e["event"] == AgentEvent.PIPELINE_FINISHED)
    assert finished["plan_id"] == str(plan_session.plan_id)


async def test_a_chat_turn_continues_the_session_and_releases_the_queued_row(plan_session, emitted):
    plan_session.plan_id = uuid.uuid4()
    await _drive(
        plan_session, emitted, fake_llm("Plan.", "Tweaked."),
        chat=[{"role": "user", "content": "make it punchier", "client_message_id": "row-7"}],
    )

    kinds = _kinds(emitted)
    assert kinds.count(AgentEvent.MESSAGE_STOP) == 2
    assert {"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": "row-7"} in emitted.events
    # The opening finish is emitted once, never again for a chat turn.
    assert kinds.count(AgentEvent.PIPELINE_FINISHED) == 1


async def test_a_sub_agent_dispatch_shows_as_a_step_chip(plan_session, emitted):
    """The SDK's Agent hooks produced `dispatch_subagent:<name>` steps; the
    same chips now come from the task tool's traffic in the stream. The
    sub-agent itself runs on the same fake, so its report closes the chip."""
    plan_session.plan_id = uuid.uuid4()
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "task",
            "args": {"description": "find topics for face_shape", "subagent_type": "research_pillar"},
            "id": "t1",
        }]),
        AIMessage(content='{"pillar_id": "face_shape", "items": []}'),  # the sub-agent's report
        AIMessage(content="Folded the research in."),
    ])

    await _drive(plan_session, emitted, llm)

    steps = [e for e in emitted.events if e["event"] in (AgentEvent.STEP_STARTED, AgentEvent.STEP_FINISHED)]
    started = next(e for e in steps if e["event"] == AgentEvent.STEP_STARTED)
    assert started["step_id"] == f"{AgentStep.DISPATCH_SUBAGENT.value}:research_pillar"
    assert started["summary"].startswith("find topics")
    finished = next(e for e in steps if e["event"] == AgentEvent.STEP_FINISHED)
    assert finished["step_id"] == started["step_id"]
    # A sub-agent's report is the agent's to relay, never streamed as prose.
    prose = "".join(e["text"] for e in emitted.events if e["event"] == AgentEvent.AGENT_MESSAGE_CHUNK)
    assert "pillar_id" not in prose


async def test_a_question_parks_the_thread_and_an_answer_resumes_it(plan_session, emitted):
    plan_session.plan_id = uuid.uuid4()
    question = {"question": "Which pillar first?", "header": "Pillar"}
    llm = ToolCallingFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "AskUserQuestion", "args": {"questions": [question]}, "id": "q1"}]),
        AIMessage(content="Starting with face shape."),
    ])

    task = asyncio.create_task(RUNNER._run_session(
        plan_session, emitted, system_prompt="sys", opening_prompt="plan it",
        llm=llm, chat_idle_timeout=0.2, resume=False,
    ))
    for _ in range(50):
        await asyncio.sleep(0.02)
        if plan_session.pending_pauses:
            break
    assert plan_session.pending_pauses, "the pause is on the session before any answer could arrive"
    (interrupt_id,) = plan_session.pending_pauses
    # The card went out before the turn's stop marker, and nothing "finished".
    kinds_so_far = _kinds(emitted)
    assert AgentEvent.QUESTIONS_REQUIRED in kinds_so_far and AgentEvent.PIPELINE_FINISHED not in kinds_so_far

    await plan_session.chat_queue.put({"resume": {interrupt_id: {question["question"]: "face shape"}}})
    await task

    kinds = _kinds(emitted)
    assert AgentEvent.PIPELINE_FINISHED in kinds
    assert not plan_session.pending_pauses


async def test_a_failed_chat_turn_is_a_row_not_the_end_of_the_session(plan_session, emitted):
    from tests.fakes import RaisingFake

    plan_session.plan_id = uuid.uuid4()
    llm = RaisingFake(responses=[AIMessage(content="Plan.")])

    await _drive(plan_session, emitted, llm, chat=[{"role": "user", "content": "again"}])

    failed = [e for e in emitted.events if e["event"] == AgentEvent.STEP_FAILED]
    assert failed and failed[0]["code"] and "step_id" not in failed[0]
    assert AgentEvent.PIPELINE_FAILED not in _kinds(emitted)


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

async def test_resume_of_an_idle_thread_is_silent_and_ready(plan_session, emitted):
    """Reload/refresh must just bring the session back: no greeting turn, the
    UI goes READY at once, and the model is not called until the user
    speaks."""
    class _Explodes(ToolCallingFake):
        def _generate(self, *a, **k):
            raise AssertionError("resume must not call the model")

    plan_session.conversation_id = uuid.uuid4()
    await _drive(plan_session, emitted, _Explodes(responses=[AIMessage(content="x")]), resume=True)

    kinds = _kinds(emitted)
    assert kinds == [AgentEvent.PIPELINE_FINISHED]
    assert emitted.events[0]["resumed"] is True


async def test_resume_of_a_pre_checkpoint_conversation_primes_the_first_message(plan_session, emitted, monkeypatch):
    """A conversation recorded before the thread was durable has a transcript
    in the DB and no checkpoint. Its summary rides on the user's first
    message; a thread that already has messages needs no primer."""
    import agents.content.persistence as persistence

    async def _primer(*_a, **_k):
        return "<resumed_context>earlier</resumed_context>\n\n"

    monkeypatch.setattr(persistence, "build_reprime_context", _primer)
    plan_session.conversation_id = uuid.uuid4()
    await _drive(plan_session, emitted, fake_llm("x"), resume=True)

    assert plan_session.needs_reprime is True
    assert "earlier" in plan_session.resume_primer


# ---------------------------------------------------------------------------
# The artifact parser — defends against real model-output quirks
# ---------------------------------------------------------------------------

def test_parser_survives_real_model_output_shapes():
    """A fenced object parses; unescaped HTML inside slides_html either
    recovers (the field is stripped — the writer derives it anyway) or yields
    None, and never raises; garbage is None. The runner logs and continues on
    None, so "never raises" is the contract that keeps a session alive."""
    fenced = '```json\n{"type": "post", "project_id": "p", "post_dir_slug": "x"}\n```'
    assert parse_artifact_json(fenced)["type"] == "post"
    broken = '{"type":"post","slides_html":"<div class="slide">x</div>","caption":"c"}'
    recovered = parse_artifact_json(broken)
    assert recovered is None or (recovered["type"] == "post" and isinstance(recovered["slides_html"], str))
    assert parse_artifact_json("not json at all") is None
