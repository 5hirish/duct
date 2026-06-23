"""Content Studio agent routes.

Streaming endpoints clone the SSE machinery from routes/audit.py:
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
  POST   /api/content/posts/{id}/metrics      — manual metric entry (saves, etc.)

Format + avatar library CRUD:
  GET/POST/PATCH/DELETE  /api/content/formats[/{id}]
  GET/POST/PATCH/DELETE  /api/content/avatars[/{id}]

Deferred:
  · PostBridge publish + sync routes — Phase 4
  · Uploads + assets routes — Phase 4b
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlmodel import Session

from agents.content.events import ContentEvent
from agents.content.styles import base_css, list_styles
from agents.content.schema import (
    ClonePostRequest,
    ContentAnswerRequest,
    ContentChatMessage,
    ContentStatus,
    DraftPostRequest,
    PostType,
)
from agents.content.v3.runner import (
    ClaudeContentRunner,
    close_session,
    create_draft_session,
    get_session,
)
from agents.planner.schema import PlannerConfig
from agents.engines import PROVIDER_CONFIG_ATTR, Engine, resolve_engine_provider
from agents.models import Platform, Provider
from config import claude_oauth_available, get_configs
from db.session import get_engine, get_session as db_session
from models.content import (
    UPLOADABLE_ASSET_TYPES,
    AssetSource,
    AssetType,
    ContentAsset,
    ContentAvatar,
    ContentFormat,
    ContentPlan,
    ContentPost,
    ContentSocialLink,
)
from models.project import Project
from service import storage
from service.pipeline import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["content"])


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


def _resolve_api_key(user_keys: dict[Provider, str] | None = None) -> str:
    """Resolve the content/planner engine key: a per-request bring-your-own key
    for the resolved provider wins over the server config key (content + planner
    are v3/Claude, so this is the Anthropic key in practice)."""
    cfg = get_configs()
    provider = resolve_engine_provider(Engine.V3, cfg.generate_provider or None)
    return (user_keys or {}).get(provider) or getattr(cfg, PROVIDER_CONFIG_ATTR[provider], "") or ""


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


def _project_or_404(db: Session, project_id: UUID) -> Project:
    proj = db.get(Project, project_id)
    if proj is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return proj


# ---------------------------------------------------------------------------
# SSE: content planner (the weekly plan — Content Planner agent)
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


async def _run_planner_worker(
    session_id: str,
    project_id: UUID,
    emit_fn: Any,
    *,
    start_date=None,
    user_keys: dict[Provider, str] | None = None,
) -> None:
    """Run the Content Planner agent (update_plan) — produces the canonical
    rolling 7-day plan via ClaudePlannerRunner."""
    try:
        from agents.planner.v3.runner import ClaudePlannerRunner

        api_key = _resolve_api_key(user_keys)
        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        runner = ClaudePlannerRunner(api_key=api_key)
        await runner.run_plan(session_id, project_id, emit_fn, start_date=start_date)
        _link_conversation_artifact(session_id, "plan")
    except Exception as exc:
        logger.exception("planner: worker error for session %s", session_id)
        await emit_fn({
            "event":      ContentEvent.PIPELINE_FAILED,
            "session_id": session_id,
            "error":      str(exc),
        })


# ---------------------------------------------------------------------------
# SSE: draft_post
# ---------------------------------------------------------------------------


async def _run_draft_worker(
    session_id: str,
    req: DraftPostRequest,
    emit_fn: Any,
    *,
    user_keys: dict[Provider, str] | None = None,
) -> None:
    try:
        api_key = _resolve_api_key(user_keys)
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
            post_type=req.post_type,
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


async def _run_clone_worker(
    session_id: str,
    req: ClonePostRequest,
    emit_fn: Any,
    *,
    user_keys: dict[Provider, str] | None = None,
) -> None:
    """Drive a clone_post session: ingest the reference (deferred + cached on the
    post's clone_source), then model it into an original draft. Mirrors
    _run_draft_worker but the pending post (with clone_source) already exists."""
    try:
        api_key = _resolve_api_key(user_keys)
        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        runner = ClaudeContentRunner(api_key=api_key)
        await runner.run_clone(
            session_id,
            req.project_id,
            emit_fn,
            post_id=req.post_id,
            plan_id=req.plan_id,
            channel=req.channel,
        )
        _link_conversation_artifact(session_id, "post")
    except Exception as exc:
        logger.exception("content: clone worker error for session %s", session_id)
        await emit_fn({
            "event":      ContentEvent.PIPELINE_FAILED,
            "session_id": session_id,
            "error":      str(exc),
        })


@router.post("/content/post/stream")
async def run_post_stream(req: DraftPostRequest) -> StreamingResponse:
    """Start a single-post draft session. SSE stream for the lifetime."""
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
async def submit_content_answers(session_id: str, req: ContentAnswerRequest) -> dict:
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
async def send_content_chat_message(session_id: str, req: ContentChatMessage) -> dict:
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
async def submit_slide_render(session_id: str, req: SlideRenderResult) -> dict:
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
    db: Session = Depends(db_session),
) -> dict:
    """Self-contained 1080×1920 single-slide HTML (images inlined as base64) for
    the browser to rasterize — backing the render_slide bridge. Origin-clean, so
    the client-side canvas capture isn't tainted."""
    from agents.content.schema import Slide
    from agents.content.templates import render_slides_html

    # Scope to the session's project — a valid session can only rasterize its
    # own project's posts (defence-in-depth; content routes lack per-user auth).
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    post = db.get(ContentPost, post_id)
    if post is None or post.project_id != session.project_id:
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
async def close_content_session(session_id: str) -> dict:
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
    db: Session = Depends(db_session),
) -> BrandContextOut:
    return _brand_out(_project_or_404(db, project_id))


@router.put("/content/brand")
def put_brand_context(
    project_id: UUID,
    body: BrandContextIn,
    db: Session = Depends(db_session),
) -> BrandContextOut:
    proj = _project_or_404(db, project_id)
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
# Competitor watchlist — TikTok handles the brand tracks in Discover's profile
# mode. Lives in content_brand.tiktok_competitors (content-owned, writable, no
# migration) and is surfaced on ContentBrandContext so the planner's
# competitor_analyst sees the same list. Single source of truth.
# ---------------------------------------------------------------------------

_WATCHLIST_KEY = "tiktok_competitors"
_WATCHLIST_MAX = 50


def _norm_handles(raw: object) -> list[str]:
    """Normalise TikTok handles: strip @, lowercase, dedupe, drop empties."""
    if not isinstance(raw, (list, tuple)):
        return []
    seen: list[str] = []
    for item in raw:
        h = str(item or "").strip().lstrip("@").lower()
        if h and h not in seen:
            seen.append(h)
        if len(seen) >= _WATCHLIST_MAX:
            break
    return seen


class WatchlistOut(BaseModel):
    handles: list[str]


class WatchlistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handles: list[str] = Field(default_factory=list)


@router.get("/content/discover/watchlist")
def get_discover_watchlist(
    project_id: UUID,
    db: Session = Depends(db_session),
) -> WatchlistOut:
    proj = _project_or_404(db, project_id)
    return WatchlistOut(handles=_norm_handles((proj.content_brand or {}).get(_WATCHLIST_KEY)))


@router.put("/content/discover/watchlist")
def put_discover_watchlist(
    project_id: UUID,
    body: WatchlistIn,
    db: Session = Depends(db_session),
) -> WatchlistOut:
    proj = _project_or_404(db, project_id)
    handles = _norm_handles(body.handles)
    # Reassign a NEW dict so SQLAlchemy detects the JSONB change (mirrors
    # put_brand_context); merging preserves the other content_brand keys.
    cb = dict(proj.content_brand or {})
    cb[_WATCHLIST_KEY] = handles
    proj.content_brand = cb
    proj.updated_at = datetime.now(timezone.utc)
    db.add(proj)
    db.commit()
    return WatchlistOut(handles=handles)


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
def list_plans(project_id: UUID, db: Session = Depends(db_session)) -> list[PlanOut]:
    rows = db.execute(
        select(ContentPlan)
        .where(ContentPlan.project_id == project_id)
        .order_by(ContentPlan.created_at.desc())
    ).scalars().all()
    return [_plan_out(r) for r in rows]


