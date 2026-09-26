"""What an insights run needs before it starts — shared by both entry points.

Insights has two doors and one agent behind them:

  * ``POST /api/agents/insights/sessions`` — a live session with a person in it.
  * ``POST /api/insights/generate`` — one unattended turn, for a scheduled
    brief, which can never block on a human.

They differ in what happens *after* the agent is assembled. Everything before
it — which model, which project (and whether the caller may see it), what that
project's autonomy is, what Duct already knows about it — is identical, and was
duplicated between the two routes until this module existed. A second copy of
the membership gate is the copy that eventually forgets to check.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from agents.core.events import AgentEvent
from agents.core.prompts import xml_block
from agents.engines import resolve_job_run, resolve_run_model
from agents.tiers import Job
from agents.models import ModelName, Provider
from agents.registry import AgentType
from db.session import get_session as db_session
from models.execution import AUTONOMY_ASK, normalize_autonomy
from models.project import Project
from service.execution.policy import effective_autonomy
from service.membership import member_role
from service.model_settings import get_model_settings
from service.memory import build_memory_context, seed_user_preferences
from service.connector_scopes import SCOPE_PARTIAL, SCOPE_UNKNOWN
from service.provider_keys import stored_keys_for

logger = logging.getLogger(__name__)


class InsightsSetupError(Exception):
    """Configuration that makes a run impossible (no API key for the provider)."""


@dataclass(frozen=True)
class InsightsRun:
    """Everything resolved before the agent is built."""

    provider: Provider
    model: ModelName | str
    api_key: str
    # The artifact summarizer runs on the Agent SDK, so only an Anthropic key
    # works there — a brief on another provider persists without a digest.
    summary_key: str
    # None unless the caller was proven to belong to the project. Everything
    # project-scoped downstream reads this, never the request.
    project_id: UUID | None
    configured_autonomy: str
    # What the run actually operates at: a model outside the allowlist runs an
    # `auto` project at `assisted`. See service/execution/policy.py.
    autonomy: str

    # The rung this run landed on, what it asked for, and what it stepped over
    # on the way. Carried so both entry points can put it on PIPELINE_STARTED
    # without resolving anything twice. Defaulted, so a caller that builds an
    # InsightsRun by hand (the tests do) is unaffected.
    tier: str = ""
    tier_requested: str = ""
    tier_skipped: tuple[tuple[str, str], ...] = ()
    tier_retry_in: float = 0.0

    # What the verifier runs on. ``Job.VERIFICATION`` sits a tier below
    # ``Job.ANALYSIS`` in the map, and until this field existed the subagent
    # silently inherited the analyst's model — the heaviest rung, reasoning
    # over twelve checks, before the analyst had written a word. None means
    # "same as the analysis", which is what a hand-built run (the tests) gets.
    verify_provider: Provider | None = None
    verify_model: ModelName | str | None = None
    verify_api_key: str = ""


def resolve_model(
    engine_override: str = "",
    user_keys: dict[Provider, str] | None = None,
    stored_keys: dict[Provider, str] | None = None,
) -> tuple[Provider, ModelName | str, str, str]:
    """Engine → provider → model → keys, as a tuple.

    The logic moved to ``agents.engines.resolve_run_model`` when content became
    the second V1 runner that needed it (a lone bring-your-own key choosing its
    own provider is what makes BYO work for every agent, not just this one).
    This wrapper keeps the tuple shape the insights routes and tests use.
    """
    run = resolve_run_model(engine_override, user_keys, stored_keys, log_prefix="insights")
    return run.provider, run.model, run.api_key, run.summary_key


def resolve_run(
    *,
    engine_override: str = "",
    user_id: UUID | None,
    project_id: Any,
    user_keys: dict[Provider, str] | None = None,
    tier_override: str = "",
) -> InsightsRun:
    """Model + membership-checked project scope + the autonomy the run gets.

    ``tier_override`` lifts the analysis — the pass that writes the brief —
    and only that: the verifier keeps its own rung whatever the composer
    asked for, because "run this on Heavy" means the answer, not the checks.
    """
    # The unattended brief has no headers at all, so without this it would be
    # the one insights path still reaching for the server key.
    stored = stored_keys_for(user_id)
    # The user's saved map, not a request field: this function serves both
    # insights doors, and the scheduled brief behind one of them has no browser
    # to send anything. Reading it here is what makes the tier map mean the
    # same thing on the run nobody is watching.
    settings = get_model_settings(user_id)
    # ProviderKeyRequired propagates deliberately — see resolve_job_run: "you
    # have not connected a key" is a 402 the browser can act on, not a 500.
    job = resolve_job_run(
        Job.ANALYSIS,
        engine_override=engine_override or settings.engine,
        user_keys=user_keys,
        stored_keys=stored,
        tier_map=settings.tiers,
        auto_fallback=settings.auto_fallback,
        log_prefix="insights",
        tier_override=tier_override,
    )
    provider, model, api_key = job.provider, job.model, job.api_key
    # Only an Anthropic key drives the artifact summariser; on any other
    # provider a brief persists without a digest rather than with a broken one.
    summary_key = api_key if provider is Provider.ANTHROPIC else ""

    # The verifier's own rung. Best-effort: the analysis resolved, so a key
    # exists, and the checking pass falling back to the analyst's model is a
    # slower run rather than a failed one.
    verify_provider: Provider | None = None
    verify_model: ModelName | str | None = None
    verify_api_key = ""
    try:
        verify = resolve_job_run(
            Job.VERIFICATION,
            engine_override=engine_override or settings.engine,
            user_keys=user_keys,
            stored_keys=stored,
            tier_map=settings.tiers,
            auto_fallback=settings.auto_fallback,
            log_prefix="insights-verify",
        )
        if (verify.provider, verify.model) != (provider, model):
            verify_provider, verify_model, verify_api_key = verify.provider, verify.model, verify.api_key
    except Exception:
        logger.warning("insights: verification tier unresolved — verifier runs on the analysis model", exc_info=True)

    scoped: UUID | None = None
    configured = AUTONOMY_ASK
    if project_id and user_id:
        try:
            candidate = UUID(str(project_id))
            with next(db_session()) as db:
                role = member_role(candidate, user_id, db)
                if role is not None:
                    row = db.get(Project, candidate)
                    configured = normalize_autonomy(getattr(row, "autonomy_level", ""))
                    scoped = candidate
            if role is None:
                logger.warning(
                    "insights: user %s is not a member of project %s — run is unscoped",
                    user_id, project_id,
                )
        except Exception:
            logger.warning("insights: project scoping unavailable", exc_info=True)

    return InsightsRun(
        provider=provider,
        model=model,
        api_key=api_key,
        summary_key=summary_key,
        project_id=scoped,
        configured_autonomy=configured,
        autonomy=effective_autonomy(configured, getattr(model, "value", str(model))),
        tier=job.tier,
        tier_requested=job.tier_requested,
        tier_skipped=job.tier_skipped,
        tier_retry_in=job.tier_retry_in,
        verify_provider=verify_provider,
        verify_model=verify_model,
        verify_api_key=verify_api_key,
    )


# The status vocabulary is ListDataSources' own (service/connector_access.py);
# the phrasing beside each is what the tool's description promises the model.
# A scope grant is named only when it limits what a fetch can reach — a
# complete grant, or a manual connector with no grant at all, adds nothing.
_SCOPE_WORTH_NAMING = frozenset({SCOPE_PARTIAL, SCOPE_UNKNOWN})
_SOURCE_STATUS_HINTS = {
    "bound": "ready to use",
    "available": "authorized, no account chosen — SelectAccount resolves it",
    "not_connected": "nothing stored — RequestConnection if the analysis needs it",
}


def render_data_sources(sources: list[dict]) -> str:
    """The ``<data_sources>`` block for the opening turn, from ListDataSources'
    rows. One line per connector, same ids and statuses the tool reports, so
    the model reads the block and the tool result in one vocabulary."""
    lines: list[str] = []
    for src in sources:
        status = str(src.get("status") or "")
        line = f"- {src.get('connector_id', '')}: {status}"
        hint = _SOURCE_STATUS_HINTS.get(status, "")
        if status == "bound" and (src.get("account_id") or src.get("account_name")):
            account = str(src.get("account_id") or "")
            name = str(src.get("account_name") or "")
            line += f" → {account}" + (f' "{name}"' if name else "")
        elif hint:
            line += f" ({hint})"
        if status == "not_connected" and src.get("auth_kind") == "manual":
            line += " · API key, added on the Connections page"
        if src.get("scope_status") in _SCOPE_WORTH_NAMING:
            line += f" · scopes: {src['scope_status']}"
        lines.append(line)
    if not lines:
        return ""
    return xml_block(
        "data_sources",
        "What this project can reach right now — the same list ListDataSources "
        "returns. Call the tool again only after a connection or account changes.\n"
        + "\n".join(lines),
    )


def data_sources_block(run: InsightsRun, *, user_id: UUID | None) -> str:
    """ListDataSources, answered before the first model call.

    The agent's first action on nearly every run was to call the tool — a
    whole model round trip, with reasoning, to learn a list the server had at
    hand. Per-project, so it rides in the USER turn beside the memory digest,
    never in the cached system prefix. Best-effort: with no block the tool is
    still mounted, and the prompt tells the agent to call it.
    """
    if run.project_id is None or user_id is None:
        return ""
    try:
        from service.connector_access import list_data_sources

        with next(db_session()) as db:
            sources = list_data_sources(db, user_id=user_id, project_id=run.project_id)
        return render_data_sources([s.as_dict() for s in sources])
    except Exception:
        logger.warning("insights: data sources block unavailable", exc_info=True)
        return ""


async def memory_blocks(
    run: InsightsRun,
    *,
    user_id: UUID | None,
    user_preferences: Any = None,
    query: str = "",
    remember: bool = True,
    emit: Callable | None = None,
    conversation_id: UUID | None = None,
) -> str:
    """The ``<project_memory>`` / ``<user_memory>`` blocks for the opening turn.

    Per-project data, so the caller puts it in the USER message and never the
    system prompt — the cached system prefix must stay byte-identical across
    customers. Best-effort: a missing digest degrades a run, never fails it.
    Emits MEMORY_RECALLED so a UI can show what the turn was primed with and
    link each chip back to its source.
    """
    if run.project_id is None or not remember:
        return ""

    def _build():
        with next(db_session()) as db:
            # Declared preferences become user-scope memory first, so the digest
            # carries them and the agent reads them from one place.
            seed_user_preferences(db, user_id, user_preferences)
            return build_memory_context(
                db,
                project_id=run.project_id,
                user_id=user_id,
                agent_type=str(AgentType.INSIGHTS),
                query=query,
                subject=query,
                conversation_id=conversation_id,
            )

    try:
        # A worker thread, not the event loop: this is a dozen-plus queries,
        # and every SSE stream on the process stalls for the duration of a
        # synchronous one.
        context = await asyncio.to_thread(_build)
    except Exception:
        logger.warning("insights: memory blocks unavailable", exc_info=True)
        return ""

    if context.recalled and emit is not None:
        try:
            await emit({
                "event": AgentEvent.MEMORY_RECALLED,
                "memories": [
                    {k: v for k, v in entry.items() if k != "uuid"}
                    for entry in context.recalled
                ],
            })
        except Exception:
            logger.debug("insights: MEMORY_RECALLED emit failed", exc_info=True)
    return context.text
