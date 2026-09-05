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

import logging
from typing import Any, Callable
from uuid import UUID, uuid4

from agents.core.connector_tools import build_connector_tools_lc
from agents.core.deep_session import (
    FILESYSTEM_TOOLS,
    SUMMARIZATION_FLOOR_TOKENS,
    DeepSession,
    RunLimits,
    build_deep_session_agent,
    fallback_chain,
    inspect_thread,
    recorder_tool_hooks,
)
from agents.core.events import AgentEvent, AgentStep, StepStatus
from agents.core.lc import (
    build_ask_user_tool,
    inspection_chat_model,
    interrupt_pause,
    resolve_chat_model,
    stream_agent,
)
from agents.core.memory_tools import build_memory_tools_lc
from agents.core.session import BaseAgentSession
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
# This agent's tools return whole GA4/Ads/Mixpanel payloads, so a long run's
# context is mostly *old tool output* — the cheapest thing in it to drop, and
# the least missed once a finding has been written down. Must stay below
# deepagents' summarization floor or the cheap pass silently never runs;
# `RunLimits` refuses to build otherwise, and `tests/test_insights_middleware.py`
# pins the floor to deepagents' own value.
TOOL_RESULT_PRUNE_TRIGGER = 120_000
TOOL_RESULTS_KEPT = 5

LIMITS = RunLimits(
    recursion=RECURSION_LIMIT,
    model_calls_per_run=MODEL_CALLS_PER_RUN,
    model_calls_per_thread=MODEL_CALLS_PER_THREAD,
    tool_calls_per_run=TOOL_CALLS_PER_RUN,
    tool_calls_per_thread=TOOL_CALLS_PER_THREAD,
    tool_result_prune_trigger=TOOL_RESULT_PRUNE_TRIGGER,
    tool_results_kept=TOOL_RESULTS_KEPT,
)

# Re-exported: the scratch-space verbs and the summarization floor are the
# shared session's (agents/core/deep_session.py); tests read them from here.
__all__ = ["AutonomousInsightsRunner", "FILESYSTEM_TOOLS", "LIMITS", "SUMMARIZATION_FLOOR_TOKENS"]

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

        # Provider outages and 429/529s end an autonomous run that may already
        # have spent several minutes fetching; one same-provider step down
        # keeps it alive (agents/core/deep_session.fallback_chain). Skipped
        # entirely when the caller injected its own `llm` — that seam is for
        # tests and for callers that have already decided which model to use.
        fallbacks: list[Any] = []
        if not injected_llm:
            fallbacks = fallback_chain(
                self.provider, self.model, self._api_key, self._temperature, thinking=self._thinking
            )

        return build_deep_session_agent(
            llm=llm,
            tools=tools,
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
            limits=LIMITS,
            session=session,
            fallbacks=fallbacks,
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

        async def _on_todo(todos: list) -> None:
            await emit({"event": AgentEvent.TODO_UPDATE, "todos": todos})

        on_tool_use, on_tool_result = recorder_tool_hooks(getattr(session, "recorder", None))

        # Version counter for this session's brief. One artifact group per
        # session (the route mints or resumes the group id); each closing tag
        # is the next version of it.
        version = {"n": start_version}

        async def _on_artifact(raw: str, turn_text: str) -> None:
            await _publish_brief(raw, emit, version)

        loop = DeepSession(
            agent,
            session=session,
            emit=emit,
            thread_id=str(conversation_id or session_id),
            limits=LIMITS,
            provider=self.provider,
            model=self.model,
            log_prefix="insights-v1",
            summariser=self._summariser_model(llm),
            on_artifact_close=_on_artifact,
            on_todo=_on_todo,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
        )
        # A resumed thread takes the raw prompt as a follow-up (or nothing, which
        # is what opening a thread from the desk asks for); a fresh one takes the
        # assembled opening turn with the per-project blocks.
        is_resume = resume and conversation_id is not None
        opening = prompt if is_resume else build_insights_user_prompt(
            prompt=prompt,
            business_context=business_context,
            user_context=user_context,
            memory=memory,
            artifact_format=artifact_format,
            autonomy=autonomy,
        )
        await loop.run(opening, resume=is_resume, chat_idle_timeout=chat_idle_timeout)

    def _summariser_model(self, llm: Any) -> Any:
        """The model an emergency compaction summarises with: the injected one
        when there is one (a test's fake must not fire a real call), else the
        runner's own."""
        if llm is not None:
            return llm
        return resolve_chat_model(
            self.provider, self.model, self._api_key, self._temperature, thinking=self._thinking
        )

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
        return await inspect_thread(agent, str(conversation_id), self.model)

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


