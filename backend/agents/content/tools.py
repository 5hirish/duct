"""In-process MCP tools exposed to the Content Studio agent.

Tool groups:
  - Writers: submit_post_draft, edit_slide, submit_assessment —
    validate Pydantic, upsert DB, emit SSE events (PLAN_GENERATED /
    POST_DRAFT_UPDATED / PUBLISH_ASSESSMENT).
  - Readers: fetch_brand_context, fetch_topic_bank, fetch_format_library,
    fetch_avatar_library, fetch_content_history, fetch_content_assets,
    fetch_post, fetch_slide_context, check_post_sanity.
  - Image + render: generate_image, edit_image, render_slide — return image
    content blocks the agent can see (for critique + visual review).

Publishing + metrics are NOT agent tools — they are UI/REST-driven
(routes/content.py: /publish, /mark-posted, /sync-metrics, /sync-daily).

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
from typing import Annotated, Any
from uuid import UUID, uuid4

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.content.results import (
    AttachPostVideoResult,
    EditImageResult,
    EditSlideResult,
    GenerateImageResult,
    RenderSlideResult,
    SubmitPostResult,
    UnderstandVideoResult,
)
from sqlmodel import Session, select

from agents.models import (
    DEFAULT_IMAGE_MODEL,
    AspectRatio,
    ImageModel,
    VideoModel,
    VideoUnderstandingModel,
)
from agents.core.tool_schema import tool_schema
from agents.content.events import ContentEvent
from agents.content.assessment import (
    MARKER_IDS,
    apply_marker_metadata,
    compute_overall,
    compute_sanity,
)
from agents.content.schema import (
    ContentMarker,
    ContentSession,
    ContentStatus,
    PostDraft,
    PostType,
    PublishAssessment,
    Slide,
    VideoBeat,
)
from agents.content.templates import derive_image_prompts, render_slides_html
from config import get_configs
from service import storage
from db.session import get_engine
from models.content import (
    AssetSource,
    AssetType,
    ContentAsset,
    ContentAvatar,
    ContentFormat,
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


def _is_youtube_url(url: str) -> bool:
    """A YouTube URL goes to Gemini as fileData (no local download); anything else
    is fetched as bytes. Host-based (not substring) so
    'https://evil.com/?x=youtube.com/' is NOT treated as YouTube."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").rstrip(".").lower()
    host = host[4:] if host.startswith("www.") else host
    return host in {"youtube.com", "m.youtube.com", "youtu.be"}


def _open_db() -> Session:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return Session(engine)


# --- Typed result serializers -------------------------------------------------
# Tool results the model reads back are modeled (see results.py) instead of
# hand-built dicts, so field names like `attached_to` / `asset_ids` are typed.

def _ok_model(m: BaseModel) -> dict:
    """Success result from a typed model (text-only)."""
    return _ok(m.model_dump(mode="json"))


def _ok_with_images(image_blocks: list[dict], m: BaseModel) -> dict:
    """Success result carrying image content blocks + a typed model as the text."""
    return {"content": [*image_blocks, {"type": "text", "text": m.model_dump_json()}]}


# --- Relational precondition guards -------------------------------------------
# "post/slide/cell exists on THIS project" is an invariant against live state the
# input schema can't express — so it's a runtime guard returning a hard _err, not
# prose for the model. Shared here to replace the copies that had drifted across
# tools (ownership check ×6, "find slide or list valid ids" ×3). Each returns the
# resolved entity OR an _err-shaped dict; callers use:  x, err = guard(...); if err: return err

def _require_post(db: Session, project_id, post_id) -> tuple[ContentPost | None, dict | None]:
    """Resolve the current post for this project, or an _err result."""
    if post_id is None:
        return None, _err("No current post in this session.")
    row = db.get(ContentPost, post_id)
    if row is None or row.project_id != project_id:
        return None, _err(f"Post {post_id} not found for this project.")
    return row, None


def _require_slide(post: ContentPost, slide_id: str) -> tuple[dict | None, int, dict | None]:
    """Find a slide on the post by id, or an _err listing the valid ids.

    Returns (slide_dict, index, None) on hit; (None, -1, err) on miss.
    """
    slides = list(post.slides or [])
    for i, s in enumerate(slides):
        if isinstance(s, dict) and str(s.get("slide_id")) == str(slide_id):
            return s, i, None
    valid = [str(s.get("slide_id")) for s in slides if isinstance(s, dict)]
    return None, -1, _err(f"slide_id {slide_id!r} isn't on this post. Use one of: {valid}.")


def _require_beat(post: ContentPost, beat_id: str) -> tuple[dict | None, int, dict | None]:
    """Find a video-storyboard beat by id, or an _err listing the valid ids
    (the video analogue of _require_slide). (beat_dict, index, None) on hit."""
    beats = list(post.video_storyboard or [])
    for i, b in enumerate(beats):
        if isinstance(b, dict) and str(b.get("beat_id")) == str(beat_id):
            return b, i, None
    valid = [str(b.get("beat_id")) for b in beats if isinstance(b, dict)]
    return None, -1, _err(f"beat_id {beat_id!r} isn't on this post. Use one of: {valid}.")


def _require_item(slide: dict, item_index: int | None) -> dict | None:
    """Range-check item_index against a slide's image cells. None = ok, else _err."""
    if item_index is None:
        return None
    n = len(slide.get("items") or [])
    if n and not (0 <= item_index < n):
        return _err(
            f"item_index {item_index} is out of range for {slide.get('slide_id')!r} "
            f"— it has {n} image cell(s) (use 0–{n - 1}), or omit it for a single image."
        )
    return None


def _arc_line_for_slide(emotional_arc: str, slide_id: str, idx: int) -> str:
    """Pull THIS slide's line out of the emotional_arc blob ("01: ...\\n02: ...").

    Matches by the slide's trailing number (slide-03 -> "3"); falls back to the
    idx-th line. Returns "" when the arc is empty or has no matching line.
    """
    arc = (emotional_arc or "").strip()
    if not arc:
        return ""
    lines = [ln.strip() for ln in arc.splitlines() if ln.strip()]
    num = ("".join(ch for ch in str(slide_id) if ch.isdigit()).lstrip("0")) or "0"
    for ln in lines:
        head = (ln.split(":", 1)[0].strip().lstrip("0")) or "0"
        if head == num:
            return ln
    return lines[idx] if 0 <= idx < len(lines) else ""


def _resolve_camera_refs(db: Session, project_id, pool: str) -> list[dict]:
    """Resolve cameraRef candidates for a pool (selfie-talking / lifestyle /
    closeup). Primary source is the repo-bundled GLOBAL camera library for that
    pool — its `asset_id` is a /static/references/... URL that generate_image
    resolves from disk. Also includes any per-project DB references. Returns up
    to 5, role-ready (the same shape fetch_content_assets emits)."""
    key = (pool or "").strip().lower()
    refs: list[dict] = []
    # Global library (camera axis, pool subtype) — where the curated refs live.
    try:
        from service.content_references import global_reference_asset_dicts
        for d in global_reference_asset_dicts(axis="camera", subtype=key or None):
            refs.append({"asset_id": d["id"], "url": d["url"], "filename": d.get("slug", "")})
    except Exception:
        logger.debug("global camera refs unavailable", exc_info=True)
    # Per-project DB references (a project may have uploaded its own).
    rows = db.exec(
        select(ContentAsset).where(
            ContentAsset.project_id == project_id,
            ContentAsset.asset_type == AssetType.REFERENCE,
        )
    ).all()
    db_matched = [a for a in rows if key and key in f"{a.filename} {a.url} {a.prompt}".lower()]
    for a in (db_matched or rows):
        refs.append({"asset_id": str(a.id), "url": a.url, "filename": a.filename})
    return refs[:5]


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


def _resolved_image_prompt(incoming: str, prev_prompt: str, prev_has_image: bool) -> str:
    """Decide a slide/cell image_prompt on the bulk re-emit (submit_post_draft)
    path. NO length heuristics — purely structural.

    Once a slide has a GENERATED IMAGE, its image_prompt is the provenance of
    that image and is LOCKED here: a whole-post resubmit is copy/structure work
    and must not rewrite it. This is what stops a rich prompt from silently
    collapsing into a stub across successive submits (2170 → 956 → … → 75 chars)
    and producing plastic output. Deliberate scene changes go through edit_slide
    (which IS allowed to shorten — a real edit, including a more concise rewrite).
    Independently, an omitted/empty incoming prompt never deletes a stored one.
    Before an image exists the slide is still being drafted, so refinements
    (shorter or longer) are accepted as-is.
    """
    inc = (incoming or "").strip()
    prev = (prev_prompt or "").strip()
    if not prev:
        return incoming            # nothing stored to protect
    if prev_has_image or not inc:  # locked to its image, or an omission
        return prev_prompt
    return incoming                # still drafting → accept the refinement


