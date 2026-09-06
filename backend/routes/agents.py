"""Unified agent session API.

All agent types share the same session lifecycle:

  POST   /api/agents/{type}/sessions            → create session + start pipeline
  GET    /api/agents/{type}/sessions/{id}/stream → SSE (full session lifetime)
  POST   /api/agents/{type}/sessions/{id}/messages → unified chat & answer endpoint
  GET    /api/agents/{type}/sessions/{id}        → session state
  DELETE /api/agents/{type}/sessions/{id}        → close session

Persisted conversations (chat history / resume):
  GET    /api/agents/{type}/conversations/{id}       → transcript for rehydration
  GET    /api/agents/{type}/conversations/{id}/state → what its thread is doing:
                                                        paused (and on what), unfinished, idle

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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from uuid import UUID

from agents.audit.events import AuditEvent
from agents.audit.schema import AuditRequest
from agents.audit.crawl import create_audit_session
from agents.audit.v1.runner import LangChainAuditRunner
from agents.audit.v3.runner import ClaudeAuditRunner
from agents.core.session import close_session, get_session
from agents.content.persistence import (
    ConversationRecorder,
    archive_conversation,
    build_reprime_context,
    get_conversation,
    list_conversations,
    load_events,
    resolve_or_create_conversation,
)
from agents.content.schema import DraftPostRequest, PlanRequest
from agents.content.v1.runner import create_draft_session, create_plan_session
from agents.insights.schema import InsightsRequest, create_insights_session
from agents.insights.setup import (
    InsightsSetupError,
    memory_blocks as insights_memory_blocks,
    resolve_run as resolve_insights_run,
)
from agents.core import session as _core_session
from agents.core.context import format_business_context
from agents.core.events import AgentEvent, StepStatus
from agents.core.errors import error_payload
from agents.core.session import CLIENT_MESSAGE_ID
from db.session import get_session as db_session
from agents.engines import (
    Engine,
    resolve_engine,
    resolve_engine_model,
    resolve_engine_provider,
    resolve_provider_key,
)
from agents.registry import AgentType, get_spec, list_specs
from config import get_configs
from models.auth import User
from service.artifact_store import (
    ArtifactPersister,
    artifacts_for_conversation,
    load_report_as_versioned,
)
from service.auth import get_current_user, get_current_user_optional, get_user_provider_keys
from service.crawl.fetcher import SSRFError, validate_public_url
from service.lead_access import lead_token_is_live
from service.membership import accessible_projects, get_project_for_user, member_role
from service.memory import (
    build_memory_context,
    seed_user_preferences,
    touch_recall,
)
from service.memory_consolidation import schedule_consolidation
from service.provider_keys import stored_keys_for
from utils.dates import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

# Sessions older than this with no active SSE consumer are pruned.
_SESSION_TTL = 1800  # 30 minutes

# When a stream disconnects we DON'T kill the session immediately — the run keeps
# going and events buffer in its queue, giving the client this long to reconnect
# and re-attach to the SAME live session (transient network blips, tab refresh).
# The inactivity pruner (_SESSION_TTL) is the longer backstop.
_RECONNECT_GRACE = 60  # seconds


def _close_and_consolidate(session_id: str) -> None:
    """Close a session and fold what it established into project memory.

    The consolidation pass is where a session's durable conclusions get written
    down — the ones the agent never paused to record with RememberFact. Reading
    the conversation id *before* closing matters: close_session drops the
    session from the registry. Fire-and-forget, and a no-op without a
    conversation to read.
    """
    session = get_session(session_id)
    conversation_id = getattr(session, "conversation_id", None) if session else None
    # A session the user asked not to be remembered is not consolidated either —
    # otherwise the "don't remember this" promise would be broken at close time,
    # which is exactly when it matters.
    if session is not None and getattr(session, "memory_off", False):
        conversation_id = None
    # Before the run is cancelled: a turn still in flight is recorded as
    # cancelled, so the list says "Stopped" and the transcript ends with why.
    recorder = getattr(session, "recorder", None) if session else None
    if recorder is not None:
        try:
            recorder.close()
        except Exception:  # noqa: BLE001 - never let bookkeeping block a close
            logger.debug("agents: recorder close failed for %s", session_id, exc_info=True)
    close_session(session_id)
    schedule_consolidation(conversation_id)


def _cancel_grace(session) -> None:
    """A consumer (re)connected — cancel any pending grace-close timer."""
    grace = getattr(session, "grace_task", None)
    if grace is not None and not grace.done():
        grace.cancel()
    if session is not None:
        session.grace_task = None


def _schedule_grace_close(session_id: str) -> None:
    """A consumer disconnected — close the session only if nobody reconnects
    within _RECONNECT_GRACE. A reconnect cancels this via _cancel_grace."""
    session = get_session(session_id)
    if session is None:
        return
    _cancel_grace(session)

    async def _close_after_grace() -> None:
        await asyncio.sleep(_RECONNECT_GRACE)  # cancelled if a consumer reconnects
        s = get_session(session_id)
        if s is not None:
            s.grace_task = None  # past the wait — don't let close_session re-cancel us
            logger.info("agents: reconnect grace elapsed; closing session %s", session_id)
            _close_and_consolidate(session_id)

    session.grace_task = asyncio.create_task(_close_after_grace())


# Started from the app lifespan in server.py (FastAPI's lifespan disables
# router-level on_event hooks, so all startup tasks are launched centrally).
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
            _close_and_consolidate(sid)


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

def _owned_session(session_id: str, agent_type: str, user: User | None):
    """The session, if this caller may drive it. 404 otherwise.

    A session is in-memory and not always project-scoped, so this is an
    ownership check rather than the membership check a conversation gets, and
    it reads whichever handle the creator left:

    - ``user_id`` — set by ``create_session`` from the Bearer token. Must match.
    - ``project_id`` — the legacy ``/api/content/*/stream`` entry points create
      sessions directly and never set ``user_id``, so fall back to membership.
    - neither — an anonymous lead-magnet audit. Nothing in it belongs to
      anyone, and there is no signed-in caller to compare against.

    Session ids are unguessable, but unguessable is not a permission: an id
    reaches a log, a shared URL, a Sentry breadcrumb. It should not also be
    the only thing standing between a stranger and someone else's live agent.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id!r} not found.")
    if session.agent_type != agent_type:
        raise HTTPException(404, f"Session {session_id!r} is not a {agent_type!r} session.")

    owner_id = getattr(session, "user_id", None)
    if owner_id is not None:
        if user is None or user.id != owner_id:
            raise HTTPException(404, f"Session {session_id!r} not found.")
        return session

    project_id = getattr(session, "project_id", None)
    if project_id is not None:
        if user is None:
            raise HTTPException(404, f"Session {session_id!r} not found.")
        with next(db_session()) as db:
            if member_role(project_id, user.id, db) is None:
                raise HTTPException(404, f"Session {session_id!r} not found.")
    return session


def _require_caller(agent_type: str, body: dict, user: User | None) -> None:
    """Every agent run needs someone it can be charged to. Mutates ``body``.

    Starting a session spends model tokens — a full crawl, enrichment and
    synthesis for an audit; a plan or a draft for content. The route used to
    take an optional user, so the only thing between the open internet and an
    unbounded provider bill was ``X-API-Key``, which ships in the browser
    bundle. A key everyone has is not a payer.

    One anonymous run survives, because it is the product: the public SEO-audit
    teaser. That flow is not really anonymous — the marketing site captures an
    email behind Cloudflare Turnstile and
    ``POST /api/lead-magnet/submit`` issues a 24-hour token — so it presents
    that token instead of a session, and the run becomes attributable to a lead
    row either way.

    The token is consumed here and removed from the body: nothing downstream
    needs it, ``AuditRequest`` forbids unknown fields, and a credential that
    stops travelling is one fewer thing to keep out of a log or a Sentry
    breadcrumb.
    """
    token = str(body.pop("lead_token", "") or "")
    if user is not None:
        return
    if agent_type == AgentType.SEO_AUDIT and body.get("lead_magnet"):
        if lead_token_is_live(token):
            return
        raise HTTPException(401, "This audit link has expired — request a new one.")
    raise HTTPException(401, "Sign in to run an agent.")


def _scope_body_to_authorized_project(agent_type: str, body: dict, user: User | None) -> None:
    """Strip project scope the caller has not proven they may use. Mutates ``body``.

    ``project_id`` arrives in the request body, and the body is not evidence.
    Every project-scoped capability an agent gets — the content MCP server's
    brand context, plans, posts, assets and PublishPost; the audit and insights
    artifact stores; project memory — is keyed off it, so an unchecked id is a
    cross-tenant read *and* write. Project ids are UUID4 and not enumerable, but
    they are not secrets either: they sit in app URLs and in the hands of every
    current and former collaborator.

    The two agents that were already careful check membership downstream
    (``_start_seo_audit`` via ``member_role``, ``_start_insights`` via
    ``resolve_insights_run``). The content agent had no such check, and neither
    did conversation resolution. Doing it here means a fourth agent inherits the
    gate instead of having to remember it.

    Unauthorized scope is handled two ways, deliberately:

    * **tiktok_studio** — 404. Project scope is mandatory there (the session is
      built from it), so there is no degraded mode to fall back to. 404 rather
      than 403 matches ``get_project_for_user``: a stranger must not learn that
      a project id is real.
    * **everything else** — drop the scope and carry on unpersisted, which is
      exactly what an audit or brief already does for a local-only project id.
      Rejecting instead would break a signed-in user whose freshly created local
      project has not finished syncing to the backend yet.

    A missing or non-UUID ``project_id`` is left alone: downstream already reads
    that as "run unscoped", and tiktok_studio still answers 422 for it.
    """
    raw = body.get("project_id")
    if raw in (None, ""):
        return
    try:
        project_id = UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return  # local-only project ids aren't UUIDs — already treated as unscoped

    if user is not None:
        with next(db_session()) as db:
            if member_role(project_id, user.id, db) is not None:
                return

    if agent_type == AgentType.TIKTOK_STUDIO:
        raise HTTPException(404, "Project not found")

    logger.warning(
        "agents: caller %s may not use project %s — %s runs unscoped",
        user.id if user else "anonymous", project_id, agent_type,
    )
    # The conversation controls only mean anything alongside a project, and a
    # conversation_id is resolved without a project check of its own — so they
    # go with it rather than being left to address someone else's transcript.
    for key in ("project_id", "conversation_id", "resume", "start_fresh",
                "artifact_type", "artifact_id"):
        body.pop(key, None)


@router.post("/{agent_type}/sessions")
async def create_session(
    agent_type: str,
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    user_keys: dict = Depends(get_user_provider_keys),
) -> dict:
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
    # Two gates, in this order. First: is there anyone to charge this run to?
    # Then: may they use the project scope they asked for? Both run before
    # anything reads the body — the session builder, the conversation resolver
    # and every tool downstream all trust it.
    _require_caller(agent_type, body, user)
    _scope_body_to_authorized_project(agent_type, body, user)
    session_id = str(uuid.uuid4())
    session = _create_session_for(agent_type, session_id, body)
    # Signed-in creator (optional — API-key-only callers get None). Downstream
    # features (artifact persistence, execution proposals) key off this.
    session.user_id = user.id if user else None

    async def emit_fn(event_body: dict[str, Any]) -> None:
        event_body["agent_type"] = agent_type
        event_body["session_id"] = session_id
        await _emit_to_queue(session.event_queue, event_body)  # type: ignore[arg-type]

    # Dispatch to the correct pipeline
    await _dispatch_start(agent_type, session_id, body, emit_fn, user_keys=user_keys)

    stream_url = f"/api/agents/{agent_type}/sessions/{session_id}/stream"
    conversation_id = getattr(session, "conversation_id", None)
    return {
        "session_id": session_id,
        "stream_url": stream_url,
        "agent_type": agent_type,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


@router.get("/{agent_type}/sessions/{session_id}/stream")
async def stream_session(
    agent_type: str,
    session_id: str,
    user: User | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """SSE stream for an active session. Stays open for the session lifetime."""
    session = _owned_session(session_id, agent_type, user)

    event_queue: asyncio.Queue = session.event_queue  # type: ignore[assignment]

    # A (re)connection arrived in time — cancel any pending grace-close so a
    # reconnect re-attaches to the SAME live run (events buffered in the queue
    # while disconnected are delivered now).
    _cancel_grace(session)

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
            # Don't tear down on a transient disconnect — keep the run alive for
            # a grace window so the client can reconnect. The pipeline keeps
            # streaming into the queue; if nobody returns, _close_after_grace
            # frees everything. A terminal event (sentinel None) ends the
            # _sse_stream loop normally; schedule grace either way.
            _schedule_grace_close(session_id)

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

    # For type="answer" — the reply to whatever the session is parked on.
    # One channel for all three pause kinds (AskUserQuestion, connection
    # required, account selection); the event told the client which card to
    # render, and the shape of the answer follows from that:
    #   questions_required          -> {"<question>": "<answer>", ...}
    #   connection_required         -> {"connected": true} | {"skipped": true}
    #   account_selection_required  -> {"account_id": "...", "account_name": "..."}
    # Values are Any rather than str because two of those carry booleans.
    answers: dict[str, Any] | None = None
    # Which pause this answers, when the run is parked on a checkpointed
    # interrupt (the event carried it). Two tools can pause in the same turn —
    # an account for GA4 and one for GSC — and each is resumed by its own id.
    # Omitted, the only pending pause is assumed; a Future-bridged session has
    # no ids at all.
    interrupt_id: str | None = None
    # Stamped by the client on a chat message so the USER_INPUT_CONSUMED event
    # can name the row it releases. Optional: older clients send none.
    client_message_id: str | None = None


@router.post("/{agent_type}/sessions/{session_id}/messages")
async def send_message(
    agent_type: str,
    session_id: str,
    msg: AgentMessage,
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    """Send a message into an active session.

    type="chat"   — follow-up question or image; queued to the agent's chat_queue.
    type="answer" — the reply to whatever the session is parked on. Two ways a
                    run parks (agents/core/session.py): a checkpointed pause is
                    resumed by queueing a ``{"resume": {id: answers}}`` the
                    runner turns into a LangGraph Command; a Future-bridged one
                    is resolved in place. The client cannot tell which.
    """
    session = _owned_session(session_id, agent_type, user)

    # A user message (chat or answer) is unambiguous activity — keep the session
    # off the stale list while a human is interacting with it.
    _core_session.touch_session(session)

    recorder = getattr(session, "recorder", None)
    pending = getattr(session, "pending_pauses", None) or {}

    if msg.type == "answer":
        if msg.answers is None:
            raise HTTPException(422, "answers field required for type='answer'")
        if pending:
            interrupt_id = msg.interrupt_id or next(iter(pending))
            if interrupt_id not in pending:
                raise HTTPException(409, "That question has already been answered")
            # Popped here, not when the turn ends: a second POST for the same
            # id in the gap would otherwise queue a resume for nothing.
            pending.pop(interrupt_id, None)
            await session.chat_queue.put({"resume": {interrupt_id: msg.answers}})  # type: ignore[attr-defined]
            if recorder is not None:
                await recorder.record_answer(msg.answers)
            return {"status": "queued", "type": "answer"}
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

    # First message after a resume: prepend the restored conversation context
    # (summary + recent turns) so the agent answers WITH history — there was no
    # greeting turn to carry it. One-time; cleared after injecting.
    if getattr(session, "needs_reprime", False):
        primer = getattr(session, "resume_primer", "") or ""
        if primer:
            content = _prepend_context(content, primer)
        session.needs_reprime = False

    item: dict = {"role": "user", "content": content}
    if msg.client_message_id:
        item[CLIENT_MESSAGE_ID] = msg.client_message_id

    # A message while the agent is busy — mid-turn, or parked on a card — is
    # never refused. A harness that can steer takes it at its next model call
    # (after the tool result a parked thread is waiting on); the others hold it
    # for the next turn. The client marks the row "queued" until the
    # USER_INPUT_CONSUMED event clears it.
    busy = bool(pending) or getattr(session, "turn_active", False)
    steer_queue = getattr(session, "steer_queue", None)
    if busy and steer_queue is not None:
        await steer_queue.put(item)
        return {"status": "queued", "type": "chat", "delivery": "steer"}
    await session.chat_queue.put(item)  # type: ignore[attr-defined]
    return {"status": "queued", "type": "chat", "delivery": "queue" if busy else "turn"}


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
async def get_session_state(
    agent_type: str,
    session_id: str,
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    """Return session metadata and available report versions."""
    session = _owned_session(session_id, agent_type, user)

    versions = [
        {
            "version_id": v.version_id,
            "label": v.label,
            "created_at": v.created_at,
        }
        for v in getattr(session, "report_versions", [])
    ]
    pending = list((getattr(session, "pending_pauses", None) or {}).values())
    parked_on = getattr(session, "parked_on", None)
    if not pending and parked_on and session.answer_future is not None:
        pending = [parked_on]
    return {
        "session_id": session_id,
        "agent_type": agent_type,
        "report_versions": versions,
        "has_pending_question": bool(pending) or session.answer_future is not None,
        # The pauses the run is parked on, whichever way it parked — what a
        # client that reattaches needs in order to put the card back on screen.
        "pending": pending,
    }


@router.delete("/{agent_type}/sessions/{session_id}")
async def delete_session(
    agent_type: str,
    session_id: str,
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    """Close a session, free its resources, and consolidate what it established.

    Idempotent and uniform, like the content route: closing an id that has
    already gone is not an error, and a session the caller does not own is
    quietly left alone rather than 404'd — a teardown call should not double as
    a way to find out whose sessions are live.
    """
    try:
        _owned_session(session_id, agent_type, user)
    except HTTPException:
        return {"status": "ok"}
    _close_and_consolidate(session_id)
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
        # What the run is doing (RunStatus) and, when it stopped on a failure,
        # the same {code, retryable, error} the live client was shown.
        "run_status": conv.run_status,
        "run_error": conv.run_error,
        "pinned": conv.pinned,
        "last_seq": conv.last_seq,
        "meta": conv.meta or {},
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "last_active_at": conv.last_active_at.isoformat() if conv.last_active_at else None,
    }


# The router is mounted behind `validate_api_key` alone, and that key ships to
# the browser as NEXT_PUBLIC_DUCT_API_KEY. It proves "this is the Duct app",
# never "this is that conversation's owner" — so it is not a boundary between
# tenants and cannot be used as one. Every conversation carries a non-null
# project_id, and project access is membership, so that is what the endpoints
# below check. This is the same gate artifacts.py applies to the documents a
# conversation produces; the transcripts had simply never been given one.


def _conversation_for_user(db: Session, user: User, agent_type: str, conversation_id: str):
    """Load a conversation the caller belongs to, or 404.

    404 rather than 403 for a non-member, matching `get_project_for_user`: a
    stranger must not be able to tell a real conversation id from a made-up
    one. A malformed id is the same answer for the same reason.
    """
    try:
        conv_uuid = UUID(conversation_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(404, f"Conversation {conversation_id!r} not found.") from None
    conv = get_conversation(db, conv_uuid)
    if not conv or conv.agent_type != agent_type:
        raise HTTPException(404, f"Conversation {conversation_id!r} not found.")
    get_project_for_user(conv.project_id, user, db)
    return conv


@router.get("/{agent_type}/conversations")
async def list_agent_conversations(
    agent_type: str,
    project_id: str | None = None,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    include_archived: bool = False,
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List conversations for an agent — used for resume lookup and history.

    Scoped to the caller either way: a named project has to be one they belong
    to, and an unfiltered call spans their own projects instead of every
    tenant's. The unfiltered shape is what made this the widest hole of the
    four — it enumerated ids that `GET .../{id}` would then read out in full.
    """
    with next(db_session()) as db:
        if project_id:
            try:
                scope = [UUID(project_id)]
            except (ValueError, AttributeError, TypeError):
                raise HTTPException(422, f"Invalid project_id {project_id!r}.") from None
            get_project_for_user(scope[0], user, db)  # 404 when not a member
        else:
            scope = [p.id for p in accessible_projects(user, db)]
        convs = list_conversations(
            db,
            agent_type=agent_type,
            project_ids=scope,
            artifact_type=artifact_type,
            artifact_id=UUID(artifact_id) if artifact_id else None,
            include_archived=include_archived,
        )
        return [_conversation_summary(c) for c in convs]


@router.get("/{agent_type}/conversations/{conversation_id}")
async def get_agent_conversation(
    agent_type: str,
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Conversation + its event log (ordered by seq) for UI rehydration.

    The event log is the whole transcript — every prompt, answer and tool
    result — which makes this the most sensitive of the four.
    """
    with next(db_session()) as db:
        conv = _conversation_for_user(db, user, agent_type, conversation_id)
        events = load_events(db, conv.id)
        return {
            "conversation": _conversation_summary(conv),
            "events": [
                {"seq": e.seq, "kind": e.kind, "data": e.data,
                 "created_at": e.created_at.isoformat() if e.created_at else None}
                for e in events
            ],
        }


@router.get("/{agent_type}/conversations/{conversation_id}/state")
async def get_agent_conversation_state(
    agent_type: str,
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """What the conversation's durable thread is doing right now.

    ``paused`` (with the pauses, so the card can be rendered before any session
    exists), ``unfinished`` (a run was cut mid-turn and will continue on
    resume), ``idle``, or ``unsupported`` for an agent whose state lives only in
    a process — the Claude Agent SDK audit runner keeps no thread to inspect.
    """
    with next(db_session()) as db:
        conv = _conversation_for_user(db, user, agent_type, conversation_id)
        conv_id = conv.id
        run = {"run_status": conv.run_status, "run_error": conv.run_error}
    # The key is never used: inspection builds the graph on a placeholder model.
    if agent_type == AgentType.INSIGHTS:
        from agents.insights.v1.runner import AutonomousInsightsRunner

        return {**(await AutonomousInsightsRunner(api_key="").thread_state(conv_id)), **run}
    if agent_type == AgentType.TIKTOK_STUDIO:
        from agents.content.v1.runner import ContentRunner

        return {**(await ContentRunner(api_key="").thread_state(conv_id)), **run}
    return {"status": "unsupported", "pauses": [], "todos": [], **run}


class ConversationPatch(BaseModel):
    """What a user may change about a conversation from a list view.

    Deliberately not the transcript: events are append-only, and a title is a
    label rather than a rewrite of what happened.
    """

    pinned: bool | None = None
    title: str | None = None


@router.patch("/{agent_type}/conversations/{conversation_id}")
async def patch_agent_conversation(
    agent_type: str,
    conversation_id: str,
    body: ConversationPatch,
    user: User = Depends(get_current_user),
) -> dict:
    """Pin or rename a conversation. Pinning floats it to the top of its list
    and does nothing else — see models/artifact.py for the same flag on the
    documents a conversation produces.
    """
    with next(db_session()) as db:
        conv = _conversation_for_user(db, user, agent_type, conversation_id)
        if body.pinned is not None:
            conv.pinned = bool(body.pinned)
        if body.title is not None:
            conv.title = body.title.strip()[:200]
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return _conversation_summary(conv)


@router.post("/{agent_type}/conversations/{conversation_id}/archive")
async def archive_agent_conversation(
    agent_type: str,
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Archive a conversation (start-fresh support) — frees the per-artifact
    active-conversation slot so a new one can be created."""
    with next(db_session()) as db:
        conv = _conversation_for_user(db, user, agent_type, conversation_id)
        archive_conversation(db, conv.id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Agent-specific pipeline dispatchers
# ---------------------------------------------------------------------------

def _as_uuid(v):
    return UUID(str(v)) if v else None


def _create_session_for(agent_type: str, session_id: str, body: dict):
    """Create + register the right session type for the agent (one shared
    registry; see agents/core/session.py).

    For tiktok_studio and audit_seo this also resolves-or-creates the persisted
    conversation (chat history / resume) and stamps it onto the session so the
    runner can re-prime from the DB and the recorder can persist each turn."""
    if agent_type == AgentType.SEO_AUDIT:
        return _create_audit_session_with_conversation(agent_type, session_id, body)
    if agent_type == AgentType.INSIGHTS:
        return _create_insights_session_with_conversation(agent_type, session_id, body)
    if agent_type == AgentType.TIKTOK_STUDIO:
        try:
            project_id = UUID(str(body["project_id"]))
        except Exception as exc:
            raise HTTPException(422, "tiktok_studio requires a valid project_id") from exc

        mode = body.get("mode", "plan_month")
        if mode not in ("plan_month", "draft_post"):
            raise HTTPException(422, f"invalid mode {mode!r}")

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
    return create_audit_session(session_id, agent_type)


def _create_audit_session_with_conversation(agent_type: str, session_id: str, body: dict):
    """Audit session with persisted-conversation plumbing.

    Conversation persistence only engages for project-scoped, non-lead-magnet
    audits — anonymous/teaser audits stay fully ephemeral. Unlike tiktok, no
    workspace artifact binding is set: an audit conversation can produce many
    artifacts, and the linkage lives on artifacts.conversation_id instead.
    Best-effort throughout: a DB failure means the audit runs without history."""
    session = create_audit_session(session_id, agent_type)
    if body.get("lead_magnet"):
        return session
    try:
        project_id = _as_uuid(body.get("project_id"))
    except Exception:
        project_id = None  # local-only project ids aren't UUIDs — run unpersisted
    if project_id is None:
        return session

    try:
        with next(db_session()) as db:
            conv, is_resume = resolve_or_create_conversation(
                db,
                agent_type=agent_type,
                project_id=project_id,
                mode=str(body.get("report_mode", "freehand")),
                conversation_id=_as_uuid(body.get("conversation_id")),
                resume=bool(body.get("resume")),
                start_fresh=bool(body.get("start_fresh")),
            )
            # Title + audited URL power the "Previous audits" list and give a
            # resume enough to rebuild the session without its artifact.
            url = str(body.get("url") or "").strip()
            if url and not conv.title:
                conv.title = f"SEO audit — {url}"
                conv.meta = {**(conv.meta or {}), "url": url}
                db.add(conv)
                db.commit()
            session.conversation_id = conv.id
            session.recorder = ConversationRecorder(conv.id)
            session.resume = is_resume
    except Exception:
        logger.warning(
            "agents: conversation persistence unavailable for audit %s — "
            "running without history", session_id, exc_info=True,
        )
    return session


def _create_insights_session_with_conversation(agent_type: str, session_id: str, body: dict):
    """Insights session with persisted-conversation plumbing.

    Same contract as the audit variant: conversation persistence engages only
    for project-scoped sessions, a non-UUID (local-only) project id runs
    unpersisted, and every failure degrades to "runs without history" rather
    than failing the session. Insights conversations bind no workspace artifact
    — one conversation can produce several briefs, and the link lives on
    ``artifacts.conversation_id``.
    """
    session = create_insights_session(session_id, agent_type)
    try:
        project_id = _as_uuid(body.get("project_id"))
    except Exception:
        project_id = None  # local-only project ids aren't UUIDs — run unpersisted
    if project_id is None:
        return session

    try:
        with next(db_session()) as db:
            conv, is_resume = resolve_or_create_conversation(
                db,
                agent_type=agent_type,
                project_id=project_id,
                mode=str(body.get("focus") or "insights"),
                conversation_id=_as_uuid(body.get("conversation_id")),
                resume=bool(body.get("resume")),
                start_fresh=bool(body.get("start_fresh")),
            )
            prompt = str(body.get("prompt") or "").strip()
            if prompt and not conv.title:
                # First line of what was asked, so the sessions list is readable
                # without opening each one.
                conv.title = prompt[:120]
                db.add(conv)
                db.commit()
            session.conversation_id = conv.id
            session.recorder = ConversationRecorder(conv.id)
            session.resume = is_resume
    except Exception:
        logger.warning(
            "agents: conversation persistence unavailable for insights %s — "
            "running without history", session_id, exc_info=True,
        )
    return session


async def _dispatch_start(
    agent_type: str,
    session_id: str,
    body: dict,
    emit_fn: Any,
    user_keys: dict | None = None,
) -> None:
    """Route session creation to the correct agent pipeline.

    ``user_keys`` are the caller's bring-your-own provider keys from the
    ``X-Provider-*`` headers. They are secrets: passed down, never logged, never
    persisted. Every pipeline takes them — a pipeline that quietly skipped them
    was a pipeline running on Duct's own key.
    """
    if agent_type == AgentType.SEO_AUDIT:
        await _start_seo_audit(session_id, body, emit_fn, user_keys=user_keys)
    elif agent_type == AgentType.TIKTOK_STUDIO:
        await _start_tiktok_studio(session_id, body, emit_fn, user_keys=user_keys)
    elif agent_type == AgentType.INSIGHTS:
        await _start_insights(session_id, body, emit_fn, user_keys=user_keys)
    else:
        raise HTTPException(501, f"Agent type {agent_type!r} is not yet implemented.")


async def _start_tiktok_studio(
    session_id: str, body: dict, emit_fn: Any, *, user_keys: dict | None = None
) -> None:
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
        coro = _run_draft_worker(session_id, req, emit_fn, user_keys)
    elif mode == "plan_month":
        try:
            req = PlanRequest.model_validate(config)
        except Exception as exc:
            raise HTTPException(422, f"Invalid plan_month config: {exc}") from exc
        coro = _run_plan_worker(session_id, req.project_id, emit_fn, user_keys)
    else:
        raise HTTPException(422, f"mode must be 'plan_month' or 'draft_post', got {mode!r}")

    task = asyncio.create_task(coro)
    session = get_session(session_id)
    if session:
        session.pipeline_task = task


async def _start_seo_audit(
    session_id: str, body: dict, emit_fn: Any, *, user_keys: dict | None = None
) -> None:
    """Validate config and start the SEO audit pipeline as a background task.

    Two shapes: a fresh audit (crawl → synthesis → chat) or a resume
    (req.resume + a persisted conversation) which rehydrates the stored report
    from the artifact store and goes straight to chat — no re-crawl."""
    try:
        req = AuditRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, f"Invalid seo-audit config: {exc}") from exc

    cfg = get_configs()
    engine = resolve_engine(req.engine or "v1")
    provider = resolve_engine_provider(engine, cfg.generate_provider or None)
    model = resolve_engine_model(engine, provider, cfg.generate_model or None)

    session = get_session(session_id)
    owner_id = getattr(session, "user_id", None) if session else None
    # The lead-magnet teaser is demand gen — Duct funds it deliberately, and
    # this is the only place in the audit path that may say so. Everything else
    # fails closed on the hosted deployment without a key of the caller's own.
    resolved = resolve_provider_key(
        provider, user_keys, stored_keys=stored_keys_for(owner_id), duct_pays=req.lead_magnet
    )
    api_key = resolved.key
    if resolved.billed_to_duct:
        logger.info(
            "audit: run billed to Duct (%s/%s, lead_magnet=%s)",
            provider.value, resolved.source, req.lead_magnet,
        )

    if engine == Engine.V3:
        runner = ClaudeAuditRunner(
            api_key=api_key,
            provider=provider,
            model=model,
            effort=req.effort,
            # Lead-magnet (teaser) audits never use extended thinking — keep the
            # first token fast regardless of what the request asked for.
            adaptive_thinking=req.adaptive_thinking and not req.lead_magnet,
        )
    else:
        runner = LangChainAuditRunner(
            api_key=api_key,
            provider=provider,
            model=model,
            gemini_api_key=cfg.gemini_api_key,
        )
    # The artifact digest runs on the caller's own provider now, so the key no
    # longer has to be zeroed for anyone. It used to be Anthropic-only (the
    # summariser was pinned to the Agent SDK), which meant a Gemini or OpenAI
    # customer's artifacts carried no summary and the next session started
    # blind to them.
    summary_key = api_key

    conv_id = getattr(session, "conversation_id", None) if session else None
    recorder = getattr(session, "recorder", None) if session else None

    def _attach_persister(emit, *, group_id=None):
        """Membership-checked, best-effort artifact persistence wrapper."""
        if not (req.project_id and owner_id and not req.lead_magnet):
            return emit
        try:
            project_uuid = UUID(str(req.project_id))
            with next(db_session()) as db:
                role = member_role(project_uuid, owner_id, db)
            if role is None:
                logger.warning(
                    "agents: user %s is not a member of project %s — audit runs unpersisted",
                    owner_id, req.project_id,
                )
                return emit
            persister = ArtifactPersister(
                project_id=project_uuid,
                user_id=owner_id,
                agent_type=str(AgentType.SEO_AUDIT),
                kind="report",
                conversation_id=conv_id,
                api_key=summary_key,
                provider=provider,
                model=model,
                group_id=group_id,
            )
            session.artifact_persister = persister
            # Membership just verified — this also unlocks the project-scoped
            # prior-artifact tools and memory blocks below.
            session.artifact_project_id = project_uuid
            # "Don't remember this session": the report still persists, but the
            # runners mount no memory tools, no digest is injected, and the
            # consolidation pass is skipped on close.
            session.memory_off = not req.remember
            return persister.wrap_emit(emit)
        except Exception:
            logger.warning(
                "agents: artifact persistence unavailable — audit runs unpersisted",
                exc_info=True,
            )
            return emit

    async def _project_memory_blocks(query: str = "") -> str:
        """<project_memory> + <user_memory> + <prior_reports> + <agent_context>.

        Per-project data — injected into the USER message (fresh runs) or the
        resume primer, never the system prompt, so the cached system prefix stays
        byte-identical across customers. Best-effort: returns "".

        Emits MEMORY_RECALLED with the entries the turn was primed with, which
        the UI renders as chips linking back to each memory's source.
        """
        project_uuid = getattr(session, "artifact_project_id", None)
        if project_uuid is None or getattr(session, "memory_off", False):
            return ""
        try:
            with next(db_session()) as db:
                # Declared preferences become user-scope memory first, so the
                # digest below carries them and the agent reads them from one
                # place instead of a per-request field.
                seed_user_preferences(db, owner_id, req.user_preferences)
                context = build_memory_context(
                    db,
                    project_id=project_uuid,
                    user_id=owner_id,
                    agent_type=str(AgentType.SEO_AUDIT),
                    query=query,
                    # The site under audit: open watches and incidents on it are
                    # raised in the opening summary instead of waiting to be asked.
                    subject=query,
                )
                touch_recall(db, context.recalled_ids)
        except Exception:
            logger.warning("agents: project memory blocks unavailable", exc_info=True)
            return ""

        if context.recalled:
            try:
                await emit_fn({
                    "event": AuditEvent.MEMORY_RECALLED,
                    # Each entry carries its title and row id, so the chip can
                    # say what was recalled and open it — attribution is the
                    # point here, not a count.
                    "memories": [
                        {k: v for k, v in entry.items() if k != "uuid"}
                        for entry in context.recalled
                    ],
                })
            except Exception:
                logger.debug("agents: MEMORY_RECALLED emit failed", exc_info=True)
        return context.text

    # ------------------------------------------------------------------
    # Resume: rehydrate the stored report, skip crawl + synthesis
    # ------------------------------------------------------------------
    if req.resume and conv_id is not None:
        rehydrated = []
        group_id = None
        try:
            with next(db_session()) as db:
                rows = [a for a in artifacts_for_conversation(db, conv_id) if a.kind == "report"]
            if rows:
                group_id = rows[-1].group_id
                versions = sorted((a for a in rows if a.group_id == group_id), key=lambda a: a.version)
                rehydrated = [load_report_as_versioned(a) for a in versions]
        except Exception:
            logger.warning("agents: report rehydration failed for %s", conv_id, exc_info=True)
        if not rehydrated:
            raise HTTPException(
                404, "No stored report found for this conversation — start a new audit instead."
            )

        session.report_versions = rehydrated
        latest = rehydrated[-1].report
        url = latest.url or req.url.strip()
        report_mode = str(latest.report_mode) or str(req.report_mode)
        template_id = latest.template_id or req.template_id

        emit_fn = _attach_persister(emit_fn, group_id=group_id)
        if recorder is not None:
            emit_fn = recorder.wrap_emit(emit_fn)

        session.needs_reprime = True
        primer = await build_reprime_context(
            session, api_key, provider=provider, model=model,
            subject="the current audit report (shown in the working_report block)",
        )
        memory = await _project_memory_blocks(query=url)
        session.resume_primer = f"{primer}{memory}\n\n" if memory else primer

        async def resume_pipeline() -> None:
            try:
                await emit_fn({"event": AuditEvent.PIPELINE_STARTED, "status": "running", "url": url})
                await runner.run_resume(
                    session_id=session_id,
                    url=url,
                    emit=emit_fn,
                    user_preferences=req.user_preferences,
                    report_mode=report_mode,
                    template_id=template_id,
                )
            except Exception as exc:
                logger.exception("seo-audit resume error for session %s", session_id)
                await emit_fn({"event": AuditEvent.PIPELINE_FAILED, "status": "error", **error_payload(exc)})

        task = asyncio.create_task(resume_pipeline())
        if session:
            session.pipeline_task = task
        return

    # ------------------------------------------------------------------
    # Fresh audit
    # ------------------------------------------------------------------
    url = req.url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    try:
        validate_public_url(url)
    except SSRFError as exc:
        raise HTTPException(422, f"Invalid URL: {exc}") from exc

    emit_fn = _attach_persister(emit_fn)
    if recorder is not None:
        emit_fn = recorder.wrap_emit(emit_fn)
        # Head event: a brand-new conversation opens with what was asked for,
        # so history rehydrates with a sensible first turn.
        if not getattr(session, "resume", False):
            try:
                await recorder.record_user(f"Run an SEO audit of {url}")
            except Exception:
                logger.debug("agents: audit head event failed", exc_info=True)

    # Project memory (digest + prior report summaries + stored agent context)
    # rides in the initial user prompt — the agent starts knowing what past
    # audits found, what is currently broken, and what the targets are.
    extra_context = await _project_memory_blocks(query=url)

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
                extra_context=extra_context,
            )
            await emit_fn({"event": AuditEvent.PIPELINE_FINISHED, "status": "success"})
        except Exception as exc:
            logger.exception("seo-audit pipeline error for session %s", session_id)
            await emit_fn({"event": AuditEvent.PIPELINE_FAILED, "status": "error", **error_payload(exc)})

    task = asyncio.create_task(pipeline())
    session = get_session(session_id)
    if session:
        session.pipeline_task = task


async def _start_insights(
    session_id: str, body: dict, emit_fn: Any, *, user_keys: dict | None = None
) -> None:
    """Start an autonomous insights session as a background task.

    The counterpart of ``POST /api/insights/generate``, which stays as the
    non-interactive brief path. The difference is the whole point: that route
    takes a fully-specified request (connectors, accounts, goal, date range)
    decided by a wizard; this one takes a project and a sentence, and the agent
    works out the rest. See
    ``docs/engineering/autonomous-insights-agent-plan.md``.
    """
    from agents.insights.brief import (
        ARTIFACT_KIND as INSIGHTS_ARTIFACT_KIND,
        DEFAULT_FORMAT,
        brief_artifact_version,
    )
    from agents.insights.v1.runner import AutonomousInsightsRunner

    try:
        req = InsightsRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(422, f"Invalid insights config: {exc}") from exc

    session = get_session(session_id)
    owner_id = getattr(session, "user_id", None) if session else None
    conv_id = getattr(session, "conversation_id", None) if session else None
    recorder = getattr(session, "recorder", None) if session else None

    # Model, membership gate and autonomy — shared with the unattended entry
    # point (see agents/insights/setup.py). `run.project_id` is None unless the
    # caller was proven to belong to the project, and everything project-scoped
    # downstream reads it rather than the request.
    try:
        run = resolve_insights_run(
            engine_override=req.engine,
            user_id=owner_id,
            project_id=req.project_id,
            user_keys=user_keys,
        )
    except InsightsSetupError as exc:
        raise HTTPException(500, str(exc)) from exc

    provider, model = run.provider, run.model
    project_uuid = run.project_id
    summary_key = run.summary_key

    if session is not None:
        session.artifact_project_id = project_uuid
        session.memory_off = not req.remember

    # ------------------------------------------------------------------
    # Artifact persistence. Every brief the agent writes becomes a version of
    # one artifact group, which is what buys the artifacts page, version
    # history, the AI summary digest and artifact-scoped memory — none of which
    # the old localStorage brief had. Membership is already proven above:
    # project_uuid is None unless it was.
    # ------------------------------------------------------------------
    start_version = 0
    group_id = None
    if project_uuid is not None:
        if req.resume and conv_id is not None:
            # Resume extends the conversation's existing brief rather than
            # starting a second one. (group_id, version) is unique, so the
            # counter has to continue from the stored head or the write drops.
            try:
                with next(db_session()) as db:
                    rows = [
                        a for a in artifacts_for_conversation(db, conv_id)
                        if a.kind == INSIGHTS_ARTIFACT_KIND
                    ]
                if rows:
                    group_id = rows[-1].group_id
                    start_version = max(a.version for a in rows if a.group_id == group_id)
            except Exception:
                logger.warning("agents: insights brief rehydration failed", exc_info=True)
        try:
            persister = ArtifactPersister(
                project_id=project_uuid,
                user_id=owner_id,
                agent_type=str(AgentType.INSIGHTS),
                kind=INSIGHTS_ARTIFACT_KIND,
                conversation_id=conv_id,
                api_key=summary_key,
                provider=provider,
                model=model,
                group_id=group_id,
                adapt=brief_artifact_version,
            )
            if session is not None:
                session.artifact_persister = persister
            emit_fn = persister.wrap_emit(emit_fn)
        except Exception:
            logger.warning(
                "agents: artifact persistence unavailable — insights runs unpersisted",
                exc_info=True,
            )

    is_resume = bool(req.resume and conv_id is not None)
    if recorder is not None:
        emit_fn = recorder.wrap_emit(emit_fn)
        # The opening prompt is the first user turn; on a resume it is a
        # follow-up typed into a thread the user is looking at. Either way it
        # is a line of the transcript and has to be there when it rehydrates.
        if req.prompt:
            try:
                await recorder.record_user(req.prompt)
            except Exception:
                logger.debug("agents: insights head event failed", exc_info=True)

    memory = await insights_memory_blocks(
        run,
        user_id=owner_id,
        user_preferences=req.user_preferences,
        query=req.prompt,
        remember=req.remember,
        emit=emit_fn,
    )
    business_context = format_business_context(req.business_context)

    runner = AutonomousInsightsRunner(
        api_key=run.api_key,
        provider=provider,
        model=model,
        temperature=1.0,
        thinking=req.user_preferences.thinking,
    )

    async def pipeline() -> None:
        try:
            # The autonomy fields ride on PIPELINE_STARTED rather than a new
            # event: the UI has to say which mode a run is in before the first
            # token, and `configured` vs `autonomy` is what makes a step-down
            # visible instead of mysterious.
            await emit_fn({
                "event": AgentEvent.PIPELINE_STARTED,
                "status": StepStatus.RUNNING,
                "autonomy": run.autonomy,
                "autonomy_configured": run.configured_autonomy,
            })
            # run_session emits PIPELINE_FINISHED itself once the opening turn
            # lands, then stays open for follow-ups — so the route must not
            # emit it again on return (that would be the chat loop ending).
            await runner.run_session(
                session_id,
                emit_fn,
                session=session,
                prompt=req.prompt,
                business_context=business_context,
                memory=memory,
                project_id=project_uuid,
                user_id=owner_id,
                conversation_id=conv_id,
                remember=req.remember,
                artifact_format=(
                    req.user_preferences.preferred_artifact_format or DEFAULT_FORMAT
                ),
                autonomy=run.autonomy,
                start_version=start_version,
                resume=is_resume,
            )
        except Exception as exc:
            logger.exception("insights pipeline error for session %s", session_id)
            await emit_fn({
                "event": AgentEvent.PIPELINE_FAILED,
                "status": StepStatus.ERROR,
                **error_payload(exc),
            })

    task = asyncio.create_task(pipeline())
    if session:
        session.pipeline_task = task