@router.get("/content/plans/{plan_id}")
def get_plan(plan_id: UUID, db: Session = Depends(db_session)) -> PlanOut:
    plan = db.get(ContentPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    posts = db.execute(
        select(ContentPost).where(ContentPost.plan_id == plan_id).order_by(ContentPost.created_at)
    ).scalars().all()
    return _plan_out(plan, posts=list(posts))


@router.post("/content/plans", status_code=201)
def create_plan(body: PlanIn, db: Session = Depends(db_session)) -> PlanOut:
    _project_or_404(db, body.project_id)
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
    db: Session = Depends(db_session),
) -> PlanOut:
    """Shallow-merge a single day's fields by its 0-based position in days[]."""
    plan = db.get(ContentPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
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


class DayAppend(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolerate extra day fields

    post_id:      UUID | None = None
    topic:        str = ""
    pillar:       str = ""
    post_type:    PostType = PostType.SLIDESHOW
    status:       str = "pending"
    source:       str = "manual"   # marks a user-added slot the planner must preserve
    scheduled_at: str | None = None   # ISO "Plan for" date/time; drives board placement
    platforms:    list[str] = Field(default_factory=lambda: ["tiktok"])


@router.post("/content/plans/{plan_id}/days", status_code=201)
def append_plan_day(
    plan_id: UUID,
    body: DayAppend,
    db: Session = Depends(db_session),
) -> PlanOut:
    """Append one day to plan.days[] — the board's Add-post flow lands user
    entries in the plan at their 'Plan for' date/time. Duplicate slots are fine
    (no dedup). The day is tagged source='manual' so content_planner preserves it
    on regeneration."""
    plan = db.get(ContentPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    day = body.model_dump(exclude_none=False)
    if day.get("post_id") is not None:
        day["post_id"] = str(day["post_id"])   # JSONB-safe
    days = list(plan.days or [])
    days.append(day)
    plan.days = days
    plan.updated_at = datetime.now(timezone.utc)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.delete("/content/plans/{plan_id}")
def delete_plan(plan_id: UUID, db: Session = Depends(db_session)) -> dict:
    plan = db.get(ContentPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
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
    post_type:     PostType = PostType.SLIDESHOW
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
    notes:         str = ""
    # Clone/reference lineage for Add-post flow (None for ordinary posts). The
    # source pointer is set on Save; the ingest cache is filled at first Draft-now.
    clone_source:  dict | None = None


class PostPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id:       UUID | None = None
    pillar:        str | None = None
    topic:         str | None = None
    topic_id:      int | None = None
    post_type:     PostType | None = None
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
    clone_source:  dict | None = None


class PostOut(BaseModel):
    id:            UUID
    project_id:    UUID
    plan_id:       UUID | None
    post_dir_slug: str
    pillar:        str
    topic:         str
    topic_id:      int | None
    post_type:     PostType
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
    # Single-clip video (post_type == "video"); empty/None for slideshow posts.
    video_url:               str = ""
    video_asset_id:          UUID | None = None
    video_prompt:            str = ""
    video_duration_seconds:  int | None = None
    video_aspect_ratio:      str = "9:16"
    source_image_asset_id:   UUID | None = None
    posted_at:     str | None
    scheduled_at:  str | None
    tiktok_url:    str
    published_via: str
    # PostBridge linkage — the frontend reads post_bridge_post_id to decide a
    # post is PostBridge-backed (shows Refresh + auto-pulls metrics on view).
    post_bridge_post_id:   str
    post_bridge_result_id: str
    perf:          dict
    daily_perf:    list
    notes:         str
    clone_source:  dict | None = None
    last_assessment: dict | None = None
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
        video_url=p.video_url,
        video_asset_id=p.video_asset_id,
        video_prompt=p.video_prompt,
        video_duration_seconds=p.video_duration_seconds,
        video_aspect_ratio=p.video_aspect_ratio,
        source_image_asset_id=p.source_image_asset_id,
        posted_at=p.posted_at.isoformat() if p.posted_at else None,
        scheduled_at=p.scheduled_at.isoformat() if p.scheduled_at else None,
        tiktok_url=p.tiktok_url,
        published_via=p.published_via,
        post_bridge_post_id=p.post_bridge_post_id,
        post_bridge_result_id=p.post_bridge_result_id,
        perf=p.perf or {},
        daily_perf=p.daily_perf or [],
        notes=p.notes,
        clone_source=p.clone_source,
        last_assessment=p.last_assessment,
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


def _post_thumb(post: ContentPost) -> str:
    """The card thumbnail: the CURRENT first-slide image (the post's cover) —
    walking slides in order, returning the first slide's (or first collage cell's)
    image_url. This is what's actually published, NOT whatever image happened to
    be generated first (which `_thumb_map` returns and is usually a stale, since-
    replaced asset)."""
    for s in post.slides or []:
        if not isinstance(s, dict):
            continue
        u = (s.get("image_url") or "").strip()
        if u:
            return u
        for it in s.get("items") or []:
            if isinstance(it, dict) and (it.get("image_url") or "").strip():
                return it["image_url"].strip()
    return ""


def _thumb_map(db: Session, post_ids: list[UUID]) -> dict[UUID, str]:
    """Fallback thumbnail — map post_id → its MOST RECENT generated/uploaded asset.
    Used when a post has no structured slide image yet (a draft mid-generation, or
    a legacy post). Latest-first so an in-progress draft shows the freshest image,
    not a stale early one. Prefer `_post_thumb` (the current first-slide cover)
    wherever the slides carry image_urls."""
    if not post_ids:
        return {}
    rows = db.execute(
        select(ContentAsset.post_id, ContentAsset.url, ContentAsset.created_at)
        .where(ContentAsset.post_id.in_(post_ids))
        .where(ContentAsset.asset_type.in_([AssetType.GENERATED, AssetType.UPLOAD]))
        .where(ContentAsset.url != "")
        .order_by(ContentAsset.created_at.desc())   # latest first
    ).all()
    out: dict[UUID, str] = {}
    for pid, url, _created in rows:
        if pid is not None and pid not in out and url:
            out[pid] = url   # first seen = most recent (desc order)
    return out


def _fmt_for(post: ContentPost, by_id: dict) -> tuple[str, str] | None:
    return by_id.get(post.format_id)


def _enrich_one(db: Session, post: ContentPost) -> PostOut:
    by_id = _format_map(db, post.project_id)
    thumb = _post_thumb(post) or _thumb_map(db, [post.id]).get(post.id, "")
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
    include_pending: bool = False,
    db: Session = Depends(db_session),
) -> list[PostOut]:
    stmt = select(ContentPost).where(ContentPost.project_id == project_id)
    if plan_id is not None:
        stmt = stmt.where(ContentPost.plan_id == plan_id)
    if status:
        stmt = stmt.where(ContentPost.status == status)
    elif not include_pending:
        # Default board view hides unsaved (pending) drafts — they live only in
        # the live drafting workspace until the user clicks Save (pending→draft).
        # The plan board passes include_pending=1 so user-added (Add-post) entries,
        # which sit at pending until drafted, still appear in their plan slot.
        stmt = stmt.where(ContentPost.status != ContentStatus.PENDING)
    stmt = stmt.order_by(ContentPost.updated_at.desc())
    rows = db.execute(stmt).scalars().all()
    by_id = _format_map(db, project_id)
    thumbs = _thumb_map(db, [r.id for r in rows])  # legacy fallback
    return [
        _post_out(r, fmt=_fmt_for(r, by_id), thumbnail_url=_post_thumb(r) or thumbs.get(r.id, ""))
        for r in rows
    ]


@router.get("/content/posts/{post_id}")
def get_post(post_id: UUID, db: Session = Depends(db_session)) -> PostOut:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
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
    thumb = _post_thumb(post) or _thumb_map(db, [post.id]).get(post.id, "")
    return _post_out(
        post,
        fmt=_fmt_for(post, by_id),
        thumbnail_url=thumb,
        active_conversation_id=active_conversation_id,
    )


def _clone_post_assets(db: Session, src: ContentPost, clone: ContentPost) -> None:
    """Deep-copy the source post's CURRENT images into NEW assets owned by the
    clone, remap the clone's slides to point at them, and re-render its HTML — so
    the variant is fully independent (publishable + downloadable on its own, and
    unaffected by the original's edits/deletion). Only the current per-slide image
    + the latest composed render per slide are copied, not the regeneration
    history. Best-effort per asset: a copy that fails leaves that slide on the
    shared URL rather than blanking it."""
    import copy
    from uuid import uuid4 as _uuid4

    from agents.content.schema import Slide
    from agents.content.templates import render_slides_html

    src_assets = db.execute(
        select(ContentAsset)
        .where(ContentAsset.post_id == src.id, ContentAsset.project_id == src.project_id)
        .order_by(ContentAsset.created_at)   # asc → latest render wins
    ).scalars().all()
    if not src_assets:
        return

    by_url = {a.url: a for a in src_assets if a.url}
    latest_render: dict[str, ContentAsset] = {}
    for a in src_assets:
        if a.asset_type == AssetType.SLIDE_RENDER:
            sid = (a.params or {}).get("slide_id")
            if sid:
                latest_render[str(sid)] = a

    copied: dict[str, ContentAsset] = {}   # old_url → new ContentAsset (dedup)

    def _copy(a: ContentAsset) -> ContentAsset | None:
        if a.url in copied:
            return copied[a.url]
        data = storage.get_bytes(a.url)
        if not data:
            return None
        sub = "renders" if a.asset_type == AssetType.SLIDE_RENDER else "generated"
        ext = Path(a.filename or "").suffix or (".png" if "png" in (a.mime_type or "") else ".jpg")
        key = f"projects/{clone.project_id}/{sub}/{_uuid4().hex}{ext}"
        new = ContentAsset(
            project_id=clone.project_id,
            post_id=clone.id,
            asset_type=a.asset_type,
            source=a.source,
            url=storage.put_image(key, data, a.mime_type or "image/png"),
            filename=a.filename,
            mime_type=a.mime_type,
            prompt=a.prompt,
            model=a.model,
            params=dict(a.params or {}),
        )
        db.add(new)
        copied[a.url] = new
        return new

    # Deep-copy: clone.slides is still the SAME list object as src.slides, and
    # nested items would otherwise be mutated in place — corrupting the original.
    slides = copy.deepcopy([s for s in (clone.slides or []) if isinstance(s, dict)])
    for s in slides:
        u = (s.get("image_url") or "").strip()
        if u in by_url:
            na = _copy(by_url[u])
            if na is not None:
                s["image_url"] = na.url
                s["image_asset_id"] = str(na.id)
        for it in s.get("items") or []:
            if isinstance(it, dict):
                iu = (it.get("image_url") or "").strip()
                if iu in by_url:
                    nia = _copy(by_url[iu])
                    if nia is not None:
                        it["image_url"] = nia.url
                        it["image_asset_id"] = str(nia.id)
        ren = latest_render.get(str(s.get("slide_id")))
        if ren is not None:
            _copy(ren)   # the clone's own composed render (publish gathers by post_id)

    clone.slides = slides
    try:
        clone.slides_html = render_slides_html(
            clone.layout or "full-bleed", [Slide.model_validate(s) for s in slides]
        )
    except Exception:
        logger.warning("clone: slides_html re-render failed; keeping copied html", exc_info=True)


@router.post("/content/posts/{post_id}/clone", status_code=201)
def clone_post(post_id: UUID, db: Session = Depends(db_session)) -> PostOut:
    """Create a new DRAFT variant from an existing post — deep-copies the content
    (slides + their own copies of the current images/renders, copy, layout, hooks,
    metadata) under a fresh slug, with all publish/metrics state cleared. Lets the
    user spin an independent version off a published (or any) post instead of
    editing the original in place."""
    src = db.get(ContentPost, post_id)
    if src is None:
        raise HTTPException(404, "Post not found")

    base = src.post_dir_slug or "post"
    taken = {
        s for (s,) in db.execute(
            select(ContentPost.post_dir_slug).where(ContentPost.project_id == src.project_id)
        ).all()
    }
    slug = f"{base}-copy"
    i = 2
    while slug in taken:
        slug = f"{base}-copy-{i}"
        i += 1

    clone = ContentPost(
        project_id=src.project_id,
        plan_id=src.plan_id,
        post_dir_slug=slug,
        pillar=src.pillar,
        topic=src.topic,
        topic_id=src.topic_id,
        post_type=src.post_type,
        format_id=src.format_id,
        avatar_id=src.avatar_id,
        layout=src.layout,
        slide_count=src.slide_count,
        slides=src.slides or [],
        slides_html=src.slides_html,
        caption=src.caption,
        hashtags=src.hashtags or [],
        tiktok_title=src.tiktok_title,
        hook_type=src.hook_type,
        hook_text=src.hook_text,
        hook_emotion=src.hook_emotion,
        save_cta=src.save_cta,
        bridge_text=src.bridge_text,
        strategic_note=src.strategic_note,
        visual_brief=src.visual_brief,
        emotional_arc=src.emotional_arc,
        camera_ref_pool=src.camera_ref_pool,
        image_prompts=src.image_prompts or [],
        audio_note=src.audio_note,
        platforms=src.platforms or [],
        status=ContentStatus.DRAFT,   # a kept draft — shows on the board immediately
        # publish + perf + last_assessment left at their cleared defaults
    )
    db.add(clone)
    _clone_post_assets(db, src, clone)   # give the variant its own image files
    db.commit()
    db.refresh(clone)
    _invalidate_analytics(clone.project_id)
    return _enrich_one(db, clone)


@router.post("/content/posts", status_code=201)
def create_post(body: PostIn, db: Session = Depends(db_session)) -> PostOut:
    _project_or_404(db, body.project_id)
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
def patch_post(post_id: UUID, body: PostPatch, db: Session = Depends(db_session)) -> PostOut:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
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
    db: Session = Depends(db_session),
    tiktok_url: str | None = None,
) -> PostOut:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
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
    db: Session = Depends(db_session),
) -> PostOut:
    """Append a snapshot to daily_perf + merge into perf (last-write-wins).

    Phase 4 will wire this into PostBridge sync jobs. For now it accepts any
    JSON-serialisable body and persists it as-is.
    """
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
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


# Manual-entry metrics. PostBridge analytics only return view/like/comment/share
# counts; saves, reach, watch time, completion, retention, and audience-age have
# to be read off the platform's native analytics screen and typed in. Field →
# canonical perf key (matches the keys metricsOf/PostCard and the migrated
# MaxAura data already read — we don't invent a third naming convention).
_MANUAL_METRIC_KEYS: dict[str, str] = {
    "views":           "views",
    "likes":           "likes",
    "comments":        "comments",
    "shares":          "shares",
    "saves":           "saves",
    "reach":           "reach",
    "profile_views":   "profileViews",
    "new_followers":   "newFollowers",
    "avg_watch_time":  "avgWatchTime",
    "completion_rate": "completionRate",
    "retention":       "retention",
    "audience_age":    "audienceAge",
}


class ManualMetrics(BaseModel):
    """Manually-entered performance numbers. All optional — only the fields the
    user filled in are merged into perf; the rest are left untouched (so a
    PostBridge sync can still own view/like/comment/share counts)."""

    model_config = ConfigDict(extra="forbid")

    views:           int | None = Field(default=None, ge=0)
    likes:           int | None = Field(default=None, ge=0)
    comments:        int | None = Field(default=None, ge=0)
    shares:          int | None = Field(default=None, ge=0)
    saves:           int | None = Field(default=None, ge=0)
    reach:           int | None = Field(default=None, ge=0)
    profile_views:   int | None = Field(default=None, ge=0)
    new_followers:   int | None = Field(default=None, ge=0)
    avg_watch_time:  float | None = Field(default=None, ge=0)   # seconds
    completion_rate: float | None = Field(default=None, ge=0, le=100)  # percent
    # {"slide1": 100, "slide2": 62, ...} — per-slide retention %, 0–100
    retention:       dict[str, float] | None = None
    # {"18-24": 53, "25-34": 22, ...} — audience-age split %, 0–100
    audience_age:    dict[str, float] | None = None


def _merge_manual_metrics(perf: dict, provided: dict, *, at: str) -> dict:
    """Merge hand-entered metrics into a perf dict (pure — no DB).

    Maps each form field to its canonical perf key, records the touched keys
    under ``manual_keys`` (so a later PostBridge sync won't be assumed to own
    them), and stamps ``manual_updated_at``. Leaves untouched keys — notably the
    PostBridge ``*_count`` fields — exactly as they were.
    """
    merged = dict(perf or {})
    manual = set(merged.get("manual_keys") or [])
    for field, value in provided.items():
        key = _MANUAL_METRIC_KEYS.get(field, field)
        merged[key] = value
        manual.add(key)
    merged["manual_keys"] = sorted(manual)
    merged["manual_updated_at"] = at
    return merged


@router.post("/content/posts/{post_id}/metrics")
def update_post_metrics(
    post_id: UUID,
    body: ManualMetrics,
    db: Session = Depends(db_session),
) -> PostOut:
    """Merge user-entered metrics into perf (last-write-wins per key).

    Distinct from /sync-metrics (PostBridge pull) and /log-metrics (append a
    daily snapshot): this only updates the current lifetime numbers and records
    which keys are human-entered, so a later PostBridge sync won't be assumed to
    own them. Does not touch daily_perf — that stays PostBridge's domain so a
    /sync-daily refresh can't clobber hand-entered history.
    """
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")

    provided = body.model_dump(exclude_none=True)
    if not provided:
        raise HTTPException(400, "No metrics provided.")

    post.perf = _merge_manual_metrics(
        post.perf, provided, at=datetime.now(timezone.utc).isoformat()
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    _invalidate_analytics(post.project_id)
    return _enrich_one(db, post)


@router.delete("/content/posts/{post_id}")
def delete_post(post_id: UUID, db: Session = Depends(db_session)) -> dict:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
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
def list_formats(project_id: UUID, db: Session = Depends(db_session)) -> list[FormatOut]:
    rows = db.execute(
        select(ContentFormat).where(ContentFormat.project_id == project_id).order_by(ContentFormat.slug)
    ).scalars().all()
    return [_format_out(r) for r in rows]


@router.post("/content/formats", status_code=201)
def upsert_format(body: FormatIn, db: Session = Depends(db_session)) -> FormatOut:
    _project_or_404(db, body.project_id)
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
def patch_format(format_id: UUID, body: FormatIn, db: Session = Depends(db_session)) -> FormatOut:
    row = db.get(ContentFormat, format_id)
    if row is None:
        raise HTTPException(404, "Format not found")
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
def delete_format(format_id: UUID, db: Session = Depends(db_session)) -> dict:
    row = db.get(ContentFormat, format_id)
    if row is None:
        raise HTTPException(404, "Format not found")
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
def list_avatars(project_id: UUID, db: Session = Depends(db_session)) -> list[AvatarOut]:
    rows = db.execute(
        select(ContentAvatar).where(ContentAvatar.project_id == project_id).order_by(ContentAvatar.name)
    ).scalars().all()
    return [_avatar_out(r) for r in rows]


@router.post("/content/avatars", status_code=201)
def create_avatar(body: AvatarIn, db: Session = Depends(db_session)) -> AvatarOut:
    _project_or_404(db, body.project_id)
    row = ContentAvatar(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _avatar_out(row)


@router.patch("/content/avatars/{avatar_id}")
def patch_avatar(avatar_id: UUID, body: AvatarIn, db: Session = Depends(db_session)) -> AvatarOut:
    row = db.get(ContentAvatar, avatar_id)
    if row is None:
        raise HTTPException(404, "Avatar not found")
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
def delete_avatar(avatar_id: UUID, db: Session = Depends(db_session)) -> dict:
    row = db.get(ContentAvatar, avatar_id)
    if row is None:
        raise HTTPException(404, "Avatar not found")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Asset uploads + listing (Phase 4b)
# ---------------------------------------------------------------------------


_ALLOWED_ASSET_TYPES = UPLOADABLE_ASSET_TYPES
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
    db: Session = Depends(db_session),
) -> ContentAssetOut:
    """Upload a logo, background, or reference image. Writes to
    /uploads/projects/{project_id}/{asset_type}/{uuid}-{filename} and
    inserts a content_assets row pointing at the public URL."""
    if asset_type not in _ALLOWED_ASSET_TYPES:
        raise HTTPException(400, f"asset_type must be one of {sorted(_ALLOWED_ASSET_TYPES)}")
    _project_or_404(db, project_id)

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
        source=AssetSource.UPLOAD,
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
    db: Session = Depends(db_session),
) -> list[ContentAssetOut]:
    stmt = select(ContentAsset).where(ContentAsset.project_id == project_id)
    if asset_type:
        stmt = stmt.where(ContentAsset.asset_type == asset_type)
    if post_id:
        stmt = stmt.where(ContentAsset.post_id == post_id)
    stmt = stmt.order_by(ContentAsset.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [_asset_out(r) for r in rows]


@router.delete("/content/assets/{asset_id}")
def delete_asset(asset_id: UUID, db: Session = Depends(db_session)) -> dict:
    asset = db.get(ContentAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
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
    db: Session = Depends(db_session),
) -> list[SocialAccountOut]:
    """List the user's connected PostBridge social accounts."""
    from service.post_bridge import PostBridgeAPIError, client_for_user
    proj = _project_or_404(db, project_id)
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
    db: Session = Depends(db_session),
) -> list[LinkedAccountOut]:
    """The social accounts this project has linked."""
    _project_or_404(db, project_id)
    rows = db.execute(
        select(ContentSocialLink)
        .where(ContentSocialLink.project_id == project_id)
        .order_by(ContentSocialLink.created_at)
    ).scalars().all()
    return [_link_out(r) for r in rows]


@router.put("/content/linked-accounts")
def save_linked_accounts(
    body: LinkedAccountsIn,
    db: Session = Depends(db_session),
) -> list[LinkedAccountOut]:
    """Replace the project's linked-account set with the supplied list."""
    _project_or_404(db, body.project_id)
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

# Most platform share URLs embed the posting handle as `/@handle` (TikTok,
# YouTube, Threads, Bluesky). We use it to attribute a row to a linked account
# when PostBridge's post-results endpoint (the only other link) is unavailable.
_HANDLE_RE = re.compile(r"/@([A-Za-z0-9._-]+)")


def _handle_from_url(url: str) -> str:
    m = _HANDLE_RE.search(url or "")
    return m.group(1).lower() if m else ""


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
    # The PostBridge social account this result belongs to (for per-account
    # filtering in the UI). Resolved via the post-result → social_account_id link.
    social_account_id:  int | None = None
    account_username:   str = ""
    # Enriched from the matching local ContentPost (when published via our system).
    pillar:             str = ""
    format_name:        str = ""
    published_via:      str = ""
    post_id:            str | None = None


@router.get("/content/analytics")
async def list_content_analytics(
    project_id: UUID,
    refresh: bool = False,
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

    proj = _project_or_404(db, project_id)

    if not refresh:
        hit = _analytics_cache.get(project_id)
        if hit is not None and (time.monotonic() - hit[0]) < _ANALYTICS_TTL:
            return hit[1]

    linked_rows = db.execute(
        select(ContentSocialLink).where(ContentSocialLink.project_id == project_id)
    ).scalars().all()
    linked_platforms = {r.platform for r in linked_rows if r.platform}
    # handle -> (social_account_id, username): the reliable, local way to attribute
    # an analytics row to an account by the handle in its share_url, used when
    # PostBridge's post-results endpoint (the only upstream link) is down.
    linked_by_handle: dict[str, tuple[int, str]] = {}
    for r in linked_rows:
        handle = (r.username or "").lstrip("@").lower()
        if not handle:
            continue
        try:
            linked_by_handle[handle] = (int(r.external_account_id), r.username)
        except (TypeError, ValueError):
            continue

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    records = []
    result_to_post: dict[str, str] = {}     # post_result_id -> post_bridge_post_id
    result_to_account: dict[str, int] = {}  # post_result_id -> social_account_id
    result_to_username: dict[str, str] = {} # post_result_id -> handle (from result)
    accounts_by_id: dict[int, str] = {}     # social_account_id -> canonical username
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
            # local posts that only stored post_bridge_post_id, and result ->
            # social account so each row can be filtered by account. Never fatal.
            try:
                for r in await pb.list_post_results(limit=100):
                    result_to_post[r.id] = r.post_id
                    if r.social_account_id:
                        result_to_account[r.id] = r.social_account_id
                    if r.platform_data and r.platform_data.username:
                        result_to_username[r.id] = r.platform_data.username
            except PostBridgeAPIError:
                pass
            # Canonical handles per account (post-result platform_data may be null).
            try:
                for acct in await pb.list_social_accounts(limit=100):
                    accounts_by_id[acct.id] = acct.username
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
        # Attribute to a social account: prefer the post-results link, fall back to
        # the handle in the share_url matched against the project's linked accounts.
        acct_id = result_to_account.get(a.post_result_id)
        acct_username = (accounts_by_id.get(acct_id, "") if acct_id else "") \
            or result_to_username.get(a.post_result_id, "")
        if acct_id is None:
            hit = linked_by_handle.get(_handle_from_url(str(a.share_url or "")))
            if hit:
                acct_id, acct_username = hit
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
            social_account_id=acct_id,
            account_username=acct_username,
            pillar=local.pillar if local else "",
            format_name=(fmt_by_id.get(local.format_id, ("", ""))[1] if local else ""),
            published_via=local.published_via if local else "",
            post_id=str(local.id) if local else None,
        ))
    rows.sort(key=lambda x: x.view_count, reverse=True)
    _analytics_cache[project_id] = (time.monotonic(), rows)
    return rows


