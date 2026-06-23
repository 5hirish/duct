"""Pre-flight enrichment for the Content Studio agent.

Runs between load_project and the orchestrator's first synthesis turn.
Two stages:

  1. Local extraction — pure compute over already-persisted
     content_posts. Computes per-pillar history (topics covered, days
     since last use, recent hook variety) so the agent doesn't repeat
     itself and isn't bottlenecked on web research for basic awareness.

  2. Optional sub-agent research — Haiku query() with built-in
     WebSearch + WebFetch tools. Returns structured TrendSignals for
     trending TikTok sounds, hashtags, hook formulas, and visual
     styles tuned to the brand's audience. Hard timeout, graceful
     degradation: if the sub-agent fails, the caller still gets the
     local signals.

Pattern borrowed from agents/audit/enrichment.py. Differences:
  - Output is content-tuned (TrendSignal records, not competitor data).
  - Local extraction reads our DB, not crawled web pages.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from agents.content.schema import (
    ContentBrandContext,
    ContentResearchContext,
    PillarHistorySignal,
    TrendSignal,
)
from agents.models import AgentPermissionMode, AgentTool, ModelName
from db.session import get_engine
from models.content import ContentPost
from service.content_metrics import metric_float

logger = logging.getLogger(__name__)


_HAIKU_MODEL = ModelName.CLAUDE_HAIKU_4_5.value
_DEFAULT_TIMEOUT = 90.0


# ---------------------------------------------------------------------------
# Stage 1 — local extraction from content_posts
# ---------------------------------------------------------------------------


def _local_content_signals(project_id: UUID) -> ContentResearchContext:
    """Build a ContentResearchContext from already-persisted content_posts.

    Cost: one SQL query. No network. Always succeeds (returns an empty
    context if no posts exist yet).
    """
    engine = get_engine()
    if engine is None:
        logger.warning("enrichment: DATABASE_URL not configured; skipping local scan")
        return ContentResearchContext()

    with Session(engine) as db:
        rows = db.execute(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .order_by(ContentPost.updated_at.desc())  # type: ignore[union-attr]
        ).scalars().all()

    if not rows:
        return ContentResearchContext()

    now = datetime.now(timezone.utc)
    by_pillar: dict[str, list[ContentPost]] = {}
    for r in rows:
        if r.pillar:
            by_pillar.setdefault(r.pillar, []).append(r)

    history: list[PillarHistorySignal] = []
    for pillar, posts in by_pillar.items():
        ts = [p.posted_at or p.updated_at for p in posts if (p.posted_at or p.updated_at)]
        # Ensure timezone-aware for arithmetic; ContentPost stores tz-aware datetimes.
        ts_aware = [
            (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) for t in ts if t is not None
        ]
        latest = max(ts_aware) if ts_aware else None
        days_since = (now - latest).days if latest else None

        # Hook variety: count occurrences over the last 10 posts.
        recent = sorted(
            posts,
            key=lambda p: (p.posted_at or p.updated_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )[:10]
        hook_counter: Counter[str] = Counter(p.hook_type for p in recent if p.hook_type)
        recent_hook_types = [h for h, _ in hook_counter.most_common(5)]

        # save_rate median where present (read via the canonical metric contract)
        rates = [
            metric_float(p.perf, "save_rate")
            for p in posts
            if isinstance(p.perf, dict) and isinstance(p.perf.get("save_rate"), (int, float))
        ]
        rates.sort()
        median = rates[len(rates) // 2] if rates else None

        history.append(PillarHistorySignal(
            pillar=pillar,
            posts_count=len(posts),
            days_since_last_post=days_since,
            recent_topics=[p.topic for p in recent[:5] if p.topic],
            recent_hook_types=recent_hook_types,
            median_save_rate=median,
        ))

    # Project-level "days since any post" — useful for "have we posted in a while?".
    all_ts = [
        ((r.posted_at or r.updated_at) or now)
        for r in rows
        if (r.posted_at or r.updated_at)
    ]
    all_ts_aware = [
        (t if t.tzinfo else t.replace(tzinfo=timezone.utc)) for t in all_ts
    ]
    latest_overall = max(all_ts_aware) if all_ts_aware else None
    days_since_overall = (now - latest_overall).days if latest_overall else None

    return ContentResearchContext(
        pillar_history=sorted(history, key=lambda h: -h.posts_count),
        total_posts_to_date=len(rows),
        days_since_last_post=days_since_overall,
    )


# ---------------------------------------------------------------------------
# Stage 2 — Haiku sub-agent for trending sounds / hashtags / hooks / styles
# ---------------------------------------------------------------------------


def _build_research_prompt(brand: ContentBrandContext) -> str:
    pillar_names = ", ".join(p.name for p in brand.pillars) or "(no pillars set)"
    return f"""\
You're scouting what's working on TikTok this week for our content agent.

Brand:        {brand.project_name} ({brand.url or 'no URL'})
Audience:     {brand.audience or '(unknown audience)'}
Content goal: {brand.content_goal or '(unspecified)'}
Voice:        {brand.brand_voice or '(unspecified)'}
Pillars:      {pillar_names}

