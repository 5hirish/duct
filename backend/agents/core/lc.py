"""LangChain adapter — model transport and stream translation for V1 runners.

Two harness-shaped pieces every V1 runner needs, in one place because there are
now two runners (audit, insights) that need them. Both started life inside
``agents/audit/v1/runner.py``; a third copy is how the twenty-three private
``_utcnow()`` definitions started, so they moved here on the second consumer
rather than the third.

What lives here and what does not:

* ``resolve_chat_model`` is the LangChain half of the **model transport** port
  (``agents/core/ports``). Named ``resolve_chat_model``, not ``resolve_model``,
  because ``agents/models.py`` already owns that name for a different job
  (string → ``ModelName``).
* ``stream_agent`` is the LangChain half of the **events out** port: it drives
  a compiled LangGraph agent and translates its stream into Duct's ``AgentEvent``
  vocabulary, so the frontend cannot tell which harness served a run.
* ``interrupt_pause`` is the LangGraph half of the **human-in-the-loop** port:
  a tool calls it, the thread parks in its checkpoint, and ``stream_agent``
  surfaces the pause as the SSE event the UI already renders. The resume is a
  ``Command`` driven back through ``stream_agent`` by the runner's chat loop.

Everything agent-specific stays in the runner — what the prompt says, which
tools are bound, what an artifact payload means. This module knows only how to
talk to LangChain.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import StructuredTool
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from agents.core.events import AgentEvent, StepStatus
from agents.core.session import (
    ASK_USER_TIMEOUT,
    BaseAgentSession,
    PauseFn,
    make_future_pause,
)
from agents.core.stream import DuctArtifactStreamParser
from agents.core.telemetry import model_span
from agents.models import (
    GATEWAY_BASE_URL,
    ModelName,
    Provider,
    get_api_key_kwargs,
    langchain_provider,
)
from agents.thinking import thinking_kwargs

logger = logging.getLogger(__name__)

# Cap on clarifying questions in one AskUserQuestion call. Matches the V3
# runners, so a user sees the same maximum whichever engine served the run.
MAX_QUESTIONS = 3


# ---------------------------------------------------------------------------
# Human-in-the-loop — the LangChain half of the AskUser port
# ---------------------------------------------------------------------------

class AskUserArgs(BaseModel):
    """Arguments for the AskUserQuestion tool."""

    questions: list[dict] = Field(
        description=(
            "Clarifying questions for the user. Each item: "
            '{"question": str, "header": str, "options": [{"label": str, "description": str}], '
            '"multiSelect": bool}.'
        )
    )


async def interrupt_pause(event: str, payload: dict, *, timeout: float | None = None) -> dict:
    """The checkpointed ``PauseFn``: park the thread on a LangGraph interrupt.

    The payload carries the SSE event name so ``stream_agent`` can emit it
    verbatim when the interrupt surfaces — the tool that paused does not emit
    anything itself. The run resumes when the runner streams a
    ``Command(resume={interrupt_id: answer})`` on the same thread, and the answer
    becomes this call's return value.

    Two properties of ``interrupt()`` matter to callers. It needs a checkpointer,
    so a binder must only hand this out for an agent that has one. And the task
    that paused re-runs from its start on resume, so whatever a tool does before
    calling this happens twice — keep it to idempotent reads. ``timeout`` is
    ignored: a checkpointed pause waits as long as the thread exists.
    """
    del timeout  # the whole point: no clock on a parked thread
    answer = interrupt({"event": event, **payload})
    return answer if isinstance(answer, dict) else {}


def build_ask_user_tool(
    session: BaseAgentSession,
    session_id: str,
    emit: Callable,
    *,
    pause: PauseFn | None = None,
    log_prefix: str = "agent-v1",
    timeout: float = ASK_USER_TIMEOUT,
    description: str = (
        "Ask the user up to 3 clarifying questions when their answer would "
        "materially change your conclusions. Use sparingly and early; never ask "
        "about information already provided."
    ),
) -> StructuredTool:
    """AskUserQuestion as a LangChain tool, parked on the pause port.

    The tool call blocks until the user answers, which is what keeps the agent
    loop paused — the same behaviour V3 gets from its ``can_use_tool`` hook.
    ``pause`` defaults to the in-process Future bridge (right for an agent with
    no checkpointer, like audit v1); a runner with durable threads passes
    ``interrupt_pause`` so the question outlives the process that asked it.
    """
    pause = pause or make_future_pause(
        session, session_id, emit, timeout=timeout, log_prefix=log_prefix
    )

    async def ask_user_question(questions: list[dict]) -> str:
        answers = await pause(
            AgentEvent.QUESTIONS_REQUIRED,
            {"questions": questions[:MAX_QUESTIONS]},
            timeout=timeout,
        )
        if not answers:
            return (
                "The user did not answer in time. Continue using the information "
                "you already have; do not ask again."
            )
        return "\n".join(f"{k}: {v}" for k, v in answers.items())

    return StructuredTool.from_function(
        coroutine=ask_user_question,
        name="AskUserQuestion",
        description=description,
        args_schema=AskUserArgs,
    )


# ---------------------------------------------------------------------------
# Model transport
# ---------------------------------------------------------------------------

def default_base_url(provider: Provider) -> str:
    """Installation-level endpoint override for gateway providers.

    Read here rather than threaded through every route because it is an
    install-wide setting, not a per-request one — and because agents/models.py
    stays a config-free leaf module. Direct vendors never consult it.
    """
    if provider not in GATEWAY_BASE_URL:
        return ""
    from config import get_configs
    return getattr(get_configs(), "openrouter_base_url", "") or ""


def _thinking_kwargs_for(provider: Provider, model, thinking: str) -> dict:
    """``thinking_kwargs`` translated into what this provider's class accepts.

    ``agents/thinking.py`` is deliberately provider-blind: it answers "what does
    this *model* call this rung" and emits LangChain's standard
    ``reasoning_effort``. That kwarg is standard across ChatAnthropic, ChatOpenAI
    and ChatGoogleGenerativeAI — but **not** ChatOpenRouter, which takes
    OpenRouter's unified ``reasoning={"effort": …}`` object instead.

    The failure mode this exists to prevent is silent: ChatOpenRouter accepts an
    unknown kwarg, warns, and forwards it inside ``model_kwargs``, so a mistyped
    dial reaches the API as a junk top-level field and the run appears to work
    at whatever depth the model defaulted to. Translating at the transport
    boundary — where the provider is known — keeps thinking.py from growing a
    provider axis it has no reason to have.
    """
    kwargs = thinking_kwargs(model, thinking)
    effort = kwargs.pop("reasoning_effort", None)
    if effort and provider is Provider.OPENROUTER:
        kwargs["reasoning"] = {"effort": effort}
    elif effort:
        kwargs["reasoning_effort"] = effort
    return kwargs


def resolve_chat_model(
    provider: Provider,
    model: ModelName | str,
    api_key: str,
    temperature: float = 1.0,
    *,
    base_url: str = "",
    thinking: str = "",
):
    """Any LangChain-supported provider — this is the point of the migration.

    ``model`` may be a plain string: OpenRouter slugs are passed through
    un-enumerated (see ``agents/engines.resolve_engine_model``). ``base_url`` is
    only consulted by gateway providers.

    ``thinking`` is a *Duct* level ("quick" … "exhaustive"), not a provider
    value. It resolves through agents/thinking.py to whatever this model calls
    that rung, and contributes nothing when the model has no such dial — which
    is why it is safe to pass unconditionally from every call site.
    """
    return init_chat_model(
        model=getattr(model, "value", model),
        model_provider=langchain_provider(provider),
        temperature=temperature,
        **_thinking_kwargs_for(provider, model, thinking),
        **get_api_key_kwargs(provider, api_key, base_url=base_url or default_base_url(provider)),
    )


# ---------------------------------------------------------------------------
# Stream translation
# ---------------------------------------------------------------------------

def split_chunk(message: Any) -> tuple[str, str]:
    """Separate visible text from reasoning in a stream chunk.

    Providers differ: a plain string, or a list of typed blocks where reasoning
    arrives as ``thinking`` / ``reasoning``. Unknown block types are ignored
    rather than leaked into the artifact.
    """
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return "", ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text_parts.append(block.get("text", ""))
        elif kind in ("thinking", "reasoning"):
            thinking_parts.append(block.get("thinking") or block.get("text", ""))
    return "".join(text_parts), "".join(thinking_parts)


async def _dispatch_updates(
    chunk: Any,
    *,
    on_todo: Callable[[list], Awaitable[None]] | None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None,
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None,
) -> None:
    """Read one ``updates`` chunk for todos and tool traffic.

    Defensive throughout: the shape is ``{node_name: state_delta}``, but
    LangGraph also puts control keys (``__interrupt__``) alongside the nodes,
    and middleware may deliver a list of deltas. Anything unrecognised is
    skipped — a stream translator must never be the thing that ends a run.
    """
    if not isinstance(chunk, dict):
        return
    for node, delta in chunk.items():
        if str(node).startswith("__"):
            continue
        for state in delta if isinstance(delta, list) else [delta]:
            if not isinstance(state, dict):
                continue
            todos = state.get("todos")
            if todos and on_todo is not None:
                await on_todo(list(todos))
            for msg in state.get("messages") or []:
                for call in getattr(msg, "tool_calls", None) or []:
                    if on_tool_use is not None and isinstance(call, dict):
                        await on_tool_use(
                            call.get("name", ""), call.get("args"), call.get("id", "") or ""
                        )
                if getattr(msg, "type", "") == "tool" and on_tool_result is not None:
                    await on_tool_result(
                        getattr(msg, "name", "") or "",
                        getattr(msg, "content", ""),
                        getattr(msg, "tool_call_id", "") or "",
                        getattr(msg, "status", "") == "error",
                    )


def _turn_input(prompt: str | Command | None) -> Any:
    """What ``astream`` is fed for one turn.

    A string is a fresh user message. ``None`` continues whatever the thread was
    doing — an unfinished run picks up from its last checkpoint, and a parked
    one re-raises its live pauses (which is how a resumed session shows the
    question it is still waiting on). A ``Command`` is a resume with answers.
    """
    if isinstance(prompt, str):
        return {"messages": [{"role": "user", "content": prompt}]}
    return prompt


def pause_from_interrupt(item: Any) -> dict | None:
    """The SSE payload for one LangGraph ``Interrupt``, or None if it is not ours.

    Every Duct pause is raised through ``interrupt_pause`` and so carries its
    ``event``. Anything else — a ``interrupt_on`` review from deepagents'
    middleware, a subagent's ad-hoc interrupt — has no card in the UI and is
    reported as a failed turn rather than guessed at.
    """
    value = getattr(item, "value", None)
    if not isinstance(value, dict) or not value.get("event"):
        return None
    return {**value, "interrupt_id": getattr(item, "id", "") or ""}


def live_pauses(snapshot: Any) -> list[dict]:
    """The pauses a thread is still parked on, from ``aget_state``.

    ``snapshot.interrupts`` is the wrong field: it keeps an interrupt whose task
    has since completed, because the superstep's other task is still pending
    and the checkpoint has not advanced. A pause is live only while its task
    has no result.
    """
    out: list[dict] = []
    for task in getattr(snapshot, "tasks", ()) or ():
        if getattr(task, "result", None) is not None:
            continue
        for item in getattr(task, "interrupts", ()) or ():
            pause = pause_from_interrupt(item)
            if pause is not None:
                out.append(pause)
    return out


class _InspectionModel(FakeListChatModel):
    """A chat model that is never called.

    ``aget_state`` needs a compiled graph to work out ``next``, and compiling a
    deepagents graph needs a model object — but reading a thread makes no model
    call, so a placeholder is the honest choice over resolving a real provider
    (and a real key) for a lookup.
    """

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - never invoked
        return self


def inspection_chat_model() -> Any:
    """The placeholder model for building an agent only to read its thread."""
    return _InspectionModel(responses=[""])


async def stream_agent(
    agent: Any,
    prompt: str | Command | None,
    emit: Callable,
    *,
    on_artifact_chunk_event: str = AgentEvent.ARTIFACT_CHUNK,
    on_artifact_close: Callable,
    log_prefix: str = "agent-v1",
    config: dict | None = None,
    provider: Provider | None = None,
    model: ModelName | str = "",
    conversation_id: str = "",
    on_todo: Callable[[list], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None = None,
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None = None,
    on_pause: Callable[[list[dict]], Awaitable[None]] | None = None,
) -> list[dict]:
    """Drive one agent turn and translate its stream into Duct's SSE vocabulary.

    Emits the same ``AgentEvent`` values as the V3 (Claude Agent SDK) runners so
    the frontend is unchanged: AGENT_MESSAGE_CHUNK for prose, ARTIFACT_CHUNK for
    tokens inside ``<duct_artifact>``, THINKING_CHUNK for reasoning deltas,
    MESSAGE_STOP at the end of the turn.

    ``prompt`` is a user message, ``None`` to continue the thread, or a
    ``Command`` to resume it with answers — see ``_turn_input``.

    Returns the pauses the turn ended on: the run is parked on every one of
    them and continues only when each is resumed by id. They are emitted as
    their SSE events *before* MESSAGE_STOP, so the transcript closes the
    streaming bubble with the card already in place. An empty list means the
    turn ran to completion. ``on_pause`` receives the same list *before* the
    events go out — the answer route has to know what the run is parked on by
    the time a client could possibly reply, and a client replies fast.

    Custom stream chunks — anything a tool writes through LangGraph's stream
    writer — are forwarded when they carry an ``event``, so progress emitted
    from inside a tool (or a subagent's tool) reaches the UI on the same wire.

    The optional ``on_todo`` / ``on_tool_*`` hooks read the ``updates`` stream.
    They default to ``None``, so a caller that wants only prose gets exactly the
    behaviour this had before they existed.
    """
    parser = DuctArtifactStreamParser(
        on_text=lambda text: emit({"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": text}),
        on_artifact_chunk=lambda text: emit({"event": on_artifact_chunk_event, "text": text}),
        on_artifact_close=on_artifact_close,
        log_prefix=log_prefix,
    )

    # V3 gets OTel traces free from the Claude Agent SDK; V1 does not, so the
    # span is emitted here. Same convention either way — see core/telemetry.py.
    with model_span(
        provider=(provider or Provider.ANTHROPIC).value,
        model=getattr(model, "value", model) or "unknown",
        conversation_id=conversation_id,
        agent_name=log_prefix,
    ):
        pauses: list[dict] = []
        foreign_interrupts = 0
        async for mode, chunk in agent.astream(
            _turn_input(prompt),
            config or {},
            stream_mode=["messages", "updates", "custom"],
        ):
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("event"):
                    await emit(dict(chunk))
                continue
            if mode == "updates":
                if isinstance(chunk, dict):
                    for item in chunk.get("__interrupt__") or ():
                        pause = pause_from_interrupt(item)
                        if pause is None:
                            foreign_interrupts += 1
                        else:
                            pauses.append(pause)
                await _dispatch_updates(
                    chunk,
                    on_todo=on_todo,
                    on_tool_use=on_tool_use,
                    on_tool_result=on_tool_result,
                )
                continue
            if mode != "messages":
                continue
            message, _meta = chunk
            text, thinking = split_chunk(message)
            if thinking:
                await emit({"event": AgentEvent.THINKING_CHUNK, "text": thinking})
            if text:
                await parser.feed(text)

    # The parser holds back the last few characters of every chunk in case they
    # are a split `<duct_artifact>` open tag, so a turn's tail only reaches the
    # stream on flush. Both V3 runners do this at their message_stop; V1 did
    # not, which silently truncated every turn by up to 14 characters — visible
    # as a short chat reply vanishing entirely.
    await parser.flush()
    if on_pause is not None:
        await on_pause(list(pauses))
    for pause in pauses:
        await emit(dict(pause))
    if foreign_interrupts:
        # The thread is parked on something no card can answer. Say so rather
        # than leave the UI in "working" forever; the next user message starts
        # a fresh turn on the same thread.
        logger.warning("%s: %d interrupt(s) without a Duct event", log_prefix, foreign_interrupts)
        await emit({
            "event": AgentEvent.STEP_FAILED,
            "status": StepStatus.ERROR,
            "error": "The agent paused on something this app cannot answer. Try rephrasing.",
        })
    await emit({"event": AgentEvent.MESSAGE_STOP})
    return pauses
