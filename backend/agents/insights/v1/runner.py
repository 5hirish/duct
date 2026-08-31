"""AutonomousInsightsRunner — insights as a session, on ``deepagents`` (V1).

Replaces the shape of ``agents/insights/v1/agent.py``, not yet the file: that
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
session id, so a follow-up turn continues the same thread instead of replaying
a message list. That is also the seam ``interrupt()`` plugs into later — see
``agents/core/ports/__init__.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from uuid import UUID

from deepagents import FilesystemMiddleware, create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from agents.core.events import AgentEvent, AgentStep, StepStatus
from agents.core.connector_tools import build_connector_tools_lc
from agents.core.lc import build_ask_user_tool, resolve_chat_model, stream_agent
from agents.core.memory_tools import build_memory_tools_lc
from agents.core.session import BaseAgentSession
from agents.insights.brief import DEFAULT_FORMAT, parse_brief
from agents.insights.data_tools import build_data_tools_lc
from agents.insights.subagents import build_verify_subagent
from agents.insights.prompts.autonomous import (
    build_insights_system_prompt,
    build_insights_user_prompt,
)
from agents.models import ModelName, Provider
from agents.registry import AgentType

logger = logging.getLogger(__name__)

# Ceiling on one turn's tool-calling loop. Generous — an autonomous run legitimately
# plans, recalls, asks and re-plans — but finite, so a pathological loop ends as a
# failed turn the user can see rather than an unbounded spend.
RECURSION_LIMIT = 60

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
    ) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._temperature = temperature

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
        """
        if llm is None:
            llm = resolve_chat_model(self.provider, self.model, self._api_key, self._temperature)

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
        tools += build_connector_tools_lc(
            project_id,
            user_id=user_id,
            session=session,
            session_id=session_id,
            emit=emit,
            log_prefix="insights-v1",
        )
        # Data reach. The verifier gets the SAME tool objects, so it inherits
        # the parent's project scoping and credential closure rather than
        # resolving its own — there is one place credentials are resolved.
        async def _on_fetch(entity_id: str, result: dict) -> None:
            """Surface each pull as a step, so a long run is legible.

            The window is in the label deliberately: a user watching a brief
            being built should be able to see the period it covers without
            waiting for the prose to say so.
            """
            if emit is None:
                return
            ok = result.get("status") == "ok"
            window = (
                f" · {result.get('date_from')} → {result.get('date_to')}"
                if result.get("date_from") else ""
            )
            await emit({
                "event": AgentEvent.STEP_FINISHED,
                "step_id": AgentStep.COLLECT_SOURCE_DATA,
                "label": f"{entity_id.replace('_', ' ')}{window}",
                "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
                "connector_id": result.get("connector_id", ""),
            })

        data_tools = build_data_tools_lc(
            project_id, user_id=user_id, log_prefix="insights-v1", on_fetch=_on_fetch
        )
        tools += data_tools

        if session is not None and emit is not None:
            tools.append(
                build_ask_user_tool(
                    session,
                    session_id,
                    emit,
                    log_prefix="insights-v1",
                    description=ASK_USER_DESCRIPTION,
                )
            )

        return create_deep_agent(
            model=llm,
            tools=tools,
            # Integrity checking runs in its own context: the analyst is looking
            # for what matters, the verifier for what is wrong with the data, and
            # mixing the two costs the analyst its whole window before it writes
            # a word. See agents/insights/subagents/verify.py.
            subagents=[build_verify_subagent(data_tools)],
            system_prompt=system_prompt or build_insights_system_prompt(),
            # Planning is opt-in since deepagents 0.7. Mounted here because the
            # todo stream is what makes a long autonomous run legible — the
            # frontend already renders it (AuditTodos.jsx).
            middleware=[
                TodoListMiddleware(),
                # Explicit rather than default, to drop the shell tool — see
                # FILESYSTEM_TOOLS. StateBackend keeps the filesystem virtual:
                # it lives in graph state, so `read_file` cannot reach Duct's
                # source, the host, or anything outside this run's scratch space.
                FilesystemMiddleware(backend=StateBackend(), tools=list(FILESYSTEM_TOOLS)),
            ],
            # Continuity across turns. In-process only, like the session
            # registry it is keyed on; a durable checkpointer is the upgrade
            # that also unlocks interrupt()-based HITL.
            checkpointer=InMemorySaver(),
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
        start_version: int = 0,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
    ) -> None:
        """Run the opening turn, then stay open for follow-ups until idle.

        Per-project context (memory digest, business context, the user's actual
        question) is assembled into the USER turn — never the system prompt —
        so the cached system prefix stays byte-identical across customers.
        ``artifact_format`` is the user's declared preference and rides there
        for the same reason.

        ``start_version`` is the highest brief version already stored for this
        conversation, so a resumed session numbers its next brief v(n+1) rather
        than colliding with v1 — the artifact store's (group_id, version) pair
        is unique, and a collision would drop the brief.
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
            "configurable": {"thread_id": session_id},
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
            """A closing </duct_artifact>: publish it as the next brief version.

            ``ArtifactPersister`` is wrapped around ``emit`` by the route, so
            emitting is all it takes to store one — the runner never touches
            the database.
            """
            brief = parse_brief(raw)
            if not brief.body.strip():
                logger.warning("insights: empty <duct_artifact> payload — nothing to version")
                return
            version["n"] += 1
            n = version["n"]
            await emit({
                "event": AgentEvent.ARTIFACT_VERSION,
                "version_id": n,
                "label": brief.label or ("Initial brief" if n == 1 else f"Update {n}"),
                "payload": {
                    "title": brief.title,
                    "format": brief.format,
                    "content": brief.body,
                    "declared_format": brief.declared_format,
                },
            })
            logger.info(
                "insights: brief v%d — %r, %s, %d chars",
                n, brief.title, brief.format, len(brief.body),
            )

        async def _turn(text: str) -> None:
            await stream_agent(
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
            )

        await _turn(
            build_insights_user_prompt(
                prompt=prompt,
                business_context=business_context,
                user_context=user_context,
                memory=memory,
                artifact_format=artifact_format,
            )
        )
        # The opening turn is done; the session is now a live chat. Signalling
        # this separately from the run's end is what lets the UI leave "working"
        # and start accepting input.
        await emit({"event": AgentEvent.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})

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
            try:
                await _turn(_as_text(chat_msg))
            except Exception:
                # One bad turn must not end the session — the user can rephrase.
                logger.exception("insights: chat turn failed for session %s", session_id)
                await emit({
                    "event": AgentEvent.STEP_FAILED,
                    "status": StepStatus.ERROR,
                    "error": "That turn failed. Try rephrasing, or ask something else.",
                })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