def _select_publish_assets(db: Session, post: ContentPost) -> list[ContentAsset]:
    """The images to actually publish: ONE per slide, in slide order — the latest
    COMPOSED render (caption baked in) when present, else a single-image slide's
    raw photo. A post accumulates dozens of assets across regenerations + per-slide
    renders; uploading them all would ship the wrong frames in the wrong order and
    take minutes. Shared by both publish routes so they upload the same set.

    Video posts are the exception: they publish ONE clip — the attached video
    asset (post.video_asset_id), with a latest-video-asset fallback.
    """
    if post.post_type == PostType.VIDEO:
        if post.video_asset_id is not None:
            vid = db.get(ContentAsset, post.video_asset_id)
            if vid is not None and vid.project_id == post.project_id:
                return [vid]
        # Fallback: the most recent video/* asset attached to this post.
        post_videos = db.execute(
            select(ContentAsset)
            .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
            .order_by(ContentAsset.created_at.desc())
        ).scalars().all()
        for a in post_videos:
            if (a.mime_type or "").startswith("video/"):
                return [a]
        return []

    all_assets = db.execute(
        select(ContentAsset)
        .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
        .order_by(ContentAsset.created_at)   # ascending → the latest render of a slide wins
    ).scalars().all()
    if not all_assets:
        return []

    renders_by_slide: dict[str, ContentAsset] = {}
    by_url: dict[str, ContentAsset] = {}
    for a in all_assets:
        if a.asset_type == AssetType.SLIDE_RENDER:
            sid = (a.params or {}).get("slide_id")
            if sid:
                renders_by_slide[str(sid)] = a
        if a.url:
            by_url.setdefault(a.url, a)

    slides_meta = [s for s in (post.slides or []) if isinstance(s, dict)]
    if not slides_meta:
        return list(all_assets)   # legacy posts with no structured slides

    chosen: list[ContentAsset] = []
    for s in slides_meta:
        sid = str(s.get("slide_id") or "")
        ren = renders_by_slide.get(sid)
        if ren is not None:
            chosen.append(ren)
            continue
        # No composed render: a single-image slide falls back to its raw photo
        # (collage / before-after must be rendered to compose, so skip).
        url = s.get("image_url")
        fb = by_url.get(url) if url else None
        if fb is not None and not s.get("items"):
            chosen.append(fb)
    return chosen


