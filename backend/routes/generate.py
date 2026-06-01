"""Interactive insight generation (fetch + goal-driven tools + LLM synthesis)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agents.engines import Engine, resolve_engine, resolve_engine_model, resolve_engine_provider, PROVIDER_CONFIG_ATTR
from agents.models import Provider
from agents.insights.agent import GenerateInsightsAgent
from agents.insights.v2.runner import AdkInsightsRunner
from agents.insights.v3.runner import ClaudeAgentSdkRunner
from config import get_configs
from routes.schemas import (
    BusinessContextField,
    BusinessContextFieldOption,
    BusinessContextFieldShowIf,
    BusinessContextFieldType,
    GenerateRequest,
    InsightGoalDescriptor,
    InsightMetadata,
    InsightMode,
    InsightModesResponse,
    ReportRequest,
    UnifiedInsight,
)
from service.google.credentials import resolve_ads_credentials, resolve_customer_id
from service.google.fetch import (
    fetch_ad_group_performance,
    fetch_device_performance,
    fetch_geo_performance,
    fetch_search_terms,
)
from service.google.ga4 import fetch_ga4_conversion_paths, fetch_ga4_landing_pages
from service.google.gsc import fetch_gsc_page_performance, fetch_gsc_query_performance
from service.pipeline import build_connector_brief, fetch_connector_payload, normalize_connections, now_iso, resolve_ga_credentials

if TYPE_CHECKING:
    from agents.models import ModelName

logger = logging.getLogger(__name__)

router = APIRouter(tags=["insights"])

STEP_COLLECT = "collect_source_data"
STEP_NORMALIZE = "normalize_connector_outputs"
STEP_SUPPLEMENTARY = "supplementary_fetch"
STEP_SYNTHESIZE = "synthesize_report"
STEP_ASSEMBLE = "assemble_report"

STEP_LABELS = {
    STEP_COLLECT: "Collecting source data",
    STEP_NORMALIZE: "Normalizing connector outputs",
    STEP_SUPPLEMENTARY: "Fetching supplementary insights",
    STEP_SYNTHESIZE: "Synthesizing recommendations",
    STEP_ASSEMBLE: "Finalizing insight",
}

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


def _resolve_agent_config(request_engine: str = "") -> tuple[str, Provider, "ModelName", Engine]:
    """Resolve engine/provider/model/API key from config.

    Request engine takes precedence over GENERATE_ENGINE env var.
    Provider and model default from the engine definition in agents/engines.py.
    """
    cfg = get_configs()
    engine = resolve_engine(request_engine or cfg.generate_engine or None)
    provider = resolve_engine_provider(engine, cfg.generate_provider or None)
    model = resolve_engine_model(engine, provider, cfg.generate_model or None)
    api_key = getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""
    return api_key, provider, model, engine


def _build_agent(
    api_key: str, provider: Provider, model: "ModelName", engine: Engine
) -> GenerateInsightsAgent | AdkInsightsRunner | ClaudeAgentSdkRunner:
    """Instantiate the insight engine resolved by _resolve_agent_config."""
    if engine == Engine.V3:
        return ClaudeAgentSdkRunner(api_key=api_key, provider=provider, model=model, temperature=1.0)
    if engine == Engine.V2:
        return AdkInsightsRunner(api_key=api_key, provider=provider, model=model, temperature=1.0)
    return GenerateInsightsAgent(api_key=api_key, provider=provider, model=model, temperature=1.0)


async def _emit(
    emit_event: EmitFn | None,
    *,
    event: str,
    step_id: str | None = None,
    status: str | None = None,
    label: str | None = None,
    connector_id: str | None = None,
    error: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if emit_event is None:
        return
    body: dict[str, Any] = {"event": event, "ts": now_iso()}
    if step_id is not None:
        body["step_id"] = step_id
    if status is not None:
        body["status"] = status
    if label is not None:
        body["label"] = label
    if connector_id is not None:
        body["connector_id"] = connector_id
    if error is not None:
        body["error"] = error
    if payload is not None:
        body["payload"] = payload
    await emit_event(body)


async def _step_started(emit_event: EmitFn | None, step_id: str, *, connector_id: str | None = None) -> None:
    await _emit(
        emit_event,
        event="step_started",
        step_id=step_id,
        label=STEP_LABELS[step_id],
        status="running",
        connector_id=connector_id,
    )


async def _step_finished(
    emit_event: EmitFn | None,
    step_id: str,
    *,
    connector_id: str | None = None,
    status: str = "success",
    error: str | None = None,
) -> None:
    await _emit(
        emit_event,
        event="step_finished",
        step_id=step_id,
        label=STEP_LABELS[step_id],
        status=status,
        connector_id=connector_id,
        error=error,
    )


async def _run_generate_pipeline(req: GenerateRequest, *, emit_event: EmitFn | None = None) -> dict[str, Any]:
    await _emit(
        emit_event,
        event="pipeline_started",
        status="running",
        payload={"connections": req.connections},
    )

    connections = normalize_connections(req.connections)
    if not req.date_from or not req.date_to:
        raise HTTPException(status_code=422, detail="date_from and date_to are required.")

    cfg = get_configs()
    ga4_property_id = (req.ga4_property_id or cfg.ga4_property_id).strip()
    gsc_site_url = (req.gsc_site_url or cfg.gsc_site_url).strip()
    ga4_refresh_token = (req.ga4_refresh_token or req.refresh_token).strip()
    gsc_refresh_token = (req.gsc_refresh_token or req.refresh_token).strip()
    ga_client_id, ga_client_secret = resolve_ga_credentials(cfg)

    if "ga4" in connections and not ga4_property_id:
        raise HTTPException(status_code=422, detail="ga4_property_id is required when GA4 is selected.")
    if "ga4" in connections and not ga4_refresh_token:
        raise HTTPException(status_code=422, detail="ga4_refresh_token is required when GA4 is selected.")
    if "gsc" in connections and not gsc_site_url:
        raise HTTPException(status_code=422, detail="gsc_site_url is required when GSC is selected.")
    if "gsc" in connections and not gsc_refresh_token:
        raise HTTPException(status_code=422, detail="gsc_refresh_token is required when GSC is selected.")
    if ("ga4" in connections or "gsc" in connections) and (not ga_client_id or not ga_client_secret):
        raise HTTPException(
            status_code=422,
            detail="Google OAuth client credentials are required for GA4/GSC connectors.",
        )

    shim = ReportRequest(
        customer_id=req.customer_id,
        refresh_token=req.refresh_token,
        login_customer_id=req.login_customer_id,
    )
    login_customer_id = (req.login_customer_id or cfg.google_ads_login_customer_id).strip()

    async def fetch_connector(connector_id: str) -> tuple[str, dict[str, Any]]:
        await _step_started(emit_event, STEP_COLLECT, connector_id=connector_id)
        try:
            data = await fetch_connector_payload(
                connector_id=connector_id,
                date_from=req.date_from,
                date_to=req.date_to,
                cfg=cfg,
                refresh_token=shim.refresh_token,
                customer_id=shim.customer_id,
                account_name=req.account_name,
                currency_code=req.currency_code,
                login_customer_id=login_customer_id,
                ga4_property_id=ga4_property_id,
                gsc_site_url=gsc_site_url,
                ga4_refresh_token=ga4_refresh_token,
                gsc_refresh_token=gsc_refresh_token,
            )
            await _step_finished(emit_event, STEP_COLLECT, connector_id=connector_id)
            return connector_id, data
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            await _step_finished(
                emit_event,
                STEP_COLLECT,
                connector_id=connector_id,
                status="error",
                error=message,
            )
            raise RuntimeError(f"{connector_id}: {message}") from exc

    fetched_rows = await asyncio.gather(*(fetch_connector(c) for c in connections), return_exceptions=True)
    fetch_failures = [item for item in fetched_rows if isinstance(item, Exception)]
    if fetch_failures:
        detail = "; ".join(str(err) for err in fetch_failures)
        raise HTTPException(status_code=502, detail=detail)
    raw_by_connector = {cid: payload for cid, payload in fetched_rows}

    async def normalize_connector(connector_id: str, raw_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        await _step_started(emit_event, STEP_NORMALIZE, connector_id=connector_id)
        try:
            brief_dict = await asyncio.to_thread(
                build_connector_brief,
                connector_id=connector_id,
                raw_data=raw_data,
                date_from=req.date_from,
                date_to=req.date_to,
            )
            await _step_finished(emit_event, STEP_NORMALIZE, connector_id=connector_id)
            return connector_id, brief_dict
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            await _step_finished(
                emit_event,
                STEP_NORMALIZE,
                connector_id=connector_id,
                status="error",
                error=message,
            )
            raise RuntimeError(f"{connector_id}: {message}") from exc

    normalized_rows = await asyncio.gather(
        *(normalize_connector(connector_id, raw_data) for connector_id, raw_data in raw_by_connector.items()),
        return_exceptions=True,
    )
    normalize_failures = [item for item in normalized_rows if isinstance(item, Exception)]
    if normalize_failures:
        detail = "; ".join(str(err) for err in normalize_failures)
        raise HTTPException(status_code=500, detail=detail)
    briefs = {cid: payload for cid, payload in normalized_rows}

    synthesis_dict = None
    mode = req.mode or "paid_ads"
    api_key, provider, model, engine = _resolve_agent_config(req.engine)

    # Build the all_briefs dict: connector_id → {"brief": ..., "raw": ...}
    all_briefs = {
        cid: {"brief": brief, "raw": raw_by_connector.get(cid)}
        for cid, brief in briefs.items()
    }

    # Determine primary connector for classification overrides (paid ads only)
    primary_connector = "google_ads" if mode == "paid_ads" else None
    supplementary: dict[str, Any] = {}

    if api_key and all_briefs:
        agent = _build_agent(api_key, provider, model, engine)

        # Build fetch functions only for connectors that are actually available.
        # For organic_growth, skip Google Ads credential resolution entirely.
        if mode == "organic_growth":
            fetch_fns = {}
            ads_customer_id = ""
            ga4_cred_kwargs = dict(
                refresh_token=ga4_refresh_token or "",
                client_id=ga_client_id,
                client_secret=ga_client_secret,
            )
            gsc_cred_kwargs = dict(
                refresh_token=gsc_refresh_token or "",
                client_id=ga_client_id,
                client_secret=ga_client_secret,
            )
            if "ga4" in connections and ga4_property_id:
                fetch_fns["fetch_ga4_landing_pages"] = partial(fetch_ga4_landing_pages, **ga4_cred_kwargs)
                fetch_fns["fetch_ga4_conversion_paths"] = partial(fetch_ga4_conversion_paths, **ga4_cred_kwargs)
            if "gsc" in connections and gsc_site_url:
                fetch_fns["fetch_gsc_query_performance"] = partial(fetch_gsc_query_performance, **gsc_cred_kwargs)
                fetch_fns["fetch_gsc_page_performance"] = partial(fetch_gsc_page_performance, **gsc_cred_kwargs)
        else:
            ads_customer_id = resolve_customer_id(request_customer_id=shim.customer_id)
            dt, cid, secret, rt = resolve_ads_credentials(request_refresh_token=shim.refresh_token)
            fetch_fns = _build_fetch_fns(
                dt, cid, secret, rt, login_customer_id,
                set(connections), ga4_property_id, gsc_site_url,
                ga4_refresh_token, gsc_refresh_token,
            )

        biz_ctx = req.business_context.model_dump() if req.business_context else None
        full_context = req.context
        if req.mode_context:
            full_context = f"{req.mode_context}\n\n{full_context}".strip() if full_context else req.mode_context

        registered = agent.setup_tools_for_goal(goal=req.goal, fetch_fns=fetch_fns, mode=mode)

        if isinstance(agent, (AdkInsightsRunner, ClaudeAgentSdkRunner)):
            # v2/v3: both phases run inside a single pipeline call
            await _step_started(emit_event, STEP_SUPPLEMENTARY)
            await _step_started(emit_event, STEP_SYNTHESIZE)
            engine = "v2" if isinstance(agent, AdkInsightsRunner) else "v3"
            logger.info("%s: running pipeline for goal '%s' (mode: %s)", engine, req.goal.value, mode)
            supplementary, synthesis = await agent.run_pipeline(
                goal=req.goal,
                custom_goal=req.custom_goal,
                context=full_context,
                all_briefs=all_briefs,
                business_context=biz_ctx,
                mode=mode,
                customer_id=ads_customer_id,
                date_from=req.date_from,
                date_to=req.date_to,
                ga4_property_id=ga4_property_id,
                gsc_site_url=gsc_site_url,
                connected_sources=connections,
                emit_event=emit_event,
            )
            await _step_finished(emit_event, STEP_SUPPLEMENTARY)
            await _step_finished(emit_event, STEP_SYNTHESIZE)
        else:
            # v1: separate Phase 1 (tool calling) + Phase 2 (synthesis)
            await _step_started(emit_event, STEP_SUPPLEMENTARY)
            if registered:
                logger.info("Phase 1: fetching supplementary data for goal '%s' (mode: %s)", req.goal.value, mode)
                supplementary = await agent.fetch_supplementary_data(
                    customer_id=ads_customer_id,
                    date_from=req.date_from,
                    date_to=req.date_to,
                    goal=req.goal,
                    ga4_property_id=ga4_property_id,
                    gsc_site_url=gsc_site_url,
                    custom_goal=req.custom_goal,
                    context=req.context,
                    connected_sources=connections,
                )
            await _step_finished(emit_event, STEP_SUPPLEMENTARY)

            await _step_started(emit_event, STEP_SYNTHESIZE)
            synthesis = await agent.synthesize(
                goal=req.goal,
                custom_goal=req.custom_goal,
                context=full_context,
                all_briefs=all_briefs,
                supplementary=supplementary or None,
                business_context=biz_ctx,
                mode=mode,
                emit_event=emit_event,
            )
            await _step_finished(emit_event, STEP_SYNTHESIZE)

        if primary_connector and primary_connector in briefs:
            agent.apply_classification_overrides(briefs[primary_connector], synthesis)
        synthesis_dict = agent.extract_synthesis(synthesis)
    else:
        await _step_started(emit_event, STEP_SUPPLEMENTARY)
        await _step_finished(emit_event, STEP_SUPPLEMENTARY)
        await _step_started(emit_event, STEP_SYNTHESIZE)
        await _step_finished(emit_event, STEP_SYNTHESIZE)

    await _step_started(emit_event, STEP_ASSEMBLE)
    envelope = UnifiedInsight(
        connectors_used=connections,
        briefs=briefs,
        supplementary=supplementary,
        synthesis=synthesis_dict,
        metadata=InsightMetadata(
            generated_at=now_iso(),
            goal=req.goal.value,
            connectors_used=connections,
        ),
    )
    await _step_finished(emit_event, STEP_ASSEMBLE)
    return envelope.model_dump()


def _build_fetch_fns(
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str,
    connections: set[str],
    ga4_property_id: str,
    gsc_site_url: str,
    ga4_refresh_token: str,
    gsc_refresh_token: str,
) -> dict[str, Callable[..., dict[str, Any]]]:
    """Build pre-credentialed fetch functions for each supplementary tool.

    Each function only needs customer_id, date_from, date_to — credentials
    are baked in via partial.
    """
    cred_kwargs = dict(
        developer_token=developer_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        login_customer_id=login_customer_id,
    )
    fetch_fns: dict[str, Callable[..., dict[str, Any]]] = {
        "fetch_search_terms": partial(fetch_search_terms, **cred_kwargs),
        "fetch_device_performance": partial(fetch_device_performance, **cred_kwargs),
        "fetch_geo_performance": partial(fetch_geo_performance, **cred_kwargs),
        "fetch_ad_group_performance": partial(fetch_ad_group_performance, **cred_kwargs),
    }
    if "ga4" in connections and ga4_property_id:
        ga4_cred_kwargs = dict(
            refresh_token=ga4_refresh_token or refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        fetch_fns["fetch_ga4_landing_pages"] = partial(fetch_ga4_landing_pages, **ga4_cred_kwargs)
        fetch_fns["fetch_ga4_conversion_paths"] = partial(fetch_ga4_conversion_paths, **ga4_cred_kwargs)
    if "gsc" in connections and gsc_site_url:
        gsc_cred_kwargs = dict(
            refresh_token=gsc_refresh_token or refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        fetch_fns["fetch_gsc_query_performance"] = partial(fetch_gsc_query_performance, **gsc_cred_kwargs)
        fetch_fns["fetch_gsc_page_performance"] = partial(fetch_gsc_page_performance, **gsc_cred_kwargs)
    return fetch_fns


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


@router.post("/insights/generate")
async def generate_insight(req: GenerateRequest) -> dict:
    """Fetch data for selected connections, build briefs, and optional synthesis."""
    return await _run_generate_pipeline(req)


@router.post("/insights/generate/stream")
async def generate_insight_stream(req: GenerateRequest) -> StreamingResponse:
    """Stream real pipeline progress events and final payload over SSE."""

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    finished = asyncio.Event()

    async def emit_event(event_payload: dict[str, Any]) -> None:
        await queue.put(event_payload)

    async def worker() -> None:
        try:
            insight = await _run_generate_pipeline(req, emit_event=emit_event)
            await _emit(
                emit_event,
                event="pipeline_finished",
                status="success",
                payload=insight,
            )
        except HTTPException as exc:
            await _emit(
                emit_event,
                event="pipeline_failed",
                status="error",
                error=str(exc.detail),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled generate stream failure")
            await _emit(
                emit_event,
                event="pipeline_failed",
                status="error",
                error=str(exc),
            )
        finally:
            finished.set()

    task = asyncio.create_task(worker())

    async def stream() -> Any:
        try:
            while not finished.is_set() or not queue.empty():
                try:
                    event_payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event_payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keep connection alive behind proxies.
                    yield ": ping\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
