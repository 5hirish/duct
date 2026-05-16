"""Unified agent session API.

All agent types share the same session lifecycle:

  POST   /api/agents/{type}/sessions            → create session + start pipeline
  GET    /api/agents/{type}/sessions/{id}/stream → SSE (full session lifetime)
  POST   /api/agents/{type}/sessions/{id}/messages → unified chat & answer endpoint
  GET    /api/agents/{type}/sessions/{id}        → session state
  DELETE /api/agents/{type}/sessions/{id}        → close session

Discovery:
  GET    /api/agents             → list all agent specs
  GET    /api/agents/{type}      → single agent spec

Adding a new agent type:
  1. Register it in agents/registry.py
  2. Implement a _start_{type}_session(session_id, body_dict, emit_fn) async function here
  3. Wire it into _dispatch_start() below
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.audit.events import AuditEvent
from agents.audit.schema import AuditRequest
from agents.audit.v3.runner import (
    ClaudeAuditRunner,
    close_session,
    create_audit_session,
    get_session,
)
from agents.engines import PROVIDER_CONFIG_ATTR, resolve_engine, resolve_engine_model, resolve_engine_provider
from agents.registry import AgentType, AGENT_REGISTRY, get_spec, list_specs
from config import get_configs
from service.crawl.fetcher import SSRFError, validate_public_url
from service.pipeline import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

# Sessions older than this with no active SSE consumer are pruned.
_SESSION_TTL = 1800  # 30 minutes


@router.on_event("startup")
async def _start_session_pruner() -> None:
    asyncio.create_task(_prune_stale_sessions())


async def _prune_stale_sessions() -> None:
    import time
    while True:
        await asyncio.sleep(300)
        now = time.monotonic()
        stale = [
            sid for sid, session in list(
                __import__("agents.audit.v3.runner", fromlist=["_sessions"])._sessions.items()
            )
            if now - session.created_at > _SESSION_TTL
        ]
        for sid in stale:
            logger.info("agents: pruning stale session %s", sid)
            close_session(sid)


# ---------------------------------------------------------------------------
# Shared SSE helpers
# ---------------------------------------------------------------------------

async def _emit_to_queue(queue: asyncio.Queue, body: dict[str, Any]) -> None:
    body.setdefault("ts", now_iso())
    await queue.put(body)


async def _sse_stream(event_queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Read from event_queue and yield SSE frames. Runs until sentinel None received."""
    while True:
        try:
            payload = await asyncio.wait_for(event_queue.get(), timeout=15)
        except asyncio.TimeoutError:
            yield ": ping\n\n"
            continue
        if payload is None:  # sentinel — session closed
            break
        yield f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@router.get("")
async def list_agents() -> list[dict]:
    """List all registered agent types."""
    return [s.model_dump() for s in list_specs()]


@router.get("/{agent_type}")
async def get_agent(agent_type: str) -> dict:
    """Get the spec for one agent type."""
    spec = get_spec(agent_type)
    if not spec:
        raise HTTPException(404, f"Unknown agent type: {agent_type!r}")
    return spec.model_dump()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@router.post("/{agent_type}/sessions")
async def create_session(agent_type: str, request: Request) -> dict:
    """Create a session and start the agent pipeline.

    Body is agent-specific — validated against each agent's config schema.
    Returns {session_id, stream_url} immediately; pipeline runs in the background.
    Connect to stream_url to receive SSE events.
    """
    spec = get_spec(agent_type)
    if not spec:
        raise HTTPException(404, f"Unknown agent type: {agent_type!r}")
    if not spec.active:
        raise HTTPException(422, f"Agent {agent_type!r} is not yet available.")

    body = await request.json()
    session_id = str(uuid.uuid4())
    session = create_audit_session(session_id, agent_type)

    async def emit_fn(event_body: dict[str, Any]) -> None:
        event_body["agent_type"] = agent_type
        event_body["session_id"] = session_id
        await _emit_to_queue(session.event_queue, event_body)  # type: ignore[arg-type]

    # Dispatch to the correct pipeline
    await _dispatch_start(agent_type, session_id, body, emit_fn)

    stream_url = f"/api/agents/{agent_type}/sessions/{session_id}/stream"
    return {"session_id": session_id, "stream_url": stream_url, "agent_type": agent_type}


@router.get("/{agent_type}/sessions/{session_id}/stream")
async def stream_session(agent_type: str, session_id: str) -> StreamingResponse:
    """SSE stream for an active session. Stays open for the session lifetime."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found.")
    if session.agent_type != agent_type:
        raise HTTPException(404, f"Session {session_id!r} is not a {agent_type!r} session.")

    event_queue: asyncio.Queue = session.event_queue  # type: ignore[assignment]

    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _sse_stream(event_queue):
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
            "X-Agent-Session-Id": session_id,
        },
    )


# ---------------------------------------------------------------------------
# Unified message endpoint (chat + AskUserQuestion answers)
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    """Unified message sent by the user into an active session."""
    type: Literal["chat", "answer"]

    # For type="chat"
    content: str | list | None = None
    context_version_id: int | None = None   # which report version to use as context

    # For type="answer" (AskUserQuestion response)
    answers: dict[str, str] | None = None


@router.post("/{agent_type}/sessions/{session_id}/messages")
async def send_message(agent_type: str, session_id: str, msg: AgentMessage) -> dict:
    """Send a message into an active session.

    type="chat"   — follow-up question or image; queued to the agent's chat_queue.
    type="answer" — answer to a pending AskUserQuestion; resolves the answer_future.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found.")
    if session.agent_type != agent_type:
        raise HTTPException(404, f"Session {session_id!r} is not a {agent_type!r} session.")

    if msg.type == "answer":
        if msg.answers is None:
            raise HTTPException(422, "answers field required for type='answer'")
        fut = session.answer_future
        if not fut or getattr(fut, "done", lambda: True)():
            raise HTTPException(400, "No pending question for this session")
        try:
            fut.set_result(msg.answers)  # type: ignore[union-attr]
        except asyncio.InvalidStateError:
            raise HTTPException(409, "Question already answered")
        return {"status": "ok", "type": "answer"}

    # type == "chat"
    if msg.content is None:
        raise HTTPException(422, "content field required for type='chat'")

    # Inject report version context for audit agent
    content = _inject_report_context(session, msg.content, msg.context_version_id)
    await session.chat_queue.put({"role": "user", "content": content})  # type: ignore[attr-defined]
    return {"status": "queued", "type": "chat"}