Use WebSearch + WebFetch (max 8 searches, 4 fetches total) to find:
  1. **Trending sounds** — 3–5 sounds getting traction right now for this audience.
     Look for "trending sounds TikTok {datetime.now().strftime('%B %Y')}",
     audience-specific creator videos, and TikTok trend digests.
  2. **Trending hashtags** — 3–5 hashtags audiences in this niche are
     using or searching this week.
  3. **Trending hooks** — 3–5 hook formulas getting high completion rates
     right now (e.g. "POV: you discovered X", "Things nobody tells you
     about Y"). Cite the post or creator account where you saw it.
  4. **Trending styles** — 2–4 visual / format trends (slideshow patterns,
     POV overlays, "before vs after" pacing, etc.).
  5. **Audience insights** — 2–4 short observations about what the
     audience is engaging with right now beyond hashtags (specific
     creators, format preferences, time-of-day patterns).

For each item: a short label + a one-sentence "why it works" + the URL
where you saw it (if from a fetch).

Skip generic SEO/marketing advice. Skip evergreen tips. Only items
specific to this week, this audience, and findings backed by a URL.

Output strictly as the provided JSON schema.
"""


async def enrich_content_context(
    brand: ContentBrandContext,
    api_key: str,
    *,
    base_context: ContentResearchContext | None = None,
    model: str = _HAIKU_MODEL,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ContentResearchContext:
    """Run the Haiku research sub-agent, layered on top of the local scan.

    Always returns a ContentResearchContext — even on sub-agent failure
    or timeout the local signals come through unchanged.
    """
    base = base_context or _local_content_signals(brand.project_id)

    if not api_key:
        logger.info("enrichment: no api_key; returning local signals only")
        return base

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError:
        logger.warning("enrichment: claude_agent_sdk not available; local signals only")
        return base

    prompt = _build_research_prompt(brand)

    options = ClaudeAgentOptions(
        model=model,
        allowed_tools=[AgentTool.WEB_SEARCH, AgentTool.WEB_FETCH],
        permission_mode=AgentPermissionMode.BYPASS,
        max_turns=12,
        env={"ANTHROPIC_API_KEY": api_key},
        setting_sources=[],
        output_format={
            "type": "json_schema",
            "schema": _research_output_schema(),
        },
    )

    async def _run() -> ContentResearchContext | None:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage) and message.structured_output:
                try:
                    sub_signals = _RawTrendingResult.model_validate(message.structured_output)
                except Exception as exc:
                    logger.warning("enrichment: sub-agent output failed validation: %s", exc)
                    return None
                logger.info(
                    "enrichment: sub-agent returned sounds=%d hashtags=%d hooks=%d styles=%d",
                    len(sub_signals.trending_sounds),
                    len(sub_signals.trending_hashtags),
                    len(sub_signals.trending_hooks),
                    len(sub_signals.trending_styles),
                )
                return ContentResearchContext(
                    # Carry forward local signals
                    pillar_history       = base.pillar_history,
                    total_posts_to_date  = base.total_posts_to_date,
                    days_since_last_post = base.days_since_last_post,
                    # Layer in sub-agent findings
                    trending_sounds      = sub_signals.trending_sounds,
                    trending_hashtags    = sub_signals.trending_hashtags,
                    trending_hooks       = sub_signals.trending_hooks,
                    trending_styles      = sub_signals.trending_styles,
                    audience_insights    = sub_signals.audience_insights,
                    enrichment_notes     = sub_signals.enrichment_notes,
                )
        return None

    try:
        enriched = await asyncio.wait_for(_run(), timeout=timeout)
        if enriched is not None:
            return enriched
    except asyncio.TimeoutError:
        logger.warning(
            "enrichment: sub-agent timed out after %.0fs; using local signals only",
            timeout,
        )
    except Exception as exc:
        logger.warning("enrichment: sub-agent failed (%s); using local signals only", exc)

    return base


# ---------------------------------------------------------------------------
# Sub-agent output shape
# ---------------------------------------------------------------------------


def _research_output_schema() -> dict:
    """JSON schema passed to the Haiku sub-agent via output_format.

    Smaller than ContentResearchContext on purpose: the sub-agent only
    fills the trend + audience fields. Local signals come from
    _local_content_signals.
    """
    return _RawTrendingResult.model_json_schema()


from pydantic import BaseModel, ConfigDict, Field  # noqa: E402 — keeps schema close to function


class _RawTrendingResult(BaseModel):
    """Sub-agent's strict output shape. Internal — not exported."""

    model_config = ConfigDict(extra="forbid")

    trending_sounds:   list[TrendSignal] = Field(default_factory=list)
    trending_hashtags: list[TrendSignal] = Field(default_factory=list)
    trending_hooks:    list[TrendSignal] = Field(default_factory=list)
    trending_styles:   list[TrendSignal] = Field(default_factory=list)
    audience_insights: list[str]         = Field(default_factory=list)
    enrichment_notes:  list[str]         = Field(default_factory=list)


__all__ = [
    "enrich_content_context",
]
