"""Content Studio agent routes.

Streaming endpoints clone the SSE machinery from routes/audit.py:
  POST   /api/content/plan/stream         — start a plan_month session
  POST   /api/content/post/stream         — start a draft_post session
  POST   /api/content/answer/{sid}        — resolve pending AskUserQuestion
  POST   /api/content/chat/{sid}          — continued chat into an active session
  DELETE /api/content/session/{sid}       — close session, free resources

Brand context (writes Project JSONB columns):
  GET    /api/content/brand?project_id=…
  PUT    /api/content/brand?project_id=…

Plans + posts CRUD:
  GET    /api/content/plans?project_id=…  · GET /api/content/plans/{id}
  POST   /api/content/plans               · DELETE /api/content/plans/{id}
  PATCH  /api/content/plans/{id}/days/{day}
  GET    /api/content/posts?project_id=…  · GET /api/content/posts/{id}
  POST   /api/content/posts               · PATCH /api/content/posts/{id}
  POST   /api/content/posts/{id}/mark-posted
  POST   /api/content/posts/{id}/log-metrics

Format + avatar library CRUD:
  GET/POST/PATCH/DELETE  /api/content/formats[/{id}]
  GET/POST/PATCH/DELETE  /api/content/avatars[/{id}]

Deferred:
  · PostBridge publish + sync routes — Phase 4
  · Uploads + assets routes — Phase 4b
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlmodel import Session

from agents.content.events import ContentEvent
from agents.content.styles import base_css, list_styles
from agents.content.schema import (
    ContentAnswerRequest,
    ContentChatMessage,
    ContentStatus,
    DraftPostRequest,
    PlanRequest,
)
from agents.content.v3.runner import (
    ClaudeContentRunner,
    close_session,
    create_draft_session,
    create_plan_session,
    get_session,
)
from agents.engines import PROVIDER_CONFIG_ATTR, Engine, resolve_engine_provider
from agents.content.channels import Platform
from config import claude_oauth_available, get_configs
from db.session import get_session as db_session
from models.content import (
    ContentAsset,
    ContentAvatar,
    ContentFormat,
    ContentPlan,
    ContentPost,
    ContentSocialLink,
)
from models.auth import User
from models.project import Project
from service import storage
from service.auth import get_current_user
from service.membership import get_project_for_user, get_project_row_for_user
from utils.dates import now_iso

logger = logging.getLogger(__name__)

# Authentication is declared on the router, not on 44 individual endpoints —
# the failure mode being closed off here is an endpoint that simply forgets. It
# is only half the job: `validate_api_key` upstream says "this is the Duct app"
# and this says "and a real user is asking", but neither says *which* user, and
# every row below belongs to a project. The membership gate is what makes that
# call, via `_project_for_user` (a project named in the request) and
# `_row_for_user` / `_session_for_user` (a project derived from the thing being
# touched). See backend/CLAUDE.md.
router = APIRouter(tags=["content"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Session tracking + pruner (mirrors routes/audit.py:38-65)
# ---------------------------------------------------------------------------

_SESSION_TTL = 1800  # 30 minutes
_session_created_at: dict[str, float] = {}

# In-process TTL cache for the PostBridge-backed analytics endpoint. That call
# paginates PostBridge's external API (≤2000 records + post-results) on every
# request; without this, opening the Analytics tab hammers PostBridge each time.
# refresh=true bypasses + repopulates; writes that change analytics clear it.
_ANALYTICS_TTL = 120.0  # seconds
_analytics_cache: dict[UUID, tuple[float, list]] = {}


def _invalidate_analytics(project_id: UUID) -> None:
    _analytics_cache.pop(project_id, None)


async def _prune_stale_sessions() -> None:
    while True:
        await asyncio.sleep(300)
        now = time.monotonic()
        stale = [
            sid for sid, created in list(_session_created_at.items())
            if now - created > _SESSION_TTL
        ]
        for sid in stale:
            logger.info("content: pruning stale session %s", sid)
            close_session(sid)
            _session_created_at.pop(sid, None)


# Launched from the app lifespan in server.py — FastAPI's lifespan disables
# router-level on_event hooks, so startup tasks are started centrally there.


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_api_key() -> str:
    cfg = get_configs()
    provider = resolve_engine_provider(Engine.V3, cfg.generate_provider or None)
    return getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""


async def _emit(queue: asyncio.Queue, body: dict[str, Any]) -> None:
    body.setdefault("ts", now_iso())
    await queue.put(body)


async def _stream_queue(
    queue: asyncio.Queue,
    finished: asyncio.Event,
) -> AsyncGenerator[str, None]:
    while not finished.is_set() or not queue.empty():
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=15)
            yield f"data: {json.dumps(payload, default=str)}\n\n"
        except asyncio.TimeoutError:
            yield ": ping\n\n"


def _project_for_user(db: Session, user: User, project_id: UUID) -> Project:
    """A project the caller belongs to, or 404.

    Replaces a bare existence check. Membership is the access model here (see
    service/membership.py), and a non-member gets the same 404 a made-up id
    does so the reply is not an oracle for which projects are real.
    """
    return get_project_for_user(project_id, user, db)


def _row_for_user(db: Session, user: User, model, row_id: UUID, label: str):
    """A project-scoped content row the caller may act on, or 404.

    Every table in this module carries a project_id, so one helper covers
    plans, posts, formats, avatars and assets alike.
    """
    return get_project_row_for_user(db, user, model, row_id, label=label)


def _session_for_user(db: Session, user: User, session_id: str):
    """A live drafting session the caller may drive, or 404.

    Session ids are unguessable, but unguessable is not a permission: the
    session knows its project, so that is what gets checked.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    get_project_for_user(session.project_id, user, db)
    return session


# ---------------------------------------------------------------------------
# SSE: plan_month
# ---------------------------------------------------------------------------


def _link_conversation_artifact(session_id: str, kind: str) -> None:
    """Bind the session's persisted conversation to the artifact it just produced
    (post/plan) so 'click post → resume' can find it. Best-effort: a brand-new
    draft creates its conversation before the post exists, so the id is only
    known once the worker finishes. No-op when the session isn't tracked."""
    sess = get_session(session_id)
    conv_id = getattr(sess, "conversation_id", None) if sess else None
    artifact_id = getattr(sess, "post_id" if kind == "post" else "plan_id", None) if sess else None
    if not conv_id or not artifact_id:
        return
    try:
        from agents.content.persistence import link_artifact
        with next(db_session()) as db:
            link_artifact(db, conv_id, kind, artifact_id)
    except Exception:
        logger.warning("content: failed to link conversation %s → %s %s",
                       conv_id, kind, artifact_id, exc_info=True)


async def _run_plan_worker(
    session_id: str,
    project_id: UUID,
    emit_fn: Any,
) -> None:
    try:
        api_key = _resolve_api_key()
        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        runner = ClaudeContentRunner(api_key=api_key)
        await runner.run_plan(session_id, project_id, emit_fn)
        _link_conversation_artifact(session_id, "plan")
    except Exception as exc:
        logger.exception("content: plan worker error for session %s", session_id)
        await emit_fn({
            "event":      ContentEvent.PIPELINE_FAILED,
            "session_id": session_id,
            "error":      str(exc),
        })


