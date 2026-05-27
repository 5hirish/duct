"""Content Marketing Agent routes.

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
from sqlalchemy import select
from sqlmodel import Session

from agents.content.events import ContentEvent
from agents.content.schema import (
    ContentAnswerRequest,
    ContentChatMessage,
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
from agents.models import Platform
from config import get_configs
from db.session import get_session as db_session
from models.content import (
    ContentAsset,
    ContentAvatar,
    ContentFormat,
    ContentPlan,
    ContentPost,
)
from models.project import Project
from service.pipeline import now_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["content"])


# ---------------------------------------------------------------------------
# Session tracking + pruner (mirrors routes/audit.py:38-65)
# ---------------------------------------------------------------------------

_SESSION_TTL = 1800  # 30 minutes
_session_created_at: dict[str, float] = {}


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


@router.on_event("startup")  # type: ignore[attr-defined]
async def _start_pruner() -> None:
    asyncio.create_task(_prune_stale_sessions())


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


def _project_or_404(db: Session, project_id: UUID) -> Project:
    proj = db.get(Project, project_id)
    if proj is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return proj


# ---------------------------------------------------------------------------
# SSE: plan_month
# ---------------------------------------------------------------------------


async def _run_plan_worker(
    session_id: str,
    project_id: UUID,
    emit_fn: Any,
) -> None:
    try:
        api_key = _resolve_api_key()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        runner = ClaudeContentRunner(api_key=api_key)
        await runner.run_plan(session_id, project_id, emit_fn)
    except Exception as exc:
        logger.exception("content: plan worker error for session %s", session_id)
        await emit_fn({
            "event":      ContentEvent.PIPELINE_FAILED,
            "session_id": session_id,
            "error":      str(exc),
        })


@router.post("/content/plan/stream")
async def run_plan_stream(req: PlanRequest) -> StreamingResponse:
    """Start a 30-day plan synthesis session. Returns an SSE stream covering
    the full session lifetime (continues after PIPELINE_FINISHED so the user
    can chat with the agent to refine the plan)."""
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
        if not api_key:
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
        await runner.run_draft(
            session_id,
            req.project_id,
            emit_fn,
            day=day_obj,
            topic=req.topic,
            pillar=req.pillar,
        )
    except Exception as exc:
        logger.exception("content: draft worker error for session %s", session_id)
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
    url:     str | None = None

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
    if body.url is not None:
        proj.url = body.url
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
                    "day_index":     post.day_index,
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
        select(ContentPost).where(ContentPost.plan_id == plan_id).order_by(ContentPost.day_index)
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


@router.patch("/content/plans/{plan_id}/days/{day}")
def patch_plan_day(
    plan_id: UUID,
    day: int,
    body: DayPatch,
    db: Session = Depends(db_session),
) -> PlanOut:
    """Shallow-merge a single day's fields. Day is 1-indexed (1..30)."""
    plan = db.get(ContentPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    days = list(plan.days or [])
    idx = day - 1
    if idx < 0 or idx >= len(days):
        raise HTTPException(400, f"Day {day} out of range (plan has {len(days)} days)")
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
    day_index:     int | None = None
    post_dir_slug: str
    pillar:        str = ""
    topic:         str = ""
    topic_id:      int | None = None
    post_type:     str = "slideshow"
    format_style:  str = "D"
    avatar_id:     UUID | None = None
    slide_count:   int = 0
    status:        str = "pending"
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
    platforms:     list[Platform] = Field(default_factory=lambda: [Platform.TIKTOK])


class PostPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id:       UUID | None = None
    day_index:     int | None = None
    pillar:        str | None = None
    topic:         str | None = None
    topic_id:      int | None = None
    post_type:     str | None = None
    format_style:  str | None = None
    avatar_id:     UUID | None = None
    slide_count:   int | None = None
    status:        str | None = None
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
    platforms:     list[Platform] | None = None
    notes:         str | None = None


class PostOut(BaseModel):
    id:            UUID
    project_id:    UUID
    plan_id:       UUID | None
    day_index:     int | None
    post_dir_slug: str
    pillar:        str
    topic:         str
    topic_id:      int | None
    post_type:     str
    format_style:  str
    avatar_id:     UUID | None
    slide_count:   int
    status:        str
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
    platforms:     list
    posted_at:     str | None
    tiktok_url:    str
    perf:          dict
    daily_perf:    list
    notes:         str
    created_at:    str
    updated_at:    str


def _post_out(p: ContentPost) -> PostOut:
    return PostOut(
        id=p.id,
        project_id=p.project_id,
        plan_id=p.plan_id,
        day_index=p.day_index,
        post_dir_slug=p.post_dir_slug,
        pillar=p.pillar,
        topic=p.topic,
        topic_id=p.topic_id,
        post_type=p.post_type,
        format_style=p.format_style,
        avatar_id=p.avatar_id,
        slide_count=p.slide_count,
        status=p.status,
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
        platforms=p.platforms or [],
        posted_at=p.posted_at.isoformat() if p.posted_at else None,
        tiktok_url=p.tiktok_url,
        perf=p.perf or {},
        daily_perf=p.daily_perf or [],
        notes=p.notes,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.get("/content/posts")
def list_posts(
    project_id: UUID,
    plan_id: UUID | None = None,
    status: str | None = None,
    db: Session = Depends(db_session),
) -> list[PostOut]:
    stmt = select(ContentPost).where(ContentPost.project_id == project_id)
    if plan_id is not None:
        stmt = stmt.where(ContentPost.plan_id == plan_id)
    if status:
        stmt = stmt.where(ContentPost.status == status)
    stmt = stmt.order_by(ContentPost.updated_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [_post_out(r) for r in rows]


@router.get("/content/posts/{post_id}")
def get_post(post_id: UUID, db: Session = Depends(db_session)) -> PostOut:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    return _post_out(post)


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
    if existing is not None:
        for k, v in values.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return _post_out(existing)
    post = ContentPost(**values)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_out(post)


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
    for k, v in patch.items():
        setattr(post, k, v)
    post.updated_at = datetime.now(timezone.utc)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_out(post)


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
    return _post_out(post)


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
    return _post_out(post)


@router.delete("/content/posts/{post_id}")
def delete_post(post_id: UUID, db: Session = Depends(db_session)) -> dict:
    post = db.get(ContentPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found")
    db.delete(post)
    db.commit()
    return {"status": "ok"}


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


_ALLOWED_ASSET_TYPES = {"logo", "background", "reference", "upload"}
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


def _uploads_dir() -> Path:
    cfg = get_configs()
    if not cfg.uploads_enabled:
        raise HTTPException(503, "Uploads are disabled — set UPLOADS_ENABLED=true.")
    base = Path(cfg.uploads_dir or "/app/uploads")
    base.mkdir(parents=True, exist_ok=True)
    return base


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

    base = _uploads_dir()
    target_dir = base / "projects" / str(project_id) / asset_type
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = _MIME_TO_EXT.get(mime, "bin")
    safe_name = (file.filename or "upload").rsplit("/", 1)[-1].replace(" ", "-")
    asset_id  = uuid4()
    filename  = f"{asset_id}-{safe_name}"
    if "." not in filename.rsplit("/", 1)[-1]:
        filename = f"{filename}.{ext}"
    target_path = target_dir / filename
    target_path.write_bytes(body)

    public_url = f"/uploads/projects/{project_id}/{asset_type}/{filename}"
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
    return _post_out(post)


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
    return _post_out(post)


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
    return _post_out(post)


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
