"""DB + PostBridge helpers for the Content Planner agent.

Kept separate from tools.py so the runner can call the same functions at
session start (load config, summarise performance) that the MCP tools expose
to the model mid-session.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from uuid import UUID

from sqlmodel import Session, select

from agents.planner.schema import PlannerConfig
from db.session import get_engine
from models.agent_context import AgentContext
from models.content import ContentPost, ContentSocialLink

logger = logging.getLogger(__name__)

AGENT_ID = "content_planner"

# How far back to summarise published-post performance for the strategist.
_PERF_LOOKBACK_LIMIT = 40


def _open_db() -> Session:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return Session(engine)


# ---------------------------------------------------------------------------
# Planner configuration (agent_contexts)
# ---------------------------------------------------------------------------


def load_planner_config(project_id: UUID) -> PlannerConfig:
    """Read the saved planner config, or an empty config if none exists."""
    with _open_db() as db:
        row = db.exec(
            select(AgentContext).where(
                AgentContext.project_id == project_id,
                AgentContext.agent_id == AGENT_ID,
            )
        ).first()
        data = (row.data if row else None) or {}
    try:
        return PlannerConfig.model_validate(data)
    except Exception as exc:  # tolerate legacy/partial blobs
        logger.warning("planner: config validate failed (%s); using empty", exc)
        return PlannerConfig()


def save_planner_config(project_id: UUID, config: PlannerConfig) -> PlannerConfig:
    """Upsert the planner config onto agent_contexts (project, content_planner)."""
    config.updated_at = datetime.now(timezone.utc)
    blob = config.model_dump(mode="json")
    with _open_db() as db:
        row = db.exec(
            select(AgentContext).where(
                AgentContext.project_id == project_id,
                AgentContext.agent_id == AGENT_ID,
            )
        ).first()
        if row is None:
            row = AgentContext(project_id=project_id, agent_id=AGENT_ID, data=blob)
        else:
            row.data = blob
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
    return config


# ---------------------------------------------------------------------------
# Connected accounts — constrains the platforms the agent may plan for
# ---------------------------------------------------------------------------


def linked_accounts(project_id: UUID) -> list[dict]:
    """The project's selected social accounts (one per platform handle)."""
    with _open_db() as db:
        rows = db.exec(
            select(ContentSocialLink).where(ContentSocialLink.project_id == project_id)
        ).all()
    return [
        {"platform": r.platform, "username": r.username, "account_id": r.external_account_id}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Published-post performance summary — what's working, to inform the plan
# ---------------------------------------------------------------------------


def _num(perf: dict, *keys: str) -> int:
    for k in keys:
        v = perf.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return 0


def _flt(perf: dict, *keys: str) -> float:
    for k in keys:
        v = perf.get(k)
        if isinstance(v, (int, float)):
            return round(float(v), 3)
    return 0.0


def performance_summary(project_id: UUID) -> dict:
    """Compact summary of recent published-post metrics, grouped by pillar and
    content type, plus the top performers. Reads already-synced perf/daily_perf
    (populated by PostBridge sync + manual logging) — never calls PostBridge.
    """
    with _open_db() as db:
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.posted_at.is_not(None))
            .order_by(ContentPost.posted_at.desc())
            .limit(_PERF_LOOKBACK_LIMIT)
        ).all()

    if not posts:
        return {"total_posted": 0, "posts": [], "by_pillar": {}, "by_type": {}, "top": []}

    rows: list[dict] = []
    saves_by_pillar: dict[str, list[int]] = defaultdict(list)
    views_by_type: dict[str, list[int]] = defaultdict(list)
    completion_by_type: dict[str, list[float]] = defaultdict(list)
    for p in posts:
        perf = p.perf or {}
        views = _num(perf, "view_count", "views")
        likes = _num(perf, "like_count", "likes")
        saves = _num(perf, "save_count", "saves")
        comments = _num(perf, "comment_count", "comments")
        shares = _num(perf, "share_count", "shares")
        # The signals that matter more than likes (see content strategy research):
        completion = _flt(perf, "completion_rate")
        save_rate = _flt(perf, "save_rate")
        profile_visits = _num(perf, "profile_visits")
        bio_clicks = _num(perf, "bio_link_clicks")
        pillar = p.pillar or "(none)"
        ptype = p.post_type or "slideshow"
        rows.append({
            "id": str(p.id),
            "topic": p.topic or "",
            "pillar": pillar,
            "post_type": ptype,
            "platforms": list(p.platforms or []),
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "views": views, "likes": likes, "saves": saves,
            "comments": comments, "shares": shares,
            "completion_rate": completion, "save_rate": save_rate,
            "profile_visits": profile_visits, "bio_link_clicks": bio_clicks,
        })
        saves_by_pillar[pillar].append(saves)
        views_by_type[ptype].append(views)
        if completion:
            completion_by_type[ptype].append(completion)

    by_pillar = {
        pillar: {"posts": len(s), "median_saves": int(median(s)) if s else 0}
        for pillar, s in saves_by_pillar.items()
    }
    by_type = {
        ptype: {
            "posts": len(v),
            "median_views": int(median(v)) if v else 0,
            "median_completion": round(median(completion_by_type[ptype]), 3) if completion_by_type.get(ptype) else None,
        }
        for ptype, v in views_by_type.items()
    }
    # Rank by the conversion-leaning signals first (saves + completion), not likes.
    top = sorted(rows, key=lambda r: (r["saves"], r["completion_rate"], r["views"]), reverse=True)[:5]

    return {
        "total_posted": len(rows),
        "posts": rows[:15],
        "by_pillar": by_pillar,
        "by_type": by_type,
        "top": top,
        "metric_note": "Optimise for completion_rate + saves + shares + bio_link_clicks, not likes.",
    }


