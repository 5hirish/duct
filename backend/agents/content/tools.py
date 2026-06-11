"""In-process MCP tools exposed to the Content Studio agent.

Two groups of tools:
  - Writers: submit_plan, submit_post_draft — validate Pydantic, upsert DB,
    emit SSE events (PLAN_GENERATED / POST_DRAFT_UPDATED).
  - Readers: fetch_brand_context, fetch_topic_bank, fetch_format_library,
    fetch_avatar_library, fetch_content_history, fetch_content_assets.
  - Stubs: generate_image, edit_image, publish_post, mark_posted, log_metrics
    — return is_error=true with "available in Phase 4/4b" until those phases land.

Every handler:
  1. Opens a short-lived DB session (db.session.get_session generator), never
     binding a long-lived session to the agent lifetime.
  2. Wraps the body in try/except — per the SDK custom-tools docs, uncaught
     exceptions stop the agent loop. Failures return is_error=true with a
     descriptive text content block so the model can correct course.
  3. Where appropriate, calls emit(...) to push events into the SSE queue.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic import ValidationError
from sqlmodel import Session, select

from agents.content.events import ContentEvent
from agents.content.schema import (
    ContentSession,
    PlanDraft,
    PostDraft,
    Slide,
)
from agents.content.templates import derive_image_prompts, render_slides_html
from config import get_configs
from db.session import get_engine
from models.content import (
    ContentAsset,
    ContentAvatar,
    ContentFormat,
    ContentPlan,
    ContentPost,
)
from models.project import Project

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Per-post write serialization. submit_post_draft / edit_slide / generate_image
# attach all read-modify-write content_posts.slides; without this, an agent
# generating images in parallel (or an attach racing an edit) can lose updates.
# Process-local asyncio locks keyed by post id — covers the agent's concurrent
# tool calls within one worker; a multi-worker deploy would also want a DB guard.
_POST_LOCKS: dict[str, asyncio.Lock] = {}


def _post_lock(key: str) -> asyncio.Lock:
    """Get-or-create the lock for a post key. Safe under single-threaded asyncio
    (no await between the get and the set)."""
    lock = _POST_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _POST_LOCKS[key] = lock
    return lock


def _ok(payload: dict | list | str) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {"content": [{"type": "text", "text": text}]}


def _err(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def _open_db() -> Session:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return Session(engine)


def _resolve_format_id(db: Session, project_id, format_slug: str):
    """Resolve a format slug (e.g. 'format-d') to the project's ContentFormat id.

    Returns None when the project has no format with that slug (link stays NULL).
    """
    slug = (format_slug or "").strip().lower()
    if not slug:
        return None
    row = db.exec(
        select(ContentFormat).where(
            ContentFormat.project_id == project_id,
            ContentFormat.slug == slug,
        )
    ).first()
    return row.id if row else None


def _merge_slide_images(incoming: list[Slide], existing_row: ContentPost | None) -> list[Slide]:
    """Carry already-generated images forward across copy/prompt edits.

    The orchestrator authors copy + image prompts; it does NOT re-send the
    generated `image_url` on every edit. So when a slide already has an image
    on the persisted row, we backfill image_url / image_asset_id /
    image_prompt_used onto the incoming slide (keyed by slide_id) UNLESS the
    incoming slide explicitly carries its own image_url.

    Staleness falls out naturally: a copy-only edit keeps the old
    image_prompt_used, so if the prompt changed the slide reads as stale
    (is_image_stale True) and the UI can offer a regenerate. A pure caption
    edit leaves prompt == prompt_used, so the image stays valid.
    """
    if existing_row is None or not getattr(existing_row, "slides", None):
        return incoming
    prev_by_id: dict[str, dict] = {}
    for s in existing_row.slides or []:
        if isinstance(s, dict) and s.get("slide_id"):
            prev_by_id[str(s["slide_id"])] = s
    merged: list[Slide] = []
    for slide in incoming:
        prev = prev_by_id.get(slide.slide_id)
        if not prev:
            merged.append(slide)
            continue
        update: dict = {}
        if not slide.image_url and prev.get("image_url"):
            update.update({
                "image_url":         prev.get("image_url", ""),
                "image_asset_id":    prev.get("image_asset_id"),
                "image_prompt_used": prev.get("image_prompt_used", ""),
            })
        # Carry generated cell images forward (collage / before-after), matched
        # by position within the slide.
        if slide.items:
            prev_items = prev.get("items") or []
            new_items = list(slide.items)
            touched = False
            for j, it in enumerate(slide.items):
                pit = prev_items[j] if j < len(prev_items) else None
                if pit and not it.image_url and pit.get("image_url"):
                    new_items[j] = it.model_copy(update={
                        "image_url":         pit.get("image_url", ""),
                        "image_asset_id":    pit.get("image_asset_id"),
                        "image_prompt_used": pit.get("image_prompt_used", ""),
                    })
                    touched = True
            if touched:
                update["items"] = new_items
        if update:
            slide = slide.model_copy(update=update)
        merged.append(slide)
    return merged


def _build_post_payload(row: ContentPost) -> dict:
    """The POST_DRAFT_UPDATED payload — shared by submit_post_draft and the
    per-slide image attach path so the frontend always gets the same shape."""
    return {
        "id":              str(row.id),
        "post_dir_slug":   row.post_dir_slug,
        "pillar":          row.pillar,
        "topic":           row.topic,
        "layout":          row.layout,
        "slide_count":     row.slide_count,
        "slides":          row.slides,
        "slides_html":     row.slides_html,
        "caption":         row.caption,
        "hashtags":        row.hashtags,
        "hook_type":       row.hook_type,
        "hook_text":       row.hook_text,
        "hook_emotion":    row.hook_emotion,
        "save_cta":        row.save_cta,
        "image_prompts":   row.image_prompts,
        "audio_note":      row.audio_note,
        "bridge_text":     row.bridge_text,
        "strategic_note":  row.strategic_note,
        "visual_brief":    row.visual_brief,
        "emotional_arc":   row.emotional_arc,
        "camera_ref_pool": row.camera_ref_pool,
        "platforms":       row.platforms,
        "status":          row.status,
    }


def _attach_image_to_slide(
    db: Session,
    row: ContentPost,
    slide_id: str,
    *,
    asset_id: str,
    url: str,
    item_index: int | None = None,
) -> bool:
    """Write a generated image onto one slide (or one cell of a multi-image
    slide) of a post + re-render the HTML.

    Sets image_url / image_asset_id and anchors image_prompt_used to the
    target's CURRENT image_prompt so later prompt edits read as stale. When
    item_index is given, the image lands on slide.items[item_index] (a collage
    cell / before-after side) instead of the slide itself. Returns True if the
    target was found + updated. The caller commits.
    """
    slides = list(row.slides or [])
    found = False
    for i, s in enumerate(slides):
        if not (isinstance(s, dict) and str(s.get("slide_id")) == str(slide_id)):
            continue
        s = dict(s)
        if item_index is not None:
            items = list(s.get("items") or [])
            if not (0 <= item_index < len(items)):
                return False
            cell = dict(items[item_index])
            cell["image_url"] = url
            cell["image_asset_id"] = asset_id
            cell["image_prompt_used"] = cell.get("image_prompt", "")
            items[item_index] = cell
            s["items"] = items
        else:
            s["image_url"] = url
            s["image_asset_id"] = asset_id
            s["image_prompt_used"] = s.get("image_prompt", "")
        slides[i] = s
        found = True
        break
    if not found:
        return False
    row.slides = slides
    parsed = [Slide.model_validate(s) for s in slides]
    row.slides_html = render_slides_html(row.layout, parsed)
    row.image_prompts = derive_image_prompts(parsed)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    return True


def _downscale_png_b64(png: bytes, max_w: int = 600) -> str:
    """Return a base64 PNG downscaled to max_w wide — the agent only needs enough
    detail to judge composition/legibility, and a full 1080×1920 PNG is a heavy
    vision input. Full-res is persisted separately for publishing. Falls back to
    the original bytes if Pillow can't process them."""
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(png))
        if img.width > max_w:
            img = img.resize((max_w, max(1, round(img.height * max_w / img.width))))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return base64.b64encode(png).decode("ascii")


