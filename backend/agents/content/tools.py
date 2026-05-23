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

import json
import logging
from collections.abc import Awaitable, Callable
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


def _stub(name: str) -> dict:
    return _err(
        f"{name} is not implemented yet — available in Phase 4 (PostBridge) "
        "or Phase 4b (Gemini image generation). Continue with the workflow "
        "without this tool for now; the user can run image generation and "
        "publishing from the Library / Publish modal UI."
    )


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

    # ----------------------- Stubs (Phase 4 / 4b) -----------------------

    @tool(
        name="generate_image",
        description="Stub — image generation lands in Phase 4b (Gemini service).",
        input_schema={
            "prompt": Annotated[str, "Image prompt (will be used in Phase 4b)."],
        },
    )
    async def generate_image(_args: dict) -> dict:
        return _stub("generate_image")

    @tool(
        name="edit_image",
        description="Stub — image editing lands in Phase 4b (Gemini service).",
        input_schema={
            "prompt": Annotated[str, "Edit prompt (will be used in Phase 4b)."],
        },
    )
    async def edit_image(_args: dict) -> dict:
        return _stub("edit_image")

    @tool(
        name="publish_post",
        description="Stub — PostBridge publishing lands in Phase 4.",
        input_schema={
            "post_id": Annotated[str, "Post UUID to publish (will be used in Phase 4)."],
        },
    )
    async def publish_post(_args: dict) -> dict:
        return _stub("publish_post")

    @tool(
        name="mark_posted",
        description="Stub — mark-posted lands in Phase 4 alongside PostBridge.",
        input_schema={
            "post_id": Annotated[str, "Post UUID."],
        },
    )
    async def mark_posted(_args: dict) -> dict:
        return _stub("mark_posted")

    @tool(
        name="log_metrics",
        description="Stub — metric ingest lands in Phase 4 alongside PostBridge.",
        input_schema={
            "post_id": Annotated[str, "Post UUID."],
        },
    )
    async def log_metrics(_args: dict) -> dict:
        return _stub("log_metrics")

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
