"""The Content Studio agent's tools, bound for the LangChain (V1) harness.

Three groups:
  - Writers: submit_plan, submit_post_draft, edit_slide — validate Pydantic,
    upsert DB rows, emit SSE events (PLAN_GENERATED / POST_DRAFT_UPDATED).
  - Readers: fetch_brand_context, fetch_topic_bank, fetch_format_library,
    fetch_avatar_library, fetch_content_history, fetch_content_assets,
    fetch_discovered_references, fetch_post, fetch_slide_context.
  - Media + publishing: render_slide, generate_image, edit_image,
    publish_post, mark_posted, log_metrics.

This file was the Claude Agent SDK's in-process MCP server until content
moved to V1. The tool *bodies* are what survived the port unchanged — the
ownership guards, the per-post write lock, the image-prompt lock, the
staleness bookkeeping. What changed is only the binding: typed Pydantic
arguments instead of ``args: dict`` against a hand-written JSON schema, and
a JSON string (or a list of content blocks, for images) instead of an MCP
result envelope.

Every handler:
  1. Opens a short-lived DB session, never binding one to the agent lifetime.
  2. Wraps the body in try/except — an uncaught exception propagates out of
     the tool node and ends the run, whereas an error *payload* lets the
     model read the problem and correct course. So failures are returned.
  3. Where appropriate, calls emit(...) to push events into the SSE queue.

``build_content_tools_lc`` is the binder (``agents/core/ports``: a
``ToolBinder``); ``project_id`` is captured in every closure so a tool call
can never reach another project's rows.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.content.results import (
    EditImageResult,
    EditSlideResult,
    GenerateImageResult,
    LogMetricsResult,
    MarkPostedResult,
    RenderSlideResult,
    SubmitPlanResult,
    SubmitPostResult,
)
from sqlmodel import Session, select

from agents.models import DEFAULT_IMAGE_MODEL, AspectRatio, ImageModel
from agents.core.memory_tools import build_memory_tools_lc
from agents.content.events import ContentEvent
from agents.content.schema import (
    ContentSession,
    ContentStatus,
    ContentTool,
    PlanDraft,
    PostDraft,
    Slide,
)
from agents.content.templates import derive_image_prompts, render_slides_html
from service import storage
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


def _ok(payload: dict | list | str) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload, default=str)


def _err(message: str) -> str:
    """Error result the model can react to.

    Returned, not raised: an exception propagates out of the tool node and
    ends the run, whereas a payload lets the model read the problem and retry.
    The shape matches the audit tools' so a transcript reads the same across
    agents.
    """
    return json.dumps({"status": "error", "message": message})


def _open_db() -> Session:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return Session(engine)


# --- Typed result serializers -------------------------------------------------
# Tool results the model reads back are modeled (see results.py) instead of
# hand-built dicts, so field names like `attached_to` / `asset_ids` are typed.

def _ok_model(m: BaseModel) -> str:
    """Success result from a typed model (text-only)."""
    return _ok(m.model_dump(mode="json"))


def _image_block(b64: str, mime: str) -> dict:
    """One image as a LangChain standard content block. ChatAnthropic turns it
    into a base64 image source inside the tool_result; that is how the model
    gets to *see* what it generated."""
    return {"type": "image", "base64": b64, "mime_type": mime}


# --- Relational precondition guards -------------------------------------------
# "post/slide/cell exists on THIS project" is an invariant against live state the
# input schema can't express — so it's a runtime guard returning a hard _err, not
# prose for the model. Shared here to replace the copies that had drifted across
# tools (ownership check ×6, "find slide or list valid ids" ×3). Each returns the
# resolved entity OR an _err-shaped dict; callers use:  x, err = guard(...); if err: return err

def _require_post(db: Session, project_id, post_id) -> tuple[ContentPost | None, str | None]:
    """Resolve the current post for this project, or an _err result."""
    if post_id is None:
        return None, _err("No current post in this session.")
    row = db.get(ContentPost, post_id)
    if row is None or row.project_id != project_id:
        return None, _err(f"Post {post_id} not found for this project.")
    return row, None


def _require_slide(post: ContentPost, slide_id: str) -> tuple[dict | None, int, str | None]:
    """Find a slide on the post by id, or an _err listing the valid ids.

    Returns (slide_dict, index, None) on hit; (None, -1, err) on miss.
    """
    slides = list(post.slides or [])
    for i, s in enumerate(slides):
        if isinstance(s, dict) and str(s.get("slide_id")) == str(slide_id):
            return s, i, None
    valid = [str(s.get("slide_id")) for s in slides if isinstance(s, dict)]
    return None, -1, _err(f"slide_id {slide_id!r} isn't on this post. Use one of: {valid}.")


def _require_item(slide: dict, item_index: int | None) -> str | None:
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
            ContentAsset.asset_type == "reference",
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
    publish_post uploads to TikTok. Returns the public url."""
    fname = f"{slide_id}-{uuid4().hex[:8]}.png"
    key = f"projects/{project_id}/renders/{fname}"
    url = storage.put_image(key, png, "image/png")
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