# ---------------------------------------------------------------------------
# Data-driven best-time — this account's own posting history (#7)
# ---------------------------------------------------------------------------

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def posting_time_analysis(project_id: UUID) -> dict:
    """Rank this account's historical posting windows by performance, so the
    planner picks best-times from OWN data rather than generic charts. Buckets
    published posts by (weekday, hour) of posted_at and ranks by average views.
    Returns {"windows": [...], "note": ...}; empty windows when history is thin.
    """
    with _open_db() as db:
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.posted_at.is_not(None))
            .limit(200)
        ).all()

    samples: dict[tuple[int, int], list[int]] = defaultdict(list)
    for p in posts:
        if not p.posted_at:
            continue
        views = _num(p.perf or {}, "view_count", "views")
        samples[(p.posted_at.weekday(), p.posted_at.hour)].append(views)

    total = sum(len(v) for v in samples.values())
    if total < 5:
        return {"windows": [], "note": "Not enough posting history yet — use trends + geography to pick times."}

    windows = [
        {
            "weekday": _WEEKDAYS[wd],
            "hour_utc": hr,
            "posts": len(vs),
            "avg_views": int(sum(vs) / len(vs)) if vs else 0,
        }
        for (wd, hr), vs in samples.items()
    ]
    windows.sort(key=lambda w: (w["avg_views"], w["posts"]), reverse=True)
    return {
        "windows": windows[:6],
        "note": "Best windows from this account's own history (hours in UTC — convert to the audience's geography).",
    }


# ---------------------------------------------------------------------------
# Bulk PostBridge refresh — the functional core behind /refresh-posts
# ---------------------------------------------------------------------------


