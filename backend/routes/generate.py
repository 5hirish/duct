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

from agents.models import Provider, resolve_model, resolve_provider
from agents.insights.agent import GenerateInsightsAgent
from config import get_configs
from routes.schemas import GenerateRequest, InsightMetadata, ReportRequest, UnifiedInsight
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


def _resolve_agent_config() -> tuple[str, Provider, ModelName]:
    """Resolve LLM provider/model/API key from config."""
    cfg = get_configs()
    provider = resolve_provider(cfg.generate_provider or None)
    model = resolve_model(cfg.generate_model or None, provider)

    key_map = {
        Provider.OPENAI: cfg.openai_api_key,
        Provider.GOOGLE_GENAI: cfg.gemini_api_key,
        Provider.ANTHROPIC: cfg.anthropic_api_key,
    }
    api_key = key_map.get(provider, cfg.gemini_api_key) or ""
    return api_key, provider, model


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
    google_ads_brief = briefs.get("google_ads")
    google_ads_raw = raw_by_connector.get("google_ads")
    api_key, provider, model = _resolve_agent_config()

    if api_key and google_ads_brief and google_ads_raw:
        await _step_started(emit_event, STEP_SUPPLEMENTARY)
        agent = GenerateInsightsAgent(
            api_key=api_key,
            provider=provider,
            model=model,
            temperature=1.0,
        )
        ads_customer_id = resolve_customer_id(request_customer_id=shim.customer_id)
        dt, cid, secret, rt = resolve_ads_credentials(request_refresh_token=shim.refresh_token)
        fetch_fns = _build_fetch_fns(
            dt,
            cid,
            secret,
            rt,
            login_customer_id,
            set(connections),
            ga4_property_id,
            gsc_site_url,
            ga4_refresh_token,
            gsc_refresh_token,
        )
        registered = agent.setup_tools_for_goal(goal=req.goal, fetch_fns=fetch_fns)
        supplementary = {}
        if registered:
            logger.info("Phase 1: fetching supplementary data for goal '%s'", req.goal.value)
            supplementary = await agent.fetch_supplementary_data(
                customer_id=ads_customer_id,
                date_from=req.date_from,
                date_to=req.date_to,
                goal=req.goal,
                ga4_property_id=ga4_property_id,
                gsc_site_url=gsc_site_url,
                custom_goal=req.custom_goal,
                context=req.context,
            )
        await _step_finished(emit_event, STEP_SUPPLEMENTARY)

        await _step_started(emit_event, STEP_SYNTHESIZE)
        biz_ctx = req.business_context.model_dump() if req.business_context else None
        synthesis = await agent.synthesize(
            goal=req.goal,
            custom_goal=req.custom_goal,
            context=req.context,
            brief_dict=google_ads_brief,
            raw_payload=google_ads_raw,
            supplementary=supplementary or None,
            business_context=biz_ctx,
        )
        agent.apply_classification_overrides(google_ads_brief, synthesis)
        synthesis_dict = agent.extract_synthesis(synthesis)
        await _step_finished(emit_event, STEP_SYNTHESIZE)
    else:
        await _step_started(emit_event, STEP_SUPPLEMENTARY)
        await _step_finished(emit_event, STEP_SUPPLEMENTARY)
        await _step_started(emit_event, STEP_SYNTHESIZE)
        await _step_finished(emit_event, STEP_SYNTHESIZE)

    await _step_started(emit_event, STEP_ASSEMBLE)
    envelope = UnifiedInsight(
        connectors_used=connections,
        briefs=briefs,
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