def build_content_tools_lc(
    project_id: UUID,
    emit: EmitFn,
    session: ContentSession,
    *,
    vision: bool = True,
    remember: bool = True,
) -> list[StructuredTool]:
    """Build the content tools scoped to this session, for ``create_deep_agent``.

    project_id is captured in closures so every tool call is implicitly
    scoped to the user's project — the model cannot leak across projects.
    emit pushes events to the SSE consumer; session lets writers stash IDs
    (e.g. session.plan_id after submit_plan).

    ``vision`` says whether the run's provider accepts image blocks inside a
    tool result. Anthropic does, and the image phase is built on the model
    looking at what it generated; a provider that does not gets the asset
    URL and a note instead of a request its API would reject.

    ``remember=False`` is a session the user asked not to be remembered: it
    gets no memory tools at all, so the agent cannot write what it cannot
    reach.
    """
    # Typed input models for the image tools — the tool's argument schema and
    # the field constraints the model sees in one place (enums from StrEnum so
    # an invalid id can't be passed; ranges via Field). Defined here, not at
    # module top, because the gemini enums pull the google client;
    # service.google.gemini is imported lazily at session-build time.
    from service.google.gemini.schema import EditMode, MaskMode, SubjectType

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
        model: ImageModel = Field(
            DEFAULT_IMAGE_MODEL,
            description=f"Optional image model id; defaults to {DEFAULT_IMAGE_MODEL.value}.",
        )
        aspect_ratio: AspectRatio = Field(
            AspectRatio.PORTRAIT_9_16, description="Optional aspect ratio. Defaults to 9:16 portrait.",
        )
        number_of_images: int = Field(1, ge=1, le=4, description="How many images to generate. Default 1, max 4.")
        negative_prompt: str | None = Field(None, description="Accepted but inert — no current image model supports negative prompting. Put the constraint in the prompt instead.")
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
        edit_mode: EditMode | None = Field(None, description="Accepted but inert — masked/mode-based editing retired with Imagen.")
        mask_asset_id: str | None = Field(None, description="Optional mask asset UUID.")
        mask_mode: MaskMode | None = Field(None, description="Optional mask mode.")
        style_asset_id: str | None = Field(None, description="Optional style reference asset UUID.")
        subject_asset_id: str | None = Field(None, description="Optional subject reference asset UUID.")
        subject_type: SubjectType | None = Field(None, description="Optional subject type.")
        aspect_ratio: AspectRatio | None = Field(None, description="Optional aspect ratio override.")
        number_of_images: int = Field(1, ge=1, le=4, description="How many images to generate (1-4).")
        negative_prompt: str | None = Field(None, description="Accepted but inert — see generate_image.")

    def _image_result(image_blocks: list[dict], m: BaseModel) -> str | list[dict]:
        """Success result for an image tool: the pictures plus the typed
        payload where the provider can look, the payload alone where it
        cannot."""
        if not vision:
            return _ok({**m.model_dump(mode="json"), "preview": "not shown — this model cannot view images in tool results"})
        return [*image_blocks, {"type": "text", "text": m.model_dump_json()}]

    # ----------------------- Argument schemas -----------------------
    # What the model sees. Descriptions live here rather than beside the
    # bodies so a field's meaning is stated once, next to its type.

    # The writers take the real models, not ``dict``: the argument schema is
    # then the contract every provider's model sees in the tool definition
    # and validates against before the body runs. With ``dict`` and a
    # description that only *named* the schema, a model without Claude's
    # prior knowledge of it went looking — grep and ls over the scratch
    # filesystem, then probes at the tool to read the shape off validation
    # errors, two of which persisted as plans.
    class SubmitPlanArgs(BaseModel):
        plan: PlanDraft = Field(description="The plan — the same object emitted in <duct_artifact>.")

    class SubmitPostDraftArgs(BaseModel):
        post: PostDraft = Field(description="The post — the same object emitted in <duct_artifact>.")

    class EditSlideArgs(BaseModel):
        slide_id: str = Field(description="The slide to edit, e.g. 'slide-03'.")
        patch: dict = Field(description="Partial Slide fields to merge (only what changes).")

    class HistoryArgs(BaseModel):
        limit: int = Field(30, ge=1, le=100, description="Max rows to return. Default 30, max 100.")

    class DiscoveredReferencesArgs(BaseModel):
        min_play_count: int = Field(
            10000, ge=0,
            description="Skip posts with fewer plays. Default 10000 (filters out outliers).",
        )
        limit: int = Field(30, ge=1, le=100, description="Max rows to return. Default 30, max 100.")

    class ContentAssetsArgs(BaseModel):
        asset_type: str = Field(
            "",
            description="Optional asset_type filter (e.g. 'generated', 'reference', 'slide_render'). Omit for all types.",
        )
        axis: str = Field(
            "",
            description="Optional reference-axis filter: 'camera' | 'layouts' | 'captions'. Only affects global library references.",
        )
        subtype: str = Field(
            "",
            description="Optional reference-subtype filter (e.g. 'selfie-talking', 'lifestyle', 'closeup'). Only affects global library references.",
        )

    class PublishPostArgs(BaseModel):
        post_id: str = Field(description="UUID of the content_posts row to publish.")
        social_account_ids: list[int] = Field(description="Numeric PostBridge social account IDs (at least one).")
        scheduled_at: str | None = Field(None, description="Optional ISO 8601 timestamp; omit to post now.")
        tiktok_draft: bool = Field(False, description="If true, post lands as a TikTok draft instead of scheduling.")
        allow_uncomposed: bool = Field(
            False,
            description=(
                "Escape hatch: publish single-image slides as their RAW photo when no composed "
                "render exists (captions won't appear). Multi-image slides still require a render. "
                "Default false."
            ),
        )

    class MarkPostedArgs(BaseModel):
        post_id: str = Field(description="UUID of the content_posts row.")
        tiktok_url: str | None = Field(None, description="Optional external URL of the live post.")

    class PostIdArgs(BaseModel):
        post_id: str = Field(description="UUID of the content_posts row.")

    class SlideIdArgs(BaseModel):
        slide_id: str = Field(description="The slide, e.g. 'slide-01'.")

    class FetchPostArgs(BaseModel):
        post_dir_slug: str = Field("", description="Post slug, e.g. '2026-06-08-001'.")
        post_id: str = Field("", description="Post UUID.")

    # ----------------------- Writers -----------------------

    async def submit_plan(plan: PlanDraft | dict) -> str:
        try:
            payload = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
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
                return _ok_model(SubmitPlanResult(plan_id=str(row.id), days=len(draft.days)))
        except Exception as exc:
            logger.exception("submit_plan failed")
            return _err(f"submit_plan failed: {exc}")

    async def submit_post_draft(post: PostDraft | dict) -> str:
        try:
            payload = post if isinstance(post, dict) else post.model_dump(mode="json")
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

    async def edit_slide(slide_id: str, patch: dict) -> str:
        try:
            slide_id = (slide_id or "").strip()
            patch = patch or {}
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

    async def fetch_brand_context() -> str:
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

    async def fetch_topic_bank() -> str:
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

    async def fetch_format_library() -> str:
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

    async def fetch_avatar_library() -> str:
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

    async def fetch_content_history(limit: int = 30) -> str:
        try:
            limit = min(int(limit or 30), 100)
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

    async def fetch_discovered_references(min_play_count: int = 10000, limit: int = 30) -> str:
        try:
            min_plays = int(min_play_count or 10000)
            limit     = min(int(limit or 30), 100)
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

    async def fetch_content_assets(asset_type: str = "", axis: str = "", subtype: str = "") -> str:
        try:
            asset_type = (asset_type or "").strip()
            axis       = (axis or "").strip() or None
            subtype    = (subtype or "").strip() or None
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

    async def generate_image(**args: Any) -> str | list[dict]:
        try:
            from service.google.gemini import (
                GeminiAPIError,
                GeminiImageClient,
                GenerateImageRequest,
                persist_generated_image,
            )
            from service.google.gemini.client import build_multi_reference_prefix

            image_key = session.gemini_api_key
            if not image_key:
                return _err(
                    "Image generation needs a Google Gemini API key. Add one in "
                    "Settings \u2192 Providers, then try again."
                )

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            # slide_id / item_index steer where the result is attached; they're
            # not Gemini params, so pull them out before building the request.
            target_slide_id = str(payload.pop("slide_id", "") or "").strip()
            _ti = payload.pop("item_index", None)
            target_item_index = int(_ti) if _ti not in (None, "") else None

            # Validate the attach target against the live post BEFORE paying for a
            # Gemini call — a bad slide_id/cell is a hard error (with the valid
            # ids), not a silent attached_to:null. Shared guards; see _require_*.
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

                client = GeminiImageClient(image_key)
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
                            "negative_prompt":   request.negative_prompt,
                            "input_asset_ids":   uuid_refs,
                            "input_global_refs": global_refs,
                        },
                        post_id=session.post_id,
                        source="gemini",
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

            image_blocks: list[dict] = []
            for img in images:
                b64, vmime = _downscale_for_vision(img.data, img.mime_type)
                image_blocks.append(_image_block(b64, vmime))
            return _image_result(image_blocks, GenerateImageResult(
                asset_ids=[str(a.asset_id) for a in assets],
                asset_urls=[a.url for a in assets],
                model=request.model.value,
                attached_to=target_slide_id if attached else None,
            ))
        except Exception:
            logger.exception("generate_image failed")
            return _err("Image generation hit a snag — please try again.")

    async def edit_image(**args: Any) -> str | list[dict]:
        try:
            from service.google.gemini import (
                EditImageRequest,
                GeminiAPIError,
                GeminiImageClient,
                persist_generated_image,
            )

            image_key = session.gemini_api_key
            if not image_key:
                return _err(
                    "Image editing needs a Google Gemini API key. Add one in "
                    "Settings \u2192 Providers, then try again."
                )

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

                def _load(ref_id: UUID | None) -> bytes | None:
                    if ref_id is None:
                        return None
                    a = db.get(ContentAsset, ref_id)
                    if a is None or a.project_id != project_id:
                        return None
                    return _load_asset_bytes(a)

                mask_bytes    = _load(request.mask_asset_id)
                style_bytes   = _load(request.style_asset_id)
                subject_bytes = _load(request.subject_asset_id)

                client = GeminiImageClient(image_key)
                try:
                    images = await client.edit_image(
                        request,
                        base_bytes=base_bytes,
                        mask_bytes=mask_bytes,
                        style_bytes=style_bytes,
                        subject_bytes=subject_bytes,
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
                            "edit_mode":         request.edit_mode.value if request.edit_mode else None,
                            "input_asset_id":    str(request.input_asset_id),
                            "mask_asset_id":     str(request.mask_asset_id)    if request.mask_asset_id    else None,
                            "style_asset_id":    str(request.style_asset_id)   if request.style_asset_id   else None,
                            "subject_asset_id":  str(request.subject_asset_id) if request.subject_asset_id else None,
                            "seed":              request.seed,
                            "negative_prompt":   request.negative_prompt,
                        },
                        post_id=session.post_id,
                        source="gemini",
                    )
                    assets.append(asset)

            image_blocks: list[dict] = []
            for img in images:
                b64, vmime = _downscale_for_vision(img.data, img.mime_type)
                image_blocks.append(_image_block(b64, vmime))
            return _image_result(image_blocks, EditImageResult(
                asset_ids=[str(a.asset_id) for a in assets],
                asset_urls=[a.url for a in assets],
                model=request.model.value,
            ))
        except Exception:
            logger.exception("edit_image failed")
            return _err("Image editing hit a snag — please try again.")

    # ----------------------- PostBridge (Phase 4) -----------------------

    async def publish_post(
        post_id: str,
        social_account_ids: list[int],
        scheduled_at: str | None = None,
        tiktok_draft: bool = False,
        allow_uncomposed: bool = False,
    ) -> str:
        try:
            from service.post_bridge import (
                PostBridgeAPIError,
                PostBridgeCreatePostRequest,
                client_for_user,
            )

            post_id_raw = post_id
            raw_ids     = social_account_ids or []
            scheduled_raw  = scheduled_at
            tiktok_draft = bool(tiktok_draft)
            allow_uncomposed = bool(allow_uncomposed)
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
                post, err = _require_post(db, project_id, post_id)
                if err:
                    return err
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
                            data = _load_asset_bytes(asset)
                            if not data:
                                return _err("Some media for this post couldn't be loaded — try regenerating the images.")
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
                    logger.warning("content: publish failed: %s", exc, exc_info=True)
                    return _err(f"Couldn't publish that just now — {exc.error.message or 'please try again shortly'}.")

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

    async def mark_posted(post_id: str, tiktok_url: str | None = None) -> str:
        try:
            post_id_raw = post_id
            if not post_id_raw:
                return _err("post_id is required.")
            post_id = UUID(str(post_id_raw))
            with _open_db() as db:
                post, err = _require_post(db, project_id, post_id)
                if err:
                    return err
                post.status    = "posted"
                post.posted_at = datetime.now(timezone.utc)
                if tiktok_url:
                    post.tiktok_url = str(tiktok_url)
                db.add(post)
                db.commit()
                db.refresh(post)
                return _ok_model(MarkPostedResult(post_id=str(post.id), status=post.status))
        except Exception as exc:
            logger.exception("mark_posted failed")
            return _err(f"mark_posted failed: {exc}")

    async def log_metrics(post_id: str) -> str:
        try:
            from service.post_bridge import PostBridgeAPIError, client_for_user

            post_id_raw = post_id
            if not post_id_raw:
                return _err("post_id is required.")
            post_id = UUID(str(post_id_raw))

            with _open_db() as db:
                post, err = _require_post(db, project_id, post_id)
                if err:
                    return err
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
                            return _err("This post hasn't finished publishing yet — try again in a few minutes.")
                        # Pick the first successful result; fall back to the latest.
                        chosen = next((r for r in results if r.success), results[0])
                        analytics_list = await pb.list_analytics(post_result_id=[chosen.id], limit=1)
                        if not analytics_list:
                            return _err("Analytics for this post haven't synced yet.")
                        analytics = analytics_list[0]
                        daily = await pb.get_analytics_daily(analytics.id)
                except PostBridgeAPIError as exc:
                    logger.warning("content: metrics pull failed: %s", exc, exc_info=True)
                    return _err(f"Couldn't pull metrics just now — {exc.error.message or 'please try again shortly'}.")

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

                return _ok_model(LogMetricsResult(
                    post_id=str(post.id),
                    view_count=analytics.view_count,
                    like_count=analytics.like_count,
                    snapshots=len(daily.snapshots),
                ))
        except Exception as exc:
            logger.exception("log_metrics failed")
            return _err(f"log_metrics failed: {exc}")

    async def render_slide(slide_id: str) -> str | list[dict]:
        try:
            slide_id = (slide_id or "").strip()
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
            return _image_result(
                [_image_block(_downscale_png_b64(png), "image/png")],
                RenderSlideResult(
                    slide_id=slide_id, asset_url=asset_url,
                    note="preview downscaled; the full-res render is saved for publishing",
                ),
            )
        except Exception as exc:
            logger.exception("render_slide failed")
            return _err(f"render_slide failed: {exc}")

    async def fetch_post(post_dir_slug: str = "", post_id: str = "") -> str:
        try:
            slug = (post_dir_slug or "").strip()
            pid = (post_id or "").strip()
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

    async def fetch_slide_context(slide_id: str) -> str:
        try:
            slide_id = (slide_id or "").strip()
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

    # Memory is cross-agent: the content agent remembers the same project the
    # audit agent does, through the same tools in agents/core.
    async def _on_memory(entry: dict) -> None:
        await emit({"event": ContentEvent.MEMORY_WRITTEN, "memory": entry})

    memory_tools = build_memory_tools_lc(
        project_id,
        user_id=getattr(session, "user_id", None),
        conversation_id=getattr(session, "conversation_id", None),
        agent_type="tiktok_studio",
        on_memory=_on_memory,
    ) if remember else []

    def _bind(fn, name: ContentTool, description: str, args_schema=None) -> StructuredTool:
        return StructuredTool.from_function(
            coroutine=fn,
            name=name.value,
            description=description,
            args_schema=args_schema,
        )

    return [
        *memory_tools,
        _bind(
            submit_plan, ContentTool.SUBMIT_PLAN,
            "Persist the monthly content plan. The argument schema is the contract: "
            "an ordered list of days, each with a topic and a pillar. Inserts a "
            "content_plans row scoped to this project and emits PLAN_GENERATED so the "
            "workspace renders it. Call this AFTER emitting <duct_artifact>{\"type\":\"plan\",...}</duct_artifact>.",
            SubmitPlanArgs,
        ),
        _bind(
            submit_post_draft, ContentTool.SUBMIT_POST_DRAFT,
            "Persist a single post draft. The argument schema is the contract; the tool "
            "upserts a content_posts row keyed by (project_id, post_dir_slug), "
            "and emits POST_DRAFT_UPDATED. Call AFTER emitting "
            "<duct_artifact>{\"type\":\"post\",...}</duct_artifact>.",
            SubmitPostDraftArgs,
        ),
        _bind(
            edit_slide, ContentTool.EDIT_SLIDE,
            "Surgically edit ONE slide of the current post WITHOUT re-sending the "
            "whole post. Pass slide_id + a `patch` of only the fields that change "
            "— e.g. {\"caption_style\":\"cap-raw\"}, {\"headline\":\"...\"}, "
            "{\"kind\":\"text\"}, {\"image_prompt\":\"...\"}, or {\"items\":[...]}. "
            "The slide is merged + revalidated, the HTML re-rendered, and "
            "POST_DRAFT_UPDATED emitted. Changing image_prompt marks that image "
            "stale (regenerate to match). Use submit_post_draft for whole-post or "
            "multi-slide changes, or to add / remove / reorder slides.",
            EditSlideArgs,
        ),
        _bind(
            fetch_brand_context, ContentTool.FETCH_BRAND_CONTEXT,
            "Return the current brand context for this project: identity "
            "(name/slug/tagline/url), audience, content_brand JSONB, pillars, "
            "and visual assets. No arguments. Call this FIRST in a new session.",
        ),
        _bind(
            fetch_topic_bank, ContentTool.FETCH_TOPIC_BANK,
            "Return per-pillar topic usage by scanning content_posts. "
            "Each entry: pillar -> { topics_used: [...], last_used_at: ISO|None }. "
            "Use this to decide whether to dispatch research_pillar sub-agents.",
        ),
        _bind(
            fetch_format_library, ContentTool.FETCH_FORMAT_LIBRARY,
            "Return the per-project content formats (name, slug, full JSONB data) "
            "AND resolved_css — the shared base engine CSS plus the format's linked "
            "styles, ready to inline verbatim into the slides <style> block. Do not "
            "write caption/hook/layout CSS yourself; use resolved_css and its classes.",
        ),
        _bind(
            fetch_avatar_library, ContentTool.FETCH_AVATAR_LIBRARY,
            "Return the list of per-project avatars (name + full JSONB data including ref images).",
        ),
        _bind(
            fetch_content_history, ContentTool.FETCH_CONTENT_HISTORY,
            "Return recent posts (default last 30) for de-duplication and "
            "to inform hook variation. Fields: post_dir_slug, pillar, topic, "
            "hook_type, status, posted_at, perf.",
            HistoryArgs,
        ),
        _bind(
            fetch_content_assets, ContentTool.FETCH_CONTENT_ASSETS,
            "Return content assets (generated images, uploads, references) "
            "for this project. Filter by asset_type if provided "
            "(e.g. 'generated', 'logo', 'background', 'reference', 'upload'). "
            "References include the repo-bundled GLOBAL library (camera / "
            "layouts / captions) served from /static/references — narrow it "
            "with the optional axis + subtype filters. A global reference's "
            "`id` is its /static/references/... URL; pass that id straight "
            "into generate_image's input_asset_ids.",
            ContentAssetsArgs,
        ),
        _bind(
            fetch_discovered_references, ContentTool.FETCH_DISCOVERED_REFERENCES,
            "Return TikTok posts the user (or a previous discovery run) saved as "
            "high-performing references. Use this to ground topic / hook / format "
            "decisions in real-world signal — what's actually working in the "
            "target audience's niche right now. Each row carries the post's "
            "engagement counts (play, digg, share, comment, collect), hashtags, "
            "music, author, and the TikTok URL. Filter by min_play_count to "
            "skip the long tail (default 10000).",
            DiscoveredReferencesArgs,
        ),
        _bind(
            fetch_post, ContentTool.FETCH_POST,
            "Return the current persisted state of ONE post — structured slides "
            "(copy + image prompts + any generated image_url), layout, and "
            "metadata. Use this to ground an edit on the live post before "
            "changing a caption/prompt or generating images, especially when "
            "resuming an earlier draft. Pass post_dir_slug or post_id; with "
            "neither, returns this session's current post. Each slide includes "
            "`image_stale` (true = the prompt changed after the image was made, "
            "so the image should be regenerated).",
            FetchPostArgs,
        ),
        _bind(
            fetch_slide_context, ContentTool.FETCH_SLIDE_CONTEXT,
            "Pre-assembled context for generating ONE slide's image — call this "
            "right before generate_image for each slide so you never work from "
            "memory. Returns the slide's current image_prompt, the post's "
            "visual_brief, THIS slide's emotional_arc line, the camera_ref_pool + "
            "resolved cameraRef candidates, the locked character asset (slide 1's "
            "image, for the slides 2-5 reference chain), and the role-ordered "
            "suggested input_asset_ids + suggested model for this slide. Use these "
            "so realism, character, and framing stay consistent across the set.",
            SlideIdArgs,
        ),
        _bind(
            render_slide, ContentTool.RENDER_SLIDE,
            "Rasterize ONE slide to a 1080×1920 (9:16) PNG and SEE it — the "
            "COMPOSED slide as it will actually look (caption overlay, gradient, "
            "layout, safe zones), not just the raw photo. Returns the image inline "
            "so you can critique composition, caption legibility, text/face "
            "overlap, and safe-zone fit, then fix the structured slide. These "
            "composed renders are also what publish_post uploads. Needs a "
            "connected session UI; if none responds it times out — then proceed "
            "on the raw photo + structured data.",
            SlideIdArgs,
        ),
        _bind(
            generate_image, ContentTool.GENERATE_IMAGE,
            "Generate one or more images from a text prompt. "
            "Returns inline image data (so you can see the result) PLUS a stable "
            "asset_url. Defaults: 9:16 portrait, 1 image. Generated images are "
            "saved to the project's media library.",
            GenerateImageInput,
        ),
        _bind(
            edit_image, ContentTool.EDIT_IMAGE,
            "Edit an existing content asset (inpaint, outpaint, bgswap, style transfer, "
            "or free-form Gemini edit). Returns the edited image inline + a stable "
            "asset_url. The original asset is preserved — every edit creates a new "
            "content_assets row.",
            EditImageInput,
        ),
        _bind(
            publish_post, ContentTool.PUBLISH_POST,
            "Publish a saved post via PostBridge. Uploads each slide's COMPOSED "
            "render (caption baked in — call render_slide first) to PostBridge, "
            "creates the post bound to one or more social_account_ids (numeric, "
            "from list_social_accounts), and stores the resulting PostBridge post "
            "id on the content_posts row. By default it refuses slides that have "
            "no render (their captions wouldn't appear).",
            PublishPostArgs,
        ),
        _bind(
            mark_posted, ContentTool.MARK_POSTED,
            "Mark a post as posted (manual flag — use when the user posted "
            "outside of PostBridge). Sets status='posted' and posted_at=now.",
            MarkPostedArgs,
        ),
        _bind(
            log_metrics, ContentTool.LOG_METRICS,
            "Refresh performance metrics for a post from PostBridge. Looks up "
            "the post_result for this post, fetches lifetime + daily analytics, "
            "and merges them into post.perf / post.daily_perf. Requires "
            "post_bridge_post_id set on the row (i.e. publish_post ran first).",
            PostIdArgs,
        ),
    ]