async def sync_all_posts(project_id: UUID) -> dict:
    """Refresh perf + daily_perf for every published project post from PostBridge.

    Mirrors the per-post /sync-metrics + /sync-daily routes, looped over the
    project's posts. Per-post failures are swallowed so one bad post can't abort
    the batch. Returns a small summary the agent can relay.
    """
    from service.post_bridge import PostBridgeAPIError, client_for_user

    synced = 0
    skipped = 0
    failed = 0
    with _open_db() as db:
        from models.project import Project

        proj = db.get(Project, project_id)
        if proj is None:
            return {"error": "project not found"}
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.post_bridge_post_id.is_not(None))
        ).all()
        if not posts:
            return {"synced": 0, "skipped": 0, "failed": 0, "note": "no published posts to sync"}

        try:
            client = client_for_user(proj.user_id, db)
        except ValueError as exc:
            return {"error": f"publishing not connected: {exc}"}

        try:
            async with client as pb:
                try:
                    await pb.sync_analytics()
                except PostBridgeAPIError as exc:
                    logger.warning("planner: sync_analytics failed: %s", exc)
                for post in posts:
                    if not post.post_bridge_post_id:
                        skipped += 1
                        continue
                    try:
                        results = await pb.list_post_results(post_id=post.post_bridge_post_id, limit=10)
                        if not results:
                            skipped += 1
                            continue
                        chosen = next((r for r in results if r.success), results[0])
                        analytics_list = await pb.list_analytics(post_result_id=[chosen.id], limit=1)
                        if not analytics_list:
                            skipped += 1
                            continue
                        analytics = analytics_list[0]
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
                        try:
                            daily = await pb.get_analytics_daily(analytics.id)
                            post.daily_perf = [s.model_dump(mode="json") for s in daily.snapshots]
                        except PostBridgeAPIError:
                            pass  # daily is best-effort
                        # Commit per post so the reported `synced` count reflects
                        # what was actually persisted — one failing commit (or an
                        # outer PostBridge error later) can't roll back the rest.
                        db.add(post)
                        db.commit()
                        synced += 1
                    except PostBridgeAPIError as exc:
                        logger.warning("planner: sync failed for post %s: %s", post.id, exc)
                        db.rollback()
                        failed += 1
                    except Exception as exc:
                        logger.warning("planner: db write failed for post %s: %s", post.id, exc)
                        db.rollback()
                        failed += 1
        except PostBridgeAPIError as exc:
            return {"error": f"PostBridge error: {exc}", "synced": synced, "failed": failed}

    return {"synced": synced, "skipped": skipped, "failed": failed}


def performance_baseline(project_id: UUID) -> dict:
    """The project's OWN posted-post baseline for Discover's "you vs niche"
    overlay. Engagement is computed the SAME way as the scraped niche —
    (likes + comments + shares + saves) / views — so the comparison is
    apples-to-apples. Returns median engagement (directional, not stat-sig) +
    the format mix. Empty (post_count=0) on cold start so the UI can degrade.
    """
    with _open_db() as db:
        posts = db.exec(
            select(ContentPost)
            .where(ContentPost.project_id == project_id)
            .where(ContentPost.posted_at.is_not(None))
            .order_by(ContentPost.posted_at.desc())
            .limit(_PERF_LOOKBACK_LIMIT)
        ).all()

    engs: list[float] = []
    fmt: dict[str, int] = defaultdict(int)
    for p in posts:
        perf = p.perf or {}
        fmt[p.post_type or "slideshow"] += 1
        views = _num(perf, "view_count", "views")
        if views <= 0:
            continue
        interactions = (
            _num(perf, "like_count", "likes")
            + _num(perf, "comment_count", "comments")
            + _num(perf, "share_count", "shares")
            + _num(perf, "save_count", "saves")
        )
        engs.append(interactions / views)

    return {
        "post_count": len(posts),
        "engagement": round(median(engs), 4) if engs else 0.0,
        "engagement_sample": len(engs),
        "format_mix": dict(fmt),
    }


__all__ = [
    "AGENT_ID",
    "linked_accounts",
    "load_planner_config",
    "performance_baseline",
    "performance_summary",
    "save_planner_config",
    "sync_all_posts",
]
