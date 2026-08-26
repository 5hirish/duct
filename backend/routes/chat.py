"""Streaming chat endpoint for insight discussion."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.models import Provider, get_api_key_kwargs, resolve_model, resolve_provider
from config import get_configs

logger = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])


class ChatMessage(BaseModel):
    role: str
    content: str


class InsightChatRequest(BaseModel):
    chat_payload: dict[str, Any]
    messages: list[ChatMessage] = Field(default_factory=list)
    message: str


@router.post("/chat")
async def insight_chat(req: InsightChatRequest) -> StreamingResponse:
    """Stream an LLM reply grounded in the insight chat payload."""
    cfg = get_configs()
    provider = resolve_provider(cfg.generate_provider or None)
    model = resolve_model(cfg.generate_model or None, provider)

    cp = req.chat_payload
    findings = cp.get("findings", [])[:8]
    campaigns = cp.get("campaigns", [])[:10]
    findings_block = "\n".join(
        f"- [{item.get('category', '?').upper()}] {item.get('title', '')}: {item.get('impact', '')}"
        for item in findings
    )
    campaigns_block = "\n".join(
        f"- {item.get('name')}: spend={item.get('spend')}, roas={item.get('roas')}, action={item.get('action')}"
        for item in campaigns
    )
    from agents.knowledge import knowledge_block

    system = (
        "You are a marketing analytics assistant helping the user understand and act on "
        "their insight data. Answer questions grounded in the data provided. "
        "Be concise and specific, and cite concrete numbers when relevant. "
        "If you suggest a change, explain which metric should improve and why.\n\n"
        f"{knowledge_block(('google_ads', 'ga4', 'gsc'))}\n\n"
        f"INSIGHT CONTEXT:\n{cp.get('summary_text', '')}\n\n"
        f"Goal: {cp.get('goal', 'unknown')}\n"
        f"Account: {cp.get('account', {}).get('name', 'unknown')}\n"
        f"Date window: {cp.get('date_window', {}).get('current', {})}\n\n"
        f"KPIs: spend={cp.get('kpis', {}).get('spend')}, "
        f"conversions={cp.get('kpis', {}).get('conversions')}, "
        f"cpa={cp.get('kpis', {}).get('cpa')}, roas={cp.get('kpis', {}).get('roas')}\n\n"
        f"Findings ({len(cp.get('findings', []))} total):\n"
        f"{findings_block}\n\n"
        f"Campaigns:\n{campaigns_block}"
    )

    history = [{"role": msg.role, "content": msg.content} for msg in req.messages]
    history.append({"role": "user", "content": req.message})

    async def stream_response():
        from langchain.chat_models import init_chat_model
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        key_map = {
            Provider.OPENAI: cfg.openai_api_key,
            Provider.GOOGLE_GENAI: cfg.gemini_api_key,
            Provider.ANTHROPIC: cfg.anthropic_api_key,
        }
        api_key = key_map.get(provider, "") or ""
        api_key_kwargs = get_api_key_kwargs(provider, api_key)

        llm = init_chat_model(
            model=model.value,
            model_provider=provider.value,
            temperature=0.7,
            **api_key_kwargs,
        )

        lc_messages = [SystemMessage(content=system)]
        for msg in history[:-1]:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            else:
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=req.message))

        try:
            async for chunk in llm.astream(lc_messages):
                token = chunk.content
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat stream failed")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
