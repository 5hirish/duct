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

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from agents.core.errors import classify_error, is_retryable, retry_after_seconds
from agents.core.events import AgentEvent, StepStatus
from agents.core.session import (
    take_client_id,
    ASK_USER_TIMEOUT,
    BaseAgentSession,
    PauseFn,
    make_future_pause,
)
from agents.core.stream import DuctArtifactStreamParser
from agents.core.telemetry import model_span
from agents.models import (
    cost_usd,
    context_window_for,
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


# LangChain names a middleware's graph nodes ``<Middleware>.<hook>``. Those
# nodes rewrite history — summarisation replaces it, context editing prunes
# tool results — and their updates carry the *surviving* messages, old tool
# calls included. Dispatching tool traffic from them replayed every earlier
# fetch as a fresh STEP_STARTED after each compaction.
MIDDLEWARE_NODE_SUFFIXES = (".before_model", ".after_model", ".before_agent", ".after_agent")
SUMMARIZATION_NODE_MARK = "summarization"


def is_middleware_node(node: Any) -> bool:
    return str(node).endswith(MIDDLEWARE_NODE_SUFFIXES)


def is_summarization_node(node: Any) -> bool:
    return SUMMARIZATION_NODE_MARK in str(node).lower()


def _states(delta: Any) -> list[dict]:
    return [d for d in (delta if isinstance(delta, list) else [delta]) if isinstance(d, dict)]


class UsageTracker:
    """Turn the per-chunk ``usage_metadata`` of a stream into one TOKEN_USAGE
    per model call.

    Providers attach usage to the last chunk of a call (Anthropic on
    ``message_delta``, OpenAI on its final chunk), and LangChain defines chunk
    usage as additive, so summing until the call's stop marker is right for
    both shapes. A call with no stop marker — a non-streaming fake, a provider
    that omits it — is flushed at the end of the turn.

    ``scope`` says whose context the call filled: a subagent's calls run in a
    nested namespace and count toward the bill, but the gauge follows the
    thread the user is talking to.
    """

    def __init__(self, model: Any) -> None:
        self.model = model
        self._pending: dict | None = None

    def feed(self, message: Any, meta: dict | None) -> dict | None:
        usage = getattr(message, "usage_metadata", None)
        response = getattr(message, "response_metadata", None) or {}
        if usage:
            if self._pending is None:
                self._pending = {
                    "input_tokens": 0, "output_tokens": 0,
                    "cache_read_tokens": 0, "cache_creation_tokens": 0,
                    "model": "", "scope": _usage_scope(meta),
                }
            details = usage.get("input_token_details") or {}
            self._pending["input_tokens"] += int(usage.get("input_tokens") or 0)
            self._pending["output_tokens"] += int(usage.get("output_tokens") or 0)
            self._pending["cache_read_tokens"] += int(details.get("cache_read") or 0)
            self._pending["cache_creation_tokens"] += int(details.get("cache_creation") or 0)
        if response.get("model_name") and self._pending is not None:
            self._pending["model"] = str(response["model_name"])
        if self._pending is not None and (response.get("stop_reason") or response.get("finish_reason")):
            return self.flush()
        return None

    def flush(self) -> dict | None:
        if self._pending is None:
            return None
        usage, self._pending = self._pending, None
        model = usage["model"] or getattr(self.model, "value", self.model) or ""
        return {
            "event": AgentEvent.TOKEN_USAGE,
            **usage,
            "model": str(model),
            "total_tokens": usage["input_tokens"] + usage["output_tokens"],
            "context_window": context_window_for(model),
            # None for a model the price table does not know: the tooltip then
            # shows tokens without a dollar figure rather than a made-up one.
            "cost_usd": cost_usd(
                model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                cache_creation_tokens=usage["cache_creation_tokens"],
            ),
        }


def _usage_scope(meta: dict | None) -> str:
    """``thread`` for the agent the user is talking to, ``subagent`` for a
    model call nested inside one of its tool calls, ``compaction`` for the
    summariser. All three count toward the bill; only the first drives the
    context gauge — the summariser's prompt is the history being replaced,
    not the context the next turn will run in."""
    if is_summarization_node((meta or {}).get("langgraph_node")):
        return "compaction"
    namespace = str((meta or {}).get("langgraph_checkpoint_ns") or "")
    return "subagent" if "tools:" in namespace or "|" in namespace else "thread"


def usage_from_messages(messages: list, model: Any) -> dict:
    """The usage a stored thread shows on open: its last model call and the
    running total, from the ``usage_metadata`` each AI message keeps.

    Summarisation drops old messages, so the total is of what survives —
    which is also what the next call will pay for again.
    """
    last: dict | None = None
    total = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "calls": 0, "cost_usd": None}
    for message in messages or []:
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            continue
        details = usage.get("input_token_details") or {}
        # The message may name the model that actually answered (a fallback);
        # price by that when it does, else by the thread's configured model.
        served = (getattr(message, "response_metadata", None) or {}).get("model_name") or model
        last = {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": int(details.get("cache_read") or 0),
        }
        last["cost_usd"] = cost_usd(
            served,
            input_tokens=last["input_tokens"],
            output_tokens=last["output_tokens"],
            cache_read_tokens=last["cache_read_tokens"],
            cache_creation_tokens=int(details.get("cache_creation") or 0),
        )
        total["input_tokens"] += last["input_tokens"]
        total["output_tokens"] += last["output_tokens"]
        total["cache_read_tokens"] += last["cache_read_tokens"]
        total["calls"] += 1
        if last["cost_usd"] is not None:
            total["cost_usd"] = round((total["cost_usd"] or 0.0) + last["cost_usd"], 6)
    return {
        "last": last,
        "total": total,
        "context_window": context_window_for(model),
        "model": str(getattr(model, "value", model) or ""),
    }