def _slide_id_of(asset: ContentAsset) -> str:
    """The slide a render belongs to (for streaming progress labels)."""
    if asset.asset_type == AssetType.SLIDE_RENDER:
        return str((asset.params or {}).get("slide_id") or "")
    return ""


def _apply_publish_status(post: ContentPost, resp, *, scheduled: bool) -> None:
    """Map PostBridge's response status onto a VALID ContentStatus. create_post
    succeeded (it returned an id), so the post is live or in-flight — anything that
    isn't an explicit schedule becomes "posted". We never persist PostBridge's
    transient values (e.g. "processing"): they aren't a ContentStatus, so they'd
    strand the post off the kanban board (which groups by ContentStatus)."""
    if scheduled or resp.status.value == "scheduled":
        post.status = "scheduled"
    else:
        post.status = "posted"
        post.posted_at = datetime.now(timezone.utc)


@router.post("/content/posts/{post_id}/publish")
async def publish_post_route(
    post_id: UUID,
    body: PublishRequest,
    db: Session = Depends(db_session),
) -> PostOut:
    """Upload each linked asset to PostBridge, then create the post."""
    from service.post_bridge import (
        PostBridgeAPIError,
        PostBridgeCreatePostRequest,
        client_for_user,
    )

    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    proj = db.get(Project, post.project_id)
    if proj is None:
        raise HTTPException(404, "Project not found")

    chosen = _select_publish_assets(db, post)
    if not chosen:
        raise HTTPException(400, "No images to publish — generate and render the slides first.")

    try:
        client = client_for_user(proj.user_id, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        async with client as pb:
            media_ids: list[str] = []
            for a in chosen:
                data = await asyncio.to_thread(storage.get_bytes, a.url)   # /uploads (disk) or R2 (HTTP)
                if not data:
                    raise HTTPException(500, f"Couldn't load image bytes for {a.url}.")
                mime = a.mime_type or "image/png"
                upload = await pb.create_upload_url(
                    name=a.filename or f"slide-{len(media_ids) + 1}.png",
                    mime_type=mime, size_bytes=len(data),
                )
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
    _apply_publish_status(post, resp, scheduled=body.scheduled_at is not None)
    db.add(post)
    db.commit()
    db.refresh(post)
    _invalidate_analytics(post.project_id)
    return _enrich_one(db, post)


@router.post("/content/posts/{post_id}/publish/stream")
async def publish_post_stream(post_id: UUID, body: PublishRequest) -> StreamingResponse:
    """Same as POST .../publish, but streams progress as SSE so the UI can show
    real per-slide steps. Events: ``prepare`` → ``upload`` (index/total/slide_id)
    → ``create`` → ``done`` | ``error``. Opens its own DB session — the request's
    session is torn down once we start streaming the body."""
    from service.post_bridge import (
        PostBridgeAPIError,
        PostBridgeCreatePostRequest,
        client_for_user,
    )

    def _sse(d: dict) -> str:
        d.setdefault("ts", now_iso())
        return f"data: {json.dumps(d, default=str)}\n\n"

    async def gen() -> AsyncGenerator[str, None]:
        try:
            with Session(get_engine()) as db:
                post = db.get(ContentPost, post_id)
                if post is None:
                    yield _sse({"event": "error", "message": "Post not found."})
                    return
                proj = db.get(Project, post.project_id)
                if proj is None:
                    yield _sse({"event": "error", "message": "Project not found."})
                    return

                chosen = _select_publish_assets(db, post)
                if not chosen:
                    yield _sse({"event": "error", "message": "No images to publish — generate and render the slides first."})
                    return

                total = len(chosen)
                yield _sse({"event": "prepare", "total": total})

                try:
                    client = client_for_user(proj.user_id, db)
                except ValueError as exc:
                    yield _sse({"event": "error", "message": str(exc)})
                    return

                media_ids: list[str] = []
                try:
                    async with client as pb:
                        for i, a in enumerate(chosen):
                            yield _sse({"event": "upload", "index": i + 1, "total": total, "slide_id": _slide_id_of(a)})
                            data = await asyncio.to_thread(storage.get_bytes, a.url)
                            if not data:
                                yield _sse({"event": "error", "message": "Couldn't load one of the slide images. Try regenerating it."})
                                return
                            mime = a.mime_type or "image/png"
                            upload = await pb.create_upload_url(
                                name=a.filename or f"slide-{i + 1}.png", mime_type=mime, size_bytes=len(data),
                            )
                            await pb.upload_media(data, upload.upload_url, mime)
                            media_ids.append(upload.media_id)

                        yield _sse({"event": "create"})
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
                    yield _sse({"event": "error", "message": _friendly_pb_error(exc)})
                    return

                post.post_bridge_post_id = resp.id
                post.published_via = "duct"
                if body.scheduled_at is not None:
                    post.scheduled_at = body.scheduled_at
                _apply_publish_status(post, resp, scheduled=body.scheduled_at is not None)
                db.add(post)
                db.commit()
                db.refresh(post)
                _invalidate_analytics(post.project_id)
                out = _enrich_one(db, post)
                yield _sse({
                    "event": "done",
                    "status": post.status,
                    "scheduled": bool(body.scheduled_at),
                    "tiktok_draft": bool(body.tiktok_draft),
                    "post": out.model_dump(mode="json"),
                })
        except Exception:
            logger.exception("publish_post_stream failed")
            yield _sse({"event": "error", "message": "Publishing failed. Please try again."})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/content/posts/{post_id}/slides.zip")
def download_post_slides(post_id: UUID, db: Session = Depends(db_session)) -> Response:
    """Download the post's composed slide renders (in slide order) + a caption.txt,
    as a zip — so the user can publish manually. Same image-selection as the
    publish routes (one composed render per slide). Sync endpoint: FastAPI runs it
    in a worker thread, so the blocking byte reads (disk / R2) don't stall the loop."""
    import io
    import zipfile

    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    chosen = _select_publish_assets(db, post)
    if not chosen:
        raise HTTPException(400, "No images to download — generate and render the slides first.")

    _ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        n = 0
        for i, a in enumerate(chosen):
            data = storage.get_bytes(a.url)
            if not data:
                continue
            ext = _ext.get((a.mime_type or "").lower(), "") or Path(a.filename or "").suffix or ".png"
            zf.writestr(f"slide-{i + 1:02d}{ext}", data)
            n += 1
        if not n:
            raise HTTPException(500, "Couldn't load the slide images. Try regenerating them.")
        caption = (post.caption or "").strip()
        tags = " ".join(t for t in (post.hashtags or []) if t)
        caption_txt = "\n\n".join(p for p in (caption, tags) if p)
        if caption_txt:
            zf.writestr("caption.txt", caption_txt + "\n")

    slug = post.post_dir_slug or str(post.id)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}-slides.zip"'},
    )


