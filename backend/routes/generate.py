"""Insight generation over HTTP — the modes catalogue and the unattended brief.

Two endpoints, and what is *not* here matters as much as what is:

  * ``GET  /api/insights/modes``    — the mode/goal catalogue the app renders.
  * ``POST /api/insights/generate`` — one brief, unattended.

The request-shaped pipeline this module used to hold is gone. It fetched a
wizard-chosen set of connectors, ran a goal-restricted tool loop and made one
structured-output call — a shape that only existed because a six-step form had
already decided every interesting question before the model was invoked. Both
the form and the pipeline behind it were deleted once the autonomous agent
could answer those questions itself; see
``docs/engineering/autonomous-insights-agent-plan.md``.

``agents/insights/v1/agent.py``, ``v2/`` (ADK) and ``v3/`` are left in place
and frozen. They no longer serve a route.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from models.auth import User
from service.auth import get_current_user_optional, get_user_provider_keys
from routes.schemas import (
    BusinessContextField,
    BusinessContextFieldOption,
    BusinessContextFieldShowIf,
    BusinessContextFieldType,
    InsightGoalDescriptor,
    InsightMode,
    InsightModesResponse,
)
from utils.dates import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])


@router.get("/insights/modes")
async def list_insight_modes() -> dict:
    """Return all intelligence modes with their goals. Frontend uses this as the single source of truth."""
    from agents.insights.goals.paid_ads import (
        InsightGenerationGoal,
        GOAL_LABELS as PAID_LABELS,
        GOAL_DESCRIPTIONS as PAID_DESCRIPTIONS,
        GOAL_ICONS as PAID_ICONS,
    )
    from agents.insights.goals.organic_growth import (
        OrganicGrowthGoal,
        GOAL_LABELS as ORGANIC_LABELS,
        GOAL_DESCRIPTIONS as ORGANIC_DESCRIPTIONS,
        GOAL_ICONS as ORGANIC_ICONS,
    )

    def _goals(enum_cls, labels, descriptions, icons) -> list[InsightGoalDescriptor]:
        return [
            InsightGoalDescriptor(
                key=g.value,
                icon=icons.get(g, ""),
                label=labels.get(g, g.value),
                description=descriptions.get(g, ""),
            )
            for g in enum_cls
        ]

    organic_business_context_fields = [
        BusinessContextField(
            key="primary_organic_kpi",
            label="Primary organic KPI",
            type=BusinessContextFieldType.SELECT,
            placeholder="Select primary KPI...",
            options=[
                BusinessContextFieldOption(value="organic_traffic", label="Organic Traffic"),
                BusinessContextFieldOption(value="keyword_rankings", label="Keyword Rankings"),
                BusinessContextFieldOption(value="backlinks", label="Backlinks"),
                BusinessContextFieldOption(value="conversions_from_organic", label="Conversions from Organic"),
            ],
        ),
        BusinessContextField(
            key="monthly_organic_traffic_target",
            label="Monthly organic traffic target (optional)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 10000",
            min=0,
            step=1,
            empty_if_zero=True,
        ),
        BusinessContextField(
            key="primary_content_type",
            label="Primary content type",
            type=BusinessContextFieldType.SELECT,
            placeholder="Select content type...",
            options=[
                BusinessContextFieldOption(value="blog_articles", label="Blog/Articles"),
                BusinessContextFieldOption(value="product_pages", label="Product Pages"),
                BusinessContextFieldOption(value="landing_pages", label="Landing Pages"),
                BusinessContextFieldOption(value="docs_help", label="Docs/Help"),
            ],
        ),
        BusinessContextField(
            key="period_changes",
            label="What changed recently? (optional)",
            type=BusinessContextFieldType.TEXTAREA,
            placeholder="e.g. Published 10 new articles, migrated to new CMS, added hreflang tags.",
            rows=2,
            full_width=True,
        ),
    ]

    paid_ads_business_context_fields = [
        BusinessContextField(
            key="industry",
            label="Industry",
            type=BusinessContextFieldType.SELECT,
            placeholder="Select industry...",
            options=[
                BusinessContextFieldOption(value="ecommerce", label="E-commerce"),
                BusinessContextFieldOption(value="saas", label="SaaS / B2B"),
                BusinessContextFieldOption(value="lead_gen", label="Lead generation"),
                BusinessContextFieldOption(value="agency", label="Agency / multi-client"),
                BusinessContextFieldOption(value="other", label="Other"),
            ],
            show_if=BusinessContextFieldShowIf.ALWAYS,
        ),
        BusinessContextField(
            key="primary_conversion_action",
            label="Primary conversion action",
            type=BusinessContextFieldType.TEXT,
            placeholder="e.g. Demo booked, Trial started, Purchase",
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="monthly_budget",
            label="Monthly budget ($)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 5000",
            min=0,
            step=0.01,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="target_cpa",
            label="Target CPA ($)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 50",
            min=0,
            step=0.01,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="target_roas",
            label="Target ROAS (x)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 3.0",
            min=0,
            step=0.1,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="target_payback_days",
            label="Target payback (days)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 90",
            min=0,
            step=1,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="gross_margin_percent",
            label="Gross margin (%)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 70",
            min=0,
            max=100,
            step=1,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="qualified_lead_value",
            label="Qualified lead value ($)",
            type=BusinessContextFieldType.NUMBER,
            placeholder="e.g. 1200",
            min=0,
            step=1,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
        BusinessContextField(
            key="period_changes",
            label="What changed during this period? (optional)",
            type=BusinessContextFieldType.TEXTAREA,
            placeholder="e.g. Switched bid strategy, launched new offer, changed landing pages, tracking updates.",
            rows=2,
            full_width=True,
            show_if=BusinessContextFieldShowIf.ADS_SELECTED,
        ),
    ]

    response = InsightModesResponse(
        modes=[
            InsightMode(
                key="product_intelligence",
                emoji="📊",
                label="Product Intelligence",
                short_label="Product",
                tagline="Weekly brief for PMs & growth teams",
                active=False,
            ),
            InsightMode(
                key="organic_growth",
                emoji="🌱",
                label="Organic Growth",
                short_label="Organic",
                tagline="Automated SEO & content intelligence",
                active=True,
                locked_connections=["gsc", "ga4"],
                goals=_goals(OrganicGrowthGoal, ORGANIC_LABELS, ORGANIC_DESCRIPTIONS, ORGANIC_ICONS),
                business_context_fields=organic_business_context_fields,
            ),
            InsightMode(
                key="paid_ads",
                emoji="📣",
                label="Paid Ads Intelligence",
                short_label="Paid Ads",
                tagline="Cross-platform brief for performance marketers",
                active=False,
                locked_connections=["google_ads"],
                goals=_goals(InsightGenerationGoal, PAID_LABELS, PAID_DESCRIPTIONS, PAID_ICONS),
                business_context_fields=paid_ads_business_context_fields,
            ),
            InsightMode(
                key="sales_revops",
                emoji="💼",
                label="Sales / RevOps",
                short_label="Sales",
                tagline="Pipeline & revenue intelligence",
                active=False,
            ),
            InsightMode(
                key="ecommerce_dtc",
                emoji="🛒",
                label="E-commerce / DTC",
                short_label="E-commerce",
                tagline="ROAS, LTV & retention synthesis",
                active=False,
            ),
            InsightMode(
                key="customer_success",
                emoji="🤝",
                label="Customer Success",
                short_label="CS",
                tagline="Early churn & health score signals",
                active=False,
            ),
        ]
    )
    return response.model_dump(mode="json")


# ---------------------------------------------------------------------------
# The unattended brief
# ---------------------------------------------------------------------------

@router.post("/insights/generate")
async def generate_insight(
    body: dict,
    user: User | None = Depends(get_current_user_optional),
    user_keys: dict = Depends(get_user_provider_keys),
) -> dict:
    """One brief, no human — the scheduled-brief entry point.

    The counterpart of ``POST /api/agents/insights/sessions``: same agent, same
    tools, same artifact store, but a single turn with nothing that can pause.
    ``backend/CLAUDE.md`` is explicit that the scheduled brief is the product
    and can never block on a person, so the unattended shape makes blocking
    impossible rather than merely discouraged — AskUserQuestion and the
    connector pause tools are not mounted, and the system prompt says there is
    nobody to ask. A question that cannot be asked becomes a stated assumption
    in the brief.

    Takes the same body as a session (a project and a sentence). It used to
    take a fully-specified wizard request — connectors, accounts, goal, date
    range — and that request shape went away with the wizard it served.

    The durable output is the artifact; the response body is for the caller's
    log.
    """
    from agents.insights.brief import ARTIFACT_KIND, DEFAULT_FORMAT, brief_artifact_version
    from agents.insights.schema import InsightsRequest
    from agents.insights.setup import (
        InsightsSetupError,
        memory_blocks,
        resolve_run,
    )
    from agents.insights.v1.runner import AutonomousInsightsRunner
    from agents.core.context import format_business_context
    from agents.registry import AgentType
    from service.artifact_store import ArtifactPersister

    try:
        req = InsightsRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, f"Invalid insights config: {exc}") from exc
    if not req.prompt.strip():
        raise HTTPException(422, "prompt is required — say what the brief should cover.")

    user_id = getattr(user, "id", None)
    try:
        run = resolve_run(
            engine_override=req.engine,
            user_id=user_id,
            project_id=req.project_id,
            user_keys=user_keys,
        )
    except InsightsSetupError as exc:
        raise HTTPException(500, str(exc)) from exc

    # No SSE consumer here, but emit is still how a brief reaches storage: the
    # persister wraps it and intercepts ARTIFACT_VERSION.
    async def emit(_event: dict) -> None:
        return None

    emit_fn = emit
    persister = None
    if run.project_id is not None:
        try:
            persister = ArtifactPersister(
                project_id=run.project_id,
                user_id=user_id,
                agent_type=str(AgentType.INSIGHTS),
                kind=ARTIFACT_KIND,
                api_key=run.summary_key,
                adapt=brief_artifact_version,
            )
            emit_fn = persister.wrap_emit(emit)
        except Exception:
            logger.warning(
                "insights: artifact persistence unavailable — brief runs unpersisted",
                exc_info=True,
            )

    memory = await memory_blocks(
        run,
        user_id=user_id,
        user_preferences=req.user_preferences,
        query=req.prompt,
        remember=req.remember,
    )

    runner = AutonomousInsightsRunner(
        api_key=run.api_key,
        provider=run.provider,
        model=run.model,
        temperature=1.0,
        thinking=req.user_preferences.thinking,
    )
    try:
        brief = await runner.run_once(
            emit_fn,
            prompt=req.prompt,
            business_context=format_business_context(req.business_context),
            memory=memory,
            project_id=run.project_id,
            user_id=user_id,
            remember=req.remember,
            artifact_format=(
                req.user_preferences.preferred_artifact_format or DEFAULT_FORMAT
            ),
            autonomy=run.autonomy,
        )
    except Exception as exc:
        logger.exception("insights: unattended brief failed")
        raise HTTPException(500, f"Brief generation failed: {exc}") from exc

    return {
        # An unattended run that reached no conclusion worth keeping says so,
        # rather than returning an empty brief that looks like a real one.
        "status": "ok" if brief else "no_brief",
        "artifact_id": str(persister.last_artifact_id) if persister and persister.last_artifact_id else "",
        "project_id": str(run.project_id) if run.project_id else "",
        "autonomy": run.autonomy,
        "generated_at": now_iso(),
        **brief,
    }