def _persist_slide_render(project_id: UUID, post_id: UUID, slide_id: str, png: bytes) -> str:
    """Best-effort: write a rasterized slide PNG to the volume + a ContentAsset
    row (asset_type='slide_render'). These composed renders are what publish_post
    uploads to TikTok. Returns the public url, or '' if uploads are disabled."""
    cfg = get_configs()
    if not cfg.uploads_enabled:
        return ""
    base = Path(cfg.uploads_dir or "/app/uploads")
    proj_dir = base / "projects" / str(project_id) / "renders"
    proj_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{slide_id}-{uuid4().hex[:8]}.png"
    (proj_dir / fname).write_bytes(png)
    url = f"/uploads/projects/{project_id}/renders/{fname}"
    with _open_db() as db:
        db.add(ContentAsset(
            project_id=project_id,
            post_id=post_id,
            asset_type="slide_render",
            source="render",
            url=url,
            filename=fname,
            mime_type="image/png",
            params={"slide_id": slide_id, "width": 1080, "height": 1920},
        ))
        db.commit()
    return url


def _asset_disk_path(asset: ContentAsset) -> Path | None:
    """Resolve a ContentAsset.url to its on-disk path.

    Handles two URL families:
      - '/uploads/...'         → Railway Volume (per-project user uploads,
                                 agent-generated images). Resolved against
                                 `config.uploads_dir`.
      - '/static/references/…' → repo-bundled global reference library.
                                 Resolved against
                                 `service/content_references.global_references_dir()`.

    Returns None if the URL matches neither family — caller treats that
    as "asset bytes unavailable" and surfaces a friendly error.
    """
    if asset.url.startswith("/uploads/"):
        cfg = get_configs()
        base = Path(cfg.uploads_dir or "/app/uploads")
        return base / asset.url[len("/uploads/"):]
    # Global references shipped with the repo — no bucket round-trip.
    from service.content_references import disk_path_for_public_url
    resolved = disk_path_for_public_url(asset.url)
    if resolved is not None:
        return resolved
    return None




# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_content_mcp_server(
    project_id: UUID,
    emit: EmitFn,
    session: ContentSession,
) -> McpSdkServerConfig:
    """Build the in-process MCP server scoped to this content session.

    project_id is captured in closures so every tool call is implicitly
    scoped to the user's project — the model cannot leak across projects.
    emit pushes events to the SSE consumer; session lets writers stash IDs
    (e.g. session.plan_id after submit_plan).
    """

    # ----------------------- Writers -----------------------

    @tool(
        name="submit_plan",
        description=(
            "Persist a 30-day content plan. Validates the payload against the "
            "PlanDraft schema, upserts a content_plans row scoped to this "
            "project, and emits a PLAN_GENERATED event so the workspace "
            "renders the plan. Call this AFTER emitting <duct_report>{\"type\":\"plan\",...}</duct_report>."
        ),
        input_schema={
            "plan": Annotated[
                dict,
                "JSON object matching the PlanDraft schema (type='plan').",
            ],
        },
    )
    async def submit_plan(args: dict) -> dict:
        try:
            payload = args.get("plan") or args
            try:
                draft = PlanDraft.model_validate(payload)
            except ValidationError as exc:
                return _err(f"PlanDraft validation failed: {exc}")
            if draft.project_id != project_id:
                return _err(
                    f"project_id mismatch: payload has {draft.project_id}, "
                    f"session is scoped to {project_id}."
                )
            # Monthly model: anchor the plan to the first of the current month;
            # the calendar lays items on sequential dates from there.
            from datetime import date as _date
            today = _date.today()
            month_start = today.replace(day=1)
            month_label = today.strftime("%B %Y")
            with _open_db() as db:
                row = ContentPlan(
                    project_id=project_id,
                    name=draft.name or f"{month_label} plan",
                    start_date=month_start,
                    character=draft.character.model_dump(mode="json"),
                    days=[d.model_dump(mode="json") for d in draft.days],
                    status="draft",
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                session.plan_id = row.id
                logger.info("content: plan %s persisted (%d days)", row.id, len(draft.days))
                await emit({
                    "event": ContentEvent.PLAN_GENERATED,
                    "session_id": session.session_id,
                    "plan_id": str(row.id),
                    "payload": {
                        "id": str(row.id),
                        "name": row.name,
                        "start_date": row.start_date.isoformat() if row.start_date else None,
                        "days": row.days,
                        "character": row.character,
                    },
                })
                return _ok({"plan_id": str(row.id), "days": len(draft.days)})
        except Exception as exc:
            logger.exception("submit_plan failed")
            return _err(f"submit_plan failed: {exc}")

    @tool(
        name="submit_post_draft",
        description=(
            "Persist a single post draft. Validates against PostDraft schema, "
            "upserts a content_posts row keyed by (project_id, post_dir_slug), "
            "and emits POST_DRAFT_UPDATED. Call AFTER emitting "
            "<duct_report>{\"type\":\"post\",...}</duct_report>."
        ),
        input_schema={
            "post": Annotated[
                dict,
                "JSON object matching the PostDraft schema (type='post').",
            ],
        },
    )
    async def submit_post_draft(args: dict) -> dict:
        try:
            payload = args.get("post") or args
            try:
                draft = PostDraft.model_validate(payload)
            except ValidationError as exc:
                return _err(f"PostDraft validation failed: {exc}")
            if draft.project_id != project_id:
                return _err(
                    f"project_id mismatch: payload has {draft.project_id}, "
                    f"session is scoped to {project_id}."
                )
            # Serialize against concurrent image-attach / edit_slide on this post.
            lock_key = str(session.post_id) if session.post_id else f"slug:{project_id}:{draft.post_dir_slug}"
            async with _post_lock(lock_key):
              with _open_db() as db:
                existing = db.exec(
                    select(ContentPost).where(
                        ContentPost.project_id == project_id,
                        ContentPost.post_dir_slug == draft.post_dir_slug,
                    )
                ).first()

                # Structured slides are the source of truth: carry already-
                # generated images forward across copy edits, render the HTML
                # deterministically, and derive the flat image_prompts list.
                # Legacy callers that still pass slides_html (no slides) keep
                # working unchanged.
                if draft.slides:
                    merged = _merge_slide_images(draft.slides, existing)
                    slides_json = [s.model_dump(mode="json") for s in merged]
                    slides_html = render_slides_html(draft.layout, merged)
                    image_prompts = derive_image_prompts(merged)
                    slide_count = len(merged)
                else:
                    slides_json = existing.slides if existing is not None else []
                    slides_html = draft.slides_html
                    image_prompts = [p.model_dump(mode="json") for p in draft.image_prompts]
                    slide_count = draft.slide_count

                values = {
                    "project_id":      project_id,
                    "plan_id":         session.plan_id,
                    "post_dir_slug":   draft.post_dir_slug,
                    "pillar":          draft.pillar,
                    "topic":           draft.topic,
                    "post_type":       draft.post_type,
                    "format_id":       _resolve_format_id(db, project_id, draft.format_slug),
                    "avatar_id":       draft.avatar_id,
                    "layout":          draft.layout.value,
                    "slide_count":     slide_count,
                    "status":          "draft",
                    "slides":          slides_json,
                    "slides_html":     slides_html,
                    "caption":         draft.caption,
                    "hashtags":        draft.hashtags,
                    "tiktok_title":    draft.tiktok_title,
                    "hook_type":       draft.hook_type,
                    "hook_text":       draft.hook_text,
                    "hook_emotion":    draft.hook_emotion or "",
                    "save_cta":        draft.save_cta or "",
                    "image_prompts":   image_prompts,
                    "audio_note":      draft.audio_note or "",
                    "bridge_text":     draft.bridge_text or "",
                    "strategic_note":  draft.strategic_note or "",
                    "visual_brief":    draft.visual_brief or "",
                    "emotional_arc":   draft.emotional_arc or "",
                    "camera_ref_pool": draft.camera_ref_pool or "",
                    "platforms":       [p.value for p in draft.platforms],
                }
                if existing is not None:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    row = existing
                else:
                    row = ContentPost(**values)
                    db.add(row)
                db.commit()
                db.refresh(row)
                session.post_id = row.id
                logger.info(
                    "content: post %s upserted (slug=%s, layout=%s, slides=%d, images=%d)",
                    row.id, row.post_dir_slug, row.layout, row.slide_count,
                    sum(1 for s in (row.slides or []) if isinstance(s, dict) and s.get("image_url")),
                )
                await emit({
                    "event": ContentEvent.POST_DRAFT_UPDATED,
                    "session_id": session.session_id,
                    "post_id": str(row.id),
                    "payload": _build_post_payload(row),
                })
                return _ok({
                    "post_id": str(row.id),
                    "post_dir_slug": row.post_dir_slug,
                    "slide_count": row.slide_count,
                    "images_generated": sum(
                        1 for s in (row.slides or [])
                        if isinstance(s, dict) and s.get("image_url")
                    ),
                })
        except Exception as exc:
            logger.exception("submit_post_draft failed")
            return _err(f"submit_post_draft failed: {exc}")

    @tool(
        name="edit_slide",
        description=(
            "Surgically edit ONE slide of the current post WITHOUT re-sending the "
            "whole post. Pass slide_id + a `patch` of only the fields that change "
            "— e.g. {\"caption_style\":\"cap-raw\"}, {\"headline\":\"...\"}, "
            "{\"kind\":\"text\"}, {\"image_prompt\":\"...\"}, or {\"items\":[...]}. "
            "The slide is merged + revalidated, the HTML re-rendered, and "
            "POST_DRAFT_UPDATED emitted. Changing image_prompt marks that image "
            "stale (regenerate to match). Use submit_post_draft for whole-post or "
            "multi-slide changes, or to add / remove / reorder slides."
        ),
        input_schema={
            "slide_id": Annotated[str, "The slide to edit, e.g. 'slide-03'."],
            "patch":    Annotated[dict, "Partial Slide fields to merge (only what changes)."],
        },
    )
    async def edit_slide(args: dict) -> dict:
        try:
            slide_id = (args.get("slide_id") or "").strip()
            patch = args.get("patch") or {}
            if not slide_id:
                return _err("slide_id is required (e.g. 'slide-03').")
            if not isinstance(patch, dict) or not patch:
                return _err("patch must be a non-empty object of the fields to change.")
            if session.post_id is None:
                return _err("No current post in this session to edit.")
            async with _post_lock(str(session.post_id)):
              with _open_db() as db:
                row = db.get(ContentPost, session.post_id)
                if row is None or row.project_id != project_id:
                    return _err("Current post not found for this project.")
                slides = list(row.slides or [])
                idx = next(
                    (i for i, s in enumerate(slides)
                     if isinstance(s, dict) and s.get("slide_id") == slide_id),
                    None,
                )
                if idx is None:
                    avail = [s.get("slide_id") for s in slides if isinstance(s, dict)]
                    return _err(f"slide_id {slide_id!r} not found. Available: {avail}")
                merged = {**slides[idx], **patch, "slide_id": slide_id}
                try:
                    slide_obj = Slide.model_validate(merged)
                except ValidationError as exc:
                    return _err(f"patched slide is invalid — fix and call again:\n{exc}")
                slides[idx] = slide_obj.model_dump(mode="json")
                parsed = [Slide.model_validate(s) for s in slides]
                row.slides = slides
                row.slides_html = render_slides_html(row.layout, parsed)
                row.image_prompts = derive_image_prompts(parsed)
                row.slide_count = len(parsed)
                row.updated_at = datetime.now(timezone.utc)
                db.add(row)
                db.commit()
                db.refresh(row)
                await emit({
                    "event": ContentEvent.POST_DRAFT_UPDATED,
                    "session_id": session.session_id,
                    "post_id": str(row.id),
                    "payload": _build_post_payload(row),
                })
                return _ok({
                    "post_id":  str(row.id),
                    "slide_id": slide_id,
                    "updated":  list(patch.keys()),
                })
        except Exception as exc:
            logger.exception("edit_slide failed")
            return _err(f"edit_slide failed: {exc}")

    # ----------------------- Readers -----------------------

    @tool(
        name="fetch_brand_context",
        description=(
            "Return the current brand context for this project: identity "
            "(name/slug/tagline/url), audience, content_brand JSONB, pillars, "
            "and visual assets. No arguments. Call this FIRST in a new session."
        ),
        input_schema={},
    )
    async def fetch_brand_context(_args: dict) -> dict:
        try:
            with _open_db() as db:
                proj = db.get(Project, project_id)
                if proj is None:
                    return _err(f"Project {project_id} not found.")
                payload = {
                    "project_id":            str(proj.id),
                    "project_name":          proj.name,
                    "slug":                  proj.slug,
                    "tagline":               proj.tagline,
                    "description":           proj.description,
                    "url":                   proj.url,
                    "company_name":          proj.company_name,
                    "industry":              proj.industry,
                    "audience":              proj.audience,
                    "content_brand":         proj.content_brand,
                    "content_pillars":       proj.content_pillars,
                    "content_visual_assets": proj.content_visual_assets,
                }
                return _ok(payload)
        except Exception as exc:
            logger.exception("fetch_brand_context failed")
            return _err(f"fetch_brand_context failed: {exc}")

    @tool(
        name="fetch_topic_bank",
        description=(
            "Return per-pillar topic usage by scanning content_posts. "
            "Each entry: pillar -> { topics_used: [...], last_used_at: ISO|None }. "
            "Use this to decide whether to dispatch research_pillar sub-agents."
        ),
        input_schema={},
    )
    async def fetch_topic_bank(_args: dict) -> dict:
        try:
            with _open_db() as db:
                rows = db.exec(
                    select(ContentPost).where(ContentPost.project_id == project_id)
                ).all()
                bank: dict[str, dict] = {}
                for r in rows:
                    if not r.pillar:
                        continue
                    slot = bank.setdefault(r.pillar, {"topics_used": [], "last_used_at": None})
                    if r.topic and r.topic not in slot["topics_used"]:
                        slot["topics_used"].append(r.topic)
                    ts = r.posted_at or r.updated_at
                    if ts is not None and (
                        slot["last_used_at"] is None
                        or ts.isoformat() > slot["last_used_at"]
                    ):
                        slot["last_used_at"] = ts.isoformat()
                return _ok({"by_pillar": bank})
        except Exception as exc:
            logger.exception("fetch_topic_bank failed")
            return _err(f"fetch_topic_bank failed: {exc}")

    @tool(
        name="fetch_format_library",
        description=(
            "Return the per-project content formats (name, slug, full JSONB data) "
            "AND resolved_css — the shared base engine CSS plus the format's linked "
            "styles, ready to inline verbatim into the slides <style> block. Do not "
            "write caption/hook/layout CSS yourself; use resolved_css and its classes."
        ),
        input_schema={},
    )
    async def fetch_format_library(_args: dict) -> dict:
        try:
            from agents.content.styles import css_for
            with _open_db() as db:
                rows = db.exec(
                    select(ContentFormat).where(ContentFormat.project_id == project_id)
                ).all()
                out = []
                for r in rows:
                    data = r.data or {}
                    linked = data.get("linked_styles") or data.get("caption_classes") or []
                    out.append({
                        "id":   str(r.id),
                        "slug": r.slug,
                        "name": r.name,
                        "data": data,
                        "resolved_css": css_for(linked),
                    })
                return _ok({"formats": out})
        except Exception as exc:
            logger.exception("fetch_format_library failed")
            return _err(f"fetch_format_library failed: {exc}")

    @tool(
        name="fetch_avatar_library",
        description="Return the list of per-project avatars (name + full JSONB data including ref images).",
        input_schema={},
    )
    async def fetch_avatar_library(_args: dict) -> dict:
        try:
            with _open_db() as db:
                rows = db.exec(
                    select(ContentAvatar).where(ContentAvatar.project_id == project_id)
                ).all()
                return _ok({
                    "avatars": [
                        {
                            "id":   str(r.id),
                            "name": r.name,
                            "data": r.data,
                        }
                        for r in rows
                    ]
                })
        except Exception as exc:
            logger.exception("fetch_avatar_library failed")
            return _err(f"fetch_avatar_library failed: {exc}")

    @tool(
        name="fetch_content_history",
        description=(
            "Return recent posts (default last 30) for de-duplication and "
            "to inform hook variation. Fields: post_dir_slug, pillar, topic, "
            "hook_type, status, posted_at, perf."
        ),
        input_schema={
            "limit": Annotated[int, "Max rows to return. Default 30, max 100."],
        },
    )
    async def fetch_content_history(args: dict) -> dict:
        try:
            limit = min(int(args.get("limit") or 30), 100)
            with _open_db() as db:
                rows = db.exec(
                    select(ContentPost)
                    .where(ContentPost.project_id == project_id)
                    .order_by(ContentPost.updated_at.desc())  # type: ignore[union-attr]
                    .limit(limit)
                ).all()
                return _ok({
                    "history": [
                        {
                            "id":            str(r.id),
                            "post_dir_slug": r.post_dir_slug,
                            "pillar":        r.pillar,
                            "topic":         r.topic,
                            "hook_type":     r.hook_type,
                            "status":        r.status,
                            "posted_at":     r.posted_at.isoformat() if r.posted_at else None,
                            "perf":          r.perf,
                        }
                        for r in rows
                    ]
                })
        except Exception as exc:
            logger.exception("fetch_content_history failed")
            return _err(f"fetch_content_history failed: {exc}")

    @tool(
        name="fetch_discovered_references",
        description=(
            "Return TikTok posts the user (or a previous discovery run) saved as "
            "high-performing references. Use this to ground topic / hook / format "
            "decisions in real-world signal — what's actually working in the "
            "target audience's niche right now. Each row carries the post's "
            "engagement counts (play, digg, share, comment, collect), hashtags, "
            "music, author, and the TikTok URL. Filter by min_play_count to "
            "skip the long tail (default 10000)."
        ),
        input_schema={
            "min_play_count": Annotated[
                int,
                "Skip posts with fewer plays. Default 10000 (filters out outliers).",
            ],
            "limit": Annotated[int, "Max rows to return. Default 30, max 100."],
        },
    )
    async def fetch_discovered_references(args: dict) -> dict:
        try:
            min_plays = int(args.get("min_play_count") or 10000)
            limit     = min(int(args.get("limit") or 30), 100)
            with _open_db() as db:
                rows = db.exec(
                    select(ContentAsset)
                    .where(
                        ContentAsset.project_id == project_id,
                        ContentAsset.asset_type == "discovered_reference",
                    )
                    .order_by(ContentAsset.created_at.desc())  # type: ignore[union-attr]
                    .limit(200)  # over-fetch; we filter in Python by min_plays
                ).all()
                items: list[dict] = []
                for r in rows:
                    p = (r.params or {}).get("post") or {}
                    if (p.get("play_count") or 0) < min_plays:
                        continue
                    items.append({
                        "asset_id":      str(r.id),
                        "tiktok_url":    r.url,
                        "play_count":    p.get("play_count"),
                        "digg_count":    p.get("digg_count"),
                        "comment_count": p.get("comment_count"),
                        "share_count":   p.get("share_count"),
                        "collect_count": p.get("collect_count"),
                        "hashtags":      p.get("hashtags") or [],
                        "music":         (p.get("music_meta") or {}).get("music_name"),
                        "author":        (p.get("author_meta") or {}).get("name"),
                        "is_slideshow":  p.get("is_slideshow"),
                        "text":          (p.get("text") or "")[:280],
                        "created_at":    p.get("create_time_iso"),
                    })
                    if len(items) >= limit:
                        break
                return _ok({"references": items, "count": len(items)})
        except Exception as exc:
            logger.exception("fetch_discovered_references failed")
            return _err(f"fetch_discovered_references failed: {exc}")

    @tool(
        name="fetch_content_assets",
        description=(
            "Return content assets (generated images, uploads, references) "
            "for this project. Filter by asset_type if provided "
            "(e.g. 'generated', 'logo', 'background', 'reference', 'upload')."
        ),
        input_schema={
            "asset_type": Annotated[
                str,
                "Optional asset_type filter. Empty string = all types.",
            ],
        },
    )
    async def fetch_content_assets(args: dict) -> dict:
        try:
            asset_type = (args.get("asset_type") or "").strip()
            with _open_db() as db:
                stmt = select(ContentAsset).where(ContentAsset.project_id == project_id)
                if asset_type:
                    stmt = stmt.where(ContentAsset.asset_type == asset_type)
                rows = db.exec(stmt).all()
                return _ok({
                    "assets": [
                        {
                            "id":         str(r.id),
                            "asset_type": r.asset_type,
                            "source":     r.source,
                            "url":        r.url,
                            "mime_type":  r.mime_type,
                            "prompt":     r.prompt,
                            "model":      r.model,
                            "params":     r.params,
                            "created_at": r.created_at.isoformat(),
                        }
                        for r in rows
                    ]
                })
        except Exception as exc:
            logger.exception("fetch_content_assets failed")
            return _err(f"fetch_content_assets failed: {exc}")

    # ----------------------- Image generation (Phase 4b) -----------------------

    @tool(
        name="generate_image",
        description=(
            "Generate one or more images from a text prompt via Gemini/Imagen. "
            "Returns inline image data (so you can see the result) PLUS a stable "
            "asset_url you must reference in slides_html. Defaults: 9:16 portrait, "
            "1 image, model=gemini-3.1-flash-image-preview. Outputs are saved to "
            "/uploads/projects/<project_id>/generated/ on the Railway Volume."
        ),
        input_schema={
            "prompt": Annotated[str, "Image prompt — the scene description for this slide."],
            "slide_id": Annotated[
                str,
                "The slide this image is for (e.g. 'slide-01'). When set, the "
                "result is attached to that slide of the current post: its "
                "image_url is filled, the preview re-renders, and a "
                "POST_DRAFT_UPDATED event fires — no separate submit_post_draft "
                "needed for the image. Always pass this during the image phase.",
            ],
            "item_index": Annotated[
                int,
                "For multi-image slides (collage / before-after), the 0-based "
                "cell to attach this image to (collage cell or before/after "
                "side). Omit for single-image slides. Generate one cell per call.",
            ],
            "model":  Annotated[str, "Optional image model id; defaults to gemini-3.1-flash-image-preview."],
            "aspect_ratio": Annotated[str, "Optional aspect ratio (e.g. '9:16'). Defaults to portrait."],
            "number_of_images": Annotated[int, "How many images to generate. Default 1, max 4."],
            "negative_prompt":  Annotated[str, "Optional negative prompt (Imagen models only)."],
            "input_asset_id":   Annotated[str, "Single reference asset UUID (legacy; prefer input_asset_ids). Gemini-class models only."],
            "input_asset_ids":  Annotated[
                list[str],
                "Multiple reference assets (Gemini-class only). Pass up to 3 UUIDs in role-order: "
                "[character_ref, camera_or_style_ref, optional_third]. For slides 2-5 the common "
                "pattern is [slide-01 character image, cameraRef from the reference library] — "
                "first image locks face/skin/hair, second imitates TikTok framing. A role-explanation "
                "prefix is auto-prepended to your prompt when 2+ ids are passed.",
            ],
        },
    )
    async def generate_image(args: dict) -> dict:
        try:
            from service.gemini import (
                GeminiAPIError,
                GeminiImageClient,
                GenerateImageRequest,
                persist_generated_image,
            )
            from service.gemini.client import build_multi_reference_prefix

            cfg = get_configs()
            if not cfg.gemini_api_key:
                return _err("GEMINI_API_KEY is not configured; image generation unavailable.")
            if not cfg.uploads_enabled:
                return _err("uploads_enabled is false; cannot persist generated images.")

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            # slide_id / item_index steer where the result is attached; they're
            # not Gemini params, so pull them out before building the request.
            target_slide_id = str(payload.pop("slide_id", "") or "").strip()
            _ti = payload.pop("item_index", None)
            target_item_index = int(_ti) if _ti not in (None, "") else None

            # Normalise single-ref legacy → list. The model may pass
            # input_asset_id, input_asset_ids, or both; merge in order.
            ref_ids_raw: list = []
            if payload.get("input_asset_id"):
                ref_ids_raw.append(payload["input_asset_id"])
            for extra in (payload.get("input_asset_ids") or []):
                if extra and extra not in ref_ids_raw:
                    ref_ids_raw.append(extra)
            if len(ref_ids_raw) > 3:
                return _err(
                    "Too many reference images — max 3 (character + style + one supplementary). "
                    "Drop the least useful and call again."
                )
            try:
                ref_uuids = [UUID(str(x)) for x in ref_ids_raw]
            except ValueError as exc:
                return _err(f"invalid reference asset id: {exc}")

            # Hand the validator a list-shaped payload regardless of which
            # legacy key the model used.
            payload["input_asset_ids"] = [str(u) for u in ref_uuids]
            payload.pop("input_asset_id", None)
            try:
                request = GenerateImageRequest.model_validate(payload)
            except ValidationError as exc:
                return _err(f"generate_image input invalid: {exc}")

            input_bytes_list: list[bytes] = []
            with _open_db() as db:
                for ref_uuid in ref_uuids:
                    asset = db.get(ContentAsset, ref_uuid)
                    if asset is None or asset.project_id != project_id:
                        return _err(f"reference asset {ref_uuid} not found for this project.")
                    p = _asset_disk_path(asset)
                    if p is None or not p.exists():
                        return _err(f"reference asset bytes missing on disk: {asset.url}")
                    input_bytes_list.append(p.read_bytes())

                # Auto-prepend the role-explanation prefix when 2+ refs.
                if len(input_bytes_list) >= 2:
                    prefix = build_multi_reference_prefix(len(input_bytes_list))
                    if prefix and not request.prompt.startswith(prefix[:60]):
                        request = request.model_copy(
                            update={"prompt": f"{prefix}\n\n{request.prompt}"}
                        )

                client = GeminiImageClient(cfg.gemini_api_key)
                try:
                    images = await client.generate_image(
                        request,
                        input_bytes_list=input_bytes_list or None,
                    )
                except GeminiAPIError as exc:
                    return _err(f"Gemini generate failed: {exc}")

                assets = []
                for img in images:
                    asset = persist_generated_image(
                        project_id, img,
                        db=db,
                        prompt=request.prompt,
                        model=request.model.value,
                        params={
                            "aspect_ratio":    request.aspect_ratio.value,
                            "image_size":      request.image_size.value,
                            "seed":            request.seed,
                            "negative_prompt": request.negative_prompt,
                            "input_asset_ids": [str(u) for u in ref_uuids],
                        },
                        post_id=session.post_id,
                        source="imagen" if request.model.value.startswith("imagen-") else "gemini",
                    )
                    assets.append(asset)

            # Attach the first image to the target slide so the preview updates
            # live (one slide at a time) without a separate submit_post_draft.
            attached = False
            if target_slide_id and assets and session.post_id is not None:
                try:
                    async with _post_lock(str(session.post_id)):
                      with _open_db() as db2:
                        row = db2.get(ContentPost, session.post_id)
                        if row is not None and row.project_id == project_id:
                            attached = _attach_image_to_slide(
                                db2, row, target_slide_id,
                                asset_id=str(assets[0].asset_id),
                                url=assets[0].url,
                                item_index=target_item_index,
                            )
                            if attached:
                                db2.commit()
                                db2.refresh(row)
                                logger.info(
                                    "content: image attached to %s%s on post %s",
                                    target_slide_id,
                                    f"#{target_item_index}" if target_item_index is not None else "",
                                    row.id,
                                )
                                await emit({
                                    "event": ContentEvent.POST_DRAFT_UPDATED,
                                    "session_id": session.session_id,
                                    "post_id": str(row.id),
                                    "payload": _build_post_payload(row),
                                })
                except Exception:
                    logger.exception("content: failed to attach image to slide %s", target_slide_id)

            content: list[dict] = []
            for img, asset in zip(images, assets, strict=False):
                content.append({
                    "type":     "image",
                    "data":     base64.b64encode(img.data).decode("ascii"),
                    "mimeType": img.mime_type,
                })
            content.append({
                "type": "text",
                "text": json.dumps({
                    "asset_ids":   [str(a.asset_id) for a in assets],
                    "asset_urls":  [a.url           for a in assets],
                    "model":       request.model.value,
                    "attached_to": target_slide_id if attached else None,
                }),
            })
            return {"content": content}
        except Exception as exc:
            logger.exception("generate_image failed")
            return _err(f"generate_image failed: {exc}")

    @tool(
        name="edit_image",
        description=(
            "Edit an existing content asset (inpaint, outpaint, bgswap, style transfer, "
            "or free-form Gemini edit). Returns the edited image inline + a stable "
            "asset_url. The original asset is preserved — every edit creates a new "
            "content_assets row."
        ),
        input_schema={
            "prompt":          Annotated[str, "Edit instruction."],
            "input_asset_id":  Annotated[str, "UUID of the source asset (required)."],
            "model":           Annotated[str, "Optional image model id."],
            "edit_mode":       Annotated[str, "Optional edit mode (Imagen only)."],
            "mask_asset_id":   Annotated[str, "Optional mask asset UUID."],
            "mask_mode":       Annotated[str, "Optional mask mode."],
            "style_asset_id":  Annotated[str, "Optional style reference asset UUID."],
            "subject_asset_id": Annotated[str, "Optional subject reference asset UUID."],
            "subject_type":    Annotated[str, "Optional subject type."],
            "aspect_ratio":    Annotated[str, "Optional aspect ratio override."],
            "number_of_images": Annotated[int, "How many images to generate (1-4)."],
            "negative_prompt": Annotated[str, "Optional negative prompt (Imagen only)."],
        },
    )
    async def edit_image(args: dict) -> dict:
        try:
            from service.gemini import (
                EditImageRequest,
                GeminiAPIError,
                GeminiImageClient,
                persist_generated_image,
            )

            cfg = get_configs()
            if not cfg.gemini_api_key:
                return _err("GEMINI_API_KEY is not configured; image editing unavailable.")
            if not cfg.uploads_enabled:
                return _err("uploads_enabled is false; cannot persist edited images.")

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            try:
                request = EditImageRequest.model_validate(payload)
            except ValidationError as exc:
                return _err(f"edit_image input invalid: {exc}")

            with _open_db() as db:
                base_asset = db.get(ContentAsset, request.input_asset_id)
                if base_asset is None or base_asset.project_id != project_id:
                    return _err(f"input_asset_id {request.input_asset_id} not found for this project.")
                base_path = _asset_disk_path(base_asset)
                if base_path is None or not base_path.exists():
                    return _err(f"input asset bytes missing on disk: {base_asset.url}")
                base_bytes = base_path.read_bytes()

                def _load(ref_id: UUID | None) -> bytes | None:
                    if ref_id is None:
                        return None
                    a = db.get(ContentAsset, ref_id)
                    if a is None or a.project_id != project_id:
                        return None
                    p = _asset_disk_path(a)
                    return p.read_bytes() if p and p.exists() else None

                mask_bytes    = _load(request.mask_asset_id)
                style_bytes   = _load(request.style_asset_id)
                subject_bytes = _load(request.subject_asset_id)

                client = GeminiImageClient(cfg.gemini_api_key)
                try:
                    images = await client.edit_image(
                        request,
                        base_bytes=base_bytes,
                        mask_bytes=mask_bytes,
                        style_bytes=style_bytes,
                        subject_bytes=subject_bytes,
                    )
                except GeminiAPIError as exc:
                    return _err(f"Gemini edit failed: {exc}")

                assets = []
                for img in images:
                    asset = persist_generated_image(
                        project_id, img,
                        db=db,
                        prompt=request.prompt,
                        model=request.model.value,
                        params={
                            "edit_mode":         request.edit_mode.value if request.edit_mode else None,
                            "input_asset_id":    str(request.input_asset_id),
                            "mask_asset_id":     str(request.mask_asset_id)    if request.mask_asset_id    else None,
                            "style_asset_id":    str(request.style_asset_id)   if request.style_asset_id   else None,
                            "subject_asset_id":  str(request.subject_asset_id) if request.subject_asset_id else None,
                            "seed":              request.seed,
                            "negative_prompt":   request.negative_prompt,
                        },
                        post_id=session.post_id,
                        source="imagen" if request.model.value.startswith("imagen-") else "gemini",
                    )
                    assets.append(asset)

            content: list[dict] = []
            for img, asset in zip(images, assets, strict=False):
                content.append({
                    "type":     "image",
                    "data":     base64.b64encode(img.data).decode("ascii"),
                    "mimeType": img.mime_type,
                })
            content.append({
                "type": "text",
                "text": json.dumps({
                    "asset_ids":  [str(a.asset_id) for a in assets],
                    "asset_urls": [a.url           for a in assets],
                    "model":      request.model.value,
                }),
            })
            return {"content": content}
        except Exception as exc:
            logger.exception("edit_image failed")
            return _err(f"edit_image failed: {exc}")

    # ----------------------- PostBridge (Phase 4) -----------------------

    @tool(
        name="publish_post",
        description=(
            "Publish a saved post via PostBridge. Uploads each slide's COMPOSED "
            "render (caption baked in — call render_slide first) to PostBridge, "
            "creates the post bound to one or more social_account_ids (numeric, "
            "from list_social_accounts), and stores the resulting PostBridge post "
            "id on the content_posts row. By default it refuses slides that have "
            "no render (their captions wouldn't appear)."
        ),
        input_schema={
            "post_id":            Annotated[str,       "UUID of the content_posts row to publish."],
            "social_account_ids": Annotated[list[int], "Numeric PostBridge social account IDs."],
            "scheduled_at":       Annotated[str,       "Optional ISO 8601 timestamp; omit to post now."],
            "tiktok_draft":       Annotated[bool,      "If true, post lands as a TikTok draft instead of scheduling."],
            "allow_uncomposed":   Annotated[bool,      "Escape hatch: publish single-image slides as their RAW photo when no composed render exists (captions won't appear). Multi-image slides still require a render. Default false."],
        },
    )
    async def publish_post(args: dict) -> dict:
        try:
            from service.post_bridge import (
                PostBridgeAPIError,
                PostBridgeCreatePostRequest,
                client_for_user,
            )

            post_id_raw = args.get("post_id")
            raw_ids     = args.get("social_account_ids") or []
            scheduled_raw  = args.get("scheduled_at")
            tiktok_draft = bool(args.get("tiktok_draft"))
            allow_uncomposed = bool(args.get("allow_uncomposed"))
            if not post_id_raw:
                return _err("post_id is required.")
            try:
                social_account_ids = [int(x) for x in raw_ids]
            except (TypeError, ValueError):
                return _err("social_account_ids must be a list of numbers.")
            if not social_account_ids:
                return _err("social_account_ids is required (at least one).")

            post_id = UUID(str(post_id_raw))
            scheduled_at = None
            if scheduled_raw:
                try:
                    scheduled_at = datetime.fromisoformat(str(scheduled_raw))
                except ValueError as exc:
                    return _err(f"scheduled_at invalid: {exc}")

            with _open_db() as db:
                post = db.get(ContentPost, post_id)
                if post is None or post.project_id != project_id:
                    return _err(f"Post {post_id} not found for this project.")
                proj = db.get(Project, project_id)
                if proj is None:
                    return _err("Project missing.")

                # Gather what to upload, in slide order. PREFER the composed
                # slide renders (caption + layout baked in) — those are what
                # should appear on TikTok. Fall back to a single-image slide's
                # raw photo only when it has no render yet.
                all_assets = db.execute(
                    select(ContentAsset)
                    .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
                    .order_by(ContentAsset.created_at)
                ).scalars().all()
                renders_by_slide: dict[str, ContentAsset] = {}
                by_url: dict[str, ContentAsset] = {}
                for a in all_assets:
                    if a.asset_type == "slide_render":
                        sid = (a.params or {}).get("slide_id")
                        if sid:
                            renders_by_slide[str(sid)] = a   # asc order → latest wins
                    if a.url:
                        by_url.setdefault(a.url, a)

                slides_meta = [s for s in (post.slides or []) if isinstance(s, dict)]
                asset_rows: list[ContentAsset] = []
                missing: list[str] = []
                uncomposed: list[str] = []
                if slides_meta:
                    for s in slides_meta:
                        sid = str(s.get("slide_id") or "")
                        ren = renders_by_slide.get(sid)
                        if ren is not None:
                            asset_rows.append(ren)
                            continue
                        # No composed render. Only a single-image slide can fall
                        # back to its raw photo, and only when explicitly allowed
                        # (collage / before-after MUST be rendered to compose).
                        url = s.get("image_url")
                        fallback = by_url.get(url) if url else None
                        if allow_uncomposed and fallback is not None and not s.get("items"):
                            asset_rows.append(fallback)
                            uncomposed.append(sid or "(unnamed)")
                        else:
                            missing.append(sid or "(unnamed)")
                else:
                    # Legacy posts with no structured slides — upload whatever's linked.
                    asset_rows = list(all_assets)

                if missing:
                    return _err(
                        "These slides have no composed render, so their captions "
                        f"wouldn't publish: {missing}. Call render_slide on each, then "
                        "publish again — or pass allow_uncomposed=true to publish "
                        "single-image slides as raw photos (captions won't appear; "
                        "collage / before-after still require a render)."
                    )
                if not asset_rows:
                    return _err("No slide images to publish — render or generate images first.")

                try:
                    client = client_for_user(proj.user_id, db)
                except ValueError as exc:
                    return _err(str(exc))

                # Upload each asset → media_id list.
                media_ids: list[str] = []
                try:
                    async with client as pb:
                        for asset in asset_rows:
                            disk = _asset_disk_path(asset)
                            if disk is None or not disk.exists():
                                return _err(f"Asset bytes missing on disk for {asset.url}.")
                            data = disk.read_bytes()
                            upload = await pb.create_upload_url(
                                name=asset.filename or f"slide-{len(media_ids)+1}.png",
                                mime_type=asset.mime_type or "image/png",
                                size_bytes=len(data),
                            )
                            await pb.upload_media(data, upload.upload_url, asset.mime_type or "image/png")
                            media_ids.append(upload.media_id)

                        platform_configs: dict = {}
                        if tiktok_draft:
                            platform_configs["tiktok"] = {"draft": True}

                        request = PostBridgeCreatePostRequest(
                            caption=post.caption or "",
                            social_accounts=social_account_ids,
                            media=media_ids,
                            scheduled_at=scheduled_at,
                            platform_configurations=platform_configs or None,
                        )
                        resp = await pb.create_post(request)
                except PostBridgeAPIError as exc:
                    return _err(f"Couldn't publish — PostBridge said: {exc.error.message or exc.status_code}")

                post.post_bridge_post_id = resp.id
                if resp.status.value == "posted":
                    post.status    = "posted"
                    post.posted_at = datetime.now(timezone.utc)
                elif resp.status.value == "scheduled":
                    post.status = "scheduled"
                else:
                    post.status = resp.status.value
                db.add(post)
                db.commit()
                db.refresh(post)
                logger.info(
                    "content: published post %s via PostBridge → id=%s status=%s",
                    post.id, resp.id, resp.status,
                )
                return _ok({
                    "post_id":               str(post.id),
                    "post_bridge_post_id":   resp.id,
                    "status":                post.status,
                    "scheduled_at":          resp.scheduled_at.isoformat() if resp.scheduled_at else None,
                    "media_count":           len(media_ids),
                    "uncomposed_slides":     uncomposed,   # published as raw photos (no caption)
                })
        except Exception as exc:
            logger.exception("publish_post failed")
            return _err(f"publish_post failed: {exc}")

    @tool(
        name="mark_posted",
        description=(
            "Mark a post as posted (manual flag — use when the user posted "
            "outside of PostBridge). Sets status='posted' and posted_at=now."
        ),
        input_schema={
            "post_id":    Annotated[str, "UUID of the content_posts row."],
            "tiktok_url": Annotated[str, "Optional external URL of the live post."],
        },
    )
    async def mark_posted(args: dict) -> dict:
        try:
            post_id_raw = args.get("post_id")
            if not post_id_raw:
                return _err("post_id is required.")
            post_id = UUID(str(post_id_raw))
            with _open_db() as db:
                post = db.get(ContentPost, post_id)
                if post is None or post.project_id != project_id:
                    return _err(f"Post {post_id} not found for this project.")
                post.status    = "posted"
                post.posted_at = datetime.now(timezone.utc)
                if args.get("tiktok_url"):
                    post.tiktok_url = str(args["tiktok_url"])
                db.add(post)
                db.commit()
                db.refresh(post)
                return _ok({"post_id": str(post.id), "status": post.status})
        except Exception as exc:
            logger.exception("mark_posted failed")
            return _err(f"mark_posted failed: {exc}")

    @tool(
        name="log_metrics",
        description=(
            "Refresh performance metrics for a post from PostBridge. Looks up "
            "the post_result for this post, fetches lifetime + daily analytics, "
            "and merges them into post.perf / post.daily_perf. Requires "
            "post_bridge_post_id set on the row (i.e. publish_post ran first)."
        ),
        input_schema={
            "post_id": Annotated[str, "UUID of the content_posts row."],
        },
    )
    async def log_metrics(args: dict) -> dict:
        try:
            from service.post_bridge import PostBridgeAPIError, client_for_user

            post_id_raw = args.get("post_id")
            if not post_id_raw:
                return _err("post_id is required.")
            post_id = UUID(str(post_id_raw))

            with _open_db() as db:
                post = db.get(ContentPost, post_id)
                if post is None or post.project_id != project_id:
                    return _err(f"Post {post_id} not found for this project.")
                if not post.post_bridge_post_id:
                    return _err("Post hasn't been published yet — run publish_post first.")
                proj = db.get(Project, project_id)
                if proj is None:
                    return _err("Project missing.")

                try:
                    client = client_for_user(proj.user_id, db)
                except ValueError as exc:
                    return _err(str(exc))

                try:
                    async with client as pb:
                        # Trigger a sync (best-effort) then chase the chain
                        # post → post_result → analytics → daily.
                        await pb.sync_analytics(platform="tiktok")
                        results = await pb.list_post_results(post_id=post.post_bridge_post_id, limit=10)
                        if not results:
                            return _err("PostBridge hasn't recorded a post_result yet — try again in a few minutes.")
                        # Pick the first successful result; fall back to the latest.
                        chosen = next((r for r in results if r.success), results[0])
                        analytics_list = await pb.list_analytics(post_result_id=[chosen.id], limit=1)
                        if not analytics_list:
                            return _err("PostBridge hasn't synced analytics for this post yet.")
                        analytics = analytics_list[0]
                        daily = await pb.get_analytics_daily(analytics.id)
                except PostBridgeAPIError as exc:
                    return _err(f"Couldn't pull metrics — PostBridge said: {exc.error.message or exc.status_code}")

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
                post.daily_perf = [s.model_dump(mode="json") for s in daily.snapshots]
                db.add(post)
                db.commit()
                db.refresh(post)

                return _ok({
                    "post_id":    str(post.id),
                    "view_count": analytics.view_count,
                    "like_count": analytics.like_count,
                    "snapshots":  len(daily.snapshots),
                })
        except Exception as exc:
            logger.exception("log_metrics failed")
            return _err(f"log_metrics failed: {exc}")

    @tool(
        name="render_slide",
        description=(
            "Rasterize ONE slide to a 1080×1920 (9:16) PNG and SEE it — the "
            "COMPOSED slide as it will actually look (caption overlay, gradient, "
            "layout, safe zones), not just the raw photo. Returns the image inline "
            "so you can critique composition, caption legibility, text/face "
            "overlap, and safe-zone fit, then fix the structured slide. These "
            "composed renders are also what publish_post uploads. Needs a "
            "connected session UI; if none responds it times out — then proceed "
            "on the raw photo + structured data."
        ),
        input_schema={
            "slide_id": Annotated[str, "The slide to render, e.g. 'slide-01'."],
        },
    )
    async def render_slide(args: dict) -> dict:
        try:
            slide_id = (args.get("slide_id") or "").strip()
            if not slide_id:
                return _err("slide_id is required (e.g. 'slide-01').")
            if session.post_id is None:
                return _err("No current post in this session to render.")
            with _open_db() as db:
                row = db.get(ContentPost, session.post_id)
                if row is None or row.project_id != project_id:
                    return _err("Current post not found for this project.")
                slide_ids = [s.get("slide_id") for s in (row.slides or []) if isinstance(s, dict)]
                if slide_id not in slide_ids:
                    return _err(f"slide_id {slide_id!r} not on this post. Available: {slide_ids}")
                post_id = row.id

            render_id = str(uuid4())
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            session.render_futures[render_id] = fut
            await emit({
                "event":      ContentEvent.SLIDE_RENDER_REQUESTED,
                "session_id": session.session_id,
                "post_id":    str(post_id),
                "slide_id":   slide_id,
                "render_id":  render_id,
            })
            try:
                png_b64 = await asyncio.wait_for(asyncio.shield(fut), timeout=25.0)
            except asyncio.TimeoutError:
                return _err(
                    "No browser rendered the slide in time (no connected session UI). "
                    "Proceed using the raw photo + the structured slide data."
                )
            finally:
                session.render_futures.pop(render_id, None)

            if not png_b64 or not str(png_b64).strip():
                return _err(
                    "the browser couldn't rasterize the slide. Proceed on the raw "
                    "photo + the structured slide data."
                )
            try:
                png = base64.b64decode(png_b64)
            except Exception:
                return _err("the render returned invalid image data.")

            asset_url = ""
            try:
                asset_url = _persist_slide_render(project_id, post_id, slide_id, png)
            except Exception:
                logger.exception("render_slide: persist failed (returning image anyway)")

            # Persist full-res (for publishing); show the agent a lighter copy.
            return {"content": [
                {"type": "image", "data": _downscale_png_b64(png), "mimeType": "image/png"},
                {"type": "text", "text": json.dumps({
                    "slide_id": slide_id, "asset_url": asset_url, "width": 1080, "height": 1920,
                    "note": "preview downscaled; the full-res render is saved for publishing",
                })},
            ]}
        except Exception as exc:
            logger.exception("render_slide failed")
            return _err(f"render_slide failed: {exc}")

    @tool(
        name="fetch_post",
        description=(
            "Return the current persisted state of ONE post — structured slides "
            "(copy + image prompts + any generated image_url), layout, and "
            "metadata. Use this to ground an edit on the live post before "
            "changing a caption/prompt or generating images, especially when "
            "resuming an earlier draft. Pass post_dir_slug or post_id; with "
            "neither, returns this session's current post. Each slide includes "
            "`image_stale` (true = the prompt changed after the image was made, "
            "so the image should be regenerated)."
        ),
        input_schema={
            "post_dir_slug": Annotated[str, "Post slug, e.g. '2026-06-08-001'. Optional."],
            "post_id":       Annotated[str, "Post UUID. Optional."],
        },
    )
    async def fetch_post(args: dict) -> dict:
        try:
            slug = (args.get("post_dir_slug") or "").strip()
            pid = (args.get("post_id") or "").strip()
            with _open_db() as db:
                row = None
                if pid:
                    try:
                        row = db.get(ContentPost, UUID(pid))
                    except ValueError:
                        return _err(f"invalid post_id: {pid}")
                elif slug:
                    row = db.exec(
                        select(ContentPost).where(
                            ContentPost.project_id == project_id,
                            ContentPost.post_dir_slug == slug,
                        )
                    ).first()
                elif session.post_id is not None:
                    row = db.get(ContentPost, session.post_id)
                if row is None or row.project_id != project_id:
                    return _err("post not found for this project (pass a valid post_dir_slug or post_id).")

                slides_out = []
                for s in row.slides or []:
                    if not isinstance(s, dict):
                        continue
                    used = (s.get("image_prompt_used") or "").strip()
                    cur = (s.get("image_prompt") or "").strip()
                    slides_out.append({
                        **s,
                        "image_stale": bool(s.get("image_url")) and (cur != used),
                    })
                return _ok({
                    "post_id":       str(row.id),
                    "post_dir_slug": row.post_dir_slug,
                    "pillar":        row.pillar,
                    "topic":         row.topic,
                    "layout":        row.layout,
                    "status":        row.status,
                    "slide_count":   row.slide_count,
                    "hook_emotion":  row.hook_emotion,
                    "emotional_arc": row.emotional_arc,
                    "visual_brief":  row.visual_brief,
                    "strategic_note": row.strategic_note,
                    "caption":       row.caption,
                    "hashtags":      row.hashtags,
                    "slides":        slides_out,
                    # The literal rendered markup, so you can see exactly how your
                    # structured choices (classes/layout) compose. Author edits as
                    # structured slides — the renderer rebuilds this on save.
                    "slides_html":   row.slides_html,
                })
        except Exception as exc:
            logger.exception("fetch_post failed")
            return _err(f"fetch_post failed: {exc}")

    return create_sdk_mcp_server(
        "duct_content",
        tools=[
            submit_plan,
            submit_post_draft,
            edit_slide,
            fetch_brand_context,
            fetch_topic_bank,
            fetch_format_library,
            fetch_avatar_library,
            fetch_content_history,
            fetch_content_assets,
            fetch_discovered_references,
            fetch_post,
            render_slide,
            generate_image,
            edit_image,
            publish_post,
            mark_posted,
            log_metrics,
        ],
    )