@router.post("/content/posts/{post_id}/sync-metrics")
async def sync_post_metrics(
    post_id: UUID,
    db: Session = Depends(db_session),
) -> PostOut:
    """Sync → find post_result → fetch analytics → merge into post.perf."""
    from service.post_bridge import PostBridgeAPIError, client_for_user

    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    if not post.post_bridge_post_id:
        raise HTTPException(400, "Publish this post first — then we can pull metrics.")
    proj = db.get(Project, post.project_id)
    if proj is None:
        raise HTTPException(404, "Project not found")

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
    db: Session = Depends(db_session),
) -> PostOut:
    """Refresh daily_perf snapshots from PostBridge."""
    from service.post_bridge import PostBridgeAPIError, client_for_user

    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    if not post.post_bridge_post_id:
        raise HTTPException(400, "Publish this post first — then we can pull daily snapshots.")
    proj = db.get(Project, post.project_id)
    if proj is None:
        raise HTTPException(404, "Project not found")

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
# Content Planner configuration (agent_contexts, agent_id='content_planner')
# ---------------------------------------------------------------------------


@router.get("/content/planner-config")
def get_planner_config(project_id: UUID) -> dict:
    """Read the saved planner config + the project's connected social accounts.

    The content_planner agent writes config via its save_planner_config tool;
    this endpoint backs the UI's display / manual reconfigure path."""
    from agents.planner.data import linked_accounts, load_planner_config

    config = load_planner_config(project_id)
    return {
        "config": config.model_dump(mode="json"),
        "is_complete": config.is_complete(),
        "connected_accounts": linked_accounts(project_id),
    }