@router.post("/content/plan/stream")
async def run_plan_stream(
    req: PlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> StreamingResponse:
    """Start a 30-day plan synthesis session. Returns an SSE stream covering
    the full session lifetime (continues after PIPELINE_FINISHED so the user
    can chat with the agent to refine the plan)."""
    _project_for_user(db, user, req.project_id)
    session_id = str(uuid.uuid4())
    _session_created_at[session_id] = time.monotonic()
    create_plan_session(session_id, req.project_id)

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def emit_fn(body: dict[str, Any]) -> None:
        await _emit(queue, body)

    async def worker() -> None:
        try:
            await _run_plan_worker(session_id, req.project_id, emit_fn)
        except Exception as exc:
            logger.exception("content: plan worker outer error")
            await emit_fn({
                "event":      ContentEvent.PIPELINE_FAILED,
                "session_id": session_id,
                "error":      str(exc),
            })

    asyncio.create_task(worker())

    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _stream_queue(queue, finished):
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            close_session(session_id)
            _session_created_at.pop(session_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":          "no-cache",
            "Connection":             "keep-alive",
            "X-Accel-Buffering":      "no",
            "X-Content-Session-Id":   session_id,
        },
    )


# ---------------------------------------------------------------------------
# SSE: draft_post
# ---------------------------------------------------------------------------


async def _run_draft_worker(
    session_id: str,
    req: DraftPostRequest,
    emit_fn: Any,
) -> None:
    try:
        api_key = _resolve_api_key()
        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        runner = ClaudeContentRunner(api_key=api_key)
        # Resolve the Day from the plan if provided; otherwise pass topic/pillar.
        day_obj = None
        if req.plan_id is not None and req.day_index is not None:
            with next(db_session()) as db:
                plan = db.get(ContentPlan, req.plan_id)
                if plan and 0 <= req.day_index < len(plan.days):
                    from agents.content.schema import Day
                    raw = plan.days[req.day_index]
                    if isinstance(raw, dict):
                        try:
                            day_obj = Day.model_validate(raw)
                        except Exception as exc:
                            logger.warning("content: failed to parse Day[%d] from plan %s: %s",
                                           req.day_index, req.plan_id, exc)
        # Primary channel: explicit request → the day's first platform → default.
        from agents.content.channels import primary_channel
        channel = req.channel or (primary_channel(day_obj.platforms) if day_obj else None)
        await runner.run_draft(
            session_id,
            req.project_id,
            emit_fn,
            day=day_obj,
            topic=req.topic,
            pillar=req.pillar,
            channel=channel,
        )
        # Link the drafted post back onto its plan-day (post_id) so the board
        # can match the new post to its slot (we link by post_id, not position).
        if req.plan_id is not None and req.day_index is not None:
            sess = get_session(session_id)
            new_post_id = getattr(sess, "post_id", None) if sess else None
            if new_post_id is not None:
                with next(db_session()) as db:
                    plan = db.get(ContentPlan, req.plan_id)
                    if plan and 0 <= req.day_index < len(plan.days):
                        days = list(plan.days)
                        day = dict(days[req.day_index]) if isinstance(days[req.day_index], dict) else {}
                        day["post_id"] = str(new_post_id)
                        days[req.day_index] = day
                        plan.days = days
                        plan.updated_at = datetime.now(timezone.utc)
                        db.add(plan)
                        db.commit()
        _link_conversation_artifact(session_id, "post")
    except Exception as exc:
        logger.exception("content: draft worker error for session %s", session_id)
        await emit_fn({
            "event":      ContentEvent.PIPELINE_FAILED,
            "session_id": session_id,
            "error":      str(exc),
        })


@router.post("/content/post/stream")
async def run_post_stream(
    req: DraftPostRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> StreamingResponse:
    """Start a single-post draft session. SSE stream for the lifetime."""
    _project_for_user(db, user, req.project_id)
    session_id = str(uuid.uuid4())
    _session_created_at[session_id] = time.monotonic()
    create_draft_session(session_id, req.project_id, plan_id=req.plan_id)

    queue: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def emit_fn(body: dict[str, Any]) -> None:
        await _emit(queue, body)

    async def worker() -> None:
        try:
            await _run_draft_worker(session_id, req, emit_fn)
        except Exception as exc:
            logger.exception("content: draft worker outer error")
            await emit_fn({
                "event":      ContentEvent.PIPELINE_FAILED,
                "session_id": session_id,
                "error":      str(exc),
            })

    asyncio.create_task(worker())

    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _stream_queue(queue, finished):
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            close_session(session_id)
            _session_created_at.pop(session_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":         "no-cache",
            "Connection":            "keep-alive",
            "X-Accel-Buffering":     "no",
            "X-Content-Session-Id":  session_id,
        },
    )


# ---------------------------------------------------------------------------
# SSE: AskUserQuestion answer + continued chat + close
# ---------------------------------------------------------------------------


