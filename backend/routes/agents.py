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
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from uuid import UUID

from agents.audit.events import AuditEvent
from agents.audit.schema import AuditRequest
from agents.audit.v3.runner import (
    ClaudeAuditRunner,
    close_session,
    create_audit_session,
    get_session,
)
from agents.content.persistence import (
    ConversationRecorder,
    archive_conversation,
    get_conversation,
    list_conversations,
    load_events,
    resolve_or_create_conversation,
)
from agents.content.schema import DraftPostRequest, PlanRequest
from agents.content.v3.runner import create_draft_session, create_plan_session
from agents.core import session as _core_session
from db.session import get_session as db_session
from agents.engines import PROVIDER_CONFIG_ATTR, resolve_engine, resolve_engine_model, resolve_engine_provider
from agents.registry import AgentType, get_spec, list_specs
from config import claude_oauth_available, get_configs
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
    while True:
        await asyncio.sleep(300)
        now = time.monotonic()
        # One shared registry across all agent types (agents/core/session.py).
        # Prune on INACTIVITY (last_activity), not total age: a session with a
        # live SSE consumer keeps refreshing last_activity via the keep-alive
        # ping, so a long-but-active run (e.g. a 30-min planning conversation
        # waiting on the user) is never hard-killed mid-stream.
        stale = [
            sid for sid, session in list(_core_session._sessions.items())
            if now - session.last_activity > _SESSION_TTL
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
        # default=str so payloads carrying UUIDs / datetimes / enums (content
        # events do) serialize instead of crashing the stream mid-flight.
        yield f"data: {json.dumps(payload, default=str)}\n\n"


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
    session = _create_session_for(agent_type, session_id, body)

    async def emit_fn(event_body: dict[str, Any]) -> None:
        event_body["agent_type"] = agent_type
        event_body["session_id"] = session_id
        await _emit_to_queue(session.event_queue, event_body)  # type: ignore[arg-type]

    # Dispatch to the correct pipeline
    await _dispatch_start(agent_type, session_id, body, emit_fn)

    stream_url = f"/api/agents/{agent_type}/sessions/{session_id}/stream"
    conversation_id = getattr(session, "conversation_id", None)
    return {
        "session_id": session_id,
        "stream_url": stream_url,
        "agent_type": agent_type,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


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
                # Each frame (data or keep-alive ping) proves the consumer is
                # still attached — refresh last_activity so the pruner measures
                # idle time, not total session age.
                _core_session.touch_session(session)
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

    # A user message (chat or answer) is unambiguous activity — keep the session
    # off the stale list while a human is interacting with it.
    _core_session.touch_session(session)

    recorder = getattr(session, "recorder", None)

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
        if recorder is not None:
            await recorder.record_answer(msg.answers)
        return {"status": "ok", "type": "answer"}

    # type == "chat"
    if msg.content is None:
        raise HTTPException(422, "content field required for type='chat'")

    # Persist the raw user text (before the XML working-context wrapper) so chat
    # history rehydrates as the user actually typed it.
    if recorder is not None:
        await recorder.record_user(msg.content)

    # Ground each follow-up in the session's current artifact so edits act on the
    # persisted state, not just the SDK process's (prunable) memory.
    content = _inject_working_context(session, msg.content, msg.context_version_id)
    await session.chat_queue.put({"role": "user", "content": content})  # type: ignore[attr-defined]
    return {"status": "queued", "type": "chat"}


def _inject_working_context(session: Any, content: str | list, version_id: int | None) -> str | list:
    """Prepend the session's current artifact as XML context for the chat agent.

    Audit/insights inject the selected (versioned) report; tiktok_studio injects
    the current plan/post straight from the DB. Grounding the model in the
    persisted artifact on every turn means a follow-up edit survives a session
    prune + reconnect (the SDK subprocess memory does not) and acts on the exact
    saved state, which tool calls (edit_slide / generate_image) may have changed.
    """
    if getattr(session, "report_versions", None):
        return _inject_report_context(session, content, version_id)
    if session.agent_type == AgentType.TIKTOK_STUDIO:
        ctx = _content_context_xml(session)
        if ctx:
            return _prepend_context(content, ctx)
    return content


def _prepend_context(content: str | list, ctx: str) -> str | list:
    """Prepend an XML context block to a chat message (str or content-block list)."""
    if isinstance(content, str):
        return ctx + content
    # List of content blocks — merge context into the text block(s), keep the rest.
    text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
    other_blocks = [b for b in content if not (isinstance(b, dict) and b.get("type") == "text")]
    combined_text = ctx + " ".join(b.get("text", "") for b in text_blocks)
    return [{"type": "text", "text": combined_text}] + other_blocks


def _inject_report_context(session: Any, content: str | list, version_id: int | None) -> str | list:
    """Prepend the selected report version as XML context for the chat agent."""
    versions = getattr(session, "report_versions", [])
    if not versions:
        return content
    # version_id is 1-based; find by matching field, not list index
    if version_id is not None:
        v = next((x for x in versions if x.version_id == version_id), versions[-1])
    else:
        v = versions[-1]

    report = getattr(v, "report", None)
    if not report:
        return content

    ctx = (
        f"<working_report version='{v.version_id}' label='{v.label}'>\n"
        f"{report.model_dump_json(exclude={'html_report'})}\n"
        "</working_report>\n\n"
    )
    return _prepend_context(content, ctx)


def _content_context_xml(session: Any) -> str:
    """Serialize the tiktok_studio session's current persisted plan or post as an
    XML context block. Returns '' when nothing is persisted yet (the first
    message before generation completes) so we never inject an empty wrapper.

    slides_html is excluded from posts: it is large and DERIVED from `slides`
    (the source of truth), the same reason audit excludes html_report.
    """
    from db.session import get_session as db_session
    from models.content import ContentPlan, ContentPost

    mode = getattr(session, "mode", "")
    plan_id = getattr(session, "plan_id", None)
    post_id = getattr(session, "post_id", None)
    try:
        with next(db_session()) as db:
            if mode == "plan_month" and plan_id is not None:
                plan = db.get(ContentPlan, plan_id)
                if plan is None:
                    return ""
                payload = {
                    "id": str(plan.id),
                    "name": plan.name,
                    "start_date": plan.start_date,
                    "character": plan.character,
                    "days": plan.days,
                }
                return (
                    f"<working_plan id='{plan.id}'>\n"
                    f"{json.dumps(payload, default=str)}\n"
                    "</working_plan>\n\n"
                )
            if mode == "draft_post" and post_id is not None:
                post = db.get(ContentPost, post_id)
                if post is None:
                    return ""
                payload = post.model_dump(exclude={"slides_html"})
                return (
                    f"<working_post id='{post.id}'>\n"
                    f"{json.dumps(payload, default=str)}\n"
                    "</working_post>\n\n"
                )
    except Exception:
        logger.warning("agents: content context injection failed for session %s", session.session_id, exc_info=True)
    return ""


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
# Persisted conversations (chat history / resume)
# ---------------------------------------------------------------------------

def _conversation_summary(conv) -> dict:
    return {
        "id": str(conv.id),
        "agent_type": conv.agent_type,
        "project_id": str(conv.project_id),
        "mode": conv.mode,
        "artifact_type": conv.artifact_type,
        "artifact_id": str(conv.artifact_id) if conv.artifact_id else None,
        "title": conv.title,
        "status": conv.status,
        "last_seq": conv.last_seq,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "last_active_at": conv.last_active_at.isoformat() if conv.last_active_at else None,
    }


@router.get("/{agent_type}/conversations")
async def list_agent_conversations(
    agent_type: str,
    project_id: str | None = None,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    """List conversations for an agent — used for resume lookup and history."""
    with next(db_session()) as db:
        convs = list_conversations(
            db,
            agent_type=agent_type,
            project_id=UUID(project_id) if project_id else None,
            artifact_type=artifact_type,
            artifact_id=UUID(artifact_id) if artifact_id else None,
            include_archived=include_archived,
        )
        return [_conversation_summary(c) for c in convs]


@router.get("/{agent_type}/conversations/{conversation_id}")
async def get_agent_conversation(agent_type: str, conversation_id: str) -> dict:
    """Conversation + its event log (ordered by seq) for UI rehydration."""
    with next(db_session()) as db:
        conv = get_conversation(db, UUID(conversation_id))
        if not conv or conv.agent_type != agent_type:
            raise HTTPException(404, f"Conversation {conversation_id!r} not found.")
        events = load_events(db, conv.id)
        return {
            "conversation": _conversation_summary(conv),
            "events": [
                {"seq": e.seq, "kind": e.kind, "data": e.data,
                 "created_at": e.created_at.isoformat() if e.created_at else None}
                for e in events
            ],
        }


@router.post("/{agent_type}/conversations/{conversation_id}/archive")
async def archive_agent_conversation(agent_type: str, conversation_id: str) -> dict:
    """Archive a conversation (start-fresh support) — frees the per-artifact
    active-conversation slot so a new one can be created."""
    with next(db_session()) as db:
        conv = get_conversation(db, UUID(conversation_id))
        if not conv or conv.agent_type != agent_type:
            raise HTTPException(404, f"Conversation {conversation_id!r} not found.")
        archive_conversation(db, conv.id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Agent-specific pipeline dispatchers
# ---------------------------------------------------------------------------

def _create_session_for(agent_type: str, session_id: str, body: dict):
    """Create + register the right session type for the agent (one shared
    registry; see agents/core/session.py).

    For tiktok_studio this also resolves-or-creates the persisted conversation
    (chat history / resume) and stamps it onto the session so the runner can
    re-prime from the DB and the recorder can persist each turn."""
    if agent_type == AgentType.TIKTOK_STUDIO:
        try:
            project_id = UUID(str(body["project_id"]))
        except Exception as exc:
            raise HTTPException(422, "tiktok_studio requires a valid project_id") from exc

        mode = body.get("mode", "plan_month")
        if mode not in ("plan_month", "draft_post"):
            raise HTTPException(422, f"invalid mode {mode!r}")

        # Resume / start-fresh inputs (all optional — omitting them is the
        # normal first-open path).
        def _as_uuid(v):
            return UUID(str(v)) if v else None

        # Resolve the conversation inside an open session and read every field we
        # need before the session closes (commit expires the ORM instance).
        # Persistence is best-effort: if the DB is unavailable the agent still
        # runs, just without chat history / resume (conv_* stay None).
        conv_id = conv_mode = conv_artifact_type = conv_artifact_id = None
        is_resume = False
        try:
            with next(db_session()) as db:
                conv, is_resume = resolve_or_create_conversation(
                    db,
                    agent_type=agent_type,
                    project_id=project_id,
                    mode=mode,
                    artifact_type=body.get("artifact_type"),
                    artifact_id=_as_uuid(body.get("artifact_id")),
                    conversation_id=_as_uuid(body.get("conversation_id")),
                    resume=bool(body.get("resume")),
                    start_fresh=bool(body.get("start_fresh")),
                )
                conv_id = conv.id
                conv_mode = conv.mode
                conv_artifact_type = conv.artifact_type
                conv_artifact_id = conv.artifact_id
        except Exception:
            logger.warning("agents: conversation persistence unavailable for %s — "
                           "running without history", session_id, exc_info=True)

        # The conversation's own mode wins on resume (the body's may be stale).
        if (conv_mode or mode) == "draft_post":
            session = create_draft_session(session_id, project_id, plan_id=_as_uuid(body.get("plan_id")))
        else:
            session = create_plan_session(session_id, project_id)

        if conv_id is not None:
            session.conversation_id = conv_id
            session.recorder = ConversationRecorder(conv_id)
            session.resume = is_resume
            # Derive the working artifact from the conversation so the runner's
            # _content_context_xml + PIPELINE_FINISHED see the right id on resume.
            if conv_artifact_type == "post" and conv_artifact_id:
                session.post_id = conv_artifact_id
            elif conv_artifact_type == "plan" and conv_artifact_id:
                session.plan_id = conv_artifact_id
        return session
    # audit + insights share the AuditSession shape.
    return create_audit_session(session_id, agent_type)


async def _dispatch_start(
    agent_type: str,
    session_id: str,
    body: dict,
    emit_fn: Any,
) -> None:
    """Route session creation to the correct agent pipeline."""
    if agent_type == AgentType.SEO_AUDIT:
        await _start_seo_audit(session_id, body, emit_fn)
    elif agent_type == AgentType.TIKTOK_STUDIO:
        await _start_tiktok_studio(session_id, body, emit_fn)
    elif agent_type == AgentType.INSIGHTS:
        await _start_insights(session_id, body, emit_fn)
    else:
        raise HTTPException(501, f"Agent type {agent_type!r} is not yet implemented.")


async def _start_tiktok_studio(session_id: str, body: dict, emit_fn: Any) -> None:
    """Start the Content Studio pipeline (plan_month or draft_post) as a
    background task, streaming to the shared session.event_queue. Reuses the
    plan/draft workers so the DB logic (Day resolution, post_id linkback) stays
    in one place."""
    # Imported lazily to avoid a route-module import cycle.
    from routes.content import _run_draft_worker, _run_plan_worker

    mode = body.get("mode", "plan_month")
    # `mode` is a dispatch discriminator, and the conversation/resume fields are
    # consumed by _create_session_for — strip them all before validating against
    # the extra="forbid" request models (which would otherwise reject the body).
    _control_fields = {"mode", "conversation_id", "resume", "start_fresh", "artifact_type", "artifact_id"}
    config = {k: v for k, v in body.items() if k not in _control_fields}

    # Persist the conversation by wrapping the emit callback (the runner already
    # emits every event — see agents/content/persistence.ConversationRecorder).
    session = get_session(session_id)
    recorder = getattr(session, "recorder", None) if session else None
    if recorder is not None:
        emit_fn = recorder.wrap_emit(emit_fn)
    if mode == "draft_post":
        try:
            req = DraftPostRequest.model_validate(config)
        except Exception as exc:
            raise HTTPException(422, f"Invalid draft_post config: {exc}") from exc
        coro = _run_draft_worker(session_id, req, emit_fn)
    elif mode == "plan_month":
        try:
            req = PlanRequest.model_validate(config)
        except Exception as exc:
            raise HTTPException(422, f"Invalid plan_month config: {exc}") from exc
        coro = _run_plan_worker(session_id, req.project_id, emit_fn)
    else:
        raise HTTPException(422, f"mode must be 'plan_month' or 'draft_post', got {mode!r}")

    task = asyncio.create_task(coro)
    session = get_session(session_id)
    if session:
        session.pipeline_task = task


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

    if not api_key and not claude_oauth_available():
        raise HTTPException(500, "ANTHROPIC_API_KEY is not configured.")

    runner = ClaudeAuditRunner(
        api_key=api_key,
        provider=provider,
        model=model,
        effort=req.effort,
        # Lead-magnet (teaser) audits never use extended thinking — keep the
        # first token fast regardless of what the request asked for.
        adaptive_thinking=req.adaptive_thinking and not req.lead_magnet,
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
                crawl_depth=req.crawl_depth,
                report_mode=req.report_mode,
                template_id=req.template_id,
                lead_magnet=req.lead_magnet,
            )
            await emit_fn({"event": AuditEvent.PIPELINE_FINISHED, "status": "success"})
        except Exception as exc:
            logger.exception("seo-audit pipeline error for session %s", session_id)
            await emit_fn({"event": AuditEvent.PIPELINE_FAILED, "status": "error", "error": str(exc)})

    task = asyncio.create_task(pipeline())
    session = get_session(session_id)
    if session:
        session.pipeline_task = task


async def _start_insights(session_id: str, body: dict, emit_fn: Any) -> None:
    """Placeholder — insights agent wired via the legacy /api/insights/generate/stream for now."""
    raise HTTPException(501, "Insights agent: use /api/insights/generate/stream (legacy) for now.")
