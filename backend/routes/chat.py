"""Streaming chat endpoint for insight discussion."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.engines import ProviderKeyRequired, resolve_job_run
from agents.tiers import Job
from models.auth import User
from service.auth import get_current_user, get_user_provider_keys
from service.model_settings import get_model_settings
from service.provider_keys import stored_keys_for

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
async def insight_chat(
    req: InsightChatRequest,
    user: User = Depends(get_current_user),
    user_keys: dict = Depends(get_user_provider_keys),
) -> StreamingResponse:
    """Stream an LLM reply grounded in the insight chat payload, on the caller's key.

    It used to stream from this instance's own key, with a prompt the caller
    writes, and a guest counts as signed in: anyone who opened /start had a
    free model on Duct's account. It resolves like every other run now
    (``resolve_job_run``): the caller's keys, this instance's only where
    ``allow_server_provider_keys()`` holds, else the 402 the browser handles.
    """
    settings = get_model_settings(user.id)
    run = resolve_job_run(
        Job.CHAT,
        engine_override=settings.engine,
        user_keys=user_keys,
        stored_keys=stored_keys_for(user.id),
        tier_map=settings.tiers,
        auto_fallback=settings.auto_fallback,
        log_prefix="insight chat",
    )
    if not run.api_key:
        # The one credential the gate returns without a key (the operator's
        # `claude` login) cannot drive a LangChain call.
        raise ProviderKeyRequired(
            run.provider,
            f"Chat needs a {run.provider.value} API key. Add your key in Settings → Providers.",
        )

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
        # Static per deployment (prompt-cache safe): the full connector gotcha
        # corpus plus the cross-platform reconciliation rules — the chat can be
        # asked about any connected source.
        f"{knowledge_block(('google_ads', 'ga4', 'gsc', 'apple_ads', 'meta', 'stripe', 'revenuecat', 'openai_ads', 'reconciliation'))}\n\n"
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
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        from agents.core.lc import resolve_chat_model

        llm = resolve_chat_model(run.provider, run.model, run.api_key, temperature=0.7)

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
        except Exception:  # noqa: BLE001
            # The provider's exception text is not ours to forward: it carries
            # request URLs, model config and, when a provider echoes the failing
            # request back, the API key itself. Log it whole, hand the browser a
            # reference it can quote at support instead.
            ref = uuid.uuid4().hex[:8]
            logger.exception("Chat stream failed (ref=%s)", ref)
            message = f"Something went wrong generating that reply. Reference: {ref}"
            yield f"data: {json.dumps({'error': message})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