@router.put("/content/planner-config")
def put_planner_config(project_id: UUID, config: PlannerConfig) -> dict:
    """Upsert the planner config for a project."""
    from agents.planner.data import save_planner_config

    saved = save_planner_config(project_id, config)
    return {"config": saved.model_dump(mode="json"), "is_complete": saved.is_complete()}


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


# In-process dedupe cache for discover runs. The backend runs a single uvicorn
# worker (railway.json), so a module-level dict is shared across all requests.
# An identical search (same project + actor + input) within the TTL reuses the
# prior Apify run instead of paying for a fresh one — the actor run is the
# expensive, slow part; reading its dataset later is free. Lost on restart
# (worst case: one extra run); swap for Redis if we ever scale to >1 replica.
_DISCOVER_CACHE: dict[str, tuple[float, str]] = {}
_DISCOVER_CACHE_TTL = 1800.0  # 30 minutes


def _discover_cache_key(project_id: UUID, actor_id: str, payload: dict) -> str:
    blob = json.dumps(payload or {}, sort_keys=True, default=str)
    return hashlib.sha256(f"{project_id}|{actor_id}|{blob}".encode()).hexdigest()


@router.post("/content/discover/start")
async def discover_start(body: DiscoverStartIn, db: Session = Depends(db_session)) -> DiscoverStartOut:
    """Kick off (or reuse a recent) Apify actor run for TikTok discovery."""
    from service.apify import ApifyAPIError
    from service.apify.schema import ApifyRunStatus

    _project_or_404(db, body.project_id)
    client = _apify_client_or_503()
    key = _discover_cache_key(body.project_id, body.actor_id, body.input_payload)
    dead = {
        ApifyRunStatus.FAILED, ApifyRunStatus.ABORTING, ApifyRunStatus.ABORTED,
        ApifyRunStatus.TIMING_OUT, ApifyRunStatus.TIMED_OUT,
    }

    try:
        async with client as c:
            cached = _DISCOVER_CACHE.get(key)
            if cached and (time.monotonic() - cached[0]) < _DISCOVER_CACHE_TTL:
                # Confirm the cached run is still usable before reusing it — a
                # since-failed run shouldn't trap repeat searches for 30 min.
                try:
                    run = await c.get_run(cached[1])
                    if run.status not in dead:
                        logger.info(
                            "discover: reusing run actor=%s project=%s run_id=%s dataset_id=%s status=%s",
                            body.actor_id, body.project_id, run.id,
                            run.default_dataset_id, run.status.value,
                        )
                        return DiscoverStartOut(
                            run_id=run.id,
                            dataset_id=run.default_dataset_id,
                            actor_id=body.actor_id,
                            status=run.status.value,
                        )
                except ApifyAPIError:
                    pass  # gone / unreachable — fall through to a fresh run
                _DISCOVER_CACHE.pop(key, None)

            run = await c.start_run(body.actor_id, body.input_payload)
    except ApifyAPIError as exc:
        raise HTTPException(exc.status_code or 502, exc.message) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    _DISCOVER_CACHE[key] = (time.monotonic(), run.id)
    logger.info(
        "discover: started run actor=%s project=%s run_id=%s dataset_id=%s",
        body.actor_id, body.project_id, run.id, run.default_dataset_id,
    )
    return DiscoverStartOut(
        run_id=run.id,
        dataset_id=run.default_dataset_id,
        actor_id=body.actor_id,
        status=run.status.value,
    )


