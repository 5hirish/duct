"""ContentRunner — the Content Studio session on ``deepagents`` (V1).

The port of ``agents/content/v3/runner.py``, which ran the same product on the
Claude Agent SDK. Everything the SDK did for free has a named counterpart
here, and the frontend cannot tell which served a run:

* **Sub-agents.** ``research_pillar`` and ``draft_post`` are ``SubAgent``
  specs dispatched through the harness's ``task`` tool. Their dispatch is
  surfaced as ``dispatch_subagent:<name>`` steps from the tool traffic in the
  stream, the same chips the SDK's ``Agent`` hooks produced.
* **The open web.** ``WebFetch`` is Duct's own tool; web search is the
  provider's server-side tool where one is verified (``agents/core/web_tools``).
* **Planning.** ``write_todos`` → ``TODO_UPDATE``, which the workspace already
  renders.
* **Human-in-the-loop.** ``AskUserQuestion`` parks the thread on a LangGraph
  ``interrupt()`` (``agents/core/lc.interrupt_pause``): the question survives a
  redeploy, has no timeout, and comes back — flagged ``replay`` — when a
  session resumes the conversation. The slide-render bridge stays on an
  in-process Future: it is the *browser* answering within seconds, not a
  person.
* **Conversation continuity.** The LangGraph thread is keyed on the
  **conversation** id, so a follow-up continues the same thread and a session
  opened tomorrow continues it too. The DB re-prime (``build_reprime_context``)
  is kept for one case: a conversation recorded before this runner existed
  has a transcript and no checkpoint, and gets the summary on its first turn.
* **The two things the SDK could not do.** Any provider — the reason for the
  consolidation — and a durable thread.

Two safety properties, both structural rather than instructed:

* **The filesystem is virtual and there is no shell.** The scratch tools run
  over graph state (``StateBackend``); ``execute`` is dropped by naming the
  filesystem tools explicitly — see ``FILESYSTEM_TOOLS`` and the insights
  runner, which established the pattern.
* **Sub-agents cannot write.** The writer tools are mounted on the
  orchestrator alone; every sub-agent's tool list is chosen by name, and the
  writers are on none of them — including the harness's own general-purpose
  sub-agent, which is supplied here read-only so its default (every tool of
  the parent) never mounts.

Why ``create_deep_agent`` and not ``create_agent``: the same four reasons the
insights session moved up a rung — planning, sub-agents, the virtual scratch
space, and the ``interrupt_on`` upgrade path — and content spends three of
them from the first turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from agents.content.artifacts import (
    ARTIFACT_PLAN,
    ARTIFACT_POST,
    RECOVERY_NUDGE_PLAN,
    RECOVERY_NUDGE_POST,
    parse_artifact_json,
)
from agents.content.events import STEP_LABELS, ContentEvent, ContentStep, StepStatus
from agents.content.prompts import (
    build_orchestrator_system_prompt,
    build_plan_user_prompt,
    build_post_user_prompt,
)
from agents.content.schema import (
    AppFeature,
    ContentBrandContext,
    ContentPillar,
    ContentSession,
    ContentTool,
    ContentVisualAssets,
    Day,
    PlanDraft,
    PostDraft,
    RunMode,
    make_session,
)
from agents.content.subagents import (
    DRAFT_POST_TOOLS,
    GENERAL_PURPOSE_TOOLS,
    RESEARCH_PILLAR_TOOLS,
    build_draft_post_subagent,
    build_general_purpose_subagent,
    build_research_pillar_subagent,
)
from agents.content.tools import build_content_tools_lc
from agents.core import session as _core_session
from agents.core.deep_session import (
    DeepSession,
    RunLimits,
    build_deep_session_agent,
    fallback_chain,
    inspect_thread,
    recorder_tool_hooks,
)
from agents.core.lc import build_ask_user_tool, inspection_chat_model, interrupt_pause, resolve_chat_model
from agents.core.session import register_session
from agents.core.web_tools import WEB_FETCH_TOOL, build_web_tools_lc
from agents.engines import Engine, resolve_fallback_models
from agents.models import ModelName, Provider
from agents.registry import AgentType

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Any]

# Runaway guards, not budgets — see the insights runner for the reasoning.
# Content turns are longer than an analysis turn (an image phase is many small
# calls), so the per-run figures sit above insights'. The superstep ceiling
# is derived from the model-call guard by RunLimits; a plan turn reads the
# libraries, dispatches a sub-agent per pillar, composes and submits, and a
# hand-picked 100 supersteps let it make 14 calls before the graph gave up.
MODEL_CALLS_PER_RUN = 80
MODEL_CALLS_PER_THREAD = 600
TOOL_CALLS_PER_RUN = 160
TOOL_CALLS_PER_THREAD = 1200

# Prune old tool results at this many tokens, keeping the most recent few. A
# content thread's bulk is old fetch payloads and image blocks the model has
# already critiqued; `keep` holds the ones it is still working from. RunLimits
# refuses a trigger above deepagents' summarisation floor.
TOOL_RESULT_PRUNE_TRIGGER = 120_000
TOOL_RESULTS_KEPT = 8

LIMITS = RunLimits(
    model_calls_per_run=MODEL_CALLS_PER_RUN,
    model_calls_per_thread=MODEL_CALLS_PER_THREAD,
    tool_calls_per_run=TOOL_CALLS_PER_RUN,
    tool_calls_per_thread=TOOL_CALLS_PER_THREAD,
    tool_result_prune_trigger=TOOL_RESULT_PRUNE_TRIGGER,
    tool_results_kept=TOOL_RESULTS_KEPT,
)

# How long a session waits for a follow-up before closing itself. Matches
# audit and insights; the route's own inactivity pruner is the longer backstop.
CHAT_IDLE_TIMEOUT = 1800.0

# Providers whose API accepts image blocks inside a tool result. The image
# phase is built on the model looking at what it generated; elsewhere the
# tools return the asset URL and the prompt says so.
VISION_PROVIDERS = frozenset({Provider.ANTHROPIC})

ASK_USER_DESCRIPTION = (
    "Ask the user up to 3 clarifying questions when their answer would materially "
    "change the plan or the post — a missing brand voice, an audience you cannot "
    "infer, which of two directions they want. Ask early, ask once, and never ask "
    "for something already in the brand context or the project memory."
)

# The tool the harness dispatches sub-agents through, and its argument that
# names which one. deepagents' own names — pinned here so a rename in a minor
# shows up as a missing step chip in the harness test, not a silent one.
TASK_TOOL = "task"
TASK_SUBAGENT_ARG = "subagent_type"

# Cap on what a step chip shows of a dispatch brief or a sub-agent's report.
_SUMMARY_CHARS = 160
_RESULT_CHARS = 240
_STEP_SUMMARY_CHARS = 140


# ---------------------------------------------------------------------------
# Session registry — shared with all agents (agents/core/session.py). These
# wrappers keep the content-specific import surface and ContentSession typing.
# ---------------------------------------------------------------------------

get_session = _core_session.get_session
close_session = _core_session.close_session


def create_plan_session(session_id: str, project_id: UUID) -> ContentSession:
    return register_session(make_session(session_id, project_id, "plan_month"))


def create_draft_session(
    session_id: str,
    project_id: UUID,
    *,
    plan_id: UUID | None = None,
) -> ContentSession:
    session = make_session(session_id, project_id, "draft_post")
    if plan_id is not None:
        session.plan_id = plan_id
    return register_session(session)


# ---------------------------------------------------------------------------
# Brand context loader
# ---------------------------------------------------------------------------


def _load_brand_context(project_id: UUID) -> ContentBrandContext:
    """Build a ContentBrandContext snapshot from the Project row.

    Read at session start so the opening prompt embeds the latest brand state.
    The fetch_brand_context tool re-reads on demand for long sessions.
    """
    from sqlmodel import Session

    from db.session import get_engine
    from models.project import Project

    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as db:
        proj = db.get(Project, project_id)
        if proj is None:
            raise ValueError(f"Project {project_id} not found.")

        brand_blob = proj.content_brand or {}
        pillars_blob = proj.content_pillars or {}
        visual_blob = proj.content_visual_assets or {}

        pillars_list = pillars_blob.get("items") if isinstance(pillars_blob, dict) else pillars_blob
        pillars = [
            ContentPillar.model_validate(p)
            for p in (pillars_list or [])
            if isinstance(p, dict)
        ]
        features = [
            AppFeature.model_validate(f)
            for f in (brand_blob.get("features") or [])
            if isinstance(f, dict)
        ]
        visual = (
            ContentVisualAssets.model_validate(visual_blob)
            if isinstance(visual_blob, dict) and visual_blob
            else ContentVisualAssets()
        )

        # Shared business fields come from the project context (single source of
        # truth); content-specific fields stay in content_brand. Fall back to the
        # legacy content_brand values for projects edited before this split.
        channels_blob = proj.brand_channels or {}
        brand_voice = str(channels_blob.get("brand_voice") or brand_blob.get("brand_voice") or "")
        audience = _compose_audience(proj.audience) or str(brand_blob.get("audience") or "")

        return ContentBrandContext(
            project_id=proj.id,
            project_name=proj.name,
            slug=proj.slug or "",
            tagline=proj.tagline or "",
            description=proj.description or "",
            url=proj.url or "",
            audience=audience,
            brand_voice=brand_voice,
            tone=str(brand_blob.get("tone") or ""),
            value_prop=str(brand_blob.get("value_prop") or ""),
            content_goal=str(brand_blob.get("content_goal") or ""),
            do_say=str(brand_blob.get("do_say") or ""),
            do_not_say=str(brand_blob.get("do_not_say") or ""),
            features=features,
            pillars=pillars,
            visual=visual,
        )


def _compose_audience(audience: dict | None) -> str:
    """Render the project's structured audience into a prompt-friendly line.

    Shape: { primary_segment, personas: [{ name, description, priority }] }.
    Returns "" when nothing usable is set so callers can fall back.
    """
    if not isinstance(audience, dict):
        return ""
    parts: list[str] = []
    segment = str(audience.get("primary_segment") or "").strip()
    if segment:
        parts.append(segment)
    personas = audience.get("personas")
    if isinstance(personas, list):
        for p in personas:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            desc = str(p.get("description") or "").strip()
            if name and desc:
                parts.append(f"{name} — {desc}")
            elif name or desc:
                parts.append(name or desc)
    return "; ".join(parts)


async def _memory_block(session: ContentSession, *, query: str = "") -> str:
    """The project's memory digest for a content run, as a user-turn block.

    Same contract as the other agents: per-project data rides in the USER
    message so the cached system prefix stays byte-identical, and a missing
    digest degrades the turn rather than failing it.
    """
    if getattr(session, "memory_off", False):
        return ""

    def _load() -> str:
        from db.session import get_session as db_session
        from service.memory import build_memory_context, touch_recall

        with next(db_session()) as db:
            context = build_memory_context(
                db,
                project_id=session.project_id,
                user_id=getattr(session, "user_id", None),
                agent_type=str(AgentType.TIKTOK_STUDIO),
                query=query,
                artifact_kind=None,
            )
            touch_recall(db, context.recalled_ids)
            return context.text

    try:
        return await asyncio.to_thread(_load)
    except Exception:  # noqa: BLE001
        logger.warning("content: project memory unavailable", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ContentRunner:
    """Content Studio as a live session: plan or draft, then chat, on any provider.

    Public surface mirrors the other session runners so ``routes/content.py``
    and ``routes/agents.py`` drive it the way they drive audit and insights.
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

    @property
    def vision(self) -> bool:
        """Whether this run's provider lets the model see the images it makes."""
        return self.provider in VISION_PROVIDERS

    # -----------------------------------------------------------------------
    # Assembly
    # -----------------------------------------------------------------------

    def build_agent(
        self,
        *,
        llm: Any = None,
        session: ContentSession | None = None,
        session_id: str = "",
        emit: EmitFn | None = None,
        project_id: UUID | None = None,
        mode: RunMode = "plan_month",
        channel: Any = None,
        remember: bool = True,
        interactive: bool = True,
        system_prompt: str = "",
    ) -> Any:
        """Assemble the agent: content tools, sub-agents, planning, questions.

        ``project_id`` arrives already membership-checked — the routes verify
        the caller belongs to the project before the session exists. Without a
        session, a project and an emitter there are no content tools at all
        (nothing to scope them to), which is the shape ``thread_state`` uses
        to read a checkpoint without extending it.

        ``llm`` is resolved from the runner's provider/model when omitted; the
        parameter exists so tests can drive the agent with a fake chat model.
        A caller-supplied model is used for the sub-agents too, so a fake never
        fans out into a real provider call.
        """
        injected_llm = llm is not None
        if llm is None:
            llm = resolve_chat_model(
                self.provider, self.model, self._api_key, self._temperature,
                thinking=self._thinking,
            )

        # Fetch, plus whichever search this provider/model can actually use —
        # the provider's built-in where that survives a tool-calling loop, and
        # Duct's own Gemini-backed tool everywhere else. One call so the
        # sub-agents below mount the same set the orchestrator does.
        emit_or_drop = emit or _drop
        web_tools: list[Any] = build_web_tools_lc(
            self.provider,
            self.model,
            getattr(session, "gemini_api_key", "") or "",
            fetch_hooks=self._step_hooks(
                session, emit_or_drop, label="Reading page", prefix="research"
            ),
            search_hooks=self._step_hooks(
                session, emit_or_drop, label="Searching the web", prefix="search"
            ),
        )

        tools: list[Any] = []
        subagents: list[dict] = []
        if session is not None and project_id is not None and emit is not None:
            content_tools = build_content_tools_lc(
                project_id, emit, session, vision=self.vision, remember=remember
            )
            tools += content_tools
            by_name = {t.name: t for t in content_tools}

            def _pick(names: tuple[str, ...]) -> list[Any]:
                chosen = [by_name[n] for n in names if n in by_name]
                if WEB_FETCH_TOOL in names:
                    chosen += web_tools
                return chosen

            # Research runs on the cheaper sibling where the family has one —
            # the same step the fallback chain takes — because topic discovery
            # is volume work. Drafting stays on the run's model: creative
            # quality is the point.
            subagents = [
                build_research_pillar_subagent(
                    _pick(RESEARCH_PILLAR_TOOLS), self._sibling_model(llm, injected_llm)
                ),
                build_draft_post_subagent(_pick(DRAFT_POST_TOOLS), llm),
                # deepagents adds a "general-purpose" sub-agent carrying EVERY
                # tool of the parent unless one by that name is supplied. That
                # would hand the writers to a sub-agent; this one reads only.
                build_general_purpose_subagent(_pick(GENERAL_PURPOSE_TOOLS), llm),
            ]
        tools += web_tools

        if interactive and session is not None and emit is not None:
            tools.append(
                build_ask_user_tool(
                    session,
                    session_id,
                    emit,
                    # Checkpointed: the question outlives the process that asked
                    # it. This agent always has a checkpointer (below).
                    pause=interrupt_pause,
                    log_prefix="content-v1",
                    description=ASK_USER_DESCRIPTION,
                )
            )

        # One same-provider step down keeps a run alive on the key the caller
        # supplied. Skipped with an injected model — that seam is for tests.
        fallbacks: list[Any] = []
        if not injected_llm:
            fallbacks = fallback_chain(
                self.provider, self.model, self._api_key, self._temperature, thinking=self._thinking
            )

        return build_deep_session_agent(
            llm=llm,
            tools=tools,
            subagents=subagents,
            system_prompt=system_prompt or build_orchestrator_system_prompt(
                None, mode, channel=channel, vision=self.vision
            ),
            limits=LIMITS,
            session=session,
            fallbacks=fallbacks,
        )

    def _sibling_model(self, llm: Any, injected: bool) -> Any:
        """The cheaper model in this family, for volume work; the run's own
        model when the family has none — or when a test injected one."""
        if injected:
            return llm
        names = resolve_fallback_models(Engine.V1, self.provider, self.model)
        if not names:
            return llm
        return resolve_chat_model(
            self.provider, names[0], self._api_key, self._temperature, thinking=self._thinking
        )

    @staticmethod
    def _step_hooks(
        session: ContentSession | None, emit: EmitFn, *, label: str, prefix: str
    ) -> tuple[Any, Any]:
        """One web call as a visible step: opened on the call, closed on the
        result. FIFO pairing is approximate under parallel calls (a research
        sub-agent fans out) but accurate enough for the progress display.

        Parameterised by label rather than duplicated per tool: fetch and
        search render identically and differ only in what they say."""
        pending: deque[str] = deque()
        seq = [0]
        session_id = session.session_id if session is not None else ""

        async def on_start(detail: str) -> None:
            seq[0] += 1
            sid = f"{prefix}:{seq[0]}"
            pending.append(sid)
            await emit({
                "event": ContentEvent.STEP_STARTED,
                "session_id": session_id,
                "step_id": sid,
                "label": label,
                "summary": detail[:_STEP_SUMMARY_CHARS],
                "status": StepStatus.RUNNING,
            })

        async def on_done(_detail: str, ok: bool) -> None:
            if not pending:
                return
            sid = pending.popleft()
            await emit({
                "event": ContentEvent.STEP_FINISHED,
                "session_id": session_id,
                "step_id": sid,
                "label": label,
                "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
            })

        return on_start, on_done

    # -----------------------------------------------------------------------
    # Entry points — drop-ins for the V3 runner's run_plan / run_draft
    # -----------------------------------------------------------------------

    async def run_plan(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        llm: Any = None,
    ) -> None:
        """Run a plan_month session end-to-end: load, enrich, plan, then chat."""
        session = get_session(session_id) or create_plan_session(session_id, project_id)

        async def _opening(brand: ContentBrandContext) -> str:
            research = await self._enrich_step(brand, emit, llm, session)
            return build_plan_user_prompt(brand, history=[], formats=[], avatars=[], research=research)

        await self._run_mode(
            session, emit,
            opening=_opening,
            memory_query="content plan performance",
            llm=llm,
            chat_idle_timeout=chat_idle_timeout,
        )

    async def run_draft(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        day: Day | None = None,
        topic: str | None = None,
        pillar: str | None = None,
        format_slug: str = "",
        channel: str | None = None,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        llm: Any = None,
    ) -> None:
        """Run a draft_post session end-to-end: load, write, then chat."""
        from agents.content.channels import resolve as resolve_channel

        session = get_session(session_id) or create_draft_session(session_id, project_id)
        ch = resolve_channel(channel)  # sync, no DB — safe before the first emit

        async def _opening(brand: ContentBrandContext) -> str:
            return build_post_user_prompt(
                brand, day,
                topic=topic, pillar=pillar, format_slug=format_slug,
                avatar=None, recent_posts=[], channel=ch,
            )

        await self._run_mode(
            session, emit,
            opening=_opening,
            memory_query=topic or pillar or "",
            channel=ch,
            # PIPELINE_STARTED carries the resolved channel; the UI notes a fallback.
            started={"channel": ch.id, "channel_label": ch.label, "channel_supported": ch.supported},
            llm=llm,
            chat_idle_timeout=chat_idle_timeout,
        )

    async def _run_mode(
        self,
        session: ContentSession,
        emit: EmitFn,
        *,
        opening: Callable[[ContentBrandContext], Awaitable[str]],
        memory_query: str,
        channel: Any = None,
        started: dict | None = None,
        llm: Any,
        chat_idle_timeout: float,
    ) -> None:
        """What both modes share: the resume shape, the lifecycle events, the
        brand load, the memory block, then the session.

        A resume restores and goes READY — no lifecycle steps, no greeting —
        because reload/refresh/reconnect must just bring the session back.
        A fresh run emits its first events BEFORE loading brand context so the
        UI leaves "Starting session…" immediately; the load is a sync DB read
        and runs off the loop so the SSE stream stays live.
        """
        resume = self._is_resume(session)
        if not resume:
            await emit({
                "event": ContentEvent.PIPELINE_STARTED,
                "session_id": session.session_id,
                "mode": session.mode,
                **(started or {}),
            })
            brand = await self._load_project_step(session.project_id, emit)
            opening_prompt = await opening(brand)
            memory = await _memory_block(session, query=memory_query)
            if memory:
                opening_prompt = f"{opening_prompt}\n\n{memory}"
        else:
            brand = await asyncio.to_thread(_load_brand_context, session.project_id)
            opening_prompt = ""

        await self._run_session(
            session, emit,
            system_prompt=build_orchestrator_system_prompt(
                brand, session.mode, channel=channel, vision=self.vision
            ),
            opening_prompt=opening_prompt,
            llm=llm,
            chat_idle_timeout=chat_idle_timeout,
            resume=resume,
            channel=channel,
        )

    async def _enrich_step(
        self, brand: ContentBrandContext, emit: EmitFn, llm: Any,
        session: ContentSession | None = None,
    ) -> Any:
        """The pre-flight research pass, as a visible step. Plan mode only."""
        from agents.content.enrichment import enrich_content_context

        await emit({
            "event": ContentEvent.STEP_STARTED,
            "step_id": ContentStep.ENRICHING,
            "label": STEP_LABELS[ContentStep.ENRICHING],
            "status": StepStatus.RUNNING,
        })
        research = await enrich_content_context(
            brand, self._api_key,
            provider=self.provider,
            model=self._research_model_name(),
            llm=llm,
            # Backs Duct's own WebSearch where the provider has no usable
            # built-in; the same key the image tools already run on.
            gemini_api_key=getattr(session, "gemini_api_key", "") or "",
        )
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.ENRICHING,
            "label": STEP_LABELS[ContentStep.ENRICHING],
            "status": StepStatus.SUCCESS,
            "payload": {
                "pillar_history": len(research.pillar_history),
                "trending_sounds": len(research.trending_sounds),
                "trending_hashtags": len(research.trending_hashtags),
                "trending_hooks": len(research.trending_hooks),
                "trending_styles": len(research.trending_styles),
            },
        })
        return research

    @staticmethod
    def _is_resume(session: ContentSession) -> bool:
        return bool(getattr(session, "resume", False) and getattr(session, "conversation_id", None))

    def _research_model_name(self) -> ModelName | str:
        """The cheaper sibling's *name* for the enrichment pass, or the run's."""
        names = resolve_fallback_models(Engine.V1, self.provider, self.model)
        return names[0] if names else self.model

    @staticmethod
    async def _load_project_step(project_id: UUID, emit: EmitFn) -> ContentBrandContext:
        await emit({
            "event": ContentEvent.STEP_STARTED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label": STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.RUNNING,
        })
        brand = await asyncio.to_thread(_load_brand_context, project_id)
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label": STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.SUCCESS,
            "payload": {"project_name": brand.project_name, "pillars": len(brand.pillars)},
        })
        return brand

    # -----------------------------------------------------------------------
    # The session loop
    # -----------------------------------------------------------------------

    async def _run_session(
        self,
        session: ContentSession,
        emit: EmitFn,
        *,
        system_prompt: str,
        opening_prompt: str,
        llm: Any,
        chat_idle_timeout: float,
        resume: bool,
        channel: Any = None,
    ) -> None:
        """Run the opening turn, then stay open for follow-ups until idle.

        The loop itself is the shared ``DeepSession``; what is content-shaped
        plugs in as hooks: the artifact handler branches on the payload's
        ``type``, a turn that ends with nothing persisted gets one recovery
        nudge, PIPELINE_FINISHED carries the plan or post id the workspace
        opens, and a pre-checkpoint conversation is re-primed from the DB.
        """
        session_id = session.session_id
        conversation_id = getattr(session, "conversation_id", None)
        agent = self.build_agent(
            llm=llm,
            session=session,
            session_id=session_id,
            emit=emit,
            project_id=session.project_id,
            mode=session.mode,
            channel=channel,
            remember=not getattr(session, "memory_off", False),
            system_prompt=system_prompt,
        )
        recorder = getattr(session, "recorder", None)
        is_plan = session.mode == "plan_month"

        def _artifact_produced() -> bool:
            # The canonical "deliverable persisted" signal is the writer tool
            # having stashed the id on the session. The <duct_artifact> tag
            # only drives the live preview, so a draft streamed but never
            # written still counts as "not produced".
            return (session.plan_id if is_plan else session.post_id) is not None

        async def _on_todo(todos: list) -> None:
            session.todos = todos
            await emit({"event": ContentEvent.TODO_UPDATE, "todos": todos})

        record_use, record_result = recorder_tool_hooks(recorder)

        # The task tool's result does not repeat which sub-agent ran, so the
        # dispatch order is kept and closed FIFO — parallel dispatches of the
        # same sub-agent share a chip anyway.
        dispatched: deque[str] = deque()

        async def _on_tool_use(name: str, tool_input: Any, tool_use_id: str) -> None:
            await record_use(name, tool_input, tool_use_id)
            if name != TASK_TOOL:
                return
            args = tool_input if isinstance(tool_input, dict) else {}
            sub = str(args.get(TASK_SUBAGENT_ARG) or "unknown")
            dispatched.append(sub)
            await emit({
                "event": ContentEvent.STEP_STARTED,
                "session_id": session_id,
                "step_id": f"{ContentStep.DISPATCH_SUBAGENT.value}:{sub}",
                "label": f"Sub-agent · {sub}",
                "summary": str(args.get("description") or "")[:_SUMMARY_CHARS],
                "status": StepStatus.RUNNING,
            })

        async def _on_tool_result(name: str, result: Any, tool_use_id: str, is_error: bool) -> None:
            await record_result(name, result, tool_use_id, is_error)
            if name != TASK_TOOL or not dispatched:
                return
            sub = dispatched.popleft()
            text = result if isinstance(result, str) else str(result)
            await emit({
                "event": ContentEvent.STEP_FINISHED,
                "session_id": session_id,
                "step_id": f"{ContentStep.DISPATCH_SUBAGENT.value}:{sub}",
                "label": f"Sub-agent · {sub}",
                "summary": text[:_RESULT_CHARS],
                "status": StepStatus.ERROR if is_error else StepStatus.SUCCESS,
            })

        async def _on_artifact(raw: str, turn_text: str) -> None:
            await _publish_artifact(raw, emit, session_id)

        def _finish_payload() -> dict:
            """PIPELINE_FINISHED carries the id the workspace opens — None when
            the opening run persisted nothing, never a hollow success."""
            artifact_id = session.plan_id if is_plan else session.post_id
            return {
                "session_id": session_id,
                "mode": session.mode,
                ("plan_id" if is_plan else "post_id"): str(artifact_id) if artifact_id else None,
                **({"resumed": True} if resume else {}),
            }

        nudged = False

        async def _nudge_if_empty(pauses: list[dict]) -> list[dict]:
            """A turn ended with nothing persisted: one nudge to save, then the
            user takes over. Never on a resume — there the thread already holds
            whatever it holds."""
            nonlocal nudged
            if pauses or nudged or resume or _artifact_produced():
                return pauses
            nudged = True
            logger.warning(
                "content: turn ended with no %s persisted for session %s — sending one recovery nudge",
                "plan" if is_plan else "post", session_id,
            )
            pauses = await loop.turn(RECOVERY_NUDGE_PLAN if is_plan else RECOVERY_NUDGE_POST)
            if not pauses and not _artifact_produced():
                logger.error("content: session %s still has no %s after the nudge", session_id, "plan" if is_plan else "post")
            return pauses

        async def _reprime_if_no_checkpoint(snapshot: Any) -> None:
            """A conversation recorded before the thread was durable: the
            transcript is in the DB and nowhere else, so its summary rides on
            the user's first message (routes/agents.py prepends it)."""
            values = getattr(snapshot, "values", None) or {}
            if values.get("messages"):
                return
            from agents.content.persistence import build_reprime_context

            session.resume_primer = await build_reprime_context(
                session, self._api_key, provider=self.provider, model=self.model
            )
            session.needs_reprime = True

        loop = DeepSession(
            agent,
            session=session,
            emit=emit,
            thread_id=str(conversation_id or session_id),
            limits=LIMITS,
            provider=self.provider,
            model=self.model,
            log_prefix="content-v1",
            summariser=self._summariser_model(llm),
            on_artifact_close=_on_artifact,
            on_todo=_on_todo,
            on_tool_use=_on_tool_use,
            on_tool_result=_on_tool_result,
            finish_payload=_finish_payload,
            after_turn=_nudge_if_empty,
            on_resume=_reprime_if_no_checkpoint,
        )
        await loop.run(opening_prompt, resume=resume, chat_idle_timeout=chat_idle_timeout)

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
        means a run was cut before it ended, ``idle`` is a thread waiting for
        its next message. Built on a placeholder model and no session — the
        checkpoint is read, not extended.
        """
        agent = self.build_agent(llm=inspection_chat_model(), remember=False, interactive=False)
        return await inspect_thread(agent, str(conversation_id), self.model)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drop(_body: dict) -> None:
    return None


async def _publish_artifact(raw: str, emit: EmitFn, session_id: str) -> dict | None:
    """A closing </duct_artifact>: parse it and emit the matching preview event.

    Validation failures are logged but do NOT raise — the writer tool
    re-validates and surfaces a clear error to the model on the next call,
    which is the right place for retry logic to live. Returns the payload it
    emitted, or None.
    """
    payload = parse_artifact_json(raw)
    if payload is None:
        logger.warning("content: <duct_artifact> JSON parse failed; nothing emitted")
        return None
    kind = payload.get("type", "")
    if kind == ARTIFACT_PLAN:
        try:
            PlanDraft.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - the writer re-validates
            logger.warning("content: PlanDraft validation failed (writer will re-validate): %s", exc)
        event = ContentEvent.PLAN_GENERATED
    elif kind == ARTIFACT_POST:
        try:
            PostDraft.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - the writer re-validates
            logger.warning("content: PostDraft validation failed (writer will re-validate): %s", exc)
        event = ContentEvent.POST_DRAFT_UPDATED
    else:
        logger.warning("content: <duct_artifact> missing 'type' discriminator (got %r); no event emitted", kind)
        return None
    await emit({"event": event, "session_id": session_id, "payload": payload, "source": "duct_artifact"})
    return payload


__all__ = [
    "ContentRunner",
    "ContentTool",
    "close_session",
    "create_draft_session",
    "create_plan_session",
    "get_session",
]
