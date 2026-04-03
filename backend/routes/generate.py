"""Interactive brief generation (fetch + LLM synthesis, no disk write)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from agents.models import Provider, resolve_model, resolve_provider
from agents.reporter.agent import GenerateAgent
from config import get_configs
from service.google.fetch import fetch_campaigns
from service.google.brief import build_brief

from routes.google_ads_helpers import resolve_ads_credentials, resolve_customer_id
from routes.schemas import GenerateRequest, ReportRequest

if TYPE_CHECKING:
    from agents.models import ModelName

router = APIRouter(tags=["generate"])


def _resolve_agent_config() -> tuple[str, Provider, "ModelName"]:
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


@router.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    """Fetch data for selected connections, build brief, optional LangChain synthesis."""
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
    customer_id = resolve_customer_id(shim)
    dt, cid, secret, rt = resolve_ads_credentials(shim)
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

    api_key, provider, model = _resolve_agent_config()
    if api_key:
        agent = GenerateAgent(
            api_key=api_key,
            provider=provider,
            model=model,
            temperature=0.3,
        )
        synthesis = await agent.synthesize(
            goal=req.goal,
            context=req.context,
            brief_dict=brief_dict,
            raw_payload=raw_payload,
        )
        brief_dict = agent.merge_synthesis(brief_dict, synthesis)

    return brief_dict
