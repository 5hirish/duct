"""In-process MCP tools for the Content Planner agent (server ``duct_planner``).

Every handler opens a short-lived DB session, wraps its body in try/except
(uncaught exceptions stop the agent loop), and returns is_error=true text on
failure so the model can correct course. submit_plan additionally emits
PLAN_GENERATED so the workspace renders the plan.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import date as _date
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from pydantic import ValidationError

from agents.content.events import ContentEvent
from agents.content.schema import PlanDraft
from agents.planner import data as _data
from agents.planner.schema import PlannerConfig, PlannerSession
from db.session import get_engine
from models.content import ContentPlan
from service.discovery import query_discovered_references, saved_reference_urls
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


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


def build_planner_mcp_server(
    project_id: UUID,
    emit: EmitFn,
    session: PlannerSession,
) -> McpSdkServerConfig:
    """Build the in-process MCP server scoped to this planner session.

    project_id is captured in closures so every tool is implicitly scoped to the
    user's project. emit pushes SSE events; session lets submit_plan stash plan_id.
    """

    # ----------------------- Writer -----------------------

    @tool(
        name="submit_plan",
        description=(
            "Persist the canonical rolling 7-day content plan. Validates the "
            "payload against the PlanDraft schema, upserts the project's ACTIVE "
            "content_plans row (updates in place if one exists — never deletes "
            "other plans), and emits PLAN_GENERATED so the timeline renders. "
            "Call AFTER emitting <duct_report>{\"type\":\"plan\",...}</duct_report>."
        ),
        input_schema={
            "plan": Annotated[
                dict,
                "JSON object matching the PlanDraft schema (type='plan', 7 days, strategy).",
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
            start = draft.start_date or _date.today()
            label = start.strftime("week of %b %d")
            strategy_json = draft.strategy.model_dump(mode="json")
            character_json = draft.character.model_dump(mode="json")
            with _open_db() as db:
                # True receipts: drop any plan evidence whose URL isn't an
                # actually-saved discovery, so citations can't be fabricated.
                saved_urls = saved_reference_urls(db, project_id)
                for d in draft.days:
                    if d.evidence:
                        d.evidence = [
                            e for e in d.evidence
                            if e.tiktok_url and e.tiktok_url in saved_urls
                        ]
                days_json = [d.model_dump(mode="json") for d in draft.days]
                # Rolling plan: refresh the existing ACTIVE plan in place so the
                # canonical plan keeps one stable row; other plans are untouched.
                row = db.exec(
                    select(ContentPlan)
                    .where(ContentPlan.project_id == project_id)
                    .where(ContentPlan.status == "active")
                    .order_by(ContentPlan.updated_at.desc())
                ).first()
                if row is None:
                    row = ContentPlan(
                        project_id=project_id,
                        name=draft.name or label,
                        start_date=start,
                        character=character_json,
                        days=days_json,
                        strategy=strategy_json,
                        status="active",
                    )
                    db.add(row)
                else:
                    row.name = draft.name or label
                    row.start_date = start
                    row.character = character_json
                    row.days = days_json
                    row.strategy = strategy_json
                    row.status = "active"
                    row.updated_at = datetime.now(timezone.utc)
                    db.add(row)
                db.commit()
                db.refresh(row)
                # Enforce one canonical active plan: demote any other active rows
                # (e.g. from a rare concurrent first-create race) to "archived" so
                # the board never shows two. Non-destructive — rows are kept.
                dupes = db.exec(
                    select(ContentPlan)
                    .where(ContentPlan.project_id == project_id)
                    .where(ContentPlan.status == "active")
                    .where(ContentPlan.id != row.id)
                ).all()
                if dupes:
                    for d in dupes:
                        d.status = "archived"
                        db.add(d)
                    db.commit()
                session.plan_id = row.id
                logger.info("planner: active plan %s persisted (%d days)", row.id, len(draft.days))
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
                        "strategy": row.strategy,
                        "status": row.status,
                    },
                })
                return _ok({"plan_id": str(row.id), "days": len(draft.days), "status": "active"})
        except Exception as exc:
            logger.exception("planner submit_plan failed")
            return _err(f"submit_plan failed: {exc}")

    # ----------------------- Readers -----------------------

    @tool(
        name="fetch_brand_context",
        description=(
            "Re-read the project's brand snapshot (audience, pillars, voice, "
            "value prop, visual identity). Use to refresh context on long runs."
        ),
        input_schema={},
    )
    async def fetch_brand_context(args: dict) -> dict:
        try:
            from agents.content.v3.runner import _load_brand_context

            brand = _load_brand_context(project_id)
            return _ok(brand.model_dump(mode="json"))
        except Exception as exc:
            logger.exception("planner fetch_brand_context failed")
            return _err(f"fetch_brand_context failed: {exc}")

    @tool(
        name="fetch_discovered_references",
        description=(
            "Return TikTok posts the user saved from the Discover feature as "
            "high-performing references — real signal for what's already working "
            "in this audience's niche. Each row carries engagement counts (play, "
            "digg, share, comment, collect), hashtags, music, author, and the "
            "tiktok_url + asset_id. Ground topic/hook/format choices in these and "
            "cite the tiktok_url. Filter the long tail with min_play_count "
            "(default 10000)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "min_play_count": {
                    "type": "integer", "minimum": 0,
                    "description": "Skip posts with fewer plays. Default 10000.",
                },
                "limit": {
                    "type": "integer", "minimum": 1, "maximum": 100,
                    "description": "Max rows to return. Default 30, max 100.",
                },
            },
            "required": [],
        },
    )
    async def fetch_discovered_references(args: dict) -> dict:
        try:
            min_plays = int(args.get("min_play_count") or 10000)
            limit     = min(int(args.get("limit") or 30), 100)
            with _open_db() as db:
                items = query_discovered_references(
                    db, project_id, min_plays=min_plays, limit=limit
                )
            return _ok({"references": items, "count": len(items)})
        except Exception as exc:
            logger.exception("planner fetch_discovered_references failed")
            return _err(f"fetch_discovered_references failed: {exc}")

    @tool(
        name="fetch_planner_config",
        description=(
            "Read the saved planner configuration (platforms, posts_per_day, "
            "geographies, primary_objective, cta_destination, upcoming, audience "
            "fields) AND the project's connected social accounts. Constrain "
            "platform choices to the connected accounts."
        ),
        input_schema={},
    )
    async def fetch_planner_config(args: dict) -> dict:
        try:
            config = _data.load_planner_config(project_id)
            accounts = _data.linked_accounts(project_id)
            return _ok({
                "config": config.model_dump(mode="json"),
                "is_complete": config.is_complete(),
                "connected_accounts": accounts,
            })
        except Exception as exc:
            logger.exception("planner fetch_planner_config failed")
            return _err(f"fetch_planner_config failed: {exc}")

    @tool(
        name="save_planner_config",
        description=(
            "Persist the planner configuration. Call after the user picks "
            "platforms, posting cadence (posts/day), 1-3 geographies, and the "
            "primary objective (plus any optional CTA / upcoming / audience info)."
        ),
        input_schema={
            "platforms": Annotated[list, "Platform ids to plan for, e.g. ['tiktok','instagram'] (from connected accounts)."],
            "posts_per_day": Annotated[int, "How many posts per day (1-10; default 1)."],
            "geographies": Annotated[list, "1-3 priority geographies, e.g. ['United States','India']."],
            "primary_objective": Annotated[str, "Primary objective: awareness | followers | saves | website_traffic | trial_signups | sales."],
            "cta_destination": Annotated[str, "Where the bio link / offer points (conversion posts). Optional."],
            "upcoming": Annotated[str, "Launches / promos / events / seasonal moments to plan around. Optional."],
            "audience_pains": Annotated[str, "Audience pains. Optional."],
            "audience_desires": Annotated[str, "Audience desires. Optional."],
            "audience_objections": Annotated[str, "Audience objections. Optional."],
            "posting_times": Annotated[dict, "Optional platform -> preferred local time note."],
        },
    )
    async def save_planner_config(args: dict) -> dict:
        try:
            payload = {
                "platforms": args.get("platforms") or [],
                "posts_per_day": args.get("posts_per_day") or 1,
                "geographies": args.get("geographies") or [],
                "primary_objective": args.get("primary_objective") or "",
                "cta_destination": args.get("cta_destination") or "",
                "upcoming": args.get("upcoming") or "",
                "audience_pains": args.get("audience_pains") or "",
                "audience_desires": args.get("audience_desires") or "",
                "audience_objections": args.get("audience_objections") or "",
                "posting_times": args.get("posting_times") or {},
            }
            try:
                config = PlannerConfig.model_validate(payload)
            except ValidationError as exc:
                return _err(f"PlannerConfig validation failed: {exc}")
            if not config.platforms:
                return _err("At least one platform is required (use a connected account).")
            if not config.geographies:
                return _err("At least one geography is required (max 3).")
            if not config.primary_objective:
                return _err("A primary_objective is required (e.g. awareness / followers / saves / trial_signups / sales).")
            saved = _data.save_planner_config(project_id, config)
            return _ok({"saved": True, "config": saved.model_dump(mode="json")})
        except Exception as exc:
            logger.exception("planner save_planner_config failed")
            return _err(f"save_planner_config failed: {exc}")

    @tool(
        name="fetch_post_metrics",
        description=(
            "Summarise recent published-post performance (per pillar, per content "
            "type, plus top performers) from already-synced metrics. Read-only — "
            "use sync_all_posts first if you need fresh numbers."
        ),
        input_schema={},
    )
    async def fetch_post_metrics(args: dict) -> dict:
        try:
            return _ok(_data.performance_summary(project_id))
        except Exception as exc:
            logger.exception("planner fetch_post_metrics failed")
            return _err(f"fetch_post_metrics failed: {exc}")

    @tool(
        name="sync_all_posts",
        description=(
            "Refresh metrics for every published post from PostBridge (the "
            "engine behind the /refresh-posts command). Updates perf + daily "
            "snapshots, then fetch_post_metrics returns the fresh numbers."
        ),
        input_schema={},
    )
    async def sync_all_posts(args: dict) -> dict:
        try:
            result = await _data.sync_all_posts(project_id)
            return _ok(result)
        except Exception as exc:
            logger.exception("planner sync_all_posts failed")
            return _err(f"sync_all_posts failed: {exc}")

    return create_sdk_mcp_server(
        "duct_planner",
        tools=[
            submit_plan,
            fetch_brand_context,
            fetch_discovered_references,
            fetch_planner_config,
            save_planner_config,
            fetch_post_metrics,
            sync_all_posts,
        ],
    )


__all__ = ["build_planner_mcp_server"]