async def _dispatch_updates(
    chunk: Any,
    *,
    on_todo: Callable[[list], Awaitable[None]] | None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None,
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None,
    on_compacted: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Read one ``updates`` chunk for todos, tool traffic and compaction.

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
        if is_middleware_node(node):
            # A summariser that returned messages replaced the history.
            if (
                on_compacted is not None
                and is_summarization_node(node)
                and any(state.get("messages") for state in _states(delta))
            ):
                await on_compacted()
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


# ---------------------------------------------------------------------------
# Retries that say so
# ---------------------------------------------------------------------------

# Four attempts is ~7 s of waiting at the default backoff (1, 2, 4 s) — about
# what a rate-limit window or an overloaded provider needs, and short enough
# that a user watching the status row is not left wondering.
MODEL_RETRY_ATTEMPTS = 4
MODEL_RETRY_INITIAL_DELAY = 1.0
MODEL_RETRY_MAX_DELAY = 8.0
# A provider's own Retry-After wins over the schedule above, up to this long.
# Past it the call is not retried at all (see ReportedRetryMiddleware): the
# user is better served by a failure they can act on now than by a status row
# counting down a minute and then failing anyway.
MODEL_RETRY_HEADER_MAX_DELAY = 30.0
_RETRY_JITTER = 0.25


def retry_delay(attempt: int, exc: BaseException | None = None) -> float:
    """Seconds to wait after the ``attempt``-th failure (1-based).

    What the provider asked for if it said (``Retry-After``), otherwise the
    jittered exponential schedule.
    """
    asked = retry_after_seconds(exc) if exc is not None else None
    if asked is not None:
        return min(asked, MODEL_RETRY_HEADER_MAX_DELAY)
    delay = min(MODEL_RETRY_INITIAL_DELAY * 2 ** (attempt - 1), MODEL_RETRY_MAX_DELAY)
    return max(0.0, delay + random.uniform(-delay * _RETRY_JITTER, delay * _RETRY_JITTER))


async def _retry_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def emit_custom(payload: dict) -> None:
    """Put a Duct event on the run's ``custom`` stream, if there is one.

    ``stream_agent`` forwards custom chunks that carry an ``event``, so this is
    how anything running inside the graph — a tool, a middleware — reaches the
    SSE stream without holding the session's emit. Outside a run it is a no-op:
    a unit test that calls the middleware directly must not need a graph.
    """
    try:
        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 - no run context
        return
    if writer is not None:
        writer(payload)


def drain_steers(queue: Any) -> list[tuple[Any, str]]:
    """Everything waiting on a steer queue, as (message, client id), without
    blocking. Empty when there is no queue."""
    out: list[tuple[Any, str]] = []
    if queue is None:
        return out
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            return out
        out.append(take_client_id(item))


def steer_messages(items: list[tuple[Any, str]]) -> list[HumanMessage]:
    """User messages for steered items; each consumed one is reported."""
    messages: list[HumanMessage] = []
    for item, client_id in items:
        content = item.get("content") if isinstance(item, dict) else item
        if content is None or content == "":
            continue
        messages.append(HumanMessage(content=content))
        if client_id:
            emit_custom({"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": client_id})
    return messages


class SteerMiddleware(AgentMiddleware):
    """Hand the model what the user typed while it was working.

    Codex drains its pending input at the top of every model call; this is
    that, as a ``before_model`` hook — a node in the graph, so the injected
    message is checkpointed with the rest of the thread and survives a
    restart. The message lands after whatever tool result the model was
    waiting on, which is the earliest point it could honestly be read.

    What arrives after the turn's last model call is not lost: the runner
    checks the queue when a turn ends and starts a follow-up with it.
    """

    def __init__(self, session: Any) -> None:
        super().__init__()
        self.session = session

    def _drain(self) -> dict | None:
        messages = steer_messages(drain_steers(getattr(self.session, "steer_queue", None)))
        return {"messages": messages} if messages else None

    def before_model(self, state, runtime):  # type: ignore[override]
        del state, runtime
        return self._drain()

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        del state, runtime
        return self._drain()


class ReportedRetryMiddleware(AgentMiddleware):
    """Retry a model call on a transient failure, and tell the UI each time.

    LangChain's ``ModelRetryMiddleware`` does the retrying but has no
    per-attempt hook, so from the browser a 429 with three retries behind it
    looked like a 10-second hang. Codex shows "Reconnecting… 2/5" in its status
    row for exactly this; MODEL_RETRYING is that event.

    What counts as transient is ``agents/core/errors.is_retryable`` — the same
    classifier that stamps the code on the failure event once attempts run out,
    so a rate limit retries and a rejected API key fails on the first try.
    """

    def __init__(self, *, attempts: int = MODEL_RETRY_ATTEMPTS) -> None:
        super().__init__()
        self.attempts = max(1, attempts)

    def _report(self, exc: Exception, attempt: int, delay: float) -> None:
        code = classify_error(exc)
        logger.warning(
            "model call failed (%s), retrying %d/%d in %.1fs", code, attempt, self.attempts, delay
        )
        # `retry_in` is a duration, not a timestamp: the client anchors it to
        # its own clock on receipt, so a skewed server clock cannot show a
        # countdown that is already over.
        emit_custom({
            "event": AgentEvent.MODEL_RETRYING,
            "attempt": attempt,
            "max_attempts": self.attempts,
            "code": code,
            "retry_in": round(delay, 1),
        })

    def _give_up(self, exc: Exception, attempt: int) -> bool:
        if attempt >= self.attempts or not is_retryable(exc):
            return True
        # A provider asking for longer than the cap is not "having a moment";
        # waiting the cap and retrying only fails again. pi fails immediately
        # above its limit for the same reason, and the code on the failure
        # ("rate limited") is the truth the user can act on.
        asked = retry_after_seconds(exc)
        return asked is not None and asked > MODEL_RETRY_HEADER_MAX_DELAY

    async def awrap_model_call(self, request, handler):  # type: ignore[override]
        for attempt in range(1, self.attempts + 1):
            try:
                return await handler(request)
            except Exception as exc:
                if self._give_up(exc, attempt):
                    raise
                delay = retry_delay(attempt, exc)
                self._report(exc, attempt, delay)
                await _retry_sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def wrap_model_call(self, request, handler):  # type: ignore[override]
        for attempt in range(1, self.attempts + 1):
            try:
                return handler(request)
            except Exception as exc:
                if self._give_up(exc, attempt):
                    raise
                delay = retry_delay(attempt, exc)
                self._report(exc, attempt, delay)
                time.sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover


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
    usage = UsageTracker(model)
    compacting = False

    async def _on_compacted() -> None:
        nonlocal compacting
        compacting = False
        await emit({"event": AgentEvent.CONTEXT_COMPACTED})

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
                    on_compacted=_on_compacted,
                )
                continue
            if mode != "messages":
                continue
            message, meta = chunk
            meta = meta if isinstance(meta, dict) else {}
            billed = usage.feed(message, meta)
            if billed is not None:
                await emit(billed)
            if is_summarization_node(meta.get("langgraph_node")):
                # The summariser's output is history, not a reply. It used to
                # stream into the transcript as if the agent had said it.
                if not compacting:
                    compacting = True
                    await emit({"event": AgentEvent.CONTEXT_COMPACTING})
                continue
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
    billed = usage.flush()
    if billed is not None:
        await emit(billed)
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
