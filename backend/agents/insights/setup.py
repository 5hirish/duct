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

import logging
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from agents.core.events import AgentEvent
from agents.engines import resolve_run_model
from agents.models import ModelName, Provider
from agents.registry import AgentType
from db.session import get_session as db_session
from models.execution import AUTONOMY_ASK, normalize_autonomy
from models.project import Project
from service.execution.policy import effective_autonomy
from service.membership import member_role
from service.memory import build_memory_context, seed_user_preferences, touch_recall
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
) -> InsightsRun:
    """Model + membership-checked project scope + the autonomy the run gets."""
    # The unattended brief has no headers at all, so without this it would be
    # the one insights path still reaching for the server key.
    provider, model, api_key, summary_key = resolve_model(
        engine_override, user_keys, stored_keys_for(user_id)
    )

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
    )


async def memory_blocks(
    run: InsightsRun,
    *,
    user_id: UUID | None,
    user_preferences: Any = None,
    query: str = "",
    remember: bool = True,
    emit: Callable | None = None,
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
    try:
        with next(db_session()) as db:
            # Declared preferences become user-scope memory first, so the digest
            # carries them and the agent reads them from one place.
            seed_user_preferences(db, user_id, user_preferences)
            context = build_memory_context(
                db,
                project_id=run.project_id,
                user_id=user_id,
                agent_type=str(AgentType.INSIGHTS),
                query=query,
                subject=query,
            )
            touch_recall(db, context.recalled_ids)
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
