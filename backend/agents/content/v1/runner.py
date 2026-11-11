"""ContentRunner — the Content Studio session on ``deepagents`` (V1).

The port of ``agents/content/v3/runner.py``, which ran the same product on the
Claude Agent SDK. Everything the SDK did for free has a named counterpart
here, and the frontend cannot tell which served a run:

* **Sub-agents.** ``research_pillar`` and ``draft_post`` are ``SubAgent``
  specs dispatched through the harness's ``task`` tool. Their dispatch is
  surfaced as ``dispatch_subagent:<name>`` steps from the tool traffic in the
  stream, the same chips the SDK's ``Agent`` hooks produced.
* **The open web.** ``WebFetch`` and ``WebSearch`` are Duct's own tools
  (``agents/core/web_tools``); Anthropic's built-in search rides along there
  because it is the one that survives a tool-calling loop.
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
import base64
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from agents.content.artifacts import (
    ARTIFACT_PLAN,
    ARTIFACT_POST,
    RECOVERY_NUDGE_PLAN,
    RECOVERY_NUDGE_POST,
    RECOVERY_NUDGE_REVIEW,
    parse_artifact_json,
)
from agents.content.events import STEP_LABELS, ContentEvent, ContentStep, StepStatus
from agents.content.channel_config import linked_pairs, load_channel_config
from agents.content.publishing import linked_accounts
from agents.content.channel_mix import ChannelMix, goal_from, load_channel_mix
from agents.content.plan_period import MAX_PLAN_DAYS, PlanPeriod, default_period, plan_end
from agents.content.voice_rules import voice_rules_of, writing_samples_of
from agents.core.events import run_context
from agents.content.feed import render_digest
from agents.content.plan_review import load_plan_review, render_plan_review
from agents.content.voice_rules import render_voice_stanza
from agents.content.prompts import (
    _research_stanza,
    build_clone_user_prompt,
    build_orchestrator_system_prompt,
    build_feed_plan_prompt,
    build_plan_review_prompt,
    build_plan_user_prompt,
    build_post_revise_prompt,
    build_post_user_prompt,
    build_reference_diagnosis_prompt,
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
    ReferenceDiagnosis,
    RunMode,
    make_session,
)
from agents.content.discover import build_discover_tool_lc
from agents.content.subagents import (
    DRAFT_POST_TOOLS,
    GENERAL_PURPOSE_TOOLS,
    RESEARCH_PILLAR_TOOLS,
    REVIEW_POST_TOOLS,
    build_draft_post_subagent,
    build_general_purpose_subagent,
    build_research_pillar_subagent,
    build_review_post_subagent,
)
from agents.content.tools import build_content_tools_lc
from agents.core import session as _core_session
from agents.core.activity import activity_hooks, announce_context
from agents.core.connector_tools import build_connector_tools_lc
from agents.core.deep_session import (
    subagent_middleware,
    DeepSession,
    RunLimits,
    build_deep_session_agent,
    fallback_chain,
    inspect_thread,
    recorder_tool_hooks,
    subagent_step_hooks,
)
from agents.core.lc import (
    UsageTracker,
    bind_tool_lc,
    build_ask_user_tool,
    inspection_chat_model,
    interrupt_pause,
    resolve_chat_model,
    structured_output,
)
from agents.core.mcp_tools import build_mcp_tools_lc
from agents.core.quota import credential_identity
from agents.core.turn import TurnContext, build_turn, spec_for
from agents.core.session import register_session
from agents.core.web_tools import WEB_FETCH_TOOL, build_web_tools_lc
from agents.insights.data_tools import build_data_tools_lc
from agents.engines import Engine, resolve_fallback_models
from agents.models import ModelName, Provider, run_model_fields
from agents.registry import AgentType
from utils.dates import utcnow

if TYPE_CHECKING:
    from service.clone_reference import CloneReference, TikTokPost

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

# Clips per turn. A clip costs dollars where a model call costs cents (an 8 s
# Veo 3.1 clip is $3.20), and the prompt asks for one at a time; this is the
# guard for when a loop forgets. Issue #284's spec sets it at three.
VIDEO_CLIPS_PER_RUN = 3

LIMITS = RunLimits(
    model_calls_per_run=MODEL_CALLS_PER_RUN,
    model_calls_per_thread=MODEL_CALLS_PER_THREAD,
    tool_calls_per_run=TOOL_CALLS_PER_RUN,
    tool_calls_per_thread=TOOL_CALLS_PER_THREAD,
    tool_result_prune_trigger=TOOL_RESULT_PRUNE_TRIGGER,
    tool_results_kept=TOOL_RESULTS_KEPT,
    per_tool_run_limits=((ContentTool.GENERATE_VIDEO.value, VIDEO_CLIPS_PER_RUN),),
)

# How long a session waits for a follow-up before closing itself. Matches
# audit and insights; the route's own inactivity pruner is the longer backstop.
CHAT_IDLE_TIMEOUT = 1800.0

# Providers whose API accepts image blocks inside a tool result. The image
# phase is built on the model looking at what it generated; elsewhere the
# tools return the asset URL and the prompt says so.
VISION_PROVIDERS = frozenset({Provider.ANTHROPIC})

ASK_USER_DESCRIPTION = (
    "Ask the user up to 3 questions when their answer would materially change "
    "the plan or the post: the direction after a review (two to four options in "
    "their words, each a label of two to five words with one short clause under "
    "it), a missing brand voice, an audience you cannot "
    "infer, which of two tools or directions they want. Ask early, and never ask "
    "for something already in the brand context or the project memory."
)

RESEARCH_TOOL = "research_trends"
RESEARCH_TOOL_DESCRIPTION = (
    "Run the research pass: what is working right now for the brand's audience on the "
    "channels it posts on (sounds, hashtags and search terms, hooks, formats and recent "
    "platform rule changes, named competitors' cadence and hooks, seasonal dates inside "
    "the period), dated and sourced. `focus` is the direction the person gave, in one "
    "sentence. One call per plan, or per post when the person wants a new concept rather "
    "than an edit; the result is the <content_research> block to work from, or a sentence "
    "saying nothing came back, in which case work from the account's own numbers and say so."
)

# Cap on what a step chip shows of a stage's detail.
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
# A plan proposal that outlived its session
# ---------------------------------------------------------------------------


def _held_proposal_sync(session: ContentSession):
    from sqlmodel import Session

    from agents.content.plan_proposal import held_proposal
    from db.session import get_engine

    engine = get_engine()
    if engine is None:
        return None
    with Session(engine) as db:
        return held_proposal(db, getattr(session, "conversation_id", None))


async def _restore_proposal(session: ContentSession, emit: EmitFn) -> None:
    """Show a resumed plan session the proposal its conversation still holds,
    with Accept, Modify and Reject, as the session that made it did
    (agents/content/plan_proposal.py). Only one made against the plan this
    session manages: a proposal for another plan, or a new plan for a period
    that has one since, would write over the wrong thing. ``replay``, because
    it is the same proposal, not a second one."""
    from agents.content.plan_proposal import PROPOSED

    if getattr(session, "proposal", None) is not None:
        return
    try:
        held = await asyncio.to_thread(_held_proposal_sync, session)
    except Exception:
        logger.warning("content: held proposal not read for session %s", session.session_id, exc_info=True)
        return
    if held is None or held.project_id != session.project_id or held.replaces_plan_id != session.plan_id:
        return
    session.proposal = held
    await emit({
        "event": ContentEvent.PLAN_GENERATED,
        "session_id": session.session_id,
        "plan_id": str(held.replaces_plan_id) if held.replaces_plan_id else None,
        "payload": held.payload(PROPOSED),
        "replay": True,
    })


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
        channel_config = load_channel_config(channels_blob, linked_pairs(linked_accounts(db, proj.id)))
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
            active_channels=channel_config.enabled(),
            channel_profiles=channel_config.profiles(),
            writing_samples=writing_samples_of(brand_blob),
            voice_rules=voice_rules_of(brand_blob),
        )


def _load_business_block(project_id: UUID) -> str:
    """The project's business context as the shared ``<business_context>``
    block: goals, positioning, competitors, growth stage. Insights and audit
    had it from day one; the plan turn never did, so the plan served a
    north-star it had only ever met as a memory chip. The mapping is
    ``agents/core/context.business_context_from_project``, shared with the
    report and the scheduled brief."""
    from sqlmodel import Session

    from agents.core.context import business_context_from_project, format_business_context
    from db.session import get_engine
    from models.project import Project

    engine = get_engine()
    if engine is None:
        return ""
    with Session(engine) as db:
        proj = db.get(Project, project_id)
        if proj is None:
            return ""
        return format_business_context(business_context_from_project(proj))


def _competitor_names(competition: dict | None) -> list[str]:
    """The shared reading of the competition blob, capped: a research pass
    over more than six competitors is a research project."""
    from agents.core.context import competitor_names

    return competitor_names(competition)[:6]


def _project_competitors(project_id: UUID) -> list[str]:
    from sqlmodel import Session

    from db.session import get_engine
    from models.project import Project

    engine = get_engine()
    if engine is None:
        return []
    with Session(engine) as db:
        proj = db.get(Project, project_id)
        return _competitor_names(proj.competition if proj and isinstance(proj.competition, dict) else {})


async def _safely(awaitable: Any, default: Any, what: str) -> Any:
    """A context block that could not be read is a block that says so, not
    a plan that never opens."""
    try:
        return await awaitable
    except Exception:  # noqa: BLE001 — a signal for the plan, never a blocker
        logger.warning("content: %s unavailable", what, exc_info=True)
        return default


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



def _voice_block(user_id) -> str:
    """The operator's ``<user_context>``, or '' when they never set a profile.

    Best-effort like every other profile read: a content session is worth
    having without it, and a settings row is not worth failing a run over.
    """
    from agents.core.voice import user_context_block
    from service.profile import get_profile

    try:
        return user_context_block(get_profile(user_id))
    except Exception:  # noqa: BLE001 — a preference, never a blocker
        logger.warning("content: profile unavailable", exc_info=True)
        return ""


def _resolve_plan_period(
    session: ContentSession, requested: PlanPeriod | None, today: date,
) -> list[dict] | None:
    """Decide which plan this run manages and fix its dates on the session.
    Returns the plan's days when the run manages a plan that already exists,
    None when it is about to make one.

    One plan per period: a run is bound to the plan it was opened on, else to
    the plan already covering the first date of its period (the month in
    progress, or the period the person picked), and only makes a new plan
    when none does. A bound run keeps that plan's own dates; revising never
    moves them. A new plan stops short of the next plan already made, so two
    plans never claim the same date. The app resolves the same plan before it
    opens the session (content/sessions/new), so the pane shows the plan the
    agent is managing.
    """
    from sqlmodel import Session, select

    from db.session import get_engine
    from models.content import ContentPlan

    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as db:
        row = db.get(ContentPlan, session.plan_id) if session.plan_id else None
        if row is not None and row.project_id == session.project_id and row.days:
            plans = []
        else:
            plans = [
                p for p in db.execute(
                    select(ContentPlan)
                    .where(ContentPlan.project_id == session.project_id)
                    .order_by(ContentPlan.created_at.desc())
                ).scalars().all()
                if p.start_date and p.days
            ]
            period = requested or default_period(today)
            row = next(
                (p for p in plans if p.start_date <= period.start <= plan_end(p.start_date, len(p.days))),
                None,
            )
        if row is not None:
            session.plan_id = row.id
            session.period_start = row.start_date or today
            session.period_days = min(len(row.days), MAX_PLAN_DAYS)
            return list(row.days)
        later = [p.start_date for p in plans if p.start_date > period.start]
        period = period.stopping_before(min(later, default=None))
        session.plan_id = None
        session.period_start, session.period_days = period.start, period.days
        return None


async def _channel_mix(project_id: UUID, brand: ContentBrandContext, days: int) -> ChannelMix | None:
    """What each channel's own posts say and how many days it gets, judged on
    the brand's content goal, for the plan's opening turn.

    None when it cannot be read: the prompt then says so rather than claiming
    the account has no history, and the plan still gets made.
    """
    try:
        return await asyncio.to_thread(
            load_channel_mix, project_id, list(brand.active_channels or []), goal_from(brand.content_goal), days,
        )
    except Exception:  # noqa: BLE001 — a signal for the plan, never a blocker
        logger.warning("content: channel performance unavailable", exc_info=True)
        return None


async def _memory_block(session: ContentSession, *, query: str = "", emit: EmitFn | None = None) -> str:
    """The project's memory digest for a content run, as a user-turn block.

    Same contract as the other agents: per-project data rides in the USER
    message so the cached system prefix stays byte-identical, and a missing
    digest degrades the turn rather than failing it. What was recalled goes
    out as MEMORY_RECALLED, the "Recalled" chips under the turn — insights
    and audit said what they remembered, content read the same digest and
    said nothing.
    """
    if getattr(session, "memory_off", False):
        return ""

    def _load():
        from db.session import get_session as db_session
        from service.memory import build_memory_context

        with next(db_session()) as db:
            return build_memory_context(
                db,
                project_id=session.project_id,
                user_id=getattr(session, "user_id", None),
                agent_type=str(AgentType.TIKTOK_STUDIO),
                query=query,
                artifact_kind=None,
                conversation_id=getattr(session, "conversation_id", None),
            )

    try:
        context = await asyncio.to_thread(_load)
    except Exception:  # noqa: BLE001
        logger.warning("content: project memory unavailable", exc_info=True)
        return ""
    if context.recalled and emit is not None:
        try:
            await emit({
                "event": ContentEvent.MEMORY_RECALLED,
                "memories": [{k: v for k, v in entry.items() if k != "uuid"} for entry in context.recalled],
            })
        except Exception:  # noqa: BLE001
            logger.debug("content: MEMORY_RECALLED emit failed", exc_info=True)
    return context.text


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
        # One conversation, one prompt cache, as insights does: every call of
        # this thread carries the same key, the fallback's included.
        cache_key = str(getattr(session, "conversation_id", None) or session_id or "")
        if llm is None:
            llm = resolve_chat_model(
                self.provider, self.model, self._api_key, self._temperature,
                thinking=self._thinking, cache_key=cache_key,
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
                project_id, emit, session, vision=self.vision, remember=remember,
                # Publishing asks first; only a run with someone to ask can send.
                pause=interrupt_pause if interactive else None,
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
            # Every sub-agent gets the loop's guards: run limits and the
            # reporting retry, on the same credential identity as the parent.
            guards = subagent_middleware(
                LIMITS,
                identity="" if injected_llm else credential_identity(self._api_key),
                provider=None if injected_llm else self.provider,
            )
            subagents = [
                build_research_pillar_subagent(
                    _pick(RESEARCH_PILLAR_TOOLS), self._sibling_model(llm, injected_llm, cache_key), middleware=guards
                ),
                build_draft_post_subagent(_pick(DRAFT_POST_TOOLS), llm, middleware=guards),
                # Judging, like drafting, stays on the run's model.
                build_review_post_subagent(_pick(REVIEW_POST_TOOLS), llm, middleware=guards),
                # deepagents adds a "general-purpose" sub-agent carrying EVERY
                # tool of the parent unless one by that name is supplied. That
                # would hand the writers to a sub-agent; this one reads only.
                build_general_purpose_subagent(_pick(GENERAL_PURPOSE_TOOLS), llm, middleware=guards),
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
            # The tools the session's user connected over MCP, the same two
            # fixed tools insights mounts (agents/core/mcp_tools.py): nothing
            # when they connected none, so most sessions keep their prefix.
            # Content had none until 2026-11-08, so a connected SEO or
            # analytics tool was invisible to the agent planning the content.
            user_id = getattr(session, "user_id", None)
            tools += build_mcp_tools_lc(user_id, pause=interrupt_pause, log_prefix="content-v1")
            # The project's own data, the reach the insights agent has: which
            # sources are connected, a pull from one, and the notes on reading
            # it. A plan built on what people search for, or a post judged on
            # the visits it sent, needs the numbers the content tables do not
            # hold. The same binders and the same credential path as insights.
            tools += build_connector_tools_lc(
                project_id,
                user_id=user_id,
                session=session,
                session_id=session_id,
                emit=emit,
                log_prefix="content-v1",
                pause=interrupt_pause,
            )
            tools += build_data_tools_lc(project_id, user_id=user_id, log_prefix="content-v1")
            # Both modes: a post the person wants re-thought needs the same
            # research a plan gets, and until 2026-11-11 only the planner had it.
            tools.append(self._build_research_tool(session, emit, llm if injected_llm else None))
            if project_id is not None:
                tools.append(build_discover_tool_lc(project_id, pause=interrupt_pause))
        elif session is not None and getattr(session, "unattended", False):
            # A scheduled run (#563) keeps what needs nobody's yes: a trusted
            # preset's read-only MCP tools (a Linear or Notion read can feed a
            # plan from shipped work). Every other server, and every tool that
            # would show an approval card, stays off.
            tools += build_mcp_tools_lc(
                getattr(session, "user_id", None), log_prefix="content-v1", trusted_only=True,
            )

        # One same-provider step down keeps a run alive on the key the caller
        # supplied. Skipped with an injected model — that seam is for tests.
        fallbacks: list[Any] = []
        if not injected_llm:
            fallbacks = fallback_chain(
                self.provider, self.model, self._api_key, self._temperature,
                thinking=self._thinking, cache_key=cache_key,
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
            # Same condition as the fallback chain, for the same reason: a
            # caller that handed us its own model handed us no credential, so
            # there is nobody to cool down when the provider says no.
            identity="" if injected_llm else credential_identity(self._api_key),
            provider=None if injected_llm else self.provider,
            # The image tools return pictures on a vision provider; the bytes
            # must not follow the thread into every later checkpoint.
            prune_seen_images=self.vision,
        )

    def _sibling_model(self, llm: Any, injected: bool, cache_key: str = "") -> Any:
        """The cheaper model in this family, for volume work; the run's own
        model when the family has none — or when a test injected one. Same
        ``cache_key`` as the run: the sub-agents' calls belong to the same
        conversation and OpenAI routes by it."""
        if injected:
            return llm
        names = resolve_fallback_models(Engine.V1, self.provider, self.model)
        if not names:
            return llm
        return resolve_chat_model(
            self.provider, names[0], self._api_key, self._temperature,
            thinking=self._thinking, cache_key=cache_key,
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
        period: PlanPeriod | None = None,
        feed: Any = None,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        llm: Any = None,
    ) -> None:
        """Run a plan_month session end-to-end: load, enrich, plan, then chat.

        With ``feed`` (feed.FeedOptions) the plan is from shipped work
        (#561): the repository and Duct's record are read and filtered
        before the model starts, and a window with nothing worth a post ends
        the run there, with no model call.

        A session bound to an existing plan (opened from "Revise plan") is the
        plan manager for that plan: it keeps the plan's dates, and on a fresh
        conversation it opens by asking what to change instead of researching
        and writing a whole new month."""
        session = get_session(session_id) or create_plan_session(session_id, project_id)
        try:
            bound_days = await asyncio.to_thread(_resolve_plan_period, session, period, utcnow().date())
        except Exception:  # noqa: BLE001 — without a period the plan is still made, just unchecked
            logger.warning("content: plan period unavailable for session %s", session_id, exc_info=True)
            bound_days = None
        managed = (
            PlanPeriod(session.period_start, session.period_days)
            if session.period_start and session.period_days
            else None
        )

        async def _opening(brand: ContentBrandContext) -> str:
            # What the plan turn reads, each piece on its own thread and each
            # allowed to be missing: the plan never waits on a block it can
            # say it lacked.
            session.active_channels = list(brand.active_channels or [])
            today = utcnow().date()
            performance = await _channel_mix(project_id, brand, (managed or default_period(today)).days)
            session.channel_mix = performance
            business = await _safely(asyncio.to_thread(_load_business_block, project_id), "", "business context")
            voice = render_voice_stanza(brand.voice_rules, brand.writing_samples, with_rules=False)
            review = await _safely(
                asyncio.to_thread(load_plan_review, project_id, today=today, period=managed),
                None, "plan review",
            )
            review_block = render_plan_review(review)
            if feed is not None:
                digest = await self._read_work_step(session, feed, emit, today=today)
                session.feed = digest
                if not digest.worth_a_plan:
                    return None
                return build_feed_plan_prompt(
                    brand, feed=render_digest(digest), max_days=feed.max_days, performance=performance,
                    period=managed, business=business, voice=voice, current_days=bound_days,
                    unattended=getattr(session, "unattended", False),
                )
            if bound_days is not None or (review is not None and review.has_history):
                # Something to review: the opening turn is the review and the
                # direction question. The plan comes after the answer, and the
                # research pass is a tool the agent calls then.
                session.review_opening = True
                return build_plan_review_prompt(
                    brand, review=review_block, performance=performance, period=managed,
                    business=business, voice=voice, current_days=bound_days,
                )
            return build_plan_user_prompt(
                brand, history=[], formats=[], avatars=[], research=None, performance=performance,
                period=managed, review=review_block, business=business, voice=voice,
            )

        await self._run_mode(
            session, emit,
            opening=_opening,
            memory_query="content plan performance",
            llm=llm,
            chat_idle_timeout=chat_idle_timeout,
        )

    @staticmethod
    async def _read_work_step(session: ContentSession, options: Any, emit: EmitFn, *, today: date) -> Any:
        """What shipped, read and filtered as a visible step. Its payload is
        the card the app draws: the chips, what was left out, and whether it
        is worth a plan. Both reads are sync (a connector call, a DB query)
        and run off the loop so the stream stays live."""
        from sqlmodel import Session, select

        from agents.content.feed import (
            GITHUB_ENTITY, FeedSource, build_digest, duct_items, feed_window, github_note, planned_refs,
        )
        from agents.insights.fetchers import fetch_entity
        from db.session import get_engine
        from models.content import ContentPlan

        label = STEP_LABELS[ContentStep.READ_WORK]
        await emit({
            "event": ContentEvent.STEP_STARTED,
            "step_id": ContentStep.READ_WORK,
            "label": label,
            "status": StepStatus.RUNNING,
        })
        project_id = session.project_id
        user_id = getattr(session, "user_id", None)

        def _plans() -> list:
            with Session(get_engine()) as db:
                return list(db.execute(
                    select(ContentPlan).where(ContentPlan.project_id == project_id)
                ).scalars().all())

        plans = await asyncio.to_thread(_plans)
        window = feed_window(options, plans, today=today)
        already = planned_refs(plans)
        rows, note = None, ""
        if FeedSource.GITHUB in options.sources:
            # A connector read is on someone's credentials; a run with no
            # user (a legacy stream route) reads Duct's record alone.
            fetched = await asyncio.to_thread(
                fetch_entity, GITHUB_ENTITY, user_id=user_id, project_id=project_id,
                date_from=window[0].isoformat(), date_to=window[1].isoformat(),
            ) if user_id is not None else {"status": "not_connected", "message": "No signed-in user."}
            rows, note = github_note(fetched)

        def _duct() -> list:
            with Session(get_engine()) as db:
                return duct_items(db, project_id, window[0], window[1], already=already)

        duct = await asyncio.to_thread(_duct) if FeedSource.DUCT in options.sources else None
        digest = build_digest(options, window, github_rows=rows, github_note_text=note, duct=duct, already=already)
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.READ_WORK,
            "label": label,
            "status": StepStatus.SUCCESS,
            "payload": digest.payload(),
        })
        return digest

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
        existing_post_id: UUID | None = None,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        llm: Any = None,
    ) -> None:
        """Run a draft_post session end-to-end: load, write, then chat.

        ``existing_post_id`` is the post a plan day already holds. With it, or
        with a session already bound to a post (opened from the post page),
        the opening turn reviews the saved post and asks, instead of drafting
        over it."""
        from agents.content.channels import resolve as resolve_channel

        session = get_session(session_id) or create_draft_session(session_id, project_id)
        ch = resolve_channel(channel)  # sync, no DB — safe before the first emit
        session.channel = ch.id
        if existing_post_id is not None:
            session.post_id = existing_post_id
        revising = session.post_id is not None

        async def _opening(brand: ContentBrandContext) -> str:
            if revising:
                return build_post_revise_prompt(brand, day, channel=ch)
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

    async def run_clone(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        clone_url: str,
        channel: str | None = None,
        chat_idle_timeout: float = CHAT_IDLE_TIMEOUT,
        llm: Any = None,
    ) -> None:
        """A draft_post session modelled on a TikTok post (issue #222).

        Not a mode of its own: the deliverable, the tools and the system
        prompt are draft_post's, so a clone shares its cached prefix and a
        resumed clone is an ordinary post conversation. What differs is the
        opening turn — the reference, why it worked, and the clone discipline,
        all in the USER turn — and the link to the reference the session
        carries for submit_post_draft to record.
        """
        from agents.content.channels import resolve as resolve_channel
        from service.clone_reference import parse_tiktok_post_url

        session = get_session(session_id) or create_draft_session(session_id, project_id)
        ch = resolve_channel(channel)
        # A clone is a photo carousel by definition (CLONE_DISCIPLINE), so it
        # drafts on the visual playbook whatever slot it fills.
        if ch.text_first:
            ch = resolve_channel(None)
        post_ref = parse_tiktok_post_url(clone_url)  # canonical already; parsed again, never trusted

        async def _opening(brand: ContentBrandContext) -> str:
            from service.clone_reference import engagement_prior

            reference = await self._reference_step(project_id, post_ref, emit)
            prior = engagement_prior(reference.post)
            diagnosis = await self._diagnose_step(reference, prior, emit, llm)
            # The URL is the one rebuilt from the parsed link, never the saved
            # row's: a reference saved through Discover carries whatever URL
            # the browser sent, and this one ends up as a link on a page.
            session.clone_reference = {
                "reference_asset_id": str(reference.asset_id),
                "url": post_ref.url,
                "author": reference.author or post_ref.handle,
                "why_it_worked": diagnosis.why_it_worked.strip() if diagnosis else "",
            }
            return build_clone_user_prompt(
                brand,
                url=post_ref.url,
                post=reference.post,
                prior=prior,
                diagnosis=diagnosis,
                channel=ch,
            )

        await self._run_mode(
            session, emit,
            opening=_opening,
            memory_query="",
            channel=ch,
            started={"channel": ch.id, "channel_label": ch.label, "channel_supported": ch.supported},
            llm=llm,
            chat_idle_timeout=chat_idle_timeout,
        )

    async def _reference_step(self, project_id: UUID, post_ref: TikTokPost, emit: EmitFn) -> CloneReference:
        """The saved reference for a clone, as a visible step.

        A reference that cannot be read ends the run: there is nothing to
        model. The step is closed as failed first, so the ladder does not
        spin above the failure; ``ReferenceUnavailable`` then reaches the
        browser as ``reference_unavailable``.
        """
        from service.clone_reference import resolve_clone_reference

        label = STEP_LABELS[ContentStep.READ_REFERENCE]
        await emit({
            "event": ContentEvent.STEP_STARTED,
            "step_id": ContentStep.READ_REFERENCE,
            "label": label,
            "status": StepStatus.RUNNING,
        })
        try:
            reference = await resolve_clone_reference(project_id, post_ref)
        except Exception:  # noqa: BLE001 — re-raised; only the step is closed here
            await emit({
                "event": ContentEvent.STEP_FINISHED,
                "step_id": ContentStep.READ_REFERENCE,
                "label": label,
                "status": StepStatus.ERROR,
            })
            raise
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.READ_REFERENCE,
            "label": label,
            "status": StepStatus.SUCCESS,
            "payload": {
                "author": reference.author,
                "slides": len(reference.slide_urls),
                "saved_before": reference.reused,
            },
        })
        return reference

    async def _diagnose_step(
        self, reference: CloneReference, prior: dict, emit: EmitFn, llm: Any
    ) -> ReferenceDiagnosis | None:
        """Why the reference worked, read by this run's own model.

        One structured call outside the session's thread, so the slides it
        looks at are never written into a checkpoint. The pictures ride along
        only on a provider that takes them (``VISION_PROVIDERS``); elsewhere
        the model reads the caption and the counts. None when the call fails:
        the clone still runs, and its turn says the reading is inferred.
        """
        from service.clone_reference import reference_images

        label = STEP_LABELS[ContentStep.DIAGNOSE_REFERENCE]
        await emit({
            "event": ContentEvent.STEP_STARTED,
            "step_id": ContentStep.DIAGNOSE_REFERENCE,
            "label": label,
            "status": StepStatus.RUNNING,
        })
        images = await asyncio.to_thread(reference_images, reference) if self.vision else []
        text = build_reference_diagnosis_prompt(reference.post, prior, images=len(images))
        content: Any = text if not images else [
            {"type": "text", "text": text},
            *({"type": "image", "base64": base64.b64encode(data).decode("ascii"), "mime_type": mime}
              for data, mime in images),
        ]
        diagnosis, raw = await diagnose_reference(self._summariser_model(llm), content)
        # Billed like any other call on the user's key, but never the gauge:
        # this call's context (the slides) is not the thread's.
        tracker = UsageTracker(self.model)
        if usage := tracker.feed(raw, None) or tracker.flush():
            await emit({**usage, "scope": "subagent"})
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.DIAGNOSE_REFERENCE,
            "label": label,
            "status": StepStatus.SUCCESS,
            # The model's own sentence, like the chat it precedes; nothing
            # here is interface copy.
            "summary": (diagnosis.why_it_worked if diagnosis else "")[:_STEP_SUMMARY_CHARS],
            "payload": {"read": diagnosis is not None, "images": len(images)},
        })
        return diagnosis

    async def _run_mode(
        self,
        session: ContentSession,
        emit: EmitFn,
        *,
        opening: Callable[[ContentBrandContext], Awaitable[str | None]],
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
                **run_model_fields(self.provider, self.model),
                **(started or {}),
            })
            brand = await self._load_project_step(session.project_id, emit)
            opening_prompt = await opening(brand)
            if opening_prompt is None:
                # The opening decided there is nothing for a model to do (a
                # plan from shipped work with nothing new): the run ends here,
                # and the step it just finished says why.
                await emit({
                    "event": ContentEvent.PIPELINE_FINISHED,
                    "status": StepStatus.SUCCESS,
                    "session_id": session.session_id,
                    "outcome": "nothing_new",
                })
                return
            # Who is being written for, and in which language. In the opening
            # turn rather than the system prompt: the orchestrator prompt is
            # shared across this account's sessions and per-user text in it
            # would cost the cached prefix on every call.
            #
            # Ordered by agents/core/turn.py rather than by hand. The hand
            # version put the memory digest *after* the ask, which is the one
            # place it cannot be cached from: memory moves between runs, so
            # everything before it is what a later run can reuse, and there was
            # nothing before it.
            ctx = TurnContext()
            ctx.set("user_context", await asyncio.to_thread(
                _voice_block, getattr(session, "user_id", None)
            ))
            ctx.set("project_memory", await _memory_block(session, query=memory_query, emit=emit))
            context_blocks = {
                "user_context": ctx.get("user_context"),
                "project_memory": ctx.get("project_memory"),
                "brand": brand.project_name,
            }
            opening_prompt = build_turn(
                spec=spec_for(AgentType.TIKTOK_STUDIO),
                context=ctx,
                request=opening_prompt,
                # Content's opening turn is a composed instruction, not the
                # user's words. Ordering it is the win here; retagging it would
                # be a prompt change this agent has no eval to catch.
                wrap_request=False,
            )
        else:
            brand = await asyncio.to_thread(_load_brand_context, session.project_id)
            opening_prompt = ""
            context_blocks = {"brand": brand.project_name}

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
            context_blocks=context_blocks,
        )

    def _build_research_tool(self, session: ContentSession, emit: EmitFn, llm: Any) -> Any:
        """``research_trends``: the research pass as a tool the agent calls
        once it knows the direction, instead of a pre-flight step that ran
        before the first word and could not know what the person wanted."""
        from pydantic import BaseModel, Field

        class ResearchArgs(BaseModel):
            focus: str = Field("", description="The direction the person gave, in one sentence; empty to scout broadly.")

        async def research_trends(focus: str = "") -> str:
            brand = await asyncio.to_thread(_load_brand_context, session.project_id)
            research = await self._enrich_step(brand, emit, llm, session, focus=focus)
            block = _research_stanza(research)
            return block or (
                "No trend research came back this run. Work from the account's own numbers and say so."
            )

        return bind_tool_lc(
            research_trends, name=RESEARCH_TOOL, description=RESEARCH_TOOL_DESCRIPTION, args_schema=ResearchArgs
        )

    async def _enrich_step(
        self, brand: ContentBrandContext, emit: EmitFn, llm: Any,
        session: ContentSession | None = None,
        *,
        focus: str = "",
    ) -> Any:
        """The research pass, as a visible step, called by the ``research_trends``
        tool once the person has given a direction (a plan, or a post's new concept)."""
        from agents.content.enrichment import enrich_content_context

        period = ""
        if session is not None and session.period_start and session.period_days:
            period = PlanPeriod(session.period_start, session.period_days).label()
        competitors = await _safely(
            asyncio.to_thread(_project_competitors, session.project_id if session else brand.project_id),
            [], "competitors",
        )
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
            focus=focus,
            period=period,
            competitors=competitors,
        )
        await emit({
            "event": ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.ENRICHING,
            "label": STEP_LABELS[ContentStep.ENRICHING],
            "status": StepStatus.SUCCESS,
            # Local signals only is still a finished step; the note says why
            # the trend counts are zero, so a dead research model does not
            # read as a quiet week.
            "summary": research.degraded_reason[:_STEP_SUMMARY_CHARS],
            "payload": {
                "pillar_history": len(research.pillar_history),
                "trending_sounds": len(research.trending_sounds),
                "trending_hashtags": len(research.trending_hashtags),
                "trending_hooks": len(research.trending_hooks),
                "trending_styles": len(research.trending_styles),
                "competitors": len(research.competitor_notes),
                "seasonal_hooks": len(research.seasonal_hooks),
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
        context_blocks: dict[str, Any] | None = None,
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
            # A scheduled run has nobody to ask: no question card, no
            # approval-carded tool, and the opening turn says so.
            interactive=not getattr(session, "unattended", False),
            system_prompt=system_prompt,
        )
        recorder = getattr(session, "recorder", None)
        is_plan = session.mode == "plan_month"
        # The CONTEXT row a review replays against, and the reader's notice
        # that the turn was enriched — the same call the other runners make.
        await announce_context(
            recorder,
            emit,
            run_context(
                agent_type=str(AgentType.TIKTOK_STUDIO),
                provider=self.provider,
                model=self.model,
                thinking=self._thinking,
                system_prompt=system_prompt,
                turn=opening_prompt,
                resume=resume,
                blocks=dict(context_blocks or {}),
            ),
        )

        def _artifact_produced() -> bool:
            # The canonical "deliverable persisted" signal is the writer tool
            # having stashed the id on the session. The <duct_artifact> tag
            # only drives the live preview, so a draft streamed but never
            # written still counts as "not produced".
            if is_plan:
                return session.plan_id is not None or getattr(session, "proposal", None) is not None
            return session.post_id is not None

        async def _on_todo(todos: list) -> None:
            session.todos = todos
            await emit({"event": ContentEvent.TODO_UPDATE, "todos": todos})

        # Recorder, then the sub-agent ladder, then the transcript's activity
        # cards — one pair of hooks wrapping the last (agents/core/activity.py
        # holds the allowlist; an image the agent draws comes through here).
        _on_tool_use, _on_tool_result = activity_hooks(
            emit,
            *subagent_step_hooks(emit, *recorder_tool_hooks(recorder), session_id=session_id),
        )

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

        # One nudge per phase: the review turn may need "ask the question",
        # and the planning turn after it may still need "save the plan".
        nudged: set[str] = set()

        async def _nudge_if_empty(pauses: list[dict]) -> list[dict]:
            """A turn ended with nothing persisted: one nudge to save, then the
            user takes over. Never on a resume — there the thread already holds
            whatever it holds."""
            # A review turn is meant to end in a question, so its nudge asks
            # for the question; a plan nudge there would write the plan the
            # review exists to hold back. Whatever this turn did, the next one
            # is the planning turn, so the flag goes down here.
            reviewing = is_plan and getattr(session, "review_opening", False)
            if reviewing:
                session.review_opening = False
            phase = "review" if reviewing else "deliverable"
            if pauses or phase in nudged or resume or (not reviewing and _artifact_produced()):
                return pauses
            nudged.add(phase)
            logger.warning(
                "content: turn ended with no %s for session %s — sending one recovery nudge",
                "direction question" if reviewing else ("plan" if is_plan else "post"), session_id,
            )
            pauses = await loop.turn(
                RECOVERY_NUDGE_REVIEW if reviewing else (RECOVERY_NUDGE_PLAN if is_plan else RECOVERY_NUDGE_POST)
            )
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

        async def _on_resume(snapshot: Any) -> None:
            await _reprime_if_no_checkpoint(snapshot)
            if is_plan:
                await _restore_proposal(session, emit)

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
            on_resume=_on_resume,
        )
        await loop.run(opening_prompt, resume=resume, chat_idle_timeout=chat_idle_timeout)

    def _summariser_model(self, llm: Any) -> Any:
        """The model an emergency compaction summarises with, and a clone's
        diagnosis reads with: the injected one when there is one (a test's
        fake must not fire a real call), else the runner's own."""
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


async def diagnose_reference(
    model: Any, content: str | list[dict]
) -> tuple[ReferenceDiagnosis | None, Any]:
    """One structured call: why a reference worked.

    Returns the diagnosis, None when it fails, and the provider's raw reply,
    whose usage the caller bills. ``content`` is the user message: the prompt
    alone, or the prompt followed by standard image blocks. Best-effort in the
    way the audit's draft inference is: a provider that cannot do structured
    output, or refuses an image, costs the clone its diagnosis and nothing else.
    """
    try:
        structured = structured_output(model, ReferenceDiagnosis, include_raw=True)
        answer = await structured.ainvoke([{"role": "user", "content": content}])
    except Exception:  # noqa: BLE001 — the clone runs on the caption and counts instead
        logger.warning("content: reference diagnosis failed", exc_info=True)
        return None, None
    answer = answer if isinstance(answer, dict) else {}
    parsed = answer.get("parsed")
    if answer.get("parsing_error") is not None:
        logger.warning("content: reference diagnosis unparseable: %s", answer["parsing_error"])
    return (parsed if isinstance(parsed, ReferenceDiagnosis) else None), answer.get("raw")


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