@router.post("/content/answer/{session_id}")
async def submit_content_answers(
    session_id: str,
    req: ContentAnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    _session_for_user(db, user, session_id)
    """Resolve a pending AskUserQuestion in the content session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    fut = session.answer_future
    if not fut or getattr(fut, "done", lambda: True)():
        raise HTTPException(400, "No pending question for this session")
    try:
        fut.set_result(req.answers)
    except asyncio.InvalidStateError as exc:
        raise HTTPException(409, "Question already answered") from exc
    return {"status": "ok"}


@router.post("/content/chat/{session_id}")
async def send_content_chat_message(
    session_id: str,
    req: ContentChatMessage,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    _session_for_user(db, user, session_id)
    """Send a follow-up message into an active content session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    await session.chat_queue.put({"role": "user", "content": req.content})
    return {"status": "queued"}


class SlideRenderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_id:    str
    image_base64: str   # the rasterized 1080×1920 PNG, base64 (no data: prefix)


@router.post("/content/slide-render/{session_id}")
async def submit_slide_render(
    session_id: str,
    req: SlideRenderResult,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    _session_for_user(db, user, session_id)
    """Resolve a pending render_slide request — the browser rasterized the slide
    and POSTs the PNG back here; we hand the bytes to the waiting agent tool.
    An empty image_base64 signals a browser-side failure (resolves to a clean
    tool error rather than hanging the agent for the full timeout)."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    fut = session.render_futures.get(req.render_id)
    if not fut or getattr(fut, "done", lambda: True)():
        raise HTTPException(400, "No pending render for this id (it may have timed out)")
    try:
        fut.set_result(req.image_base64)
    except asyncio.InvalidStateError as exc:
        raise HTTPException(409, "Render already resolved") from exc
    return {"status": "ok"}


def _inline_local_images(html: str) -> str:
    """Replace src="/uploads/…" with base64 data URIs so a browser rasterizing
    the doc isn't CORS-tainted (the app + backend are different origins).

    Hardened against path traversal: image_url is agent-influenceable (a slide's
    image_url survives submit/edit), so a value like "/uploads/../../etc/passwd"
    must NOT be read off disk. We resolve and require the path stays inside
    uploads_dir before reading.
    """
    import base64
    import re

    cfg = get_configs()
    base = Path(cfg.uploads_dir or "/app/uploads").resolve()

    def _repl(m: "re.Match") -> str:
        url = m.group(1)
        rel = url[len("/uploads/"):]
        try:
            p = (base / rel).resolve()
            if not p.is_relative_to(base) or not p.is_file():
                return m.group(0)   # traversal / missing → leave the src untouched
            suffix = p.suffix.lower()
            mime = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(suffix, "image/png")
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            return f'src="data:{mime};base64,{data}"'
        except Exception:
            return m.group(0)

    return re.sub(r'src="(/uploads/[^"]+)"', _repl, html)


@router.get("/content/slide-doc/{session_id}")
def get_slide_render_doc(
    session_id: str,
    post_id: UUID,
    slide_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Self-contained 1080×1920 single-slide HTML (images inlined as base64) for
    the browser to rasterize — backing the render_slide bridge. Origin-clean, so
    the client-side canvas capture isn't tainted."""
    from agents.content.schema import Slide
    from agents.content.templates import render_slides_html

    # Two gates, not one. The caller must belong to the session's project, and
    # the post must belong to that same session — so a member of project A
    # cannot rasterize project B's slides, and cannot use their own session to
    # reach a post outside it either.
    session = _session_for_user(db, user, session_id)
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    if post.project_id != session.project_id:
        raise HTTPException(404, "Post not found")
    raw = next(
        (s for s in (post.slides or []) if isinstance(s, dict) and s.get("slide_id") == slide_id),
        None,
    )
    if raw is None:
        raise HTTPException(404, f"Slide {slide_id} not found on this post")
    slide = Slide.model_validate(raw)
    html = render_slides_html(post.layout or "full-bleed", [slide])
    return {"html": _inline_local_images(html), "width": 1080, "height": 1920}


@router.delete("/content/session/{session_id}")
async def close_content_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Close a drafting session. Idempotent, and deliberately uniform.

    Always answers ok. Closing an id that never existed is not an error — a
    client tearing down should not have to know whether it won the race — and
    answering differently for "not yours" would hand that same client a way to
    probe which sessions are live. So a session the caller does not belong to
    is simply not closed, and its prune timestamp is left alone.
    """
    session = get_session(session_id)
    if session is not None:
        try:
            get_project_for_user(session.project_id, user, db)
        except HTTPException:
            return {"status": "ok"}
        close_session(session_id)
    _session_created_at.pop(session_id, None)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Brand context
# ---------------------------------------------------------------------------


_JSONB_MAX_BYTES = 256_000


class BrandContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_brand:         dict | None = None
    content_pillars:       dict | None = None
    content_visual_assets: dict | None = None
    slug:    str | None = None
    tagline: str | None = None
    description: str | None = None
    # NOTE: `url` (website) is owned by project context (company.website_url);
    # it is intentionally NOT writable here to avoid two editors clobbering one column.

    @field_validator("content_brand", "content_pillars", "content_visual_assets", mode="after")
    @classmethod
    def _check_size(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v, default=str)) > _JSONB_MAX_BYTES:
            raise ValueError("Section payload too large (max 256 KB).")
        return v


class BrandContextOut(BaseModel):
    project_id:            UUID
    project_name:          str
    slug:                  str
    tagline:               str
    description:           str
    url:                   str
    content_brand:         dict
    content_pillars:       dict
    content_visual_assets: dict


def _brand_out(p: Project) -> BrandContextOut:
    return BrandContextOut(
        project_id=p.id,
        project_name=p.name,
        slug=p.slug or "",
        tagline=p.tagline or "",
        description=p.description or "",
        url=p.url or "",
        content_brand=p.content_brand or {},
        content_pillars=p.content_pillars or {},
        content_visual_assets=p.content_visual_assets or {},
    )


@router.get("/content/brand")
def get_brand_context(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> BrandContextOut:
    return _brand_out(_project_for_user(db, user, project_id))


@router.put("/content/brand")
def put_brand_context(
    project_id: UUID,
    body: BrandContextIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> BrandContextOut:
    proj = _project_for_user(db, user, project_id)
    if body.content_brand is not None:
        proj.content_brand = body.content_brand
    if body.content_pillars is not None:
        proj.content_pillars = body.content_pillars
    if body.content_visual_assets is not None:
        proj.content_visual_assets = body.content_visual_assets
    if body.slug is not None:
        proj.slug = body.slug
    if body.tagline is not None:
        proj.tagline = body.tagline
    if body.description is not None:
        proj.description = body.description
    proj.updated_at = datetime.now(timezone.utc)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _brand_out(proj)


# ---------------------------------------------------------------------------
# Plans CRUD
# ---------------------------------------------------------------------------


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name:       str = ""
    start_date: str | None = None
    character:  dict = Field(default_factory=dict)
    days:       list = Field(default_factory=list)
    status:     str = "draft"


class PlanOut(BaseModel):
    id:         UUID
    project_id: UUID
    name:       str
    start_date: str | None
    character:  dict
    days:       list
    status:     str
    created_at: str
    updated_at: str
    posts:      list[dict] | None = None


def _plan_out(p: ContentPlan, posts: list[ContentPost] | None = None) -> PlanOut:
    return PlanOut(
        id=p.id,
        project_id=p.project_id,
        name=p.name,
        start_date=p.start_date.isoformat() if p.start_date else None,
        character=p.character or {},
        days=p.days or [],
        status=p.status,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        posts=(
            [
                {
                    "id":            str(post.id),
                    "post_dir_slug": post.post_dir_slug,
                    "pillar":        post.pillar,
                    "topic":         post.topic,
                    "status":        post.status,
                    "slide_count":   post.slide_count,
                }
                for post in posts
            ]
            if posts is not None
            else None
        ),
    )


@router.get("/content/plans")
def list_plans(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[PlanOut]:
    _project_for_user(db, user, project_id)
    rows = db.execute(
        select(ContentPlan)
        .where(ContentPlan.project_id == project_id)
        .order_by(ContentPlan.created_at.desc())
    ).scalars().all()
    return [_plan_out(r) for r in rows]


@router.get("/content/plans/{plan_id}")
def get_plan(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PlanOut:
    plan = _row_for_user(db, user, ContentPlan, plan_id, "Plan")
    posts = db.execute(
        select(ContentPost).where(ContentPost.plan_id == plan_id).order_by(ContentPost.created_at)
    ).scalars().all()
    return _plan_out(plan, posts=list(posts))


@router.post("/content/plans", status_code=201)
def create_plan(
    body: PlanIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PlanOut:
    _project_for_user(db, user, body.project_id)
    start = None
    if body.start_date:
        try:
            start = datetime.fromisoformat(body.start_date).date()
        except ValueError as exc:
            raise HTTPException(400, f"Invalid start_date: {exc}") from exc
    plan = ContentPlan(
        project_id=body.project_id,
        name=body.name or "30-day plan",
        start_date=start,
        character=body.character or {},
        days=body.days or [],
        status=body.status or "draft",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


class DayPatch(BaseModel):
    model_config = ConfigDict(extra="allow")  # shallow merge of arbitrary day fields


@router.patch("/content/plans/{plan_id}/days/{index}")
def patch_plan_day(
    plan_id: UUID,
    index: int,
    body: DayPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PlanOut:
    """Shallow-merge a single day's fields by its 0-based position in days[]."""
    plan = _row_for_user(db, user, ContentPlan, plan_id, "Plan")
    days = list(plan.days or [])
    idx = index
    if idx < 0 or idx >= len(days):
        raise HTTPException(400, f"Index {index} out of range (plan has {len(days)} items)")
    existing = dict(days[idx]) if isinstance(days[idx], dict) else {}
    patch = body.model_dump(exclude_unset=True)
    existing.update(patch)
    days[idx] = existing
    plan.days = days
    plan.updated_at = datetime.now(timezone.utc)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.delete("/content/plans/{plan_id}")
def delete_plan(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    plan = _row_for_user(db, user, ContentPlan, plan_id, "Plan")
    db.delete(plan)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Posts CRUD
# ---------------------------------------------------------------------------


class PostIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id:    UUID
    plan_id:       UUID | None = None
    post_dir_slug: str
    pillar:        str = ""
    topic:         str = ""
    topic_id:      int | None = None
    post_type:     str = "slideshow"
    format_slug:   str = ""   # resolved to format_id; "" leaves the post unlinked
    avatar_id:     UUID | None = None
    layout:        str = "full-bleed"
    slide_count:   int = 0
    status:        str = "pending"
    slides:        list = Field(default_factory=list)
    slides_html:   str = ""
    caption:       str = ""
    hashtags:      list = Field(default_factory=list)
    tiktok_title:  str = ""
    hook_type:     str = ""
    hook_text:     str = ""
    hook_emotion:  str = ""
    save_cta:      str = ""
    image_prompts: list = Field(default_factory=list)
    audio_note:    str = ""
    bridge_text:   str = ""
    strategic_note: str = ""
    visual_brief:  str = ""
    emotional_arc: str = ""
    camera_ref_pool: str = ""
    platforms:     list[Platform] = Field(default_factory=lambda: [Platform.TIKTOK])


class PostPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id:       UUID | None = None
    pillar:        str | None = None
    topic:         str | None = None
    topic_id:      int | None = None
    post_type:     str | None = None
    format_slug:   str | None = None
    avatar_id:     UUID | None = None
    layout:        str | None = None
    slide_count:   int | None = None
    status:        str | None = None
    slides:        list | None = None
    slides_html:   str | None = None
    caption:       str | None = None
    hashtags:      list | None = None
    tiktok_title:  str | None = None
    hook_type:     str | None = None
    hook_text:     str | None = None
    hook_emotion:  str | None = None
    save_cta:      str | None = None
    image_prompts: list | None = None
    audio_note:    str | None = None
    bridge_text:   str | None = None
    strategic_note: str | None = None
    visual_brief:  str | None = None
    emotional_arc: str | None = None
    camera_ref_pool: str | None = None
    platforms:     list[Platform] | None = None
    notes:         str | None = None


class PostOut(BaseModel):
    id:            UUID
    project_id:    UUID
    plan_id:       UUID | None
    post_dir_slug: str
    pillar:        str
    topic:         str
    topic_id:      int | None
    post_type:     str
    format_id:     UUID | None
    format_slug:   str
    format_name:   str
    avatar_id:     UUID | None
    thumbnail_url: str
    layout:        str
    slide_count:   int
    status:        str
    slides:        list
    slides_html:   str
    caption:       str
    hashtags:      list
    tiktok_title:  str
    hook_type:     str
    hook_text:     str
    hook_emotion:  str
    save_cta:      str
    image_prompts: list
    audio_note:    str
    bridge_text:   str
    strategic_note: str
    visual_brief:  str
    emotional_arc: str
    camera_ref_pool: str
    platforms:     list
    posted_at:     str | None
    scheduled_at:  str | None
    tiktok_url:    str
    published_via: str
    perf:          dict
    daily_perf:    list
    notes:         str
    created_at:    str
    updated_at:    str
    # The active agent conversation for this post (if any) — drives "click post →
    # resume the chat" on the detail page. None ⇒ open a fresh session.
    active_conversation_id: UUID | None = None


def _post_out(
    p: ContentPost,
    *,
    fmt: tuple[str, str] | None = None,
    thumbnail_url: str = "",
    active_conversation_id: UUID | None = None,
) -> PostOut:
    """Serialize a post. `fmt` is an optional (slug, name) for the linked format."""
    return PostOut(
        active_conversation_id=active_conversation_id,
        id=p.id,
        project_id=p.project_id,
        plan_id=p.plan_id,
        post_dir_slug=p.post_dir_slug,
        pillar=p.pillar,
        topic=p.topic,
        topic_id=p.topic_id,
        post_type=p.post_type,
        format_id=p.format_id,
        format_slug=(fmt[0] if fmt else ""),
        format_name=(fmt[1] if fmt else ""),
        avatar_id=p.avatar_id,
        thumbnail_url=thumbnail_url,
        layout=p.layout or "full-bleed",
        slide_count=p.slide_count,
        status=p.status,
        slides=p.slides or [],
        slides_html=p.slides_html,
        caption=p.caption,
        hashtags=p.hashtags or [],
        tiktok_title=p.tiktok_title,
        hook_type=p.hook_type,
        hook_text=p.hook_text,
        hook_emotion=p.hook_emotion,
        save_cta=p.save_cta,
        image_prompts=p.image_prompts or [],
        audio_note=p.audio_note,
        bridge_text=p.bridge_text,
        strategic_note=p.strategic_note,
        visual_brief=p.visual_brief,
        emotional_arc=p.emotional_arc,
        camera_ref_pool=p.camera_ref_pool,
        platforms=p.platforms or [],
        posted_at=p.posted_at.isoformat() if p.posted_at else None,
        scheduled_at=p.scheduled_at.isoformat() if p.scheduled_at else None,
        tiktok_url=p.tiktok_url,
        published_via=p.published_via,
        perf=p.perf or {},
        daily_perf=p.daily_perf or [],
        notes=p.notes,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Post enrichment — link format + derive a thumbnail
# ---------------------------------------------------------------------------

def _format_map(db: Session, project_id: UUID) -> dict:
    """Return a by_id lookup of (slug, name) for a project's formats."""
    rows = db.execute(
        select(ContentFormat).where(ContentFormat.project_id == project_id)
    ).scalars().all()
    return {f.id: (f.slug, f.name or f.slug) for f in rows}


def _resolve_format_id(db: Session, project_id: UUID, format_slug: str) -> UUID | None:
    """Find the format row in this project matching a slug (e.g. 'format-d')."""
    slug = (format_slug or "").strip().lower()
    if not slug:
        return None
    row = db.execute(
        select(ContentFormat).where(
            ContentFormat.project_id == project_id,
            ContentFormat.slug == slug,
        )
    ).scalars().first()
    return row.id if row else None


def _thumb_map(db: Session, post_ids: list[UUID]) -> dict[UUID, str]:
    """Map post_id → first usable image asset url (generated or uploaded)."""
    if not post_ids:
        return {}
    rows = db.execute(
        select(ContentAsset.post_id, ContentAsset.url, ContentAsset.created_at)
        .where(ContentAsset.post_id.in_(post_ids))
        .where(ContentAsset.asset_type.in_(["generated", "upload"]))
        .where(ContentAsset.url != "")
        .order_by(ContentAsset.created_at.asc())
    ).all()
    out: dict[UUID, str] = {}
    for pid, url, _created in rows:
        if pid is not None and pid not in out and url:
            out[pid] = url
    return out


def _fmt_for(post: ContentPost, by_id: dict) -> tuple[str, str] | None:
    return by_id.get(post.format_id)


def _enrich_one(db: Session, post: ContentPost) -> PostOut:
    by_id = _format_map(db, post.project_id)
    thumb = _thumb_map(db, [post.id]).get(post.id, "")
    return _post_out(post, fmt=_fmt_for(post, by_id), thumbnail_url=thumb)


def _rerender_slides(post: ContentPost) -> None:
    """Re-derive slides_html + image_prompts + slide_count from structured
    slides. Called after a slides edit so the rendered preview, the flat
    image-prompt list, and the count stay in lock-step. Staleness is implicit:
    a slide whose image_prompt now differs from image_prompt_used renders with
    the 'outdated' flag (see agents/content/templates.py)."""
    from agents.content.schema import Slide
    from agents.content.templates import derive_image_prompts, render_slides_html

    parsed = [Slide.model_validate(s) for s in (post.slides or [])]
    post.slides_html = render_slides_html(post.layout or "full-bleed", parsed)
    post.image_prompts = derive_image_prompts(parsed)
    post.slide_count = len(parsed)


@router.get("/content/posts")
def list_posts(
    project_id: UUID,
    plan_id: UUID | None = None,
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[PostOut]:
    _project_for_user(db, user, project_id)
    stmt = select(ContentPost).where(ContentPost.project_id == project_id)
    if plan_id is not None:
        stmt = stmt.where(ContentPost.plan_id == plan_id)
    if status:
        stmt = stmt.where(ContentPost.status == status)
    else:
        # Default board view hides unsaved (pending) drafts — they live only in
        # the live drafting workspace until the user clicks Save (pending→draft).
        stmt = stmt.where(ContentPost.status != ContentStatus.PENDING)
    stmt = stmt.order_by(ContentPost.updated_at.desc())
    rows = db.execute(stmt).scalars().all()
    by_id = _format_map(db, project_id)
    thumbs = _thumb_map(db, [r.id for r in rows])
    return [
        _post_out(r, fmt=_fmt_for(r, by_id), thumbnail_url=thumbs.get(r.id, ""))
        for r in rows
    ]


@router.get("/content/posts/{post_id}")
def get_post(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    # Best-effort: the active-conversation lookup drives "click post → resume",
    # but a persistence-table issue (e.g. migration not yet applied) must never
    # break viewing a post — degrade to "no conversation" instead.
    active_conversation_id = None
    try:
        from agents.content.persistence import find_active_conversation
        conv = find_active_conversation(db, artifact_type="post", artifact_id=post.id)
        active_conversation_id = conv.id if conv else None
    except Exception:
        db.rollback()
        logger.warning("content: active-conversation lookup failed for post %s", post_id, exc_info=True)
    by_id = _format_map(db, post.project_id)
    thumb = _thumb_map(db, [post.id]).get(post.id, "")
    return _post_out(
        post,
        fmt=_fmt_for(post, by_id),
        thumbnail_url=thumb,
        active_conversation_id=active_conversation_id,
    )


@router.post("/content/posts", status_code=201)
def create_post(
    body: PostIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    _project_for_user(db, user, body.project_id)
    # Upsert by (project_id, post_dir_slug) so the route is idempotent.
    existing = db.execute(
        select(ContentPost).where(
            ContentPost.project_id == body.project_id,
            ContentPost.post_dir_slug == body.post_dir_slug,
        )
    ).scalars().first()
    values = {
        **body.model_dump(),
        "platforms": [p.value for p in body.platforms],
    }
    # format_slug is an input-only selector — resolve it to the FK and drop it.
    values.pop("format_slug", None)
    values["format_id"] = _resolve_format_id(db, body.project_id, body.format_slug)
    # If structured slides came in without HTML, render the HTML from the template.
    if values.get("slides") and not values.get("slides_html"):
        from agents.content.schema import Slide
        from agents.content.templates import derive_image_prompts, render_slides_html
        parsed = [Slide.model_validate(s) for s in values["slides"]]
        values["slides_html"] = render_slides_html(values.get("layout") or "full-bleed", parsed)
        values["image_prompts"] = derive_image_prompts(parsed)
        values["slide_count"] = len(parsed)
    if existing is not None:
        for k, v in values.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return _enrich_one(db, existing)
    post = ContentPost(**values)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _enrich_one(db, post)


@router.patch("/content/posts/{post_id}")
def patch_post(
    post_id: UUID,
    body: PostPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    patch = body.model_dump(exclude_unset=True)
    if "platforms" in patch and patch["platforms"] is not None:
        patch["platforms"] = [
            p.value if isinstance(p, Platform) else p
            for p in patch["platforms"]
        ]
    # format_slug is input-only — resolve to the FK rather than setting a column.
    format_slug = patch.pop("format_slug", None)
    for k, v in patch.items():
        setattr(post, k, v)
    if format_slug is not None:
        post.format_id = _resolve_format_id(db, post.project_id, format_slug)
    # When structured slides change, re-render the HTML from the template unless
    # the caller also passed an explicit slides_html (don't clobber that).
    if "slides" in patch and "slides_html" not in patch:
        try:
            _rerender_slides(post)
        except Exception:
            logger.exception("patch_post: failed to re-render slides for %s", post_id)
    post.updated_at = datetime.now(timezone.utc)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _enrich_one(db, post)


@router.post("/content/posts/{post_id}/mark-posted")
def mark_post_posted(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
    tiktok_url: str | None = None,
) -> PostOut:
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    post.status = "posted"
    post.posted_at = datetime.now(timezone.utc)
    if tiktok_url:
        post.tiktok_url = tiktok_url
    db.add(post)
    db.commit()
    db.refresh(post)
    return _enrich_one(db, post)


class MetricsLog(BaseModel):
    model_config = ConfigDict(extra="allow")  # forward-compatible with future PostBridge fields


@router.post("/content/posts/{post_id}/log-metrics")
def log_post_metrics(
    post_id: UUID,
    body: MetricsLog,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    """Append a snapshot to daily_perf + merge into perf (last-write-wins).

    Phase 4 will wire this into PostBridge sync jobs. For now it accepts any
    JSON-serialisable body and persists it as-is.
    """
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    metrics = body.model_dump()
    metrics["recorded_at"] = datetime.now(timezone.utc).isoformat()
    post.daily_perf = (post.daily_perf or []) + [metrics]
    merged = dict(post.perf or {})
    merged.update({k: v for k, v in metrics.items() if k != "recorded_at"})
    merged["last_synced_at"] = metrics["recorded_at"]
    post.perf = merged
    db.add(post)
    db.commit()
    db.refresh(post)
    return _enrich_one(db, post)


@router.delete("/content/posts/{post_id}")
def delete_post(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    db.delete(post)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Styles registry — shared, generic slide CSS (read-only, shipped in code)
# ---------------------------------------------------------------------------


@router.get("/content/styles")
def get_styles() -> dict:
    """The shared TikTok slide style registry — base engine CSS + linkable
    styles (captions, hook, text card). Formats link to these by key; the
    slide-builder inlines them; the Library previews them."""
    return {"base_css": base_css(), "styles": list_styles()}


# ---------------------------------------------------------------------------
# Format library CRUD
# ---------------------------------------------------------------------------


class FormatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    slug:       str
    name:       str = ""
    data:       dict = Field(default_factory=dict)


class FormatOut(BaseModel):
    id:         UUID
    project_id: UUID
    slug:       str
    name:       str
    data:       dict
    created_at: str
    updated_at: str


def _format_out(f: ContentFormat) -> FormatOut:
    return FormatOut(
        id=f.id,
        project_id=f.project_id,
        slug=f.slug,
        name=f.name,
        data=f.data or {},
        created_at=f.created_at.isoformat(),
        updated_at=f.updated_at.isoformat(),
    )


@router.get("/content/formats")
def list_formats(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[FormatOut]:
    _project_for_user(db, user, project_id)
    rows = db.execute(
        select(ContentFormat).where(ContentFormat.project_id == project_id).order_by(ContentFormat.slug)
    ).scalars().all()
    return [_format_out(r) for r in rows]


@router.post("/content/formats", status_code=201)
def upsert_format(
    body: FormatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> FormatOut:
    _project_for_user(db, user, body.project_id)
    existing = db.execute(
        select(ContentFormat).where(
            ContentFormat.project_id == body.project_id,
            ContentFormat.slug == body.slug,
        )
    ).scalars().first()
    if existing is not None:
        existing.name = body.name or existing.name
        existing.data = body.data or existing.data
        existing.updated_at = datetime.now(timezone.utc)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return _format_out(existing)
    row = ContentFormat(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _format_out(row)


@router.patch("/content/formats/{format_id}")
def patch_format(
    format_id: UUID,
    body: FormatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> FormatOut:
    row = _row_for_user(db, user, ContentFormat, format_id, "Format")
    row.slug = body.slug or row.slug
    row.name = body.name or row.name
    if body.data:
        row.data = body.data
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _format_out(row)


@router.delete("/content/formats/{format_id}")
def delete_format(
    format_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    row = _row_for_user(db, user, ContentFormat, format_id, "Format")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Avatar library CRUD
# ---------------------------------------------------------------------------


class AvatarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name:       str
    data:       dict = Field(default_factory=dict)


class AvatarOut(BaseModel):
    id:         UUID
    project_id: UUID
    name:       str
    data:       dict
    created_at: str
    updated_at: str


def _avatar_out(a: ContentAvatar) -> AvatarOut:
    return AvatarOut(
        id=a.id,
        project_id=a.project_id,
        name=a.name,
        data=a.data or {},
        created_at=a.created_at.isoformat(),
        updated_at=a.updated_at.isoformat(),
    )


@router.get("/content/avatars")
def list_avatars(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[AvatarOut]:
    _project_for_user(db, user, project_id)
    rows = db.execute(
        select(ContentAvatar).where(ContentAvatar.project_id == project_id).order_by(ContentAvatar.name)
    ).scalars().all()
    return [_avatar_out(r) for r in rows]


@router.post("/content/avatars", status_code=201)
def create_avatar(
    body: AvatarIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> AvatarOut:
    _project_for_user(db, user, body.project_id)
    row = ContentAvatar(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _avatar_out(row)


@router.patch("/content/avatars/{avatar_id}")
def patch_avatar(
    avatar_id: UUID,
    body: AvatarIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> AvatarOut:
    row = _row_for_user(db, user, ContentAvatar, avatar_id, "Avatar")
    if body.name:
        row.name = body.name
    if body.data:
        row.data = body.data
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _avatar_out(row)


@router.delete("/content/avatars/{avatar_id}")
def delete_avatar(
    avatar_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    row = _row_for_user(db, user, ContentAvatar, avatar_id, "Avatar")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Asset uploads + listing (Phase 4b)
# ---------------------------------------------------------------------------


_ALLOWED_ASSET_TYPES = {"logo", "background", "reference", "upload", "discovered_reference"}
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
_MIME_TO_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class ContentAssetOut(BaseModel):
    id:         UUID
    project_id: UUID
    post_id:    UUID | None
    asset_type: str
    source:     str
    url:        str
    filename:   str
    mime_type:  str
    prompt:     str
    model:      str
    params:     dict
    created_at: str


def _asset_out(a: ContentAsset) -> ContentAssetOut:
    return ContentAssetOut(
        id=a.id,
        project_id=a.project_id,
        post_id=a.post_id,
        asset_type=a.asset_type,
        source=a.source,
        url=a.url,
        filename=a.filename,
        mime_type=a.mime_type,
        prompt=a.prompt,
        model=a.model,
        params=a.params or {},
        created_at=a.created_at.isoformat(),
    )


@router.post("/content/uploads", status_code=201)
async def upload_asset(
    project_id: UUID = Form(...),
    asset_type: str  = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> ContentAssetOut:
    """Upload a logo, background, or reference image. Writes to
    /uploads/projects/{project_id}/{asset_type}/{uuid}-{filename} and
    inserts a content_assets row pointing at the public URL."""
    if asset_type not in _ALLOWED_ASSET_TYPES:
        raise HTTPException(400, f"asset_type must be one of {sorted(_ALLOWED_ASSET_TYPES)}")
    _project_for_user(db, user, project_id)

    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_MIME:
        raise HTTPException(400, f"content_type must be one of {sorted(_ALLOWED_MIME)}")

    body = await file.read()
    if len(body) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {_MAX_UPLOAD_BYTES} bytes).")

    ext = _MIME_TO_EXT.get(mime, "bin")
    safe_name = (file.filename or "upload").rsplit("/", 1)[-1].replace(" ", "-")
    asset_id  = uuid4()
    filename  = f"{asset_id}-{safe_name}"
    if "." not in filename.rsplit("/", 1)[-1]:
        filename = f"{filename}.{ext}"

    key = f"projects/{project_id}/{asset_type}/{filename}"
    public_url = storage.put_image(key, body, mime)
    row = ContentAsset(
        id=asset_id,
        project_id=project_id,
        asset_type=asset_type,
        source="upload",
        url=public_url,
        filename=filename,
        mime_type=mime,
        params={"size_bytes": len(body)},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _asset_out(row)


@router.get("/content/assets")
def list_assets(
    project_id: UUID,
    asset_type: str | None = None,
    post_id:    UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[ContentAssetOut]:
    _project_for_user(db, user, project_id)
    stmt = select(ContentAsset).where(ContentAsset.project_id == project_id)
    if asset_type:
        stmt = stmt.where(ContentAsset.asset_type == asset_type)
    if post_id:
        stmt = stmt.where(ContentAsset.post_id == post_id)
    stmt = stmt.order_by(ContentAsset.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [_asset_out(r) for r in rows]


@router.delete("/content/assets/{asset_id}")
def delete_asset(
    asset_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    asset = _row_for_user(db, user, ContentAsset, asset_id, "Asset")
    if asset.url.startswith("/uploads/"):
        cfg = get_configs()
        base = Path(cfg.uploads_dir or "/app/uploads")
        try:
            (base / asset.url[len("/uploads/"):]).unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("delete_asset: failed to remove file %s: %s", asset.url, exc)
    db.delete(asset)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# PostBridge proxies (Phase 4) — schemas match the PostBridge v1 API
# ---------------------------------------------------------------------------


class SocialAccountOut(BaseModel):
    id:       int
    platform: str
    username: str


class PublishRequest(BaseModel):
    """Body for POST /content/posts/{id}/publish.

    social_account_ids are PostBridge's numeric IDs (see GET
    /content/social-accounts). hashtags belong in `caption` per PostBridge.
    """

    model_config = ConfigDict(extra="forbid")

    social_account_ids: list[int]
    scheduled_at:       datetime | None = None
    tiktok_draft:       bool = False


@router.get("/content/social-accounts")
async def list_social_accounts(
    project_id: UUID,
    platform: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[SocialAccountOut]:
    """List the user's connected PostBridge social accounts."""
    from service.post_bridge import PostBridgeAPIError, client_for_user
    proj = _project_for_user(db, user, project_id)
    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        async with client as pb:
            accounts = await pb.list_social_accounts(platform=platform)
    except PostBridgeAPIError as exc:
        raise HTTPException(exc.status_code or 502, _friendly_pb_error(exc)) from exc
    return [
        SocialAccountOut(id=a.id, platform=a.platform.value, username=a.username)
        for a in accounts
    ]


# ---------------------------------------------------------------------------
# Linked accounts — the project's persisted selection of social accounts.
# ---------------------------------------------------------------------------

class LinkedAccountOut(BaseModel):
    account_id: int
    platform:   str
    username:   str


class LinkedAccountIn(BaseModel):
    account_id: int
    platform:   str = ""
    username:   str = ""


class LinkedAccountsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    accounts:   list[LinkedAccountIn] = Field(default_factory=list)


def _link_out(row: ContentSocialLink) -> LinkedAccountOut:
    return LinkedAccountOut(
        account_id=int(row.external_account_id),
        platform=row.platform,
        username=row.username,
    )


@router.get("/content/linked-accounts")
def list_linked_accounts(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[LinkedAccountOut]:
    """The social accounts this project has linked."""
    _project_for_user(db, user, project_id)
    rows = db.execute(
        select(ContentSocialLink)
        .where(ContentSocialLink.project_id == project_id)
        .order_by(ContentSocialLink.created_at)
    ).scalars().all()
    return [_link_out(r) for r in rows]


@router.put("/content/linked-accounts")
def save_linked_accounts(
    body: LinkedAccountsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[LinkedAccountOut]:
    """Replace the project's linked-account set with the supplied list."""
    _project_for_user(db, user, body.project_id)
    db.execute(
        delete(ContentSocialLink).where(ContentSocialLink.project_id == body.project_id)
    )
    # De-dupe by account id, last wins.
    by_id: dict[int, LinkedAccountIn] = {a.account_id: a for a in body.accounts}
    for acc in by_id.values():
        db.add(ContentSocialLink(
            project_id=body.project_id,
            external_account_id=str(acc.account_id),
            platform=acc.platform,
            username=acc.username,
        ))
    db.commit()
    # Analytics output is filtered by the linked platform set — drop its cache.
    _invalidate_analytics(body.project_id)
    rows = db.execute(
        select(ContentSocialLink)
        .where(ContentSocialLink.project_id == body.project_id)
        .order_by(ContentSocialLink.created_at)
    ).scalars().all()
    return [_link_out(r) for r in rows]


# ---------------------------------------------------------------------------
# Analytics — live, pulled straight from PostBridge for the linked accounts.
# (Distinct from per-post `perf`, which only covers posts published via Duct.)
# ---------------------------------------------------------------------------

class AnalyticsRowOut(BaseModel):
    id:                 str
    post_result_id:     str
    platform:           str
    title:              str
    share_url:          str
    cover_image_url:    str
    view_count:         int
    like_count:         int
    comment_count:      int
    share_count:        int
    platform_created_at: str | None
    last_synced_at:     str | None
    # Enriched from the matching local ContentPost (when published via our system).
    pillar:             str = ""
    format_name:        str = ""
    published_via:      str = ""
    post_id:            str | None = None


@router.get("/content/analytics")
async def list_content_analytics(
    project_id: UUID,
    refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> list[AnalyticsRowOut]:
    """Per-post analytics for the project, read straight from PostBridge.

    Mirrors the original marketing app: PostBridge `/v1/analytics` is the source
    of truth — it captures everything published to the account (via this app,
    the PB dashboard, or TikTok Studio), with counts + share_url + cover image.
    Paginates all records, then scopes to the platforms the project has linked
    (Accounts tab); if nothing is linked, shows all. refresh=true syncs first.
    """
    from service.post_bridge import PostBridgeAPIError, client_for_user

    proj = _project_for_user(db, user, project_id)

    if not refresh:
        hit = _analytics_cache.get(project_id)
        if hit is not None and (time.monotonic() - hit[0]) < _ANALYTICS_TTL:
            return hit[1]

    linked_platforms = {
        r.platform
        for r in db.execute(
            select(ContentSocialLink).where(ContentSocialLink.project_id == project_id)
        ).scalars().all()
        if r.platform
    }

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    records = []
    result_to_post: dict[str, str] = {}  # post_result_id -> post_bridge_post_id
    try:
        async with client as pb:
            if refresh:
                await pb.sync_analytics()
            # Paginate all analytics records (PostBridge caps limit at 100).
            offset = 0
            for _ in range(20):  # safety cap: 2000 records
                page = await pb.list_analytics(limit=100, offset=offset)
                records.extend(page)
                if len(page) < 100:
                    break
                offset += 100
            # Best-effort: map result -> PostBridge post id so we can also match
            # local posts that only stored post_bridge_post_id. Never fatal.
            try:
                for r in await pb.list_post_results(limit=100):
                    result_to_post[r.id] = r.post_id
            except PostBridgeAPIError:
                pass
    except PostBridgeAPIError as exc:
        raise HTTPException(exc.status_code or 502, _friendly_pb_error(exc)) from exc

    # Index this project's local posts so each analytics row can be tied back to
    # a pillar/format and badged "via Duct" — by result id (direct) or post id.
    local_posts = db.execute(
        select(ContentPost).where(ContentPost.project_id == project_id)
    ).scalars().all()
    local_by_result = {p.post_bridge_result_id: p for p in local_posts if p.post_bridge_result_id}
    local_by_post = {p.post_bridge_post_id: p for p in local_posts if p.post_bridge_post_id}
    fmt_by_id = _format_map(db, project_id)  # format_id → (slug, name)

    # Self-heal: when post-results responded, persist the result id onto any local
    # post that only had a post id, so it stays matched even if post-results 500s
    # on later loads. (post-results is intermittently flaky on PostBridge's side.)
    backfilled = False
    for result_id, post_id in result_to_post.items():
        lp = local_by_post.get(post_id)
        if lp is not None and not lp.post_bridge_result_id:
            lp.post_bridge_result_id = result_id
            local_by_result[result_id] = lp
            db.add(lp)
            backfilled = True
    if backfilled:
        db.commit()

    rows: list[AnalyticsRowOut] = []
    for a in records:
        if linked_platforms and a.platform not in linked_platforms:
            continue
        local = local_by_result.get(a.post_result_id) or local_by_post.get(result_to_post.get(a.post_result_id, ""))
        rows.append(AnalyticsRowOut(
            id=a.id,
            post_result_id=a.post_result_id,
            platform=a.platform or "",
            title=str(a.video_description or ""),
            share_url=str(a.share_url or ""),
            cover_image_url=str(a.cover_image_url or ""),
            view_count=a.view_count or 0,
            like_count=a.like_count or 0,
            comment_count=a.comment_count or 0,
            share_count=a.share_count or 0,
            platform_created_at=a.platform_created_at if isinstance(a.platform_created_at, str) else None,
            last_synced_at=a.last_synced_at.isoformat() if a.last_synced_at else None,
            pillar=local.pillar if local else "",
            format_name=(fmt_by_id.get(local.format_id, ("", ""))[1] if local else ""),
            published_via=local.published_via if local else "",
            post_id=str(local.id) if local else None,
        ))
    rows.sort(key=lambda x: x.view_count, reverse=True)
    _analytics_cache[project_id] = (time.monotonic(), rows)
    return rows


@router.post("/content/posts/{post_id}/publish")
async def publish_post_route(
    post_id: UUID,
    body: PublishRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    """Upload each linked asset to PostBridge, then create the post."""
    from service.post_bridge import (
        PostBridgeAPIError,
        PostBridgeCreatePostRequest,
        client_for_user,
    )

    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    proj = _project_for_user(db, user, post.project_id)

    asset_rows = db.execute(
        select(ContentAsset)
        .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
        .order_by(ContentAsset.created_at)
    ).scalars().all()
    if not asset_rows:
        raise HTTPException(400, "Generate or upload at least one image before publishing.")

    cfg = get_configs()
    base = Path(cfg.uploads_dir or "/app/uploads")
    asset_paths: list[tuple[Path, str, str, str]] = []
    for a in asset_rows:
        if not a.url.startswith("/uploads/"):
            continue
        disk = base / a.url[len("/uploads/"):]
        if not disk.exists():
            raise HTTPException(500, f"Asset bytes missing on disk for {a.url}.")
        asset_paths.append((disk, a.filename or disk.name, a.mime_type or "image/png", a.url))
    if not asset_paths:
        raise HTTPException(400, "Couldn't find any uploaded image files for this post.")

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        async with client as pb:
            media_ids: list[str] = []
            for disk, name, mime, _url in asset_paths:
                data = disk.read_bytes()
                upload = await pb.create_upload_url(name=name, mime_type=mime, size_bytes=len(data))
                await pb.upload_media(data, upload.upload_url, mime)
                media_ids.append(upload.media_id)

            platform_configs: dict = {}
            if body.tiktok_draft:
                platform_configs["tiktok"] = {"draft": True}

            request = PostBridgeCreatePostRequest(
                caption=post.caption or "",
                social_accounts=body.social_account_ids,
                media=media_ids,
                scheduled_at=body.scheduled_at,
                platform_configurations=platform_configs or None,
            )
            resp = await pb.create_post(request)
    except PostBridgeAPIError as exc:
        raise HTTPException(exc.status_code or 502, _friendly_pb_error(exc)) from exc

    post.post_bridge_post_id = resp.id
    post.published_via = "duct"  # published through our system
    if body.scheduled_at is not None:
        post.scheduled_at = body.scheduled_at
    if resp.status.value == "posted":
        post.status = "posted"
        post.posted_at = datetime.now(timezone.utc)
    elif resp.status.value == "scheduled":
        post.status = "scheduled"
    else:
        post.status = resp.status.value
    db.add(post)
    db.commit()
    db.refresh(post)
    _invalidate_analytics(post.project_id)
    return _enrich_one(db, post)


@router.post("/content/posts/{post_id}/sync-metrics")
async def sync_post_metrics(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    """Sync → find post_result → fetch analytics → merge into post.perf."""
    from service.post_bridge import PostBridgeAPIError, client_for_user

    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    if not post.post_bridge_post_id:
        raise HTTPException(400, "Publish this post first — then we can pull metrics.")
    proj = _project_for_user(db, user, post.project_id)

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        async with client as pb:
            await pb.sync_analytics(platform="tiktok")
            results = await pb.list_post_results(post_id=post.post_bridge_post_id, limit=10)
            if not results:
                raise HTTPException(409, "No post result yet — try again in a few minutes.")
            chosen = next((r for r in results if r.success), results[0])
            analytics_list = await pb.list_analytics(post_result_id=[chosen.id], limit=1)
            if not analytics_list:
                raise HTTPException(409, "Analytics haven't synced yet — try again in a few minutes.")
            analytics = analytics_list[0]
    except PostBridgeAPIError as exc:
        raise HTTPException(exc.status_code or 502, _friendly_pb_error(exc)) from exc

    merged = dict(post.perf or {})
    merged.update({
        k: v for k, v in analytics.model_dump(mode="json").items()
        if v is not None and k not in ("id",)
    })
    merged["last_synced_at"] = (
        analytics.last_synced_at.isoformat() if analytics.last_synced_at else None
    )
    post.perf = merged
    post.post_bridge_result_id = chosen.id
    db.add(post)
    db.commit()
    db.refresh(post)
    _invalidate_analytics(post.project_id)
    return _enrich_one(db, post)


@router.post("/content/posts/{post_id}/sync-daily")
async def sync_post_daily(
    post_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> PostOut:
    """Refresh daily_perf snapshots from PostBridge."""
    from service.post_bridge import PostBridgeAPIError, client_for_user

    post = _row_for_user(db, user, ContentPost, post_id, "Post")
    if not post.post_bridge_post_id:
        raise HTTPException(400, "Publish this post first — then we can pull daily snapshots.")
    proj = _project_for_user(db, user, post.project_id)

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    analytics_id = post.post_bridge_result_id
    try:
        async with client as pb:
            if not analytics_id:
                results = await pb.list_post_results(post_id=post.post_bridge_post_id, limit=10)
                chosen = next((r for r in results if r.success), results[0]) if results else None
                if chosen is None:
                    raise HTTPException(409, "No post result yet — try again in a few minutes.")
                analytics_list = await pb.list_analytics(post_result_id=[chosen.id], limit=1)
                if not analytics_list:
                    raise HTTPException(409, "Analytics haven't synced yet — try again in a few minutes.")
                analytics_id = analytics_list[0].id
                post.post_bridge_result_id = chosen.id
            daily = await pb.get_analytics_daily(analytics_id)
    except PostBridgeAPIError as exc:
        raise HTTPException(exc.status_code or 502, _friendly_pb_error(exc)) from exc

    post.daily_perf = [s.model_dump(mode="json") for s in daily.snapshots]
    db.add(post)
    db.commit()
    db.refresh(post)
    _invalidate_analytics(post.project_id)
    return _enrich_one(db, post)


def _friendly_pb_error(exc) -> str:
    """Translate PostBridge errors into something a user can act on.

    Hides internal status codes and stack traces; only surfaces what the
    user can do next.
    """
    msg = (getattr(exc, "error", None) and getattr(exc.error, "message", "")) or ""
    code = getattr(exc, "status_code", 0)
    if code == 401 or code == 403:
        return "Publishing isn't connected — ask your admin to set up the PostBridge connection."
    if code == 429:
        return "Hit the publishing rate limit — wait a minute and try again."
    if code == 0:
        return "Couldn't reach the publishing service. Check your internet and try again."
    return msg or "Publishing failed. Please try again in a moment."


# ---------------------------------------------------------------------------
# Discovery (Apify TikTok scraper)
# ---------------------------------------------------------------------------


class DiscoverStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id:    UUID
    actor_id:      str
    input_payload: dict = Field(default_factory=dict)


class DiscoverStartOut(BaseModel):
    run_id:     str
    dataset_id: str
    actor_id:   str
    status:     str


class DiscoverStatusOut(BaseModel):
    run_id:     str
    status:     str
    dataset_id: str
    started_at:  str | None = None
    finished_at: str | None = None


class DiscoverResultOut(BaseModel):
    run_id:     str
    dataset_id: str
    count:      int
    items:      list[dict]


class DiscoverSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    actor_id:   str
    run_id:     str
    dataset_id: str
    request:    dict = Field(default_factory=dict)
    post:       dict   # raw ScrapedPost — re-validated server-side


def _apify_client_or_503():
    cfg = get_configs()
    if not cfg.apify_api_key:
        raise HTTPException(503, "Discovery isn't connected — APIFY_API_KEY is not set.")
    from service.apify import ApifyClient
    return ApifyClient(cfg.apify_api_key)


@router.post("/content/discover/start")
async def discover_start(
    body: DiscoverStartIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> DiscoverStartOut:
    """Kick off an Apify actor run for TikTok content discovery."""
    _project_for_user(db, user, body.project_id)
    from service.apify import ApifyAPIError

    client = _apify_client_or_503()
    try:
        async with client as c:
            run = await c.start_run(body.actor_id, body.input_payload)
    except ApifyAPIError as exc:
        raise HTTPException(exc.status_code or 502, exc.message) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return DiscoverStartOut(
        run_id=run.id,
        dataset_id=run.default_dataset_id,
        actor_id=body.actor_id,
        status=run.status.value,
    )


@router.get("/content/discover/status/{run_id}")
async def discover_status(run_id: str) -> DiscoverStatusOut:
    from service.apify import ApifyAPIError

    client = _apify_client_or_503()
    try:
        async with client as c:
            run = await c.get_run(run_id)
    except ApifyAPIError as exc:
        raise HTTPException(exc.status_code or 502, exc.message) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return DiscoverStatusOut(
        run_id=run.id,
        status=run.status.value,
        dataset_id=run.default_dataset_id,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
    )


@router.get("/content/discover/results/{dataset_id}")
async def discover_results(dataset_id: str, limit: int = 200) -> DiscoverResultOut:
    """Fetch raw items from a finished run's dataset.

    We pass items through the ScrapedPost model to drop weird rows, then
    return the validated dicts — keeps the frontend a thin renderer.
    """
    from service.apify import ApifyAPIError

    client = _apify_client_or_503()
    try:
        async with client as c:
            posts = await c.get_dataset_posts(dataset_id, limit=limit)
    except ApifyAPIError as exc:
        raise HTTPException(exc.status_code or 502, exc.message) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return DiscoverResultOut(
        run_id="",
        dataset_id=dataset_id,
        count=len(posts),
        items=[p.model_dump(mode="json") for p in posts],
    )


@router.post("/content/discover/save", status_code=201)
def discover_save(
    body: DiscoverSaveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> ContentAssetOut:
    """Persist one discovered post as a ContentAsset reference.

    No bytes downloaded — we save the metadata + slideshow image URLs in
    `params` so the agent can reference them by URL when generating new
    posts. Downloading + caching the image bytes is a follow-up.
    """
    from service.apify.schema import ScrapedPost

    _project_for_user(db, user, body.project_id)
    try:
        post = ScrapedPost.model_validate(body.post)
    except Exception as exc:  # ValidationError or anything else odd
        raise HTTPException(400, f"Invalid scraped post payload: {exc}") from exc

    # The asset's URL points at the TikTok webVideoUrl (the source of
    # truth); slideshow_image_links go in params so the agent can pull
    # them when constructing image prompts.
    asset = ContentAsset(
        project_id=body.project_id,
        asset_type="discovered_reference",
        source="apify",
        url=post.web_video_url or f"apify://{body.actor_id}/{post.id}",
        filename=f"tiktok-{post.id}",
        mime_type="application/json",
        prompt="",
        model="",
        params={
            "actor_id":    body.actor_id,
            "run_id":      body.run_id,
            "dataset_id":  body.dataset_id,
            "request":     body.request,
            "post":        post.model_dump(mode="json"),
            "saved_at":    datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_out(asset)