@router.get("/content/discover/status/{run_id}")
async def discover_status(run_id: str, response: Response) -> DiscoverStatusOut:
    from service.apify import ApifyAPIError

    # Polled every 3s while a run is in flight — never serve a stale status.
    response.headers["Cache-Control"] = "no-store"
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
async def discover_results(dataset_id: str, response: Response, limit: int = 200) -> DiscoverResultOut:
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

    # A finished run's dataset is immutable, so let the browser cache it on
    # refresh/revisit. Kept modest — the TikTok cover URLs inside are signed
    # and expire within hours, so a day-long cache would surface dead images.
    response.headers["Cache-Control"] = "private, max-age=3600"
    return DiscoverResultOut(
        run_id="",
        dataset_id=dataset_id,
        count=len(posts),
        items=[p.model_dump(mode="json") for p in posts],
    )


class DiscoverReferenceOut(BaseModel):
    asset_id:     str
    tiktok_url:   str
    cover_url:    str
    is_slideshow: bool
    author:       str
    text:         str
    metrics:      dict   # views/likes/comments/shares/saves
    diagnostic:   dict   # dominant lever + ratios (service.discovery.diagnose_reference)
    has_media:    bool


@router.get("/content/discover/references")
def discover_references(
    project_id: UUID,
    min_plays: int = 0,
    limit: int = 60,
    db: Session = Depends(db_session),
) -> list[DiscoverReferenceOut]:
    """Saved discovered references for the Add-post 'References' picker — newest
    first, with a captured cover + the 'why it worked' diagnostic so each card is
    self-describing. min_plays defaults to 0 (show everything the user saved)."""
    from service.discovery import diagnose_reference

    rows = db.execute(
        select(ContentAsset)
        .where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == AssetType.DISCOVERED_REFERENCE,
        )
        .order_by(ContentAsset.created_at.desc())
        .limit(200)
    ).scalars().all()

    out: list[DiscoverReferenceOut] = []
    for r in rows:
        params = r.params or {}
        post = params.get("post") or {}
        if (post.get("play_count") or 0) < min_plays:
            continue
        media = params.get("media") or {}
        vm = post.get("video_meta") or {}
        cover = media.get("cover") or vm.get("cover_url") or vm.get("original_cover_url") or ""
        out.append(DiscoverReferenceOut(
            asset_id=str(r.id),
            tiktok_url=r.url,
            cover_url=cover,
            is_slideshow=bool(post.get("is_slideshow")),
            author=(post.get("author_meta") or {}).get("name") or "",
            text=(post.get("text") or "")[:280],
            metrics={
                "views":    post.get("play_count"),
                "likes":    post.get("digg_count"),
                "comments": post.get("comment_count"),
                "shares":   post.get("share_count"),
                "saves":    post.get("collect_count"),
            },
            diagnostic=diagnose_reference(post),
            has_media=(media.get("status") == "ok"),
        ))
        if len(out) >= limit:
            break
    return out


@router.get("/content/discover/oembed")
async def discover_oembed(url: str, response: Response) -> dict:
    """Free TikTok oEmbed peek for the paste-URL Add-post mode — proxied so the
    browser dodges CORS. Returns {title, author_name, thumbnail_url}. NO Apify
    cost (oEmbed is a public, free TikTok endpoint); the full scrape is deferred
    to Draft-now. Best-effort: a 502 just means the modal shows the raw URL."""
    import httpx

    if not url.startswith(("http://", "https://")) or "tiktok" not in url:
        raise HTTPException(400, "Provide a TikTok URL.")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
            r = await c.get("https://www.tiktok.com/oembed", params={"url": url})
        if r.status_code != 200:
            raise HTTPException(502, "oEmbed unavailable")
        data = r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"oEmbed failed: {exc}") from exc
    response.headers["Cache-Control"] = "private, max-age=600"
    return {
        "title":         data.get("title") or "",
        "author_name":   data.get("author_name") or "",
        "thumbnail_url": data.get("thumbnail_url") or "",
    }


@router.post("/content/discover/save", status_code=201)
def discover_save(
    body: DiscoverSaveIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(db_session),
) -> ContentAssetOut:
    """Persist one discovered post as a ContentAsset reference.

    Returns immediately with the metadata + source URLs; a background task then
    downloads the cover + slideshow image bytes into our bucket (params.media)
    so the reference survives TikTok's signed-URL expiry and can be analysed
    later. See service.discovery.capture_reference_media.
    """
    from service.apify.schema import ScrapedPost
    from service.discovery import capture_reference_media

    _project_or_404(db, body.project_id)
    try:
        post = ScrapedPost.model_validate(body.post)
    except Exception as exc:  # ValidationError or anything else odd
        raise HTTPException(400, f"Invalid scraped post payload: {exc}") from exc

    # The asset's URL points at the TikTok webVideoUrl (the source of
    # truth); slideshow_image_links go in params so the agent can pull
    # them when constructing image prompts.
    asset = ContentAsset(
        project_id=body.project_id,
        asset_type=AssetType.DISCOVERED_REFERENCE,
        source=AssetSource.APIFY,
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

    # Fire-and-forget: pull the cover + slideshow bytes into our bucket before
    # TikTok's signed CDN URLs expire. Runs after the response is sent.
    background_tasks.add_task(
        capture_reference_media, asset.id, post.model_dump(mode="json")
    )
    return _asset_out(asset)


@router.post("/content/discover/recapture-media")
def recapture_discover_media(
    project_id: UUID,
    limit: int = 50,
    db: Session = Depends(db_session),
) -> dict:
    """Backfill media for saved discoveries whose capture was lost (server
    restart) or failed. Recovers only while the TikTok CDN URLs are still
    alive. Manual/cron trigger — see service.discovery.recapture_missing_media.
    """
    from service.discovery import recapture_missing_media

    _project_or_404(db, project_id)
    return recapture_missing_media(project_id, limit=max(1, min(limit, 200)))


@router.get("/content/discover/benchmark")
def get_discover_benchmark(
    project_id: UUID,
    db: Session = Depends(db_session),
) -> dict:
    """The project's own posted-post baseline (median engagement + format mix),
    for Discover's "you vs niche" overlay. Engagement is computed the same way
    as the scraped niche so the comparison is apples-to-apples. Empty on cold
    start (no posted posts yet).
    """
    from agents.planner.data import performance_baseline

    _project_or_404(db, project_id)
    return performance_baseline(project_id)