def _merge_slide_images(incoming: list[Slide], existing_row: ContentPost | None) -> list[Slide]:
    """Carry already-generated images forward across copy/prompt edits.

    The orchestrator authors copy + image prompts; it does NOT re-send the
    generated `image_url` on every edit. So when a slide already has an image
    on the persisted row, we backfill image_url / image_asset_id /
    image_prompt_used onto the incoming slide (keyed by slide_id) UNLESS the
    incoming slide explicitly carries its own image_url.

    We ALSO guard image_prompt against degradation (see _keep_richer_prompt):
    the bulk re-emit may only enhance a stored prompt, never shorten or drop it.
    This makes it safe for the agent to omit/abbreviate image_prompt on re-emit
    — the richer stored prompt is preserved.

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
        prev_has_image = bool(prev.get("image_url"))
        # A generated slide's image_prompt is locked on the bulk re-emit path —
        # only edit_slide may change it. (Structural, no length compare.)
        kept_prompt = _resolved_image_prompt(slide.image_prompt, prev.get("image_prompt", ""), prev_has_image)
        if kept_prompt != slide.image_prompt:
            update["image_prompt"] = kept_prompt
            if prev_has_image and (slide.image_prompt or "").strip():
                logger.info(
                    "content: kept locked image_prompt for generated slide %s on bulk re-emit "
                    "(use edit_slide to change a generated slide's prompt)", slide.slide_id,
                )
        if not slide.image_url and prev_has_image:
            update.update({
                "image_url":         prev.get("image_url", ""),
                "image_asset_id":    prev.get("image_asset_id"),
                "image_prompt_used": prev.get("image_prompt_used", ""),
            })
        # Carry generated cell images forward (collage / before-after), matched
        # by position within the slide. Cell prompts get the same structural lock.
        if slide.items:
            prev_items = prev.get("items") or []
            new_items = list(slide.items)
            touched = False
            for j, it in enumerate(slide.items):
                pit = prev_items[j] if j < len(prev_items) else None
                if not pit:
                    continue
                cell_update: dict = {}
                pit_has_image = bool(pit.get("image_url"))
                kept_cell_prompt = _resolved_image_prompt(it.image_prompt, pit.get("image_prompt", ""), pit_has_image)
                if kept_cell_prompt != it.image_prompt:
                    cell_update["image_prompt"] = kept_cell_prompt
                if not it.image_url and pit_has_image:
                    cell_update.update({
                        "image_url":         pit.get("image_url", ""),
                        "image_asset_id":    pit.get("image_asset_id"),
                        "image_prompt_used": pit.get("image_prompt_used", ""),
                    })
                if cell_update:
                    new_items[j] = it.model_copy(update=cell_update)
                    touched = True
            if touched:
                update["items"] = new_items
        if update:
            slide = slide.model_copy(update=update)
        merged.append(slide)
    return merged


def _merge_beat_images(incoming: list[VideoBeat], existing_row: ContentPost | None) -> list[VideoBeat]:
    """Carry already-generated keyframe stills forward across copy/prompt edits —
    the video-storyboard analogue of _merge_slide_images. Keyed by beat_id, backfill
    the first-frame (image_*) and the optional after-frame (end_image_*) from the
    persisted row UNLESS the incoming beat carries its own url. A copy-only re-emit
    that omits the generated urls keeps the keyframes; a changed prompt with the old
    image_prompt_used reads as stale so the UI can offer a regenerate."""
    if existing_row is None or not getattr(existing_row, "video_storyboard", None):
        return incoming
    prev_by_id: dict[str, dict] = {}
    for b in existing_row.video_storyboard or []:
        if isinstance(b, dict) and b.get("beat_id"):
            prev_by_id[str(b["beat_id"])] = b
    merged: list[VideoBeat] = []
    for beat in incoming:
        prev = prev_by_id.get(beat.beat_id)
        if not prev:
            merged.append(beat)
            continue
        update: dict = {}
        if not beat.image_url and prev.get("image_url"):
            update.update({
                "image_url":         prev.get("image_url", ""),
                "image_asset_id":    prev.get("image_asset_id"),
                "image_prompt_used": prev.get("image_prompt_used", ""),
            })
        if not beat.end_image_url and prev.get("end_image_url"):
            update.update({
                "end_image_url":         prev.get("end_image_url", ""),
                "end_image_asset_id":    prev.get("end_image_asset_id"),
                "end_image_prompt_used": prev.get("end_image_prompt_used", ""),
            })
        # The per-beat clip is attached later (not re-authored) — preserve it.
        if not beat.clip_url and prev.get("clip_url"):
            update["clip_url"] = prev.get("clip_url", "")
        if update:
            beat = beat.model_copy(update=update)
        merged.append(beat)
    return merged


def _attach_image_to_beat(
    db: Session,
    row: ContentPost,
    beat_id: str,
    *,
    asset_id: str,
    url: str,
    frame: str = "first",
    prompt_used: str | None = None,
) -> bool:
    """Write a generated keyframe onto one beat of a video post's storyboard.

    ``frame`` selects the first-frame (default) or the 'after' frame of a
    transformation beat ("last"). Sets image_url / image_asset_id (or end_*), and
    keeps the prompt + provenance in sync so the beat doesn't read falsely stale
    right after a successful (re)generation — same contract as
    _attach_image_to_slide. Returns True if the beat was found + updated; the
    caller commits."""
    beats = list(row.video_storyboard or [])
    for i, b in enumerate(beats):
        if not (isinstance(b, dict) and str(b.get("beat_id")) == str(beat_id)):
            continue
        b = dict(b)
        if frame == "last":
            b["end_image_url"] = url
            b["end_image_asset_id"] = asset_id
            b["end_image_prompt_used"] = prompt_used if prompt_used is not None else b.get("end_image_prompt", "")
            if prompt_used is not None:
                b["end_image_prompt"] = prompt_used
        else:
            b["image_url"] = url
            b["image_asset_id"] = asset_id
            b["image_prompt_used"] = prompt_used if prompt_used is not None else b.get("image_prompt", "")
            if prompt_used is not None:
                b["image_prompt"] = prompt_used
        beats[i] = b
        row.video_storyboard = beats
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        return True
    return False


def _build_post_payload(row: ContentPost) -> dict:
    """The POST_DRAFT_UPDATED payload — shared by submit_post_draft and the
    per-slide image attach path so the frontend always gets the same shape."""
    return {
        "id":              str(row.id),
        "project_id":      str(row.project_id),
        "post_dir_slug":   row.post_dir_slug,
        "pillar":          row.pillar,
        "topic":           row.topic,
        # Drives the viewport switch on the frontend (slideshow/image → slides
        # carousel; video → <video> player). Previously omitted from the payload.
        "post_type":       row.post_type,
        "layout":          row.layout,
        "slide_count":     row.slide_count,
        "slides":          row.slides,
        "slides_html":     row.slides_html,
        # Single-clip video (populated when post_type == "video"; see attach_post_video).
        "video_url":             row.video_url,
        "video_asset_id":        str(row.video_asset_id) if row.video_asset_id else None,
        "video_prompt":          row.video_prompt,
        "video_duration_seconds": row.video_duration_seconds,
        "video_aspect_ratio":    row.video_aspect_ratio,
        "source_image_asset_id": str(row.source_image_asset_id) if row.source_image_asset_id else None,
        "video_storyboard":      row.video_storyboard,
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
        "last_assessment": row.last_assessment,
        # Clone lineage (None for ordinary posts) → lets the viewport render the
        # reference diagnostic + the Kept-vs-Changed ledger trust panel.
        "clone_source":    row.clone_source,
    }


def _attach_image_to_slide(
    db: Session,
    row: ContentPost,
    slide_id: str,
    *,
    asset_id: str,
    url: str,
    item_index: int | None = None,
    prompt_used: str | None = None,
) -> bool:
    """Write a generated image onto one slide (or one cell of a multi-image
    slide) of a post + re-render the HTML.

    Sets image_url / image_asset_id. When ``prompt_used`` is given (the
    descriptive prompt the image was generated from, before any reference
    prefix), it is recorded as BOTH ``image_prompt`` and ``image_prompt_used``:
    generating an image is a deliberate act that defines what the slide depicts,
    so the slide's prompt and its provenance stay in sync — the slide does NOT
    read as falsely stale right after a successful (re)generation. (The accidental
    degradation path — a bulk submit_post_draft re-emit — is still guarded
    separately in _merge_slide_images; a later deliberate edit_slide that changes
    image_prompt correctly marks the image stale.) When ``prompt_used`` is omitted
    we only anchor image_prompt_used to the slide's current image_prompt (legacy).
    item_index targets a collage/before-after cell when the slide has cells; a
    stray item_index on a single-image slide falls through to a plain attach
    (the model routinely passes item_index=0 for ordinary photo slides). Returns
    True if the target was found + updated. The caller commits.
    """
    slides = list(row.slides or [])
    found = False
    for i, s in enumerate(slides):
        if not (isinstance(s, dict) and str(s.get("slide_id")) == str(slide_id)):
            continue
        s = dict(s)
        items = list(s.get("items") or [])
        # item_index only applies to multi-image slides. On a single-image slide
        # (no cells) the model's stray item_index=0 must NOT fail the attach —
        # fall through to the single-image path.
        if item_index is not None and items:
            if not (0 <= item_index < len(items)):
                return False
            cell = dict(items[item_index])
            cell["image_url"] = url
            cell["image_asset_id"] = asset_id
            if prompt_used is not None:
                cell["image_prompt"] = prompt_used       # keep prompt + provenance in sync
                cell["image_prompt_used"] = prompt_used
            else:
                cell["image_prompt_used"] = cell.get("image_prompt", "")
            items[item_index] = cell
            s["items"] = items
        else:
            s["image_url"] = url
            s["image_asset_id"] = asset_id
            if prompt_used is not None:
                s["image_prompt"] = prompt_used          # keep prompt + provenance in sync
                s["image_prompt_used"] = prompt_used
            else:
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


def _downscale_for_vision(data: bytes, mime: str, max_edge: int = 1536) -> tuple[str, str]:
    """Prepare a generated image for the agent's critique view: cap the long edge
    at ~max_edge and re-encode (JPEG for opaque photos). Claude resizes to
    ≤1568px on the long edge server-side anyway, so this only trims the
    backend→model upload with no fidelity loss. The full-res original is what we
    persist to storage and reference in the slide. Returns (base64, mimeType);
    falls back to the original bytes on any error."""
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(data))
        long_edge = max(img.width, img.height)
        if long_edge > max_edge:
            scale = max_edge / long_edge
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
        buf = BytesIO()
        if img.mode in ("RGBA", "LA", "P"):
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii"), "image/png"
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return base64.b64encode(data).decode("ascii"), mime


def _persist_slide_render(project_id: UUID, post_id: UUID, slide_id: str, png: bytes) -> str:
    """Best-effort: write a rasterized slide PNG to object storage + a
    ContentAsset row (asset_type='slide_render'). These composed renders are what
    the publish route uploads to TikTok. Returns the public url."""
    fname = f"{slide_id}-{uuid4().hex[:8]}.png"
    key = f"projects/{project_id}/renders/{fname}"
    url = storage.put_image(key, png, "image/png")
    with _open_db() as db:
        db.add(ContentAsset(
            project_id=project_id,
            post_id=post_id,
            asset_type=AssetType.SLIDE_RENDER,
            source=AssetSource.RENDER,
            url=url,
            filename=fname,
            mime_type="image/png",
            params={"slide_id": slide_id, "width": 1080, "height": 1920},
        ))
        db.commit()
    return url


def _load_asset_bytes(asset: ContentAsset) -> bytes | None:
    """Resolve a ContentAsset to its raw bytes from the configured object store.

    Delegates to service.storage.get_bytes, which handles every URL family we
    emit: absolute R2/CDN URLs (HTTP GET), local '/uploads/...' (disk), and
    repo-bundled '/static/references/...'. Returns None when unavailable —
    callers surface a friendly error.
    """
    return storage.get_bytes(asset.url)




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
    (e.g. session.post_id after submit_post_draft).
    """
    # Typed input models for the image tools — the source of truth for both the
    # tool input_schema (via tool_schema()) and the field constraints the model
    # sees (enums from StrEnum so an invalid id can't be passed; ranges via
    # Field). Defined here, not at module top, because the gemini enums pull the
    # google client; service.gemini is imported lazily at session-build time.

    class GenerateImageInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(description="Image prompt — the scene description for this slide.")
        slide_id: str | None = Field(
            None,
            description=(
                "The slide this image is for (e.g. 'slide-01'). When set, the result is "
                "attached to that slide of the current post: image_url is filled, the preview "
                "re-renders, and POST_DRAFT_UPDATED fires — no separate submit_post_draft "
                "needed. Always pass this during the image phase."
            ),
        )
        item_index: int | None = Field(
            None, ge=0,
            description=(
                "For multi-image slides (collage / before-after), the 0-based cell to attach "
                "this image to. Omit for single-image slides."
            ),
        )
        beat_id: str | None = Field(
            None,
            description=(
                "For VIDEO posts: the storyboard beat this keyframe is for (e.g. 'beat-01'). "
                "When set, the standalone still is attached to that beat of the current post "
                "(image_url filled, POST_DRAFT_UPDATED fires) — the video analogue of slide_id. "
                "Mutually exclusive with slide_id."
            ),
        )
        frame: str = Field(
            "first",
            description=(
                "With beat_id, which keyframe of the beat to attach to: 'first' (default, the "
                "opening frame) or 'last' (the 'after' frame of a before→after transformation "
                "beat, used for first+last-frame interpolation)."
            ),
        )
        model: ImageModel = Field(
            DEFAULT_IMAGE_MODEL,
            description=f"Optional image model id; defaults to {DEFAULT_IMAGE_MODEL.value}.",
        )
        aspect_ratio: AspectRatio = Field(
            AspectRatio.PORTRAIT_9_16, description="Optional aspect ratio. Defaults to 9:16 portrait.",
        )
        number_of_images: int = Field(1, ge=1, le=4, description="How many images to generate. Default 1, max 4.")
        input_asset_id: str | None = Field(
            None, description="Single reference asset UUID (legacy; prefer input_asset_ids). Gemini-class models only.",
        )
        input_asset_ids: list[str] = Field(
            default_factory=list,
            description=(
                "Multiple reference assets (Gemini-class only). Up to 3 UUIDs in role-order: "
                "[character_ref, camera_or_style_ref, optional_third]. For slides 2-5 the common "
                "pattern is [slide-01 character image, cameraRef from the reference library] — "
                "first image locks face/skin/hair, second imitates TikTok framing. A role-explanation "
                "prefix is auto-prepended to your prompt when 2+ ids are passed."
            ),
        )

    class EditImageInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        prompt: str = Field(description="Edit instruction.")
        input_asset_id: str = Field(description="UUID of the source asset to edit.")
        model: ImageModel | None = Field(None, description="Optional image model id.")
        aspect_ratio: AspectRatio | None = Field(None, description="Optional aspect ratio override.")
        number_of_images: int = Field(1, ge=1, le=4, description="How many images to generate (1-4).")

    class AttachPostVideoInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        source_url: str = Field(
            description=(
                "The URL of the FINISHED video clip returned by Higgsfield "
                "(mcp__higgsfield__*) once generation has completed. The clip is "
                "downloaded and stored in the project's media library, then attached "
                "to the current video post (POST_DRAFT_UPDATED fires)."
            ),
        )
        video_prompt: str = Field(
            "", description="The motion / action prompt used to generate the clip (kept for provenance).",
        )
        duration_seconds: int | None = Field(
            None, ge=1, le=15, description="Clip length in seconds, if known.",
        )
        aspect_ratio: AspectRatio = Field(
            AspectRatio.PORTRAIT_9_16, description="Clip aspect ratio. Defaults to 9:16 portrait.",
        )
        model: str = Field("", description="The Higgsfield model that produced the clip (e.g. 'kling-3.0'), if known.")
        source_image_asset_id: str | None = Field(
            None,
            description=(
                "The content asset UUID of the keyframe still that was animated, when the "
                "keyframe was a Duct/Gemini image (from generate_image). Omit if the keyframe "
                "was generated inside Higgsfield."
            ),
        )

    class UnderstandVideoInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        target: str = Field(
            "reference",
            description=(
                "'reference' (default) deconstructs the post's CLONE REFERENCE; 'generated' "
                "watches the post's OWN generated clip (post.video_url) — use this in review to "
                "check what the clip ACTUALLY contains (on-screen text rendered? transformation "
                "shown? artifacts?). Ignored when video_url is given."
            ),
        )
        video_url: str | None = Field(
            None,
            description=(
                "Optional direct .mp4 URL to fetch, OR a public YouTube URL (analysed "
                "without downloading). Omit to deconstruct the CURRENT post's clone "
                "reference (the usual case) — the reference clip was captured at ingest."
            ),
        )
        media_resolution: str | None = Field(
            None,
            description=(
                "Token/detail per frame: 'low' (~100 tokens/sec, cheaper, good for long "
                "clips) or 'high' (more detail). Omit for the default (~300 tokens/sec)."
            ),
        )
        fps: float | None = Field(
            None, ge=0.1, le=10,
            description=(
                "Sampling frame rate. Default 3 (catches fast hard cuts). Lower (0.5–1) for "
                "long videos to save tokens; higher (5) for very fast motion."
            ),
        )
        start_offset: str | None = Field(
            None, description="Analyse only from this point, e.g. '30s' or '1m15s'.",
        )
        end_offset: str | None = Field(
            None, description="Analyse only up to this point, e.g. '80s'.",
        )
        model: VideoUnderstandingModel | None = Field(
            None,
            description="Override the model (gemini-3.5-flash to save cost). Default gemini-3.1-pro-preview.",
        )
        force: bool = Field(
            False,
            description=(
                "Re-run the analysis even if a cached deconstruction already exists on the "
                "reference. Default false returns the cached one instantly (no extra cost)."
            ),
        )

    class GenerateVideoClipInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        motion_prompt: str = Field(
            description=(
                "The Veo direction for the clip — the beat-by-beat DYNAMIC/STATIC/AUDIO motion "
                "prompt (camera, action, lighting, any spoken line in double quotes). Detailed "
                "cinematography wins; Veo generates synced audio."
            ),
        )
        beat_id: str | None = Field(
            None,
            description=(
                "Animate this storyboard beat's keyframe as the first frame (and, for a "
                "transformation beat, its 'after' frame as the last frame). Omit to animate the "
                "post's opening keyframe."
            ),
        )
        reference_asset_ids: list[str] = Field(
            default_factory=list,
            description="Up to 3 reference stills (character/product) for subject consistency (Veo 3.1).",
        )
        duration_seconds: int = Field(
            8, ge=4, le=15,
            description="Clip length in seconds. Default 8. Veo: 4/6/8 (snapped); Grok 1.5: ≤12; Seedance 2.0: ≤15.",
        )
        aspect_ratio: AspectRatio = Field(
            AspectRatio.PORTRAIT_9_16, description="Clip aspect ratio. Defaults to 9:16 portrait.",
        )
        model: VideoModel | None = Field(None, description="Veo model id (default veo-3.1-generate-preview).")
        negative_prompt: str | None = Field(None, description="What to exclude from the clip.")
        person_generation: str | None = Field(
            None, description="'dont_allow' | 'allow_adult' | 'allow_all' — whether to generate people.",
        )
        generate_audio: bool = Field(
            True,
            description=(
                "Veo generates synced audio (voice/SFX/music) by default. Set false for a SILENT "
                "clip — e.g. a pure-vibe montage where the creator adds their own trending sound."
            ),
        )
        extension_prompts: list[str] = Field(
            default_factory=list,
            description=(
                "Extend the clip into a LONGER CONTINUOUS shot: each entry adds a +7s continuation "
                "segment directed by its prompt (the output is the full cumulative clip — no "
                "stitching). Use for a single evolving shot beyond 8s (e.g. a continuous "
                "talking-head/vibe shot), NOT for hard cuts between distinct beats. ≤20 segments "
                "(≤148s); Veo 3.1 / 3.1-Fast only; 720p during extension."
            ),
        )

    # ----------------------- Writers -----------------------

    @tool(
        name="submit_post_draft",
        description=(
            "Persist a single post draft. Validates against PostDraft schema, "
            "upserts a content_posts row keyed by (project_id, post_dir_slug), "
            "and emits POST_DRAFT_UPDATED. Call AFTER emitting "
            "<duct_artifact>{\"type\":\"post\",...}</duct_artifact>."
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
                # A revise/resume session is bound to a specific post via
                # session.post_id (routes/agents.py derives it from the
                # conversation's artifact_id). That binding wins over the
                # model-supplied slug: a drafting agent that mints a fresh
                # date-slug (e.g. today's date) would otherwise miss the upsert
                # key and FORK a brand-new post, orphaning it from the chat.
                # Resolve the bound row first and keep its slug.
                existing = None
                if session.post_id is not None:
                    bound = db.get(ContentPost, session.post_id)
                    if bound is not None and bound.project_id == project_id:
                        existing = bound
                if existing is None:
                    existing = db.exec(
                        select(ContentPost).where(
                            ContentPost.project_id == project_id,
                            ContentPost.post_dir_slug == draft.post_dir_slug,
                        )
                    ).first()
                # Never rename a post we're updating in place — the slug is its
                # stable identity (URL + conversation link). Only a brand-new
                # insert adopts the model-supplied slug.
                effective_slug = existing.post_dir_slug if existing is not None else draft.post_dir_slug

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

                # Video storyboard (multi-beat) — same carry-forward contract as
                # slides: generated keyframes persist across copy-only re-emits.
                if draft.video_storyboard:
                    storyboard_json = [
                        b.model_dump(mode="json")
                        for b in _merge_beat_images(draft.video_storyboard, existing)
                    ]
                else:
                    storyboard_json = existing.video_storyboard if existing is not None else []

                values = {
                    "project_id":      project_id,
                    "plan_id":         session.plan_id,
                    "post_dir_slug":   effective_slug,
                    "pillar":          draft.pillar,
                    "topic":           draft.topic,
                    "post_type":       draft.post_type,
                    "format_id":       _resolve_format_id(db, project_id, draft.format_slug),
                    "avatar_id":       draft.avatar_id,
                    "layout":          draft.layout.value,
                    "slide_count":     slide_count,
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
                    # Video (single-clip). The motion prompt + clip settings are
                    # authored copy → always taken from the draft. The generated
                    # clip itself (video_url / video_asset_id) and its keyframe are
                    # attached LATER by attach_post_video; a copy-edit re-submit
                    # must not wipe them, so carry the persisted values forward
                    # unless the draft explicitly supplies new ones (same guard as
                    # _merge_slide_images does for generated slide images).
                    "video_prompt":           draft.video_prompt or "",
                    "video_duration_seconds": draft.video_duration_seconds,
                    "video_aspect_ratio":     draft.video_aspect_ratio.value,
                    "video_url":              draft.video_url or (existing.video_url if existing is not None else ""),
                    "video_asset_id":         draft.video_asset_id or (existing.video_asset_id if existing is not None else None),
                    "source_image_asset_id":  draft.source_image_asset_id or (existing.source_image_asset_id if existing is not None else None),
                    "video_storyboard":       storyboard_json,
                }
                if existing is not None:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    # Preserve a saved status across agent re-submits (chat
                    # refinements): a post the user already Saved (draft) or
                    # published must NOT be reset to "pending". `status` is
                    # deliberately absent from `values` above.
                    row = existing
                else:
                    # A brand-new post is unsaved — the user's Save flips it
                    # pending → draft (see routes/content.py PATCH + the UI).
                    row = ContentPost(**values, status=ContentStatus.PENDING)
                    db.add(row)
                db.commit()
                db.refresh(row)
                session.post_id = row.id
                # Bind the conversation to this post the MOMENT it's persisted so
                # "open post → resume" works right away. Previously the link was set
                # only when the worker RETURNED (_link_conversation_artifact at
                # session end) — but interactive video sessions stay alive through
                # the keyframe gates, so a post opened mid/post-draft found no linked
                # conversation and the agent restarted from scratch.
                _conv_id = getattr(session, "conversation_id", None)
                if _conv_id is not None:
                    from agents.content.persistence import link_artifact
                    try:
                        link_artifact(db, _conv_id, "post", row.id)
                    except Exception:
                        logger.warning("content: failed to link conversation %s -> post %s",
                                       _conv_id, row.id, exc_info=True)
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
                return _ok_model(SubmitPostResult(
                    post_id=str(row.id),
                    post_dir_slug=row.post_dir_slug,
                    slide_count=row.slide_count,
                    images_generated=sum(
                        1 for s in (row.slides or [])
                        if isinstance(s, dict) and s.get("image_url")
                    ),
                ))
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
                row, err = _require_post(db, project_id, session.post_id)
                if err:
                    return err
                slides = list(row.slides or [])
                _slide, idx, err = _require_slide(row, slide_id)
                if err:
                    return err
                existing_slide = slides[idx]
                # edit_slide is the DELIBERATE surgical path — a real prompt edit
                # (including a more concise rewrite) is allowed here. Degradation
                # protection lives on the bulk re-emit path (_merge_slide_images),
                # which is where prompts silently collapsed.
                merged = {**existing_slide, **patch, "slide_id": slide_id}
                # If this patch manually attaches an image (image_url) without
                # declaring which prompt produced it, anchor provenance to the
                # slide's current prompt — a blank image_prompt_used makes the
                # slide read as falsely stale.
                if patch.get("image_url") and "image_prompt_used" not in patch:
                    merged["image_prompt_used"] = merged.get("image_prompt", "")
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
                return _ok_model(EditSlideResult(
                    post_id=str(row.id),
                    slide_id=slide_id,
                    updated=list(patch.keys()),
                ))
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
                    select(ContentPost).where(
                        ContentPost.project_id == project_id,
                        ContentPost.status != ContentStatus.PENDING,  # unsaved drafts aren't "covered"
                    )
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
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100,
                          "description": "Max rows to return. Default 30, max 100."},
            },
            "required": [],
        },
    )
    async def fetch_content_history(args: dict) -> dict:
        try:
            limit = min(int(args.get("limit") or 30), 100)
            with _open_db() as db:
                rows = db.exec(
                    select(ContentPost)
                    .where(
                        ContentPost.project_id == project_id,
                        ContentPost.status != ContentStatus.PENDING,  # exclude unsaved drafts
                    )
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
        name="fetch_content_assets",
        description=(
            "Return content assets (generated images, uploads, references) "
            "for this project. Filter by asset_type if provided "
            "(e.g. 'generated', 'logo', 'background', 'reference', 'upload'). "
            "References include the repo-bundled GLOBAL library (camera / "
            "layouts / captions) served from /static/references — narrow it "
            "with the optional axis + subtype filters. A global reference's "
            "`id` is its /static/references/... URL; pass that id straight "
            "into generate_image's input_asset_ids."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string",
                    "description": "Optional asset_type filter (e.g. 'generated', 'reference', 'slide_render'). Omit for all types.",
                },
                "axis": {
                    "type": "string",
                    "description": "Optional reference-axis filter: 'camera' | 'layouts' | 'captions'. Only affects global library references.",
                },
                "subtype": {
                    "type": "string",
                    "description": "Optional reference-subtype filter (e.g. 'selfie-talking', 'lifestyle', 'closeup'). Only affects global library references.",
                },
            },
            "required": [],
        },
    )
    async def fetch_content_assets(args: dict) -> dict:
        try:
            asset_type = (args.get("asset_type") or "").strip()
            axis       = (args.get("axis") or "").strip() or None
            subtype    = (args.get("subtype") or "").strip() or None
            with _open_db() as db:
                stmt = select(ContentAsset).where(ContentAsset.project_id == project_id)
                if asset_type:
                    stmt = stmt.where(ContentAsset.asset_type == asset_type)
                rows = db.exec(stmt).all()
                assets = [
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
            # Merge the repo-bundled global reference library (disk, not DB).
            # Globals are project-agnostic, so they ride alongside the
            # project-scoped rows whenever references are in scope.
            if asset_type in ("", "reference"):
                from service.content_references import global_reference_asset_dicts
                assets.extend(global_reference_asset_dicts(axis=axis, subtype=subtype))
            return _ok({"assets": assets})
        except Exception as exc:
            logger.exception("fetch_content_assets failed")
            return _err(f"fetch_content_assets failed: {exc}")

    # ----------------------- Image generation (Phase 4b) -----------------------

    @tool(
        name="generate_image",
        description=(
            "Generate one or more images from a text prompt. "
            "Returns inline image data (so you can see the result) PLUS a stable "
            "asset_url you must reference in slides_html. Defaults: 9:16 portrait, "
            "1 image. Generated images are saved to the project's media library."
        ),
        input_schema=tool_schema(GenerateImageInput),
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
                return _err("Image generation isn't enabled for this workspace yet.")

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            # slide_id / item_index (carousel) or beat_id / frame (video) steer where
            # the result is attached; they're not Gemini params, so pull them out
            # before building the request.
            target_slide_id = str(payload.pop("slide_id", "") or "").strip()
            _ti = payload.pop("item_index", None)
            target_item_index = int(_ti) if _ti not in (None, "") else None
            target_beat_id = str(payload.pop("beat_id", "") or "").strip()
            target_frame = "last" if str(payload.pop("frame", "first")).strip().lower() == "last" else "first"

            # Validate the attach target against the live post BEFORE paying for a
            # Gemini call — a bad slide_id/cell/beat_id is a hard error (with the
            # valid ids), not a silent attached_to:null. Shared guards; see _require_*.
            if target_slide_id:
                with _open_db() as db0:
                    post0, err = _require_post(db0, project_id, session.post_id)
                    if err:
                        return err
                    slide0, _idx, err = _require_slide(post0, target_slide_id)
                    if err:
                        return err
                    if (err := _require_item(slide0, target_item_index)):
                        return err
            elif target_beat_id:
                with _open_db() as db0:
                    post0, err = _require_post(db0, project_id, session.post_id)
                    if err:
                        return err
                    _beat0, _bidx, err = _require_beat(post0, target_beat_id)
                    if err:
                        return err

            # Normalise single-ref legacy → list. The model may pass
            # input_asset_id, input_asset_ids, or both; merge in order.
            # Order encodes role: [character_ref, camera/style_ref].
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

            # A reference id is EITHER a per-project ContentAsset UUID
            # (resolved from the DB + Railway Volume) OR a repo-bundled
            # global library URL ('/static/references/...', resolved from
            # disk — no DB row, no project scope). Classify in order so the
            # [character, camera] role ordering is preserved.
            from service.content_references import disk_path_for_public_url

            ref_plan: list[tuple[str, str]] = []   # (kind, value); kind: 'global'|'uuid'
            uuid_refs: list[str] = []
            for raw in ref_ids_raw:
                raw_s = str(raw).strip()
                if disk_path_for_public_url(raw_s) is not None:
                    ref_plan.append(("global", raw_s))
                    continue
                try:
                    parsed = UUID(raw_s)
                except ValueError:
                    return _err(
                        f"invalid reference asset id {raw_s!r} — expected a content "
                        "asset UUID or a /static/references/... library URL."
                    )
                ref_plan.append(("uuid", str(parsed)))
                uuid_refs.append(str(parsed))

            # The Pydantic request carries UUIDs only (input_asset_ids is
            # typed list[UUID]); global library refs reach the client as
            # bytes via input_bytes_list below.
            payload["input_asset_ids"] = uuid_refs
            payload.pop("input_asset_id", None)
            try:
                request = GenerateImageRequest.model_validate(payload)
            except ValidationError as exc:
                return _err(f"The image request was invalid: {exc}")
            # The descriptive prompt the agent passed — captured BEFORE the
            # multi-reference prefix is prepended below, so image_prompt_used
            # stays comparable to the slide's stored image_prompt for staleness.
            generating_prompt = request.prompt

            input_bytes_list: list[bytes] = []
            global_refs: list[str] = []
            with _open_db() as db:
                for kind, value in ref_plan:
                    if kind == "global":
                        gp = disk_path_for_public_url(value)
                        if gp is None or not gp.exists():
                            return _err(f"reference library file missing on disk: {value}")
                        input_bytes_list.append(gp.read_bytes())
                        global_refs.append(value)
                        continue
                    ref_uuid = UUID(value)
                    asset = db.get(ContentAsset, ref_uuid)
                    if asset is None or asset.project_id != project_id:
                        return _err(f"reference asset {ref_uuid} not found for this project.")
                    ref_bytes = _load_asset_bytes(asset)
                    if not ref_bytes:
                        logger.warning("content: reference asset bytes unavailable: %s", asset.url)
                        return _err("One of the reference images couldn't be loaded — try regenerating it.")
                    input_bytes_list.append(ref_bytes)

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
                    logger.warning("content: image generation failed: %s", exc, exc_info=True)
                    return _err("Image generation failed — please try again in a moment.")

                assets = []
                for img in images:
                    asset = persist_generated_image(
                        project_id, img,
                        db=db,
                        prompt=request.prompt,
                        model=request.model.value,
                        params={
                            "aspect_ratio":      request.aspect_ratio.value,
                            "image_size":        request.image_size.value,
                            "seed":              request.seed,
                            "input_asset_ids":   uuid_refs,
                            "input_global_refs": global_refs,
                        },
                        post_id=session.post_id,
                        source=AssetSource.GEMINI,
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
                                prompt_used=generating_prompt,
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
                                # Instant first paint: ship a small inline data
                                # URI of the just-generated image so the viewport
                                # renders it immediately, with no CDN round-trip;
                                # the client swaps to the full-res CDN url once it
                                # preloads.
                                _pv_b64, _pv_mime = _downscale_for_vision(
                                    images[0].data, images[0].mime_type, max_edge=800
                                )
                                await emit({
                                    "event": ContentEvent.POST_DRAFT_UPDATED,
                                    "session_id": session.session_id,
                                    "post_id": str(row.id),
                                    "payload": _build_post_payload(row),
                                    "inline_preview": {
                                        "slide_id":   target_slide_id,
                                        "item_index": target_item_index,
                                        "data_uri":   f"data:{_pv_mime};base64,{_pv_b64}",
                                    },
                                })
                except Exception:
                    logger.exception("content: failed to attach image to slide %s", target_slide_id)

            # Video posts: attach the keyframe to its storyboard beat (first or the
            # 'after' frame). Mirrors the slide path — the keyframe still is a normal
            # content_assets row; this just links it onto the beat + refreshes preview.
            elif target_beat_id and assets and session.post_id is not None:
                try:
                    async with _post_lock(str(session.post_id)):
                      with _open_db() as db2:
                        row = db2.get(ContentPost, session.post_id)
                        if row is not None and row.project_id == project_id:
                            attached = _attach_image_to_beat(
                                db2, row, target_beat_id,
                                asset_id=str(assets[0].asset_id),
                                url=assets[0].url,
                                frame=target_frame,
                                prompt_used=generating_prompt,
                            )
                            if attached:
                                db2.commit()
                                db2.refresh(row)
                                logger.info(
                                    "content: keyframe attached to %s (%s) on post %s",
                                    target_beat_id, target_frame, row.id,
                                )
                                _pv_b64, _pv_mime = _downscale_for_vision(
                                    images[0].data, images[0].mime_type, max_edge=800
                                )
                                await emit({
                                    "event": ContentEvent.POST_DRAFT_UPDATED,
                                    "session_id": session.session_id,
                                    "post_id": str(row.id),
                                    "payload": _build_post_payload(row),
                                    "inline_preview": {
                                        "beat_id":  target_beat_id,
                                        "frame":    target_frame,
                                        "data_uri": f"data:{_pv_mime};base64,{_pv_b64}",
                                    },
                                })
                except Exception:
                    logger.exception("content: failed to attach keyframe to beat %s", target_beat_id)

            image_blocks: list[dict] = []
            for img in images:
                b64, vmime = _downscale_for_vision(img.data, img.mime_type)
                image_blocks.append({"type": "image", "data": b64, "mimeType": vmime})
            return _ok_with_images(image_blocks, GenerateImageResult(
                asset_ids=[str(a.asset_id) for a in assets],
                asset_urls=[a.url for a in assets],
                model=request.model.value,
                attached_to=((target_slide_id or target_beat_id) if attached else None),
            ))
        except Exception:
            logger.exception("generate_image failed")
            return _err("Image generation hit a snag — please try again.")

    @tool(
        name="edit_image",
        description=(
            "Edit an existing content asset via a free-form Gemini edit (describe the "
            "change in the prompt). Returns the edited image inline + a stable "
            "asset_url. The original asset is preserved — every edit creates a new "
            "content_assets row."
        ),
        input_schema=tool_schema(EditImageInput),
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
                return _err("Image editing isn't enabled for this workspace yet.")

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            try:
                request = EditImageRequest.model_validate(payload)
            except ValidationError as exc:
                return _err(f"The image edit request was invalid: {exc}")

            with _open_db() as db:
                base_asset = db.get(ContentAsset, request.input_asset_id)
                if base_asset is None or base_asset.project_id != project_id:
                    return _err(f"input_asset_id {request.input_asset_id} not found for this project.")
                base_bytes = _load_asset_bytes(base_asset)
                if not base_bytes:
                    return _err("The image you're editing couldn't be loaded — try regenerating it.")

                client = GeminiImageClient(cfg.gemini_api_key)
                try:
                    images = await client.edit_image(
                        request,
                        base_bytes=base_bytes,
                    )
                except GeminiAPIError as exc:
                    logger.warning("content: image edit failed: %s", exc, exc_info=True)
                    return _err("Image editing failed — please try again in a moment.")

                assets = []
                for img in images:
                    asset = persist_generated_image(
                        project_id, img,
                        db=db,
                        prompt=request.prompt,
                        model=request.model.value,
                        params={
                            "input_asset_id":    str(request.input_asset_id),
                            "seed":              request.seed,
                        },
                        post_id=session.post_id,
                        source=AssetSource.GEMINI,
                    )
                    assets.append(asset)

            image_blocks: list[dict] = []
            for img in images:
                b64, vmime = _downscale_for_vision(img.data, img.mime_type)
                image_blocks.append({"type": "image", "data": b64, "mimeType": vmime})
            return _ok_with_images(image_blocks, EditImageResult(
                asset_ids=[str(a.asset_id) for a in assets],
                asset_urls=[a.url for a in assets],
                model=request.model.value,
            ))
        except Exception:
            logger.exception("edit_image failed")
            return _err("Image editing hit a snag — please try again.")

    @tool(
        name="attach_post_video",
        description=(
            "Attach a finished Higgsfield video clip to the current VIDEO post. "
            "Call this AFTER a Higgsfield image-to-video generation has completed and "
            "you have the final clip URL: it downloads the clip into the project's "
            "media library (as a video/mp4 content asset), sets the post's video_url + "
            "video_asset_id, and emits POST_DRAFT_UPDATED so the viewport plays it. "
            "Only for post_type='video'."
        ),
        input_schema=tool_schema(AttachPostVideoInput),
    )
    async def attach_post_video(args: dict) -> dict:
        try:
            from service.higgsfield.storage import download_video_bytes, persist_generated_video

            source_url = str(args.get("source_url") or "").strip()
            if not source_url:
                return _err("source_url is required — pass the finished Higgsfield clip URL.")
            if session.post_id is None:
                return _err("No current post in this session — draft the video post first (submit_post_draft).")

            video_prompt = str(args.get("video_prompt") or "")
            model = str(args.get("model") or "higgsfield")
            aspect_ratio = str(args.get("aspect_ratio") or AspectRatio.PORTRAIT_9_16.value)
            _dur = args.get("duration_seconds")
            duration_seconds = int(_dur) if _dur not in (None, "") else None
            _src_img = str(args.get("source_image_asset_id") or "").strip()
            try:
                source_image_asset_id = UUID(_src_img) if _src_img else None
            except ValueError:
                return _err(f"source_image_asset_id {_src_img!r} is not a valid UUID — omit it if unknown.")

            # Validate the target post exists on this project before downloading.
            with _open_db() as db0:
                post0, err = _require_post(db0, project_id, session.post_id)
                if err:
                    return err

            # Download the finished clip (can be a few MB; generous timeout).
            try:
                data = await asyncio.to_thread(download_video_bytes, source_url)
            except Exception as exc:
                logger.warning("attach_post_video: download failed from %s", source_url, exc_info=True)
                return _err(f"Couldn't download the clip from Higgsfield ({exc}). Re-check the URL or retry.")
            if not data:
                return _err("The clip downloaded empty — the Higgsfield URL may have expired. Re-generate and retry.")

            mime_type = "video/mp4"
            if source_url.lower().split("?")[0].endswith(".webm"):
                mime_type = "video/webm"
            elif source_url.lower().split("?")[0].endswith(".mov"):
                mime_type = "video/quicktime"

            # Persist + attach under the post lock so a concurrent submit_post_draft
            # re-emit can't race the clip onto the row.
            async with _post_lock(str(session.post_id)):
                with _open_db() as db:
                    asset = persist_generated_video(
                        project_id,
                        db=db,
                        data=data,
                        mime_type=mime_type,
                        prompt=video_prompt,
                        model=model,
                        params={
                            "aspect_ratio":          aspect_ratio,
                            "duration_seconds":      duration_seconds,
                            "source_url":            source_url,
                            "source_image_asset_id": str(source_image_asset_id) if source_image_asset_id else None,
                        },
                        duration_seconds=duration_seconds,
                        post_id=session.post_id,
                        source=AssetSource.HIGGSFIELD,
                    )
                    row = db.get(ContentPost, session.post_id)
                    if row is None or row.project_id != project_id:
                        return _err("The video post disappeared while attaching — re-draft and retry.")
                    row.post_type = PostType.VIDEO
                    row.video_url = asset.url
                    row.video_asset_id = asset.asset_id
                    row.video_prompt = video_prompt
                    row.video_duration_seconds = duration_seconds
                    row.video_aspect_ratio = aspect_ratio
                    if source_image_asset_id is not None:
                        row.source_image_asset_id = source_image_asset_id
                    row.updated_at = datetime.now(timezone.utc)
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    logger.info("content: attached video asset %s to post %s", asset.asset_id, row.id)
                    await emit({
                        "event": ContentEvent.POST_DRAFT_UPDATED,
                        "session_id": session.session_id,
                        "post_id": str(row.id),
                        "payload": _build_post_payload(row),
                    })
                    return _ok_model(AttachPostVideoResult(
                        post_id=str(row.id),
                        video_asset_id=str(asset.asset_id),
                        video_url=asset.url,
                        duration_seconds=duration_seconds,
                    ))
        except Exception:
            logger.exception("attach_post_video failed")
            return _err("Attaching the video hit a snag — please try again.")

    @tool(
        name="understand_video",
        description=(
            "Deconstruct a reference video into a director-grade breakdown: a beat-by-beat "
            "shot list (camera, lighting, character/outfit/mood changes), the "
            "transformation/narrative arc, on-screen text verbatim, audio + any dialogue, "
            "the hook and why it works, and the aesthetic. Omit video_url to analyse the "
            "CURRENT post's clone reference — it was already watched at ingest, so this "
            "returns the cached deconstruction instantly (pass force=true to re-watch). Use "
            "this BEFORE drafting a video clone so you rebuild the EXACT structure (the "
            "before→after, the on-screen text) instead of inventing one."
        ),
        input_schema=tool_schema(UnderstandVideoInput),
    )
    async def understand_video(args: dict) -> dict:
        try:
            from service.discovery import (
                analyze_video_bytes,
                analyze_youtube_video,
                understand_reference_video,
            )

            video_url = str(args.get("video_url") or "").strip()
            force = bool(args.get("force") or False)
            # The documented video-understanding knobs, forwarded to Gemini. None =
            # use the service default (fps 3, gemini-3.1-pro-preview, default resolution).
            knobs = {
                k: args.get(k)
                for k in ("media_resolution", "fps", "start_offset", "end_offset", "model")
                if args.get(k) is not None
            }

            # Ad-hoc: analyse any video URL (not tied to the current post). A YouTube
            # URL goes straight to Gemini as fileData; any other URL is fetched.
            # video_url is agent/user-controlled, so guard it against SSRF (private /
            # link-local / non-http hosts) before any fetch or hand-off to Gemini.
            if video_url:
                from service.url_safety import is_public_http_url, safe_get_bytes

                if not is_public_http_url(video_url):
                    return _err(
                        "That video URL isn't allowed — pass a public http(s) URL "
                        "(internal/loopback/link-local addresses are blocked)."
                    )
                if _is_youtube_url(video_url):
                    analysis = await analyze_youtube_video(video_url, **knobs)
                else:
                    data = await asyncio.to_thread(safe_get_bytes, video_url)
                    if not data:
                        return _err(f"Couldn't download a video from {video_url} — check the URL.")
                    analysis = await analyze_video_bytes(data, **knobs)
                if not analysis:
                    return _err(
                        "Video analysis came back empty — the clip may be unreadable or the "
                        "Gemini key isn't configured."
                    )
                return _ok_model(UnderstandVideoResult(analysis=analysis, source="url"))

            target = str(args.get("target") or "reference").strip().lower()

            # 'generated': watch the post's OWN generated clip (for review — does it
            # actually contain the on-screen text / transformation it was meant to?).
            # The clip is our own asset (trusted bucket URL, may be a relative /uploads
            # path) → load via storage.get_bytes, not the SSRF-guarded fetch. Cached on
            # clone_source keyed by the current video_asset_id, so re-reviews are free but
            # a re-generate (new asset id) invalidates it.
            if target == "generated":
                if session.post_id is None:
                    return _err("No current post — open the video post first.")
                with _open_db() as db:
                    post, err = _require_post(db, project_id, session.post_id)
                    if err:
                        return err
                    clip_url = (post.video_url or "").strip()
                    clip_key = str(post.video_asset_id or clip_url)
                    cached = (dict(post.clone_source or {}).get("generated_analysis") or {})
                if not clip_url:
                    return _err("This post has no generated clip yet — generate it first (generate_video_clip).")
                if not force and cached.get("video_asset_id") == clip_key and cached.get("analysis"):
                    return _ok_model(UnderstandVideoResult(
                        analysis=cached["analysis"], source="cache", post_id=str(session.post_id),
                    ))
                data = await asyncio.to_thread(storage.get_bytes, clip_url)
                analysis = await analyze_video_bytes(data, **knobs) if data else ""
                if not analysis:
                    return _err("Couldn't read the generated clip — it may still be processing; retry shortly.")
                # Persist the analysis keyed on the current clip's asset id.
                async with _post_lock(str(session.post_id)):
                    with _open_db() as db:
                        row = db.get(ContentPost, session.post_id)
                        if row is not None and row.project_id == project_id:
                            cs2 = dict(row.clone_source or {})
                            cs2["generated_analysis"] = {"video_asset_id": clip_key, "analysis": analysis}
                            row.clone_source = cs2
                            db.add(row)
                            db.commit()
                return _ok_model(UnderstandVideoResult(
                    analysis=analysis, source="generated", post_id=str(session.post_id),
                ))

            # Default: the current post's clone reference (captured at ingest).
            if session.post_id is None:
                return _err("No current post — open the clone first, or pass an explicit video_url.")
            with _open_db() as db:
                post, err = _require_post(db, project_id, session.post_id)
                if err:
                    return err
                cs = dict(post.clone_source or {})

            cached = (cs.get("video_analysis") or "").strip()
            if cached and not force:
                return _ok_model(UnderstandVideoResult(
                    analysis=cached, source="cache", post_id=str(session.post_id),
                ))

            # Re-watch: prefer the captured stable mp4, else the scraped post's mediaUrls.
            stored_video = ((cs.get("media") or {}).get("video") or "").strip()
            if stored_video:
                data = await asyncio.to_thread(storage.get_bytes, stored_video)
                analysis = await analyze_video_bytes(data, **knobs) if data else ""
            else:
                analysis = await understand_reference_video(cs.get("scraped_post") or {}, **knobs)
            if not analysis:
                return _err(
                    "Couldn't deconstruct the reference clip — it may not be a video or the "
                    "source expired. Fall back to the cover frame + metadata."
                )

            # Persist back onto the post so later turns / a re-draft reuse it.
            async with _post_lock(str(session.post_id)):
                with _open_db() as db:
                    row = db.get(ContentPost, session.post_id)
                    if row is not None and row.project_id == project_id:
                        cs2 = dict(row.clone_source or {})
                        cs2["video_analysis"] = analysis
                        row.clone_source = cs2
                        db.add(row)
                        db.commit()
            return _ok_model(UnderstandVideoResult(
                analysis=analysis, source="fresh", post_id=str(session.post_id),
            ))
        except Exception:
            logger.exception("understand_video failed")
            return _err(
                "Analysing the video hit a snag — please try again, or draft from the cover "
                "frame + metadata."
            )

    @tool(
        name="generate_video_clip",
        description=(
            "Generate the VIDEO post's clip IN-HOUSE with Veo (no Higgsfield needed). Animates a "
            "keyframe still into a clip: pass beat_id to use that storyboard beat's keyframe as the "
            "first frame (and its 'after' frame as the last frame for a transformation), or omit it "
            "to animate the post's opening keyframe. Pass reference_asset_ids (up to 3) for character/"
            "product consistency. Generation takes minutes — this polls to completion, stores the mp4 "
            "as a content asset, sets the post's video_url + video_asset_id, and emits "
            "POST_DRAFT_UPDATED. Only for post_type='video'."
        ),
        input_schema=tool_schema(GenerateVideoClipInput),
    )
    async def generate_video_clip(args: dict) -> dict:
        try:
            from agents.models import VideoProvider, video_provider_for
            from service.gemini.video_gen import DEFAULT_VEO_MODEL
            from service.higgsfield.storage import persist_generated_video

            cfg = get_configs()
            if session.post_id is None:
                return _err("No current post — draft the video post first (submit_post_draft).")

            motion_prompt = str(args.get("motion_prompt") or "").strip()
            if not motion_prompt:
                return _err("motion_prompt is required — describe the clip's motion + audio.")
            beat_id = str(args.get("beat_id") or "").strip()
            model = str(args.get("model") or "").strip() or DEFAULT_VEO_MODEL
            # Route to the provider that serves this model (Veo / Grok / Seedance) + check its key.
            provider = video_provider_for(model)
            if provider == VideoProvider.GROK and not cfg.xai_api_key:
                return _err("Grok video isn't configured — set XAI_API_KEY to use grok-imagine models.")
            if provider == VideoProvider.SEEDANCE and not cfg.byteplus_api_key:
                return _err("Seedance isn't configured — set BYTEPLUS_API_KEY to use seedance models.")
            if provider == VideoProvider.VEO and not cfg.gemini_api_key:
                return _err("Veo isn't configured — set GEMINI_API_KEY to generate clips in-house.")
            aspect_ratio = str(args.get("aspect_ratio") or AspectRatio.PORTRAIT_9_16.value)
            _dur = args.get("duration_seconds")
            duration_seconds = int(_dur) if _dur not in (None, "") else 8
            negative_prompt = str(args.get("negative_prompt") or "").strip() or None
            person_generation = str(args.get("person_generation") or "").strip() or None
            generate_audio = bool(args.get("generate_audio", True))
            ext_prompts = [str(p).strip() for p in (args.get("extension_prompts") or []) if str(p).strip()][:20]
            ref_ids = [str(r).strip() for r in (args.get("reference_asset_ids") or []) if str(r).strip()]
            # The persisted clip length — each provider branch sets it precisely below
            # (Veo adds +7s per extension; Grok/Seedance have none). Default keeps it bound.
            total_duration = duration_seconds

            # Resolve the keyframe(s) + reference bytes against the live post. The sync DB
            # queries + asset byte-loads (HTTP for R2 assets) run OFF the event loop in a
            # thread, and the connection is released here — well before the minutes-long
            # generate call. first_frame is the opening/beat keyframe; last_frame is the
            # beat's 'after' frame for a transformation.
            def _resolve_inputs():
                with _open_db() as db0:
                    post0, perr = _require_post(db0, project_id, session.post_id)
                    if perr:
                        return perr, None, None, [], None
                    if beat_id:
                        beat0, _bi, berr = _require_beat(post0, beat_id)
                        if berr:
                            return berr, None, None, [], None
                        first_id = beat0.get("image_asset_id")
                        end_id = beat0.get("end_image_asset_id") if beat0.get("is_transformation") else None
                    else:
                        # Opening keyframe: the post's source_image_asset_id, else the first beat's.
                        first_id = post0.source_image_asset_id
                        if not first_id:
                            for b in (post0.video_storyboard or []):
                                if isinstance(b, dict) and b.get("image_asset_id"):
                                    first_id = b["image_asset_id"]
                                    break
                        end_id = None

                    def _bytes_for(aid):
                        if not aid:
                            return None
                        a = db0.get(ContentAsset, UUID(str(aid)))
                        return _load_asset_bytes(a) if (a and a.project_id == project_id) else None

                    ff = _bytes_for(first_id) if first_id else None
                    kf_id = None
                    if first_id:
                        try:
                            kf_id = UUID(str(first_id))
                        except ValueError:
                            kf_id = None
                    lf = _bytes_for(end_id)
                    refs = []
                    for rid in ref_ids[:3]:
                        rb = _bytes_for(rid)
                        if rb:
                            refs.append(rb)
                    return None, ff, lf, refs, kf_id

            err, first_frame, last_frame, ref_bytes, keyframe_asset_id = await asyncio.to_thread(_resolve_inputs)
            if err:
                return err

            if first_frame is None and not beat_id:
                return _err(
                    "No keyframe to animate yet — generate the opening keyframe first "
                    "(generate_image), then call this."
                )

            # Generate (minutes; no db connection held). Route to the provider's client.
            try:
                if provider == VideoProvider.GROK:
                    from service.xai.video_gen import GrokVideoClient

                    if last_frame or ref_bytes or ext_prompts:
                        logger.info(
                            "content: Grok ignores last_frame/reference_images/extension "
                            "(Veo-only) — generating from the first frame + prompt.",
                        )
                    grok_duration = min(duration_seconds, 12)   # Grok 1.5 caps at 12s
                    data = await GrokVideoClient(cfg.xai_api_key).generate_video(
                        prompt=motion_prompt,
                        first_frame=first_frame,
                        duration_seconds=grok_duration,
                        model=model,
                    )
                    clip_source = AssetSource.GROK
                    total_duration = grok_duration  # Grok has no extension
                elif provider == VideoProvider.SEEDANCE:
                    from service.byteplus.video_gen import SeedanceVideoClient

                    if ext_prompts:
                        logger.info("content: Seedance ignores extension_prompts (Veo-only).")
                    # Seedance supports first+last (transformation) + reference images natively.
                    data = await SeedanceVideoClient(cfg.byteplus_api_key).generate_video(
                        prompt=motion_prompt,
                        first_frame=first_frame,
                        last_frame=last_frame,
                        reference_images=ref_bytes or None,
                        duration_seconds=duration_seconds,   # Seedance 2.0: up to 15s
                        aspect_ratio=aspect_ratio,
                        generate_audio=generate_audio,
                        model=model,
                    )
                    clip_source = AssetSource.SEEDANCE
                    total_duration = duration_seconds
                else:
                    from service.gemini.video_gen import GeminiVeoClient

                    # Veo accepts only 4/6/8 — snap anything else to 8.
                    veo_duration = duration_seconds if duration_seconds in (4, 6, 8) else 8
                    data = await GeminiVeoClient(cfg.gemini_api_key).generate_video(
                        prompt=motion_prompt,
                        first_frame=first_frame,
                        last_frame=last_frame,
                        reference_images=ref_bytes or None,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        duration_seconds=veo_duration,
                        person_generation=person_generation,
                        negative_prompt=negative_prompt,
                        generate_audio=generate_audio,
                        extension_prompts=ext_prompts or None,
                    )
                    clip_source = AssetSource.VEO
                    total_duration = veo_duration + 7 * len(ext_prompts)
            except Exception as exc:
                logger.warning("generate_video_clip: %s failed", provider.value, exc_info=True)
                return _err(f"{provider.value.title()} couldn't generate the clip ({exc}). Re-check inputs or retry.")

            # Persist + attach under the post lock.
            async with _post_lock(str(session.post_id)):
                with _open_db() as db:
                    asset = persist_generated_video(
                        project_id,
                        db=db,
                        data=data,
                        mime_type="video/mp4",
                        prompt=motion_prompt,
                        model=model,
                        params={
                            "aspect_ratio":    aspect_ratio,
                            "duration_seconds": total_duration,
                            "beat_id":         beat_id or None,
                            "reference_asset_ids": ref_ids,
                            "first_last":      bool(last_frame),
                            "generate_audio":  generate_audio,
                            "extensions":      len(ext_prompts),
                        },
                        duration_seconds=total_duration,
                        post_id=session.post_id,
                        source=clip_source,
                    )
                    row = db.get(ContentPost, session.post_id)
                    if row is None or row.project_id != project_id:
                        return _err("The video post disappeared while attaching — re-draft and retry.")
                    row.post_type = PostType.VIDEO
                    row.video_url = asset.url
                    row.video_asset_id = asset.asset_id
                    row.video_prompt = motion_prompt
                    row.video_duration_seconds = total_duration
                    row.video_aspect_ratio = aspect_ratio
                    if keyframe_asset_id is not None:
                        row.source_image_asset_id = keyframe_asset_id
                    # Record the clip on its beat too, when beat-scoped.
                    if beat_id:
                        beats = list(row.video_storyboard or [])
                        for i, b in enumerate(beats):
                            if isinstance(b, dict) and str(b.get("beat_id")) == beat_id:
                                b = dict(b)
                                b["clip_url"] = asset.url
                                beats[i] = b
                                row.video_storyboard = beats
                                break
                    row.updated_at = datetime.now(timezone.utc)
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    logger.info("content: Veo clip %s attached to post %s", asset.asset_id, row.id)
                    await emit({
                        "event": ContentEvent.POST_DRAFT_UPDATED,
                        "session_id": session.session_id,
                        "post_id": str(row.id),
                        "payload": _build_post_payload(row),
                    })
                    return _ok_model(AttachPostVideoResult(
                        post_id=str(row.id),
                        video_asset_id=str(asset.asset_id),
                        video_url=asset.url,
                        duration_seconds=duration_seconds,
                    ))
        except Exception:
            logger.exception("generate_video_clip failed")
            return _err("Generating the clip hit a snag — please try again.")

    # Publishing + metrics are UI/REST-driven (PublishModal → POST /publish;
    # board → /mark-posted; metrics → /sync-metrics + /sync-daily). The agent
    # surface is creation + review only, so the publish_post / mark_posted /
    # log_metrics tools were removed — the routes in routes/content.py are the
    # single source of truth. render_slide stays: it's the agent's eyes, not a
    # publish path.

    @tool(
        name="render_slide",
        description=(
            "Rasterize ONE slide to a 1080×1920 (9:16) PNG and SEE it — the "
            "COMPOSED slide as it will actually look (caption overlay, gradient, "
            "layout, safe zones), not just the raw photo. Returns the image inline "
            "so you can critique composition, caption legibility, text/face "
            "overlap, and safe-zone fit, then fix the structured slide. These "
            "composed renders are also what gets published. Needs a "
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
                row, err = _require_post(db, project_id, session.post_id)
                if err:
                    return err
                _slide, _idx, err = _require_slide(row, slide_id)
                if err:
                    return err
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
            return _ok_with_images(
                [{"type": "image", "data": _downscale_png_b64(png), "mimeType": "image/png"}],
                RenderSlideResult(
                    slide_id=slide_id, asset_url=asset_url,
                    note="preview downscaled; the full-res render is saved for publishing",
                ),
            )
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
            "type": "object",
            "properties": {
                "post_dir_slug": {"type": "string", "description": "Post slug, e.g. '2026-06-08-001'."},
                "post_id":       {"type": "string", "description": "Post UUID."},
            },
            "required": [],  # pass either, or neither (defaults to the session's current post)
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

    @tool(
        name="fetch_slide_context",
        description=(
            "Pre-assembled context for generating ONE slide's image — call this "
            "right before generate_image for each slide so you never work from "
            "memory. Returns the slide's current image_prompt, the post's "
            "visual_brief, THIS slide's emotional_arc line, the camera_ref_pool + "
            "resolved cameraRef candidates, the locked character asset (slide 1's "
            "image, for the slides 2-5 reference chain), and the role-ordered "
            "suggested input_asset_ids + suggested model for this slide. Use these "
            "so realism, character, and framing stay consistent across the set."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slide_id": {"type": "string", "description": "The slide to fetch context for, e.g. 'slide-03'."},
            },
            "required": ["slide_id"],
        },
    )
    async def fetch_slide_context(args: dict) -> dict:
        try:
            slide_id = (args.get("slide_id") or "").strip()
            if not slide_id:
                return _err("slide_id is required (e.g. 'slide-03').")
            with _open_db() as db:
                post, err = _require_post(db, project_id, session.post_id)
                if err:
                    return err
                slide, idx, err = _require_slide(post, slide_id)
                if err:
                    return err

                # Locked character = slide-1's generated image (the reference every
                # later slide chains from). None until slide 1 is generated.
                character_asset_id = None
                for s in post.slides or []:
                    if isinstance(s, dict) and str(s.get("slide_id")).strip().endswith("01"):
                        character_asset_id = s.get("image_asset_id")
                        break

                camera_refs = _resolve_camera_refs(db, project_id, post.camera_ref_pool or "")
                cam = camera_refs[0]["asset_id"] if camera_refs else None
                is_slide_one = str(slide.get("slide_id")).strip().endswith("01")
                char = str(character_asset_id) if character_asset_id else None
                # Role-ordered ref chain: slide 1 = [cameraRef]; slides 2-5 =
                # [character, cameraRef]. (Collage/before-after cells: pass only
                # the cameraRef per cell — see the image discipline brief.)
                suggested_refs = ([cam] if cam else []) if is_slide_one \
                    else [x for x in (char, cam) if x]

                cur = (slide.get("image_prompt") or "").strip()
                used = (slide.get("image_prompt_used") or "").strip()
                return _ok({
                    "slide_id":            slide_id,
                    "role":                slide.get("role", ""),
                    "kind":                slide.get("kind", "photo"),
                    "headline":            slide.get("headline", ""),
                    "subtext":             slide.get("subtext", ""),
                    "image_prompt":        slide.get("image_prompt", ""),
                    "image_stale":         bool(slide.get("image_url")) and (cur != used),
                    "visual_brief":        post.visual_brief,
                    "emotional_arc_line":  _arc_line_for_slide(post.emotional_arc, slide_id, idx),
                    "camera_ref_pool":     post.camera_ref_pool,
                    "camera_ref_assets":   camera_refs,
                    "character_asset_id":  char,
                    "suggested_input_asset_ids": suggested_refs,
                    "suggested_model":     "gemini-3-pro-image" if is_slide_one else None,
                })
        except Exception as exc:
            logger.exception("fetch_slide_context failed")
            return _err(f"fetch_slide_context failed: {exc}")

    @tool(
        name="check_post_sanity",
        description=(
            "Run the deterministic pre-publish completeness checks on the current "
            "post (or pass post_id): every slide has a fresh image, the hook + text "
            "slides carry copy, the caption + hashtags exist, and there's no "
            "placeholder text. No side-effects — returns the pass/fail checks so you "
            "know what's incomplete before scoring. Sanity is mechanical; the "
            "subjective quality scoring is yours (submit_assessment)."
        ),
        input_schema={
            "post_id": Annotated[str, "Optional UUID; defaults to the current post in this session."],
        },
    )
    async def check_post_sanity(args: dict) -> dict:
        try:
            pid = (args.get("post_id") or "").strip()
            with _open_db() as db:
                if pid:
                    try:
                        row = db.get(ContentPost, UUID(pid))
                    except ValueError:
                        return _err(f"invalid post_id: {pid}")
                    if row is None or row.project_id != project_id:
                        return _err("post not found for this project.")
                else:
                    row, err = _require_post(db, project_id, session.post_id)
                    if err:
                        return err
                checks = compute_sanity(row.slides or [], row.caption or "", row.hashtags or [])
            passed = sum(1 for c in checks if c.passed)
            return _ok({
                "post_id": str(row.id),
                "passed":  passed,
                "total":   len(checks),
                "checks":  [c.model_dump(mode="json") for c in checks],
            })
        except Exception as exc:
            logger.exception("check_post_sanity failed")
            return _err(f"check_post_sanity failed: {exc}")

    @tool(
        name="submit_assessment",
        description=(
            "Persist + emit the pre-publish review for the current post. Pass your "
            "scored content `markers` — the SIX quality markers, each 0–100 with a "
            "one-line verdict, the why, and the single most valuable fix. This tool "
            "re-runs the deterministic sanity checks, computes the weighted overall "
            "score, and emits PUBLISH_ASSESSMENT to the user's review panel. "
            "Advisory only — it never blocks publishing. Marker ids (score ALL six): "
            "hook_strength, narrative_momentum, save_worthiness, "
            "shareability_resonance, visual_quality, cta_caption_fit."
        ),
        input_schema={
            "markers": Annotated[
                list,
                "List of {id, score (0-100), verdict, why, fix}, one per marker id.",
            ],
            "notes":   Annotated[str, "Optional one-line overall summary."],
            "post_id": Annotated[str, "Optional UUID; defaults to the current post."],
        },
    )
    async def submit_assessment(args: dict) -> dict:
        try:
            raw = args.get("markers") or []
            if not isinstance(raw, list) or not raw:
                return _err("markers is required: a list of {id, score, verdict, why, fix}.")
            try:
                parsed = [ContentMarker.model_validate(m) for m in raw]
            except ValidationError as exc:
                return _err(f"marker validation failed: {exc}")
            markers = apply_marker_metadata(parsed)
            if not markers:
                return _err(f"no recognised marker ids; expected from: {', '.join(MARKER_IDS)}.")

            # Signal partial coverage rather than silently scoring on a subset.
            missing = [mid for mid in MARKER_IDS if mid not in {m.id for m in markers}]
            note = (args.get("notes") or "").strip()
            if missing:
                note = (
                    f"Only {len(markers)}/{len(MARKER_IDS)} markers scored "
                    f"(missing: {', '.join(missing)}). {note}"
                ).strip()

            pid = (args.get("post_id") or "").strip()
            with _open_db() as db:
                if pid:
                    try:
                        row = db.get(ContentPost, UUID(pid))
                    except ValueError:
                        return _err(f"invalid post_id: {pid}")
                    if row is None or row.project_id != project_id:
                        return _err("post not found for this project.")
                else:
                    row, err = _require_post(db, project_id, session.post_id)
                    if err:
                        return err
                sanity = compute_sanity(row.slides or [], row.caption or "", row.hashtags or [])
                overall, content_score, band = compute_overall(markers, sanity)
                assessment = PublishAssessment(
                    post_id=str(row.id),
                    overall=overall,
                    content_score=content_score,
                    band=band,
                    sanity=sanity,
                    markers=markers,
                    sanity_passed=sum(1 for c in sanity if c.passed),
                    sanity_total=len(sanity),
                    notes=note,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                )
                # Persist so the panel survives reload + shows on the detail page.
                row.last_assessment = assessment.model_dump(mode="json")
                db.add(row)
                db.commit()
                post_id_str = str(row.id)

            await emit({
                "event":      ContentEvent.PUBLISH_ASSESSMENT,
                "session_id": session.session_id,
                "post_id":    post_id_str,
                "payload":    assessment.model_dump(mode="json"),
            })
            weakest = min(markers, key=lambda m: m.score)
            summary = (
                f"Pre-publish review: {overall}/100 ({band}). "
                f"Sanity {assessment.sanity_passed}/{assessment.sanity_total}. "
                f"Weakest: {weakest.label} ({weakest.score}) — "
                f"{weakest.fix or weakest.verdict}"
            ).strip()
            return _ok(summary)
        except Exception as exc:
            logger.exception("submit_assessment failed")
            return _err(f"submit_assessment failed: {exc}")

    return create_sdk_mcp_server(
        "duct_content",
        tools=[
            submit_post_draft,
            edit_slide,
            fetch_brand_context,
            fetch_topic_bank,
            fetch_format_library,
            fetch_avatar_library,
            fetch_content_history,
            fetch_content_assets,
            fetch_post,
            fetch_slide_context,
            render_slide,
            generate_image,
            edit_image,
            attach_post_video,
            understand_video,
            generate_video_clip,
            check_post_sanity,
            submit_assessment,
        ],
    )
