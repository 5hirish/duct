"""SEO Audit Agent routes.

Endpoints:
  POST /api/audit/run/stream          — start an audit session (SSE stream for lifetime of session)
  POST /api/audit/answer/{session_id} — submit AskUserQuestion answers while stream is paused
  POST /api/audit/chat/{session_id}   — send follow-up message or image into the session
  DELETE /api/audit/session/{session_id} — close session and cleanup
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agents.audit.events import AuditEvent, AuditStep, STEP_LABELS
from agents.audit.schema import (
    AuditAnswerRequest,
    AuditBusinessContext,
    AuditChatMessage,
    AuditRequest,
)
from agents.audit.v3.runner import ClaudeAuditRunner, close_session, get_session
from agents.engines import Engine, resolve_engine, resolve_engine_model, resolve_engine_provider, PROVIDER_CONFIG_ATTR
from service.crawl.fetcher import SSRFError, validate_public_url
from config import get_configs
from service.pipeline import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])

# Sessions older than this (seconds) with no active SSE consumer are pruned.
_SESSION_TTL = 1800  # 30 minutes
_session_created_at: dict[str, float] = {}  # session_id → creation timestamp


async def _prune_stale_sessions() -> None:
    """Background task: close sessions that have exceeded _SESSION_TTL.

    Runs every 5 minutes. Prevents unbounded memory growth when clients
    disconnect without calling DELETE /api/audit/session/{id}.
    """
    import time
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        now = time.monotonic()
        stale = [
            sid for sid, created in list(_session_created_at.items())
            if now - created > _SESSION_TTL
        ]
        for sid in stale:
            logger.info("audit: pruning stale session %s", sid)
            close_session(sid)
            _session_created_at.pop(sid, None)


@router.on_event("startup")  # type: ignore[attr-defined]
async def _start_pruner() -> None:
    asyncio.create_task(_prune_stale_sessions())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_agent_config(request_engine: str = "") -> tuple[str, Any, Any, Engine]:
    cfg = get_configs()
    engine = resolve_engine(request_engine or "v3")  # default v3
    provider = resolve_engine_provider(engine, cfg.generate_provider or None)
    model = resolve_engine_model(engine, provider, cfg.generate_model or None)
    api_key = getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""
    return api_key, provider, model, engine


async def _emit(queue: asyncio.Queue, body: dict[str, Any]) -> None:
    body.setdefault("ts", now_iso())
    await queue.put(body)


async def _stream_queue(
    queue: asyncio.Queue,
    finished: asyncio.Event,
) -> AsyncGenerator[str, None]:
    try:
        while not finished.is_set() or not queue.empty():
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        pass


# ---------------------------------------------------------------------------
# SSE audit stream
# ---------------------------------------------------------------------------

async def _run_audit_pipeline(
    session_id: str,
    req: AuditRequest,
    emit_fn: Any,
) -> None:
    try:
        api_key, provider, model, _ = _resolve_agent_config(req.engine)
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        await emit_fn({
            "event": AuditEvent.PIPELINE_STARTED,
            "session_id": session_id,
            "url": req.url,
            "status": "running",
        })

        await emit_fn({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.RESOLVE_URL,
            "label": STEP_LABELS[AuditStep.RESOLVE_URL],
            "status": "running",
        })

        url = req.url.strip()
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            validate_public_url(url)
        except SSRFError as exc:
            raise ValueError(f"Invalid URL: {exc}") from exc

        await emit_fn({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.RESOLVE_URL,
            "label": STEP_LABELS[AuditStep.RESOLVE_URL],
            "status": "success",
        })

        runner = ClaudeAuditRunner(api_key=api_key, provider=provider, model=model)
        report = await runner.run_pipeline(
            session_id=session_id,
            url=url,
            business_context=req.business_context,
            emit=emit_fn,
            max_blog_posts=req.max_blog_posts,
        )

        if report:
            await emit_fn({
                "event": AuditEvent.PIPELINE_FINISHED,
                "status": "success",
                "payload": report.model_dump(),
            })
        else:
            await emit_fn({
                "event": AuditEvent.PIPELINE_FAILED,
                "status": "error",
                "error": "Synthesis produced no report",
            })

    except Exception as exc:
        logger.exception("audit pipeline error for session %s", session_id)
        await emit_fn({
            "event": AuditEvent.PIPELINE_FAILED,
            "status": "error",
            "error": str(exc),
        })


@router.post("/audit/run/stream")
async def run_audit_stream(req: AuditRequest) -> StreamingResponse:
    """Start an SEO audit. Returns an SSE stream covering the full session lifetime."""
    import time
    session_id = str(uuid.uuid4())
    _session_created_at[session_id] = time.monotonic()

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def emit_fn(body: dict[str, Any]) -> None:
        await _emit(queue, body)

    async def worker() -> None:
        try:
            await _run_audit_pipeline(session_id, req, emit_fn)
        except Exception as exc:
            logger.exception("audit worker error")
            await emit_fn({"event": AuditEvent.PIPELINE_FAILED, "status": "error", "error": str(exc)})
        finally:
            # Don't set finished yet — session stays alive for chat
            # finished is only set when the session is explicitly closed
            pass

    asyncio.create_task(worker())

    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _stream_queue(queue, finished):
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            close_session(session_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Audit-Session-Id": session_id,
        },
    )


# ---------------------------------------------------------------------------
# AskUserQuestion answer
# ---------------------------------------------------------------------------

@router.post("/audit/answer/{session_id}")
async def submit_audit_answers(session_id: str, req: AuditAnswerRequest) -> dict:
    """Resolve a pending AskUserQuestion in the audit session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    fut = session.answer_future
    if not fut or getattr(fut, "done", lambda: True)():
        raise HTTPException(400, "No pending question for this session")
    try:
        fut.set_result(req.answers)  # type: ignore[union-attr]
    except asyncio.InvalidStateError:
        raise HTTPException(409, "Question already answered")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Continued chat
# ---------------------------------------------------------------------------

@router.post("/audit/chat/{session_id}")
async def send_chat_message(session_id: str, req: AuditChatMessage) -> dict:
    """Send a follow-up message (text or with images) into an active audit session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    # Inject the selected report version as context
    versions = session.report_versions
    if versions:
        idx = req.context_version_id if req.context_version_id is not None else -1
        try:
            v = versions[idx]
        except IndexError:
            v = versions[-1]
        ctx_header = (
            f"<working_report version='{v.version_id}' label='{v.label}'>\n"
            f"{v.report.model_dump_json()}\n"
            "</working_report>\n\n"
        )
    else:
        ctx_header = ""

    # Build enriched content
    if isinstance(req.content, str):
        content = ctx_header + req.content
    else:
        # List of content blocks — prepend context as first text block
        text_blocks = [b for b in req.content if isinstance(b, dict) and b.get("type") == "text"]
        other_blocks = [b for b in req.content if not (isinstance(b, dict) and b.get("type") == "text")]
        combined_text = ctx_header + " ".join(b.get("text", "") for b in text_blocks)
        content = [{"type": "text", "text": combined_text}] + other_blocks

    await session.chat_queue.put({"role": "user", "content": content})  # type: ignore[union-attr]
    return {"status": "queued"}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.delete("/audit/session/{session_id}")
async def close_audit_session(session_id: str) -> dict:
    """Close an audit session and free resources."""
    close_session(session_id)
    _session_created_at.pop(session_id, None)
    return {"status": "ok"}