def _inject_report_context(session: Any, content: str | list, version_id: int | None) -> str | list:
    """Prepend the selected report version as XML context for the chat agent."""
    versions = getattr(session, "report_versions", [])
    if not versions:
        return content
    try:
        v = versions[version_id] if version_id is not None else versions[-1]
    except IndexError:
        v = versions[-1]

    report = getattr(v, "report", None)
    if not report:
        return content

    ctx = (
        f"<working_report version='{v.version_id}' label='{v.label}'>\n"
        f"{report.model_dump_json(exclude={'html_report'})}\n"
        "</working_report>\n\n"
    )

    if isinstance(content, str):
        return ctx + content

    # List of content blocks — merge context into existing text block or prepend
    text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
    other_blocks = [b for b in content if not (isinstance(b, dict) and b.get("type") == "text")]
    combined_text = ctx + " ".join(b.get("text", "") for b in text_blocks)
    return [{"type": "text", "text": combined_text}] + other_blocks


# ---------------------------------------------------------------------------
# Session state + close
# ---------------------------------------------------------------------------

@router.get("/{agent_type}/sessions/{session_id}")
async def get_session_state(agent_type: str, session_id: str) -> dict:
    """Return session metadata and available report versions."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found.")
    if session.agent_type != agent_type:
        raise HTTPException(404, f"Session {session_id!r} is not a {agent_type!r} session.")

    versions = [
        {
            "version_id": v.version_id,
            "label": v.label,
            "created_at": v.created_at,
        }
        for v in getattr(session, "report_versions", [])
    ]
    return {
        "session_id": session_id,
        "agent_type": agent_type,
        "report_versions": versions,
        "has_pending_question": session.answer_future is not None,
    }


@router.delete("/{agent_type}/sessions/{session_id}")
async def delete_session(agent_type: str, session_id: str) -> dict:
    """Close a session and free all resources."""
    close_session(session_id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Agent-specific pipeline dispatchers
# ---------------------------------------------------------------------------

async def _dispatch_start(
    agent_type: str,
    session_id: str,
    body: dict,
    emit_fn: Any,
) -> None:
    """Route session creation to the correct agent pipeline."""
    if agent_type == AgentType.SEO_AUDIT:
        await _start_seo_audit(session_id, body, emit_fn)
    elif agent_type == AgentType.INSIGHTS:
        await _start_insights(session_id, body, emit_fn)
    else:
        raise HTTPException(501, f"Agent type {agent_type!r} is not yet implemented.")


async def _start_seo_audit(session_id: str, body: dict, emit_fn: Any) -> None:
    """Validate config and start the SEO audit pipeline as a background task."""
    try:
        req = AuditRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, f"Invalid seo-audit config: {exc}") from exc

    url = req.url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    try:
        validate_public_url(url)
    except SSRFError as exc:
        raise HTTPException(422, f"Invalid URL: {exc}") from exc

    cfg = get_configs()
    engine = resolve_engine(req.engine or "v3")
    provider = resolve_engine_provider(engine, cfg.generate_provider or None)
    model = resolve_engine_model(engine, provider, cfg.generate_model or None)
    api_key = getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""

    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not configured.")

    runner = ClaudeAuditRunner(
        api_key=api_key,
        provider=provider,
        model=model,
        effort=req.effort,
        adaptive_thinking=req.adaptive_thinking,
    )

    async def pipeline() -> None:
        try:
            await emit_fn({"event": AuditEvent.PIPELINE_STARTED, "status": "running", "url": url})
            await runner.run_pipeline(
                session_id=session_id,
                url=url,
                business_context=req.business_context,
                emit=emit_fn,
                max_blog_posts=req.max_blog_posts,
                user_preferences=req.user_preferences,
            )
            await emit_fn({"event": AuditEvent.PIPELINE_FINISHED, "status": "success"})
        except Exception as exc:
            logger.exception("seo-audit pipeline error for session %s", session_id)
            await emit_fn({"event": AuditEvent.PIPELINE_FAILED, "status": "error", "error": str(exc)})

    asyncio.create_task(pipeline())


async def _start_insights(session_id: str, body: dict, emit_fn: Any) -> None:
    """Placeholder — insights agent wired via the legacy /api/insights/generate/stream for now."""
    raise HTTPException(501, "Insights agent: use /api/insights/generate/stream (legacy) for now.")
