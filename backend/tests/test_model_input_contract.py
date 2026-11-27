"""What the person sent is what the model receives, on every way in.

Each layer had its own tests: the app builds the image block, the recorder
stores it, the runner streams a turn. None asked what the model was handed,
and from 2026-09-05 to 2026-11-27 a picture attached to a follow-up never
reached it: the chat loop flattened the message to text, the model said it
could not see the image, and every suite stayed green. These tests post
through the real messages route into a real session loop and read the request
the fake model got, so the seam between the layers is what is under test.

One row per entry path. A new way for a message to reach a turn gets a row.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import routes.agents as agents_routes
from agents.core.deep_session import DeepSession, RunLimits, build_deep_session_agent
from agents.core.session import BaseAgentSession, close_session, register_session
from agents.models import ModelName, Provider
from tests.fakes import RecordingFake

PICTURE = "QUFBQQ=="
PDF = "JVBERi0="


def _limits() -> RunLimits:
    return RunLimits(
        model_calls_per_run=8, model_calls_per_thread=50,
        tool_calls_per_run=10, tool_calls_per_thread=100,
        tool_result_prune_trigger=1_000, tool_results_kept=2,
    )


def _message() -> list[dict]:
    """What `contentBlocks` in app/src/lib/attachments.js sends for a note
    with a screenshot and a PDF attached."""
    return [
        {"type": "text", "text": "does slide 3 fit the topic?"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PICTURE}},
        {"type": "file", "base64": PDF, "mime_type": "application/pdf", "filename": "brief.pdf"},
    ]


def _carries_attachments(message) -> bool:
    content = message.content if isinstance(message.content, list) else []
    image = any(b.get("type") == "image" and PICTURE in str(b) for b in content if isinstance(b, dict))
    pdf = any(b.get("type") == "file" and PDF in str(b) for b in content if isinstance(b, dict))
    return image and pdf


def _saw_attachments(llm: RecordingFake) -> bool:
    return any(
        _carries_attachments(m)
        for request in llm.requests
        for m in request["messages"]
        if isinstance(m, HumanMessage)
    )


class _Rig:
    """A registered session, its loop and the model it talks to."""

    def __init__(self, emitted):
        self.session = register_session(BaseAgentSession(
            session_id=f"contract-{uuid.uuid4()}", agent_type="insights",
            event_queue=asyncio.Queue(), chat_queue=asyncio.Queue(),
            steer_queue=asyncio.Queue(),
        ))
        self.llm = RecordingFake(responses=[AIMessage(content=f"reply {i}") for i in range(8)])
        agent = build_deep_session_agent(
            llm=self.llm, tools=[], system_prompt="x", limits=_limits(), session=self.session,
        )
        self.loop = DeepSession(
            agent, emit=emitted, thread_id=str(uuid.uuid4()), limits=_limits(),
            provider=Provider.ANTHROPIC, model=ModelName.CLAUDE_HAIKU, log_prefix="contract",
            summariser=self.llm, session=self.session,
        )

    async def post(self, content) -> dict:
        """The messages route, as the app calls it."""
        return await agents_routes.send_message(
            "insights", self.session.session_id,
            agents_routes.AgentMessage(type="chat", content=content),
            user=None, user_keys={},
        )

    def close(self):
        close_session(self.session.session_id)


@pytest.fixture
def rig(emitted):
    made = _Rig(emitted)
    yield made
    made.close()


async def _settle(rig: _Rig) -> None:
    """Let the loop pick up what was queued and finish the turn it starts."""
    for _ in range(100):
        await asyncio.sleep(0.01)
        if rig.session.chat_queue.empty() and not rig.session.turn_active:
            return


async def test_an_idle_follow_up(rig):
    task = asyncio.create_task(rig.loop.run("open", resume=False, chat_idle_timeout=5))
    await _settle(rig)

    sent = await rig.post(_message())
    await _settle(rig)
    await rig.session.chat_queue.put(None)
    await task

    assert sent["delivery"] == "turn"
    assert _saw_attachments(rig.llm)


async def test_a_message_sent_while_the_agent_works(rig):
    rig.session.turn_active = True  # what the route reads to steer instead of queue
    sent = await rig.post(_message())
    rig.session.turn_active = False

    await rig.loop.run("open", resume=False, chat_idle_timeout=0.05)

    assert sent["delivery"] == "steer"
    assert _saw_attachments(rig.llm)


async def test_a_message_that_missed_the_turns_last_model_call(rig):
    await rig.loop.open("open", resume=False)
    rig.session.turn_active = True
    await rig.post(_message())
    rig.session.turn_active = False

    await rig.loop._leftover_steers([])

    assert _saw_attachments(rig.llm)


async def test_the_first_message_of_a_resumed_thread(rig):
    """A resume prepends the restored context to the first message; the
    attachments must survive being wrapped."""
    rig.session.needs_reprime = True  # type: ignore[attr-defined]
    rig.session.resume_primer = "<conversation_so_far>earlier turns</conversation_so_far>"  # type: ignore[attr-defined]
    task = asyncio.create_task(rig.loop.run("open", resume=False, chat_idle_timeout=5))
    await _settle(rig)

    await rig.post(_message())
    await _settle(rig)
    await rig.session.chat_queue.put(None)
    await task

    assert _saw_attachments(rig.llm)
    primed = [m for r in rig.llm.requests for m in r["messages"] if _carries_attachments(m)]
    assert "earlier turns" in str(primed[-1].content)


async def test_text_alone_stays_text(rig):
    """The common case must not change shape: a plain message is one string."""
    task = asyncio.create_task(rig.loop.run("open", resume=False, chat_idle_timeout=5))
    await _settle(rig)
    await rig.post("just text")
    await _settle(rig)
    await rig.session.chat_queue.put(None)
    await task

    last = [m for m in rig.llm.requests[-1]["messages"] if isinstance(m, HumanMessage)][-1]
    assert "just text" in str(last.content)
    assert not _saw_attachments(rig.llm)


# ---------------------------------------------------------------------------
# What rides along with the person's words
# ---------------------------------------------------------------------------

class _Recorder:
    """The part of ConversationRecorder the messages route calls."""

    def __init__(self):
        self.users: list = []

    async def record_user(self, content):
        self.users.append(content)

    def wrap_emit(self, emit):
        return emit


async def test_the_message_is_stored_as_sent_so_a_reload_shows_it(rig):
    """A seam-breaking check found this unguarded: drop the route's write and
    every suite stayed green, while a reload would show a thread missing
    the person's own messages."""
    rig.session.recorder = _Recorder()  # type: ignore[attr-defined]
    await rig.post(_message())
    assert rig.session.recorder.users == [_message()]  # type: ignore[attr-defined]


async def test_a_follow_up_is_grounded_in_the_report_on_screen(rig):
    """The second unguarded seam: a follow-up must carry the saved report it
    is about, or "make finding 2 shorter" edits what the model remembers
    rather than the version the person is looking at."""
    from types import SimpleNamespace

    class Report:
        def model_dump_json(self, exclude=None):
            del exclude
            return '{"title": "Organic growth, week 47"}'

    rig.session.report_versions = [  # type: ignore[attr-defined]
        SimpleNamespace(version_id=1, label="Initial", report=Report()),
    ]
    task = asyncio.create_task(rig.loop.run("open", resume=False, chat_idle_timeout=5))
    await _settle(rig)
    await rig.post(_message())
    await _settle(rig)
    await rig.session.chat_queue.put(None)
    await task

    sent = [m for r in rig.llm.requests for m in r["messages"] if _carries_attachments(m)]
    assert "Organic growth, week 47" in str(sent[-1].content)
