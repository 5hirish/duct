"""The ``deepagents`` session shape every session runner shares.

Insights and content are the same kind of thing: a deep agent with a durable
thread, driven turn by turn from a chat queue, that can park on a question,
take a message mid-turn, compact once when the provider says the request is
too long, and resume tomorrow where it stopped. The first runner (insights)
wrote that loop; the second (content) copied it. This is the extraction on
the second consumer, per the ports rule — the third copy is how the
twenty-three ``_utcnow()`` definitions started.

Two pieces, kept separate because they answer different questions:

* ``build_deep_session_agent`` — **assembly.** The middleware stack, the
  virtual filesystem, the runaway guards, the fallback chain and the
  checkpointer, in the order the harness needs them. A runner supplies what is
  *its own*: tools, sub-agents, the system prompt, and its ``RunLimits``.
* ``DeepSession`` — **the loop.** One object per live session: opening turn
  or resume, pauses, steers, compaction, the chat loop, and the failure
  posture (one bad turn is a row, not the end). A runner plugs in what is
  *its own* through hooks: what an artifact means, what the finish event
  carries, what to do after a turn (content nudges), what to do on a resume
  with no checkpoint (content re-primes).

Deliberately not an ``AgentHarness`` interface (``agents/core/ports``): both
runners are on the same harness, so this is a shared implementation, not an
abstraction over harnesses. The harness stays harness-shaped in here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from deepagents import FilesystemMiddleware, create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
)
from langgraph.types import Command

from agents.core.checkpoint import get_checkpointer
from agents.core.errors import ErrorCode, classify_error, error_payload
from agents.core.events import AgentEvent, StepStatus
from agents.core.lc import (
    ReportedRetryMiddleware,
    SeenImagePruneMiddleware,
    SteerMiddleware,
    chat_message_text,
    compact_thread,
    drain_steers,
    live_pauses,
    resolve_chat_model,
    stream_agent,
    usage_from_messages,
)
from agents.core.session import BaseAgentSession, take_client_id
from agents.engines import Engine, resolve_fallback_models
from agents.models import ModelName, Provider

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]
Pauses = list[dict]

# The lowest summarization trigger deepagents will pick: its no-profile
# default, which is also 0.85 × a 200k window. A prune trigger must stay under
# it or the cheap pass silently never runs — see RunLimits.__post_init__ and
# tests/test_insights_middleware.py for the threshold relationship.
SUMMARIZATION_FLOOR_TOKENS = 170_000

# The scratch-space verbs an agent gets, and the one it does not.
#
# `deepagents` mounts an `execute` tool alongside these — a shell. It is inert
# under `StateBackend` (which does not implement SandboxBackendProtocol), but
# "inert because of which backend happens to be configured" is not a
# guarantee: swapping in a sandbox backend later would silently hand every
# agent a shell. Naming the tools explicitly omits it from the dispatchable
# tool node entirely, which makes the isolation structural. `delete` is left
# out for the same reason of minimal surface — nothing needs it.
FILESYSTEM_TOOLS = ("ls", "read_file", "write_file", "edit_file", "glob", "grep")

# What one model call costs in LangGraph supersteps on this assembly. Every
# middleware hook is a node — deepagents' own stack plus the six mounted
# below — so measured against `build_deep_session_agent` with a fake model
# the minimum recursion_limit is 15 for 2 calls, 29 for 4, 50 for 7: a slope
# of 7. `tests/test_deep_session.py` pins that the derived budget admits
# every call the model-call guard allows; re-measure when the stack changes.
SUPERSTEPS_PER_MODEL_CALL = 7
# Headroom for the nodes around the final answer and the limit's own exit.
RECURSION_SLACK = 20

# Tools whose results the context pruner must never clear. A cleared
# AskUserQuestion answer reads as the user never having replied, and the
# agent asks again.
NEVER_PRUNED = ("AskUserQuestion",)


@dataclass(frozen=True)
class RunLimits:
    """Runaway guards for one deep agent, not budgets.

    The model and tool counts are what actually cost money: per *run* means
    one user turn, per *thread* the whole conversation, which is what makes
    them meaningful now that a thread survives a restart. ``recursion`` is
    LangGraph's superstep ceiling for the turn and is *derived* from the
    model-call guard: it was a hand-picked number once, and at 7 supersteps
    per call a "generous" 100 admitted 14 model calls — the graph error fired
    long before the guard that was meant to, and reached the browser as
    "Something went wrong".
    ``exit_behavior="end"`` on the model limit ends the turn with an AI
    message saying so; the tool limit refuses the offending call with an
    error the model can react to and lets the turn proceed.

    ``tool_result_prune_trigger`` / ``tool_results_kept`` drive the cheap
    context pass: prune old tool results before an LLM compaction is needed.
    """

    model_calls_per_run: int
    model_calls_per_thread: int
    tool_calls_per_run: int
    tool_calls_per_thread: int
    tool_result_prune_trigger: int
    tool_results_kept: int

    def __post_init__(self) -> None:
        # Ordering here is by threshold, not by position: deepagents mounts
        # SummarizationMiddleware in its base stack and user middleware lands
        # after it, so summarization gets the request first and delegates
        # straight through below its trigger. Above the floor, pruning never
        # sees an untouched request and silently stops happening.
        if self.tool_result_prune_trigger >= SUMMARIZATION_FLOOR_TOKENS:
            raise ValueError(
                f"tool_result_prune_trigger ({self.tool_result_prune_trigger}) must stay "
                f"below deepagents' summarization floor ({SUMMARIZATION_FLOOR_TOKENS})"
            )
        if self.model_calls_per_run >= self.model_calls_per_thread:
            raise ValueError("a run's model-call limit must be below the thread's")
        if self.tool_calls_per_run >= self.tool_calls_per_thread:
            raise ValueError("a run's tool-call limit must be below the thread's")

    @property
    def recursion(self) -> int:
        """Supersteps that admit every model call the run guard allows."""
        return self.model_calls_per_run * SUPERSTEPS_PER_MODEL_CALL + RECURSION_SLACK


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def fallback_chain(
    provider: Provider,
    model: ModelName | str,
    api_key: str,
    temperature: float = 1.0,
    *,
    thinking: str = "",
) -> list[Any]:
    """The models to fall back to when ``model`` errors, as chat models.

    Provider outages and 429/529s end an autonomous run that may already have
    spent several minutes working. One same-provider step down keeps it alive
    on the key the caller supplied — see MODEL_FALLBACK in agents/models.py
    for why the chain is one step and never crosses a provider. Empty for a
    model at the bottom of its family or a raw OpenRouter slug, so the caller
    mounts no middleware at all rather than an empty one.
    """
    return [
        resolve_chat_model(provider, name, api_key, temperature, thinking=thinking)
        for name in resolve_fallback_models(Engine.V1, provider, model)
    ]


def build_deep_session_agent(
    *,
    llm: Any,
    tools: list[Any],
    system_prompt: str,
    limits: RunLimits,
    subagents: list[Any] | None = None,
    session: BaseAgentSession | None = None,
    fallbacks: list[Any] | None = None,
    checkpointer: Any = None,
    prune_seen_images: bool = False,
) -> Any:
    """One deep agent, assembled the way every Duct session needs it.

    ``fallbacks`` is what ``fallback_chain`` returned, or nothing: a runner
    that was handed its model (a test's fake, a caller that already decided)
    passes none, because second-guessing an injected model here would fire
    real provider calls out of a fake-model test. ``prune_seen_images`` is
    for a runner whose tools hand the model pictures: the bytes leave the
    durable thread after the model call that looked at them.
    """
    # One backend for the whole agent. `create_deep_agent` defaults to its
    # own StateBackend when none is passed, which left the first runner with
    # two instances — one for FilesystemMiddleware and an internal one the
    # summarization middleware offloads evicted history to. Passing one makes
    # the offloaded transcript (`/conversation_history/*.md`) reachable by the
    # `read_file` tool this agent mounts. Still virtual: state, not disk.
    backend = StateBackend()
    return create_deep_agent(
        model=llm,
        tools=tools,
        backend=backend,
        subagents=list(subagents or []),
        system_prompt=system_prompt,
        middleware=[
            # Planning is opt-in since deepagents 0.7. The todo stream is what
            # makes a long autonomous run legible — the workspace renders it.
            TodoListMiddleware(),
            # Explicit rather than default, to drop the shell tool — see
            # FILESYSTEM_TOOLS.
            FilesystemMiddleware(backend=backend, tools=list(FILESYSTEM_TOOLS)),
            # Prune stale tool results so an LLM compaction is the second
            # response to a filling window, not the first. `keep` holds the
            # most recent results intact — the ones the model is still
            # reasoning over.
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=limits.tool_result_prune_trigger,
                        keep=limits.tool_results_kept,
                        clear_tool_inputs=False,
                        exclude_tools=NEVER_PRUNED,
                    )
                ],
            ),
            *([SeenImagePruneMiddleware()] if prune_seen_images else []),
            ModelCallLimitMiddleware(
                thread_limit=limits.model_calls_per_thread,
                run_limit=limits.model_calls_per_run,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                thread_limit=limits.tool_calls_per_thread,
                run_limit=limits.tool_calls_per_run,
                exit_behavior="continue",
            ),
            # Last of ours, so it sits closest to the model call and the limit
            # guards above still count a fallback attempt as the call it is.
            *([ModelFallbackMiddleware(*fallbacks)] if fallbacks else []),
            # Innermost, so each model in the chain gets its retries before
            # the fallback moves on, and a transient 429 on the primary never
            # costs a downgrade. Reports every attempt to the UI.
            ReportedRetryMiddleware(),
            # A message typed mid-turn reaches the model at its next call.
            *([SteerMiddleware(session)] if session is not None else []),
        ],
        # Continuity across turns, durable: the saver is opened once by the
        # app lifespan and follows DATABASE_URL; in-memory outside a server.
        checkpointer=checkpointer if checkpointer is not None else get_checkpointer(),
    )


def recorder_tool_hooks(recorder: Any) -> tuple[Callable, Callable]:
    """The tool-traffic hooks that write a transcript's forensics.

    Every tool the agent runs is logged with its full input and output,
    paired by tool_use_id. A runner that wants to *also* surface a tool as a
    step wraps these rather than re-reading the recorder itself.
    """

    async def on_tool_use(name: str, tool_input: Any, tool_use_id: str) -> None:
        if recorder is not None:
            await recorder.record_tool_use(name, tool_input, tool_use_id)

    async def on_tool_result(name: str, result: Any, tool_use_id: str, is_error: bool) -> None:
        if recorder is not None:
            await recorder.record_tool_result(name, result, tool_use_id, is_error=is_error)

    return on_tool_use, on_tool_result


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class DeepSession:
    """One live session over a compiled deep agent and its durable thread.

    ``run`` is the whole lifecycle; ``turn`` is one exchange with the model,
    and is public so a runner (or a test) can drive the loop by hand.

    Hooks, all optional, all the runner's own vocabulary:

    * ``on_artifact_close(raw, turn_text)`` — a closing ``</duct_artifact>``.
    * ``on_todo`` / ``on_tool_use`` / ``on_tool_result`` — the updates stream.
    * ``finish_payload()`` — extra keys on the PIPELINE_FINISHED that ends the
      opening run (content puts the plan or post id there).
    * ``after_turn(pauses)`` — runs after every completed turn and may run
      more; content's recovery nudge lives here.
    * ``on_resume(snapshot)`` — a resumed thread, before anything runs; content
      re-primes a conversation that predates the checkpoint.
    """

    def __init__(
        self,
        agent: Any,
        *,
        emit: EmitFn,
        thread_id: str,
        limits: RunLimits,
        provider: Provider,
        model: ModelName | str,
        log_prefix: str,
        summariser: Any,
        session: BaseAgentSession | None = None,
        on_artifact_close: Callable[[str, str], Awaitable[None]] | None = None,
        on_todo: Callable[[list], Awaitable[None]] | None = None,
        on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None = None,
        finish_payload: Callable[[], dict] | None = None,
        after_turn: Callable[[Pauses], Awaitable[Pauses]] | None = None,
        on_resume: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        self.agent = agent
        self.session = session
        self.emit = emit
        self.thread_id = thread_id
        self.provider = provider
        self.model = model
        self.log_prefix = log_prefix
        self._summariser = summariser
        self._on_artifact_close = on_artifact_close or _no_artifact
        self._on_todo = on_todo
        self._on_tool_use = on_tool_use
        self._on_tool_result = on_tool_result
        self._finish_payload = finish_payload
        self._after_turn = after_turn
        self._on_resume = on_resume
        self.config = {
            # The conversation is the thread. A session is one process's window
            # onto it; keying on the session would give every resume an agent
            # with no memory of the transcript it is shown beside.
            "configurable": {"thread_id": thread_id},
            "recursion_limit": limits.recursion,
        }
        self.opened = False

    # -- one turn -------------------------------------------------------------

    async def _stream(self, text: str | Command | None) -> Pauses:
        return await stream_agent(
            self.agent,
            text,
            self.emit,
            on_artifact_close=self._on_artifact_close,
            log_prefix=self.log_prefix,
            config=self.config,
            provider=self.provider,
            model=self.model,
            conversation_id=self.thread_id,
            on_todo=self._on_todo,
            on_tool_use=self._on_tool_use,
            on_tool_result=self._on_tool_result,
            on_pause=self._on_pause,
        )

    async def _on_pause(self, pauses: Pauses) -> None:
        # The route resolves an answer against this: written before the
        # events go out, so the answer to a card can never arrive at a route
        # that has not heard of it. Replaced whole each turn — a pause that
        # was answered is gone, one that re-raised is back.
        if self.session is not None:
            self.session.pending_pauses = {p["interrupt_id"]: p for p in pauses}

    async def _stream_with_room(self, text: str | Command | None) -> Pauses:
        """One turn, with one emergency compaction if the provider says the
        request is too long. The failed request is checkpointed with its
        input, so the retry continues from the checkpoint rather than
        re-sending the text; a second overflow is the ordinary failure."""
        try:
            return await self._stream(text)
        except Exception as exc:
            if classify_error(exc) is not ErrorCode.CONTEXT_WINDOW:
                raise
            logger.info("%s: request too long for %s; compacting once and retrying", self.log_prefix, self.thread_id)
            await self.emit({"event": AgentEvent.CONTEXT_COMPACTING})
            if not await compact_thread(self.agent, self.config, self._summariser):
                raise
            await self.emit({"event": AgentEvent.CONTEXT_COMPACTED})
            return await self._stream(None)

    async def turn(self, text: str | Command | None) -> Pauses:
        """One exchange: stream it, then absorb any steers that missed it.

        Returns the pauses the thread is parked on; empty means it ran to
        completion. ``after_turn`` runs on every completed turn.
        """
        if self.session is not None:
            self.session.turn_active = True
        try:
            pauses = await self._stream_with_room(text)
        finally:
            if self.session is not None:
                self.session.turn_active = False
        if not pauses:
            await self._on_pause([])  # a turn that ran to completion clears the table
        pauses = await self._leftover_steers(pauses)
        if self._after_turn is not None:
            pauses = await self._after_turn(pauses)
        return pauses

    async def _leftover_steers(self, pauses: Pauses) -> Pauses:
        """A message that arrived after the turn's last model call never met
        the steer middleware. It becomes the next turn now, not a surprise at
        the top of whatever the user asks next."""
        while not pauses and self.session is not None:
            items = drain_steers(self.session.steer_queue)
            if not items:
                return pauses
            for _, client_id in items:
                if client_id:
                    await self.emit({"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": client_id})
            text = "\n\n".join(chat_message_text(item) for item, _ in items if chat_message_text(item))
            if not text:
                return pauses
            pauses = await self.turn(text)
        return pauses

    # -- lifecycle ------------------------------------------------------------

    async def _finish_opening(self, pauses: Pauses) -> None:
        """The opening run is what moves the UI out of "working": the finish
        event is held back until a turn ends with nothing parked, however
        many answers that takes, and is emitted once."""
        if self.opened or pauses:
            return
        self.opened = True
        extra = self._finish_payload() if self._finish_payload is not None else {}
        await self.emit({"event": AgentEvent.PIPELINE_FINISHED, "status": StepStatus.SUCCESS, **extra})

    async def open(self, opening_prompt: str, *, resume: bool) -> Pauses:
        """The first thing a session does.

        Fresh: the opening prompt is the first turn. Resumed: what happens
        depends on what the thread was doing — a parked one re-raises the
        pause it is waiting on (with ``replay`` set so the recorder does not
        write the question twice), an unfinished one continues from its last
        checkpoint, and an idle one runs the prompt as a follow-up or, with
        no prompt, waits for the user. Never a greeting.
        """
        if not resume:
            pauses = await self.turn(opening_prompt)
            await self._finish_opening(pauses)
            return pauses

        snapshot = await self.agent.aget_state(self.config)
        if self._on_resume is not None:
            await self._on_resume(snapshot)
        parked = live_pauses(snapshot)
        if parked:
            for pause in parked:
                await self.emit({**pause, "replay": True})
            if self.session is not None:
                self.session.pending_pauses = {p["interrupt_id"]: p for p in parked}
            pauses = parked
        elif snapshot.next:
            pauses = await self.turn(None)  # cut mid-run: continue from the checkpoint
        elif opening_prompt:
            pauses = await self.turn(opening_prompt)  # a follow-up on an idle thread
        else:
            pauses = []
        await self._finish_opening(pauses)
        return pauses

    async def chat_loop(self, chat_idle_timeout: float) -> None:
        """Stay open for follow-ups until idle or closed.

        An answer to a parked card arrives as ``{"resume": {id: answer}}`` and
        becomes a ``Command``; anything else is the next user turn. One bad
        turn must not end the session — the user can rephrase — so a failure
        is a STEP_FAILED with its code, never an exception out of here.
        """
        session = self.session
        if session is None:
            return
        while True:
            try:
                chat_msg = await asyncio.wait_for(session.chat_queue.get(), timeout=chat_idle_timeout)
            except asyncio.TimeoutError:
                logger.info("%s: session %s chat idle timeout", self.log_prefix, session.session_id)
                return
            if chat_msg is None:  # sentinel from close_session
                return
            chat_msg, client_id = take_client_id(chat_msg)
            if client_id:
                await self.emit({"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": client_id})
            try:
                if isinstance(chat_msg, dict) and "resume" in chat_msg:
                    pauses = await self.turn(Command(resume=chat_msg["resume"]))
                else:
                    pauses = await self.turn(chat_message_text(chat_msg))
                await self._finish_opening(pauses)
            except Exception as exc:
                logger.exception("%s: chat turn failed for session %s", self.log_prefix, session.session_id)
                await self.emit({
                    "event": AgentEvent.STEP_FAILED,
                    "status": StepStatus.ERROR,
                    **error_payload(exc),
                })

    async def run(self, opening_prompt: str, *, resume: bool, chat_idle_timeout: float) -> None:
        """Open, then stay open for follow-ups until idle."""
        await self.open(opening_prompt, resume=resume)
        await self.chat_loop(chat_idle_timeout)


async def inspect_thread(agent: Any, thread_id: str, model: ModelName | str) -> dict:
    """What a thread is doing, without running it.

    ``paused`` carries the pauses the thread is parked on, ``unfinished`` means
    a run was cut before it ended (a redeploy mid-turn), ``idle`` is a thread
    waiting for its next message. Built on a placeholder model by the caller:
    ``aget_state`` needs a compiled graph to work out ``next``, and no model
    call is ever made — the checkpoint is read, not extended.
    """
    snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    pauses = live_pauses(snapshot)
    values = getattr(snapshot, "values", None) or {}
    return {
        "status": "paused" if pauses else "unfinished" if snapshot.next else "idle",
        "pauses": pauses,
        "todos": list(values.get("todos") or []),
        "message_count": len(values.get("messages") or []),
        # What the context gauge shows before any new turn has run.
        "usage": usage_from_messages(values.get("messages") or [], model),
    }


async def _no_artifact(_raw: str, _turn_text: str) -> None:
    return None


__all__ = [
    "FILESYSTEM_TOOLS",
    "NEVER_PRUNED",
    "RECURSION_SLACK",
    "SUPERSTEPS_PER_MODEL_CALL",
    "SUMMARIZATION_FLOOR_TOKENS",
    "DeepSession",
    "RunLimits",
    "build_deep_session_agent",
    "fallback_chain",
    "inspect_thread",
    "recorder_tool_hooks",
]
