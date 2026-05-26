"""In-process MCP tools exposed to the Content Marketing Agent.

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

import base64
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic import ValidationError
from sqlmodel import Session, select

from agents.content.events import ContentEvent
from agents.content.schema import (
    ContentSession,
    PlanDraft,
    PostDraft,
)
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


def _asset_disk_path(asset: ContentAsset) -> Path | None:
    """Resolve a ContentAsset.url ('/uploads/...') to its on-disk path under
    config.uploads_dir. Returns None if the URL doesn't map into uploads."""
    cfg = get_configs()
    base = Path(cfg.uploads_dir or "/app/uploads")
    if not asset.url.startswith("/uploads/"):
        return None
    return base / asset.url[len("/uploads/"):]




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
            with _open_db() as db:
                row = ContentPlan(
                    project_id=project_id,
                    name=draft.name or "30-day plan",
                    start_date=draft.start_date,
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
            with _open_db() as db:
                existing = db.exec(
                    select(ContentPost).where(
                        ContentPost.project_id == project_id,
                        ContentPost.post_dir_slug == draft.post_dir_slug,
                    )
                ).first()
                values = {
                    "project_id":      project_id,
                    "plan_id":         session.plan_id,
                    "post_dir_slug":   draft.post_dir_slug,
                    "pillar":          draft.pillar,
                    "topic":           draft.topic,
                    "post_type":       draft.post_type,
                    "format_style":    draft.format_style,
                    "avatar_id":       draft.avatar_id,
                    "slide_count":     draft.slide_count,
                    "status":          "draft",
                    "slides_html":     draft.slides_html,
                    "caption":         draft.caption,
                    "hashtags":        draft.hashtags,
                    "tiktok_title":    draft.tiktok_title,
                    "hook_type":       draft.hook_type,
                    "hook_text":       draft.hook_text,
                    "image_prompts":   [p.model_dump(mode="json") for p in draft.image_prompts],
                    "audio_note":      draft.audio_note or "",
                    "strategic_note":  draft.strategic_note or "",
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
                    "content: post %s upserted (slug=%s, slides=%d)",
                    row.id, row.post_dir_slug, row.slide_count,
                )
                await emit({
                    "event": ContentEvent.POST_DRAFT_UPDATED,
                    "session_id": session.session_id,
                    "post_id": str(row.id),
                    "payload": {
                        "id":              str(row.id),
                        "post_dir_slug":   row.post_dir_slug,
                        "pillar":          row.pillar,
                        "topic":           row.topic,
                        "slide_count":     row.slide_count,
                        "slides_html":     row.slides_html,
                        "caption":         row.caption,
                        "hashtags":        row.hashtags,
                        "hook_type":       row.hook_type,
                        "hook_text":       row.hook_text,
                        "image_prompts":   row.image_prompts,
                        "audio_note":      row.audio_note,
                        "strategic_note":  row.strategic_note,
                        "platforms":       row.platforms,
                        "status":          row.status,
                    },
                })
                return _ok({"post_id": str(row.id), "post_dir_slug": row.post_dir_slug})
        except Exception as exc:
            logger.exception("submit_post_draft failed")
            return _err(f"submit_post_draft failed: {exc}")

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
        description="Return the list of per-project content formats (name, slug, full JSONB data).",
        input_schema={},
    )
    async def fetch_format_library(_args: dict) -> dict:
        try:
            with _open_db() as db:
                rows = db.exec(
                    select(ContentFormat).where(ContentFormat.project_id == project_id)
                ).all()
                return _ok({
                    "formats": [
                        {
                            "id":   str(r.id),
                            "slug": r.slug,
                            "name": r.name,
                            "data": r.data,
                        }
                        for r in rows
                    ]
                })
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
                            "day_index":     r.day_index,
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
            "prompt": Annotated[str, "Image prompt — the alt-text style description from slides_html."],
            "model":  Annotated[str, "Optional image model id; defaults to gemini-3.1-flash-image-preview."],
            "aspect_ratio": Annotated[str, "Optional aspect ratio (e.g. '9:16'). Defaults to portrait."],
            "number_of_images": Annotated[int, "How many images to generate. Default 1, max 4."],
            "negative_prompt":  Annotated[str, "Optional negative prompt (Imagen models only)."],
            "input_asset_id":   Annotated[str, "Optional reference asset UUID (Gemini-class models only)."],
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

            cfg = get_configs()
            if not cfg.gemini_api_key:
                return _err("GEMINI_API_KEY is not configured; image generation unavailable.")
            if not cfg.uploads_enabled:
                return _err("uploads_enabled is false; cannot persist generated images.")

            payload = {k: v for k, v in args.items() if v not in (None, "")}
            payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
            try:
                request = GenerateImageRequest.model_validate(payload)
            except ValidationError as exc:
                return _err(f"generate_image input invalid: {exc}")

            input_bytes: bytes | None = None
            with _open_db() as db:
                if "input_asset_id" in payload and payload["input_asset_id"]:
                    asset = db.get(ContentAsset, UUID(str(payload["input_asset_id"])))
                    if asset is None or asset.project_id != project_id:
                        return _err(f"input_asset_id {payload['input_asset_id']} not found for this project.")
                    p = _asset_disk_path(asset)
                    if p is None or not p.exists():
                        return _err(f"input asset bytes missing on disk: {asset.url}")
                    input_bytes = p.read_bytes()

                client = GeminiImageClient(cfg.gemini_api_key)
                try:
                    images = await client.generate_image(request, input_bytes=input_bytes)
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
                            "input_asset_id":  payload.get("input_asset_id"),
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
            "Publish a saved post via PostBridge. Uploads each generated slide "
            "image to PostBridge, creates the post bound to one or more "
            "social_account_ids (numeric, from list_social_accounts), and "
            "stores the resulting PostBridge post id on the content_posts row."
        ),
        input_schema={
            "post_id":            Annotated[str,       "UUID of the content_posts row to publish."],
            "social_account_ids": Annotated[list[int], "Numeric PostBridge social account IDs."],
            "scheduled_at":       Annotated[str,       "Optional ISO 8601 timestamp; omit to post now."],
            "tiktok_draft":       Annotated[bool,      "If true, post lands as a TikTok draft instead of scheduling."],
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

                # Gather the image assets we plan to upload (in slide order).
                asset_rows = db.execute(
                    select(ContentAsset)
                    .where(ContentAsset.post_id == post.id, ContentAsset.project_id == post.project_id)
                    .order_by(ContentAsset.created_at)
                ).scalars().all()
                if not asset_rows:
                    return _err("No image assets linked to this post — generate or upload images first.")

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

    return create_sdk_mcp_server(
        "duct_content",
        tools=[
            submit_plan,
            submit_post_draft,
            fetch_brand_context,
            fetch_topic_bank,
            fetch_format_library,
            fetch_avatar_library,
            fetch_content_history,
            fetch_content_assets,
            generate_image,
            edit_image,
            publish_post,
            mark_posted,
            log_metrics,
        ],
    )
