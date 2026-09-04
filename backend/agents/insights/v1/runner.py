"""AutonomousInsightsRunner — insights as a session, on ``deepagents`` (V1).

Replaced the shape of ``agents/insights/v1/agent.py``, and now the file too: that
two-call pipeline (tool loop → one structured-output call) still serves
``POST /api/insights/generate`` and the saved-routine refresh until the phase
plan retires it. Nothing here touches it.

Why ``create_deep_agent`` rather than ``create_agent``
-----------------------------------------------------
``backend/CLAUDE.md``'s rung rule says to pick the lowest layer that works, and
it classified insights as a ``create_agent`` job. That was right for a pipeline
with one tool loop and no planning. The autonomous shape needs four things
``create_agent`` does not have: a planning loop the UI already renders
(``write_todos`` → ``TODO_UPDATE``), subagents for the verification pass,
skills for the ten connector knowledge packs, and the ``interrupt_on`` upgrade
path for human review. So the rung moves up for this agent, deliberately.

Two safety properties worth stating, because they are the reason an autonomous
loop is shippable here at all:

* **The filesystem is virtual and there is no shell.** ``ls`` / ``read_file`` /
  ``write_file`` / ``edit_file`` / ``glob`` / ``grep`` run over graph state
  (``StateBackend``), not the disk, so the agent cannot read Duct's source or
  the host. ``deepagents`` also mounts an ``execute`` (shell) tool by default;
  it is dropped explicitly here rather than left to be inert — see
  ``FILESYSTEM_TOOLS``.
* **Execution stays gated in code.** When the execution tools mount (a later
  phase) the destructive gate and the auto-apply allowlist in
  ``service/execution/policy.py`` still decide what applies. There is no
  agent-facing approve tool, so no amount of autonomy talks past review.

Conversation continuity comes from a LangGraph checkpointer keyed on the
**conversation** id, so a follow-up turn continues the same thread instead of
replaying a message list — and a session opened tomorrow on the same
conversation continues it too. It was keyed on the session id once, which made
"resume" a transcript the user could see and the agent could not.

The same checkpoint is where a pause lives. A clarifying question, a connector
to authorize or an account to choose is a LangGraph ``interrupt()`` raised from
inside the tool (``agents/core/lc.interrupt_pause``): the thread parks, the
answer arrives as a ``Command(resume=...)`` through the chat queue, and a
session that reconnects — or a new one that resumes the conversation — is shown
the pause it is still waiting on. No timeout, no Future, nothing lost on a
redeploy. See ``agents/core/session.py`` for the port this implements.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from uuid import UUID, uuid4

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
from agents.core.events import AgentEvent, AgentStep, StepStatus
from agents.core.errors import error_payload
from agents.core.connector_tools import build_connector_tools_lc
from agents.core.lc import (
    ReportedRetryMiddleware,
    SteerMiddleware,
    drain_steers,
    build_ask_user_tool,
    inspection_chat_model,
    interrupt_pause,
    live_pauses,
    resolve_chat_model,
    stream_agent,
    usage_from_messages,
)
from agents.core.memory_tools import build_memory_tools_lc
from agents.core.session import BaseAgentSession, take_client_id
from agents.insights.brief import DEFAULT_FORMAT, parse_brief
from agents.insights.data_tools import build_data_tools_lc
from agents.insights.subagents import build_verify_subagent
from agents.insights.prompts.autonomous import (
    CAPABILITIES_PHASE_3,
    CAPABILITIES_UNATTENDED,
    build_insights_system_prompt,
    build_insights_user_prompt,
)
from agents.tools.execution_tools import build_execution_tools_lc
from agents.engines import Engine, resolve_fallback_models
from agents.models import ModelName, Provider
from agents.registry import AgentType
from models.execution import AUTONOMY_ASK

logger = logging.getLogger(__name__)

# Ceiling on one turn's tool-calling loop. Generous — an autonomous run legitimately
# plans, recalls, asks and re-plans — but finite, so a pathological loop ends as a
# failed turn the user can see rather than an unbounded spend.
RECURSION_LIMIT = 60

# Runaway guards, not budgets. `RECURSION_LIMIT` caps LangGraph *supersteps*,
# which is a graph-shape ceiling, not a spend one: a turn can stay well inside
# it and still make far more model calls than any real analysis needs. These
# two count the things that actually cost money.
#
# `exit_behavior="end"` on the model limit ends the turn with an AI message
# saying so, which the existing stream renders like any other reply — a
# truncated brief the user can read and re-ask beats a 500. The tool limit uses
# "continue": the offending tool is refused with an error the model can react
# to, while the rest of the turn proceeds.
#
# Per *run* means one user turn; per *thread* means the whole conversation,
# which is what makes these meaningful now that a thread survives a restart.
MODEL_CALLS_PER_RUN = 60
MODEL_CALLS_PER_THREAD = 400
TOOL_CALLS_PER_RUN = 120
TOOL_CALLS_PER_THREAD = 600

# Prune old tool results at this many tokens, keeping the most recent few.
#
# Must stay strictly below deepagents' summarization trigger or the cheap pass
# stops running — see the ContextEditingMiddleware comment in build_agent for
# why that is a threshold relationship and not an ordering one. Summarization
# fires at 0.85 of the model's window, or a flat 170k for a model with no
# profile, so 170k is the ceiling this has to clear on the smallest window Duct
# supports. `tests/test_insights_middleware.py` asserts it.
TOOL_RESULT_PRUNE_TRIGGER = 120_000
TOOL_RESULTS_KEPT = 5

# The lowest summarization trigger deepagents will pick: its no-profile default,
# which is also 0.85 × a 200k window. The prune trigger must stay under it.
SUMMARIZATION_FLOOR_TOKENS = 170_000

# The scratch-space verbs the agent gets, and the one it does not.
#
# `deepagents` mounts an `execute` tool alongside these — a shell. It is inert
# under the default StateBackend (which does not implement
# SandboxBackendProtocol, so the tool returns "Execution not available"), but
# "inert because of which backend happens to be configured" is not a guarantee:
# swapping in a sandbox backend later would silently hand this agent a shell.
# Naming the tools explicitly omits it from the dispatchable tool node entirely,
# which makes the isolation structural. `delete` is left out for the same
# reason of minimal surface — nothing needs it.
FILESYSTEM_TOOLS = ("ls", "read_file", "write_file", "edit_file", "glob", "grep")

# How long a session waits for a follow-up before closing itself. Matches audit
# and content; the route's own inactivity pruner is the longer backstop.
CHAT_IDLE_TIMEOUT = 1800.0

ASK_USER_DESCRIPTION = (
    "Ask the user up to 3 clarifying questions when their answer would materially "
    "change your analysis — which account or property to look at, which of two "
    "readings of their question is right, what a target actually is. Ask early, ask "
    "once, and never ask for something already in the project memory or business "
    "context. If you can state an assumption and continue, do that instead."
)


class AutonomousInsightsRunner:
    """Insight generation as a live session: chat, planning, memory, questions.

    Public surface mirrors the other session runners so ``routes/agents.py``
    drives it the same way it drives audit and content.
    """

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.ANTHROPIC,
        model: ModelName | str = ModelName.CLAUDE_SONNET,
        temperature: float = 1.0,
        thinking: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._temperature = temperature
        # A Duct level ("quick" … "exhaustive"), translated per model in
        # agents/thinking.py. Empty leaves the model on its own default.
        self._thinking = thinking

    # -----------------------------------------------------------------------
    # Assembly
    # -----------------------------------------------------------------------

    def build_agent(
        self,
        *,
        llm: Any = None,
        session: BaseAgentSession | None = None,
        session_id: str = "",
        emit: Callable | None = None,
        project_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        remember: bool = True,
        execute: bool = True,
        interactive: bool = True,
        system_prompt: str = "",
    ) -> Any:
        """Assemble the agent: memory tools, mid-run questions, planning.

        ``project_id`` arrives already membership-checked — ``routes/agents.py``
        stamps ``artifact_project_id`` on the session only after verifying the
        caller belongs to the project, and that is the id passed here. An
        unremembered session gets no memory tools at all: the agent cannot write
        what it cannot reach.

        ``llm`` is resolved from the runner's provider/model when omitted; the
        parameter exists so tests can drive the agent with a fake chat model, the
        same seam ``build_audit_agent`` uses.

        ``execute`` mounts the staged-execution tools. They need a user AND a
        membership-checked project, so the binder returns nothing without both;
        the flag exists for the caller that has both and still wants a
        read-only session.

        ``interactive=False`` is the unattended shape: no AskUserQuestion, and
        no connector tool that would pause the run waiting for a human. The
        system prompt says so in its own words, because an agent that plans
        around a question it will never get to ask produces a brief with a hole
        in it rather than a stated assumption.
        """
        # Recorded before the default is filled in: a caller-supplied model is
        # a deliberate choice (tests, and any caller that already resolved one),
        # and the fallback chain below must not override it.
        injected_llm = llm is not None
        if llm is None:
            llm = resolve_chat_model(
                self.provider,
                self.model,
                self._api_key,
                self._temperature,
                thinking=self._thinking,
            )

        tools: list[Any] = []
        if remember:
            async def _on_memory_written(entry: dict) -> None:
                if emit is not None:
                    await emit({"event": AgentEvent.MEMORY_WRITTEN, "memory": entry})

            tools += build_memory_tools_lc(
                project_id,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_type=str(AgentType.INSIGHTS),
                on_memory=_on_memory_written,
            )
        # Connector discovery. ListDataSources needs only a user; the two that
        # pause or bind need a project and a live session, and the binder mounts
        # only what it can actually serve.
        # An unattended run gets the read-only half by passing no session: the
        # binder mounts a pause tool only when there is somebody to pause for.
        # The pause tools park on the checkpoint (interrupt_pause), so the
        # session is only scoping here; an unattended run passes no pause and
        # gets the read-only tool alone.
        tools += build_connector_tools_lc(
            project_id,
            user_id=user_id,
            session=session if interactive else None,
            session_id=session_id,
            emit=emit,
            log_prefix="insights-v1",
            pause=interrupt_pause if interactive and session is not None else None,
        )
        # Data reach. The verifier gets the SAME tool objects, so it inherits
        # the parent's project scoping and credential closure rather than
        # resolving its own — there is one place credentials are resolved.
        def _fetch_label(entity_id: str, date_from: str, date_to: str) -> str:
            """The window is in the label deliberately: a user watching a brief
            being built should be able to see the period it covers without
            waiting for the prose to say so."""
            window = f" · {date_from} → {date_to}" if date_from else ""
            return f"{entity_id.replace('_', ' ')}{window}"

        async def _on_fetch_start(entity_id: str, date_from: str, date_to: str) -> None:
            """A pull begins — the ladder shows it running, not just finished."""
            if emit is None:
                return
            await emit({
                "event": AgentEvent.STEP_STARTED,
                "step_id": AgentStep.COLLECT_SOURCE_DATA,
                "label": _fetch_label(entity_id, date_from, date_to),
                "status": StepStatus.RUNNING,
            })

        async def _on_fetch(entity_id: str, result: dict) -> None:
            """Surface each pull as a step, so a long run is legible."""
            if emit is None:
                return
            ok = result.get("status") == "ok"
            await emit({
                "event": AgentEvent.STEP_FINISHED,
                "step_id": AgentStep.COLLECT_SOURCE_DATA,
                "label": _fetch_label(
                    entity_id, str(result.get("date_from") or ""), str(result.get("date_to") or "")
                ),
                "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
                "connector_id": result.get("connector_id", ""),
            })

        data_tools = build_data_tools_lc(
            project_id,
            user_id=user_id,
            log_prefix="insights-v1",
            on_fetch=_on_fetch,
            on_fetch_start=_on_fetch_start,
        )
        tools += data_tools

        # Acting. The agent proposes; whether a proposal applies without a
        # click is decided in service/execution/policy.py and never here —
        # there is deliberately no approve or apply tool to mount.
        execution_tools: list[Any] = []
        if execute:
            async def _on_change_set(card: dict) -> None:
                if emit is not None:
                    await emit({"event": AgentEvent.EXECUTION_PROPOSED, "change_set": card})

            execution_tools = build_execution_tools_lc(
                user_id=user_id,
                project_id=project_id,
                conversation_id=conversation_id,
                agent_type=str(AgentType.INSIGHTS),
                on_change_set=_on_change_set,
                log_prefix="insights-v1",
            )
            tools += execution_tools

        if interactive and session is not None and emit is not None:
            tools.append(
                build_ask_user_tool(
                    session,
                    session_id,
                    emit,
                    # Checkpointed: the question outlives the process that asked
                    # it. This agent always has a checkpointer (below).
                    pause=interrupt_pause,
                    log_prefix="insights-v1",
                    description=ASK_USER_DESCRIPTION,
                )
            )

        # One backend for the whole agent. `create_deep_agent` defaults to its
        # own `StateBackend()` when none is passed, which left this runner with
        # two instances — the one below for `FilesystemMiddleware` and an
        # internal one the summarization middleware offloads evicted history to.
        # They read the same graph-state key so nothing was broken, but passing
        # one instance makes it explicit that the offloaded transcript
        # (`/conversation_history/*.md`) is reachable by the `read_file` tool
        # this agent actually mounts. Still virtual: state, not disk.
        backend = StateBackend()

        # Provider outages and 429/529s end an autonomous run that may already
        # have spent several minutes fetching. One same-provider step down keeps
        # it alive on the key the caller supplied — see MODEL_FALLBACK in
        # agents/engines.py for why the chain is one step and never crosses a
        # provider.
        #
        # Only mounted when a chain exists, so a model at the bottom of its
        # family (or a raw OpenRouter slug) carries no middleware at all rather
        # than an empty one. Skipped entirely when the caller injected its own
        # `llm` — that seam is for tests and for callers that have already
        # decided which model to use; second-guessing it here would fire real
        # provider calls out of a fake-model test.
        fallbacks: list[Any] = []
        if not injected_llm:
            fallbacks = [
                resolve_chat_model(
                    self.provider, name, self._api_key, self._temperature,
                    thinking=self._thinking,
                )
                for name in resolve_fallback_models(Engine.V1, self.provider, self.model)
            ]

        return create_deep_agent(
            model=llm,
            tools=tools,
            backend=backend,
            # Integrity checking runs in its own context: the analyst is looking
            # for what matters, the verifier for what is wrong with the data, and
            # mixing the two costs the analyst its whole window before it writes
            # a word. See agents/insights/subagents/verify.py.
            subagents=[build_verify_subagent(data_tools)],
            system_prompt=system_prompt or build_insights_system_prompt(
                capabilities=(
                    CAPABILITIES_PHASE_3 if interactive else CAPABILITIES_UNATTENDED
                ),
                can_execute=bool(execution_tools),
            ),
            # Planning is opt-in since deepagents 0.7. Mounted here because the
            # todo stream is what makes a long autonomous run legible — the
            # frontend already renders it (AuditTodos.jsx).
            middleware=[
                TodoListMiddleware(),
                # Explicit rather than default, to drop the shell tool — see
                # FILESYSTEM_TOOLS. StateBackend keeps the filesystem virtual:
                # it lives in graph state, so `read_file` cannot reach Duct's
                # source, the host, or anything outside this run's scratch space.
                FilesystemMiddleware(backend=backend, tools=list(FILESYSTEM_TOOLS)),
                # Prune stale tool results so an LLM compaction is the second
                # response to a filling window, not the first. This agent's
                # tools return whole GA4/Ads/Mixpanel payloads, so a long run's
                # context is mostly *old tool output* — the cheapest thing in it
                # to drop, and the least missed once a finding has been written
                # down.
                #
                # Ordering here is by threshold, not by position. deepagents
                # mounts SummarizationMiddleware in its base stack and user
                # middleware always lands after it, so summarization is the
                # *outer* wrapper and gets the request first. What keeps it from
                # pre-empting this is its trigger: 0.85 of the model's context
                # window (or 170k with no profile). Below that it delegates
                # straight through, and this sees the untouched request — so a
                # trigger under 120k means pruning gets first crack on every turn
                # summarization decides not to touch. Raising it above ~145k
                # would silently invert that on a 200k model.
                #
                # `keep` holds the most recent results intact — the ones the
                # model is still reasoning over. AskUserQuestion is excluded
                # because a cleared answer reads as the user never having
                # replied, and the agent asks again.
                ContextEditingMiddleware(
                    edits=[
                        ClearToolUsesEdit(
                            trigger=TOOL_RESULT_PRUNE_TRIGGER,
                            keep=TOOL_RESULTS_KEPT,
                            clear_tool_inputs=False,
                            exclude_tools=("AskUserQuestion",),
                        )
                    ],
                ),
                ModelCallLimitMiddleware(
                    thread_limit=MODEL_CALLS_PER_THREAD,
                    run_limit=MODEL_CALLS_PER_RUN,
                    exit_behavior="end",
                ),
                ToolCallLimitMiddleware(
                    thread_limit=TOOL_CALLS_PER_THREAD,
                    run_limit=TOOL_CALLS_PER_RUN,
                    exit_behavior="continue",
                ),
                # Last of ours, so it sits closest to the model call and the
                # limit guards above still count a fallback attempt as the call
                # it is. `*fallbacks` splats to nothing when there is no chain,
                # which is how a bottom-tier model ends up with no middleware
                # rather than an empty one.
                *([ModelFallbackMiddleware(*fallbacks)] if fallbacks else []),
                # Innermost, so each model in the chain gets its retries before
                # the fallback moves on, and a transient 429 on the primary
                # never costs a downgrade. Reports every attempt to the UI.
                ReportedRetryMiddleware(),
                # A message typed mid-turn reaches the model at its next call.
                *([SteerMiddleware(session)] if session is not None else []),
            ],
            # Continuity across turns, now durable: the saver is opened once by
            # the app lifespan and follows DATABASE_URL (Postgres on Railway,
            # SQLite in the sidecar), so a follow-up turn survives the redeploy
            # or restart that used to reset the thread. Falls back to in-memory
            # when there is no database — see agents/core/checkpoint.py.
            checkpointer=get_checkpointer(),
        )

    # -----------------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------------

    async def run_session(
        self,
        session_id: str,
        emit: Callable,
        *,
        llm: Any = None,
        session: BaseAgentSession | None = None,
        prompt: str = "",
        business_context: str = "",
        user_context: str = "",
        memory: str = "",
        project_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        remember: bool = True,
        artifact_format: str = DEFAULT_FORMAT,
        autonomy: str = AUTONOMY_ASK,
        start_version: int = 0,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        resume: bool = False,
    ) -> None:
        """Run the opening turn, then stay open for follow-ups until idle.

        ``resume`` means the conversation already has a thread. What happens
        first depends on what that thread was doing: a parked one re-raises
        the pause it is waiting on (so the UI shows the card again, with
        ``replay`` set so it is not recorded twice), an unfinished one picks up
        from its last checkpoint, and an idle one runs ``prompt`` as a plain
        follow-up — or nothing at all when there is no prompt, which is what
        opening a thread from the desk asks for. Never a greeting.

        Per-project context (memory digest, business context, the user's actual
        question) is assembled into the USER turn — never the system prompt —
        so the cached system prefix stays byte-identical across customers.
        ``artifact_format`` is the user's declared preference and rides there
        for the same reason.

        ``start_version`` is the highest brief version already stored for this
        conversation, so a resumed session numbers its next brief v(n+1) rather
        than colliding with v1 — the artifact store's (group_id, version) pair
        is unique, and a collision would drop the brief.

        ``autonomy`` is the level this run *operates at* — the route resolves
        it through ``effective_autonomy``, so a model outside the allowlist has
        already been stepped down before it reaches here. It shapes how freely
        the agent asks; what may auto-apply is decided in
        ``service/execution/policy.py`` at propose time, not from this string.
        """
        agent = self.build_agent(
            llm=llm,
            session=session,
            session_id=session_id,
            emit=emit,
            project_id=project_id,
            user_id=user_id,
            conversation_id=conversation_id,
            remember=remember,
        )
        config = {
            # The conversation is the thread. A session is one process's
            # window onto it; keying on the session would give every resume
            # an agent with no memory of the transcript it is shown beside.
            "configurable": {"thread_id": str(conversation_id or session_id)},
            "recursion_limit": RECURSION_LIMIT,
        }
        recorder = getattr(session, "recorder", None)

        async def _on_todo(todos: list) -> None:
            await emit({"event": AgentEvent.TODO_UPDATE, "todos": todos})

        async def _on_tool_use(name: str, tool_input: Any, tool_use_id: str) -> None:
            if recorder is not None:
                await recorder.record_tool_use(name, tool_input, tool_use_id)

        async def _on_tool_result(name: str, result: Any, tool_use_id: str, is_error: bool) -> None:
            if recorder is not None:
                await recorder.record_tool_result(name, result, tool_use_id, is_error=is_error)

        # Version counter for this session's brief. One artifact group per
        # session (the route mints or resumes the group id); each closing tag
        # is the next version of it.
        version = {"n": start_version}

        async def _on_artifact(raw: str, turn_text: str) -> None:
            await _publish_brief(raw, emit, version)

        async def _on_pause(pauses: list[dict]) -> None:
            # The route resolves an answer against this: it is how a POST with
            # an interrupt id turns into the Command the next loop iteration
            # streams. Written before the events go out, so the answer to a
            # card can never arrive at a route that has not heard of it.
            # Replaced whole each turn — a pause that was answered is gone,
            # one that re-raised is back.
            if session is not None:
                session.pending_pauses = {p["interrupt_id"]: p for p in pauses}

        async def _turn(text: str | Command | None) -> list[dict]:
            if session is not None:
                session.turn_active = True
            try:
                pauses = await stream_agent(
                    agent,
                    text,
                    emit,
                    on_artifact_close=_on_artifact,
                    log_prefix="insights-v1",
                    config=config,
                    provider=self.provider,
                    model=self.model,
                    conversation_id=str(conversation_id or session_id),
                    on_todo=_on_todo,
                    on_tool_use=_on_tool_use,
                    on_tool_result=_on_tool_result,
                    on_pause=_on_pause,
                )
            finally:
                if session is not None:
                    session.turn_active = False
            if not pauses:
                await _on_pause([])  # a turn that ran to completion clears the table
            return await _leftover_steers(pauses)

        async def _leftover_steers(pauses: list[dict]) -> list[dict]:
            """A message that arrived after the turn's last model call never
            met the steer middleware. It becomes the next turn now, not a
            surprise at the top of whatever the user asks next."""
            while not pauses and session is not None:
                items = drain_steers(session.steer_queue)
                if not items:
                    return pauses
                for _, client_id in items:
                    if client_id:
                        await emit({"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": client_id})
                text = "\n\n".join(_as_text(item) for item, _ in items if _as_text(item))
                if not text:
                    return pauses
                pauses = await _turn(text)
            return pauses

        # The opening turn is what moves the UI out of "working" — PIPELINE_FINISHED
        # is held back until a turn ends with nothing parked, however many
        # answers that takes.
        opened = False

        async def _finish_opening(pauses: list[dict]) -> None:
            nonlocal opened
            if opened or pauses:
                return
            opened = True
            await emit({"event": AgentEvent.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})

        if resume and conversation_id is not None:
            snapshot = await agent.aget_state(config)
            parked = live_pauses(snapshot)
            if parked:
                # Show the pause again without re-running anything. `replay`
                # keeps the recorder from writing the question a second time.
                for pause in parked:
                    await emit({**pause, "replay": True})
                if session is not None:
                    session.pending_pauses = {p["interrupt_id"]: p for p in parked}
                pauses = parked
            elif snapshot.next:
                pauses = await _turn(None)  # cut mid-run: continue from the checkpoint
            elif prompt:
                pauses = await _turn(prompt)  # a follow-up on an idle thread
            else:
                pauses = []
        else:
            pauses = await _turn(
                build_insights_user_prompt(
                    prompt=prompt,
                    business_context=business_context,
                    user_context=user_context,
                    memory=memory,
                    artifact_format=artifact_format,
                    autonomy=autonomy,
                )
            )
        await _finish_opening(pauses)

        if session is None:
            return

        while True:
            try:
                chat_msg = await asyncio.wait_for(
                    session.chat_queue.get(), timeout=chat_idle_timeout
                )
            except asyncio.TimeoutError:
                logger.info("insights: session %s chat idle timeout", session_id)
                break
            if chat_msg is None:  # sentinel from close_session
                break
            chat_msg, client_id = take_client_id(chat_msg)
            if client_id:
                await emit({"event": AgentEvent.USER_INPUT_CONSUMED, "client_message_id": client_id})
            try:
                if isinstance(chat_msg, dict) and "resume" in chat_msg:
                    pauses = await _turn(Command(resume=chat_msg["resume"]))
                else:
                    pauses = await _turn(_as_text(chat_msg))
                await _finish_opening(pauses)
            except Exception as exc:
                # One bad turn must not end the session — the user can rephrase.
                # The code says what kind of failure it was; the client picks
                # the copy and whether a retry button makes sense.
                logger.exception("insights: chat turn failed for session %s", session_id)
                await emit({
                    "event": AgentEvent.STEP_FAILED,
                    "status": StepStatus.ERROR,
                    **error_payload(exc),
                })

    # -----------------------------------------------------------------------
    # Inspection
    # -----------------------------------------------------------------------

    async def thread_state(self, conversation_id: UUID) -> dict:
        """What a conversation's thread is doing, without running it.

        ``paused`` carries the pauses the thread is parked on, ``unfinished``
        means a run was cut before it ended (a redeploy mid-turn), ``idle`` is
        a thread waiting for its next message. The UI reads this on open so a
        parked question is on screen before any session exists; the desk can
        badge a thread that is waiting on its owner.

        Built on a placeholder model: ``aget_state`` needs a compiled graph to
        work out ``next``, and no model call is ever made. Only what shapes the
        graph matters, so the tools that need a session or a project are left
        out — the checkpoint is read, not extended.
        """
        agent = self.build_agent(
            llm=inspection_chat_model(), remember=False, execute=False, interactive=False
        )
        snapshot = await agent.aget_state(
            {"configurable": {"thread_id": str(conversation_id)}}
        )
        pauses = live_pauses(snapshot)
        values = getattr(snapshot, "values", None) or {}
        return {
            "status": "paused" if pauses else "unfinished" if snapshot.next else "idle",
            "pauses": pauses,
            "todos": list(values.get("todos") or []),
            "message_count": len(values.get("messages") or []),
            # What the context gauge shows before any new turn has run.
            "usage": usage_from_messages(values.get("messages") or [], self.model),
        }


    # -----------------------------------------------------------------------
    # Unattended
    # -----------------------------------------------------------------------

    async def run_once(
        self,
        emit: Callable,
        *,
        llm: Any = None,
        prompt: str = "",
        business_context: str = "",
        user_context: str = "",
        memory: str = "",
        project_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        remember: bool = True,
        artifact_format: str = DEFAULT_FORMAT,
        autonomy: str = AUTONOMY_ASK,
        start_version: int = 0,
    ) -> dict:
        """One turn, nobody watching. Returns the brief it wrote.

        The entry point for a scheduled brief. ``backend/CLAUDE.md`` is explicit
        that the scheduled brief is the product and it can never block on a
        human, so this shape exists to make blocking *impossible* rather than
        discouraged: the tools that pause are not mounted, and the system
        prompt says there is nobody to ask.

        ``emit`` still matters even with no SSE consumer — the caller wraps it
        with ``ArtifactPersister``, so emitting ARTIFACT_VERSION is what stores
        the brief. The return value is for the caller's response body; the
        durable output is the artifact.
        """
        agent = self.build_agent(
            llm=llm,
            session=None,
            emit=emit,
            project_id=project_id,
            user_id=user_id,
            conversation_id=conversation_id,
            remember=remember,
            interactive=False,
        )
        written: list[dict] = []
        version = {"n": start_version}

        async def _on_artifact(raw: str, turn_text: str) -> None:
            payload = await _publish_brief(raw, emit, version)
            if payload is not None:
                written.append(payload)

        await stream_agent(
            agent,
            build_insights_user_prompt(
                prompt=prompt,
                business_context=business_context,
                user_context=user_context,
                memory=memory,
                artifact_format=artifact_format,
                autonomy=autonomy,
            ),
            emit,
            on_artifact_close=_on_artifact,
            log_prefix="insights-v1",
            config={
                "configurable": {"thread_id": str(conversation_id or uuid4())},
                "recursion_limit": RECURSION_LIMIT,
            },
            provider=self.provider,
            model=self.model,
            conversation_id=str(conversation_id or ""),
        )
        await emit({"event": AgentEvent.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})
        # A run that reached no conclusion worth keeping is reported as such
        # rather than dressed up as an empty brief.
        return written[-1] if written else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _publish_brief(raw: str, emit: Callable, version: dict) -> dict | None:
    """A closing </duct_artifact>: publish it as the next brief version.

    ``ArtifactPersister`` is wrapped around ``emit`` by the caller, so emitting
    is all it takes to store one — the runner never touches the database.
    Returns the payload, or None when the payload was empty (an empty version
    would be a blank brief in the artifacts list forever).
    """
    brief = parse_brief(raw)
    if not brief.body.strip():
        logger.warning("insights: empty <duct_artifact> payload — nothing to version")
        return None
    version["n"] += 1
    n = version["n"]
    payload = {
        "title": brief.title,
        "format": brief.format,
        "content": brief.body,
        "declared_format": brief.declared_format,
    }
    await emit({
        "event": AgentEvent.ARTIFACT_VERSION,
        "version_id": n,
        "label": brief.label or ("Initial brief" if n == 1 else f"Update {n}"),
        "payload": payload,
    })
    logger.info(
        "insights: brief v%d — %r, %s, %d chars", n, brief.title, brief.format, len(brief.body)
    )
    return payload


def _as_text(chat_msg: Any) -> str:
    """A queued chat message as plain text.

    ``routes/agents.py`` queues ``{"role": "user", "content": ...}`` where the
    content is a string or a content-block list (image uploads), so unwrap the
    envelope and flatten the list form rather than handing either to a prompt
    slot. Plain strings are accepted too — that is what the content runner's
    internal nudges put on the same queue.
    """
    if isinstance(chat_msg, dict):
        chat_msg = chat_msg.get("content", "")
    if isinstance(chat_msg, str):
        return chat_msg
    if isinstance(chat_msg, list):
        return "\n".join(
            block.get("text", "")
            for block in chat_msg
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(chat_msg or "")
