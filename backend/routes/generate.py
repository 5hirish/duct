"""Interactive brief generation (fetch + goal-driven tools + LLM synthesis)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import partial
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException

from agents.models import Provider, resolve_model, resolve_provider
from agents.reporter.agent import GenerateAgent
from config import get_configs
from service.google.fetch import (
    fetch_ad_group_performance,
    fetch_campaigns,
    fetch_device_performance,
    fetch_geo_performance,
    fetch_search_terms,
)
from service.google.brief import build_brief

from service.google.credentials import resolve_ads_credentials, resolve_customer_id
from routes.schemas import GenerateRequest, ReportMetadata, ReportRequest, UnifiedReport

if TYPE_CHECKING:
    from agents.models import ModelName

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


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


def _build_fetch_fns(
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    login_customer_id: str,
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
    return {
        "fetch_search_terms": partial(fetch_search_terms, **cred_kwargs),
        "fetch_device_performance": partial(fetch_device_performance, **cred_kwargs),
        "fetch_geo_performance": partial(fetch_geo_performance, **cred_kwargs),
        "fetch_ad_group_performance": partial(fetch_ad_group_performance, **cred_kwargs),
    }


@router.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    """Fetch data for selected connections, build brief, goal-driven LangChain synthesis."""
    if not req.connections:
        raise HTTPException(status_code=422, detail="At least one connection is required.")
    if "google_ads" not in req.connections:
        raise HTTPException(
            status_code=422,
            detail="Only google_ads is supported for now.",
        )
    if not req.date_from or not req.date_to:
        raise HTTPException(status_code=422, detail="date_from and date_to are required.")

    shim = ReportRequest(
        customer_id=req.customer_id,
        refresh_token=req.refresh_token,
        login_customer_id=req.login_customer_id,
    )
    customer_id = resolve_customer_id(request_customer_id=shim.customer_id)
    dt, cid, secret, rt = resolve_ads_credentials(request_refresh_token=shim.refresh_token)
    login = (req.login_customer_id or get_configs().google_ads_login_customer_id).strip()

    try:
        raw_payload = fetch_campaigns(
            customer_id=customer_id,
            developer_token=dt,
            client_id=cid,
            client_secret=secret,
            refresh_token=rt,
            date_from=req.date_from,
            date_to=req.date_to,
            account_name=req.account_name,
            currency_code=req.currency_code,
            login_customer_id=login,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not raw_payload.get("rows"):
        raise HTTPException(
            status_code=422,
            detail="No campaigns returned for this customer and date range.",
        )

    brief = build_brief(raw_payload, theme="paid_ads")
    brief_dict = brief.to_dict()

    synthesis_dict = None
    api_key, provider, model = _resolve_agent_config()
    if api_key:
        agent = GenerateAgent(
            api_key=api_key,
            provider=provider,
            model=model,
            temperature=1.0,
        )

        # Phase 1: Register goal-driven tools and fetch supplementary data
        fetch_fns = _build_fetch_fns(dt, cid, secret, rt, login)
        registered = agent.setup_tools_for_goal(goal=req.goal, fetch_fns=fetch_fns)
        supplementary = {}
        if registered:
            logger.info("Phase 1: fetching supplementary data for goal '%s'", req.goal.value)
            supplementary = await agent.fetch_supplementary_data(
                customer_id=customer_id,
                date_from=req.date_from,
                date_to=req.date_to,
                goal=req.goal,
                custom_goal=req.custom_goal,
                context=req.context,
            )

        # Phase 2: Synthesis with all collected data + business context
        biz_ctx = req.business_context.model_dump() if req.business_context else None
        synthesis = await agent.synthesize(
            goal=req.goal,
            custom_goal=req.custom_goal,
            context=req.context,
            brief_dict=brief_dict,
            raw_payload=raw_payload,
            supplementary=supplementary or None,
            business_context=biz_ctx,
        )

        # Apply LLM overrides to campaign actions, extract synthesis layer
        agent.apply_classification_overrides(brief_dict, synthesis)
        synthesis_dict = agent.extract_synthesis(synthesis)

    # Build unified envelope
    envelope = UnifiedReport(
        connectors_used=["google_ads"],
        briefs={"google_ads": brief_dict},
        synthesis=synthesis_dict,
        metadata=ReportMetadata(
            generated_at=datetime.now(timezone.utc).isoformat(),
            goal=req.goal.value,
            connectors_used=["google_ads"],
        ),
    )
    return envelope.model_dump()
