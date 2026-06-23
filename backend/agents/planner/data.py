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

from agents.content.schema import PostType
from agents.planner.schema import PlannerConfig
from db.session import get_engine
from models.agent_context import AgentContext
from models.content import ContentPlan, ContentPost, ContentSocialLink
from service.content_metrics import metric_float, metric_int

logger = logging.getLogger(__name__)

AGENT_ID = "content_planner"

# How far back to summarise published-post performance for the strategist.
_PERF_LOOKBACK_LIMIT = 40

# The content types the planner allocates across. Used to flag types that have
# NO history yet (so the planner can seed an exploratory slot to learn). Plain
# string values (not enum members) so dict-key lookups + f-strings render clean.
_ALL_POST_TYPES = tuple(pt.value for pt in PostType)
# Below this post count a type's medians are too thin to trust — the planner
# treats it as "unproven" (worth testing, not yet worth scaling).
_MIN_CONFIDENT_POSTS = 3


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


def _planned_hypotheses(db: Session, project_id: UUID) -> dict[str, dict]:
    """Map each posted post's id → the STRATEGIC BET the plan made for it
    (hook_type / funnel_stage / objective), read from the plan day that produced
    it (day.post_id). Scans all the project's plans (active + archived) so the bet
    survives a re-plan that overwrote the active week. Used to grade which bets
    actually earned completion+saves — not just which content TYPE did."""
    plans = db.exec(
        select(ContentPlan).where(ContentPlan.project_id == project_id)
    ).all()
    out: dict[str, dict] = {}
    for plan in plans:
        for d in (plan.days or []):
            if not isinstance(d, dict):
                continue
            pid = d.get("post_id")
            if not pid:
                continue
            # Later plans win if a post was re-planned; archived weeks fill gaps.
            out[str(pid)] = {
                "hook_type": (d.get("hook_type") or "").strip(),
                "funnel_stage": (d.get("funnel_stage") or "").strip().lower(),
                "objective": (d.get("objective") or "").strip().lower()[:40],
            }
    return out


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
        planned = _planned_hypotheses(db, project_id)

    if not posts:
        return {"total_posted": 0, "posts": [], "by_pillar": {}, "by_type": {}, "top": []}

    rows: list[dict] = []
    saves_by_pillar: dict[str, list[int]] = defaultdict(list)
    views_by_type: dict[str, list[int]] = defaultdict(list)
    completion_by_type: dict[str, list[float]] = defaultdict(list)
    saves_by_type: dict[str, list[int]] = defaultdict(list)
    # Grade the PLAN'S BETS: completion/saves bucketed by the hook_type / funnel /
    # objective the plan chose for each post (not just by content type).
    comp_by: dict[str, dict[str, list[float]]] = {"hook_type": defaultdict(list), "funnel_stage": defaultdict(list), "objective": defaultdict(list)}
    saves_by: dict[str, dict[str, list[int]]] = {"hook_type": defaultdict(list), "funnel_stage": defaultdict(list), "objective": defaultdict(list)}
    for p in posts:
        perf = p.perf or {}
        views = metric_int(perf, "views")
        likes = metric_int(perf, "likes")
        saves = metric_int(perf, "saves")
        comments = metric_int(perf, "comments")
        shares = metric_int(perf, "shares")
        # The signals that matter more than likes (see content strategy research):
        completion = metric_float(perf, "completion_rate")
        save_rate = metric_float(perf, "save_rate")
        profile_visits = metric_int(perf, "profile_visits")
        bio_clicks = metric_int(perf, "bio_link_clicks")
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
        saves_by_type[ptype].append(saves)
        if completion:
            completion_by_type[ptype].append(completion)

        # Bucket the post's outcome by the plan's bet. hook_type falls back to the
        # post's own (so manual/clone posts still count); funnel/objective are
        # plan-only, so they only score posts that were actually planned.
        bet = planned.get(str(p.id)) or {}
        buckets = {
            "hook_type": bet.get("hook_type") or (p.hook_type or "").strip(),
            "funnel_stage": bet.get("funnel_stage") or "",
            "objective": bet.get("objective") or "",
        }
        for dim, val in buckets.items():
            if not val:
                continue
            saves_by[dim][val].append(saves)
            if completion:
                comp_by[dim][val].append(completion)

    by_pillar = {
        pillar: {"posts": len(s), "median_saves": int(median(s)) if s else 0}
        for pillar, s in saves_by_pillar.items()
    }
    by_type = {
        ptype: {
            "posts": len(v),
            "median_views": int(median(v)) if v else 0,
            "median_completion": round(median(completion_by_type[ptype]), 3) if completion_by_type.get(ptype) else None,
            "median_saves": int(median(saves_by_type[ptype])) if saves_by_type.get(ptype) else 0,
        }
        for ptype, v in views_by_type.items()
    }
    # Rank by the conversion-leaning signals first (saves + completion), not likes.
    top = sorted(rows, key=lambda r: (r["saves"], r["completion_rate"], r["views"]), reverse=True)[:5]

    type_performance = _rank_content_types(by_type)

    # Score the plan's STRATEGIC bets: for each dimension (hook_type / funnel /
    # objective), median completion+saves per bucket, ranked so the planner can
    # double down on the angles that earned and trim the ones that didn't.
    def _bucket_summary(dim: str) -> list[dict]:
        out = []
        for val, saves_list in saves_by[dim].items():
            comp_list = comp_by[dim].get(val) or []
            out.append({
                "value": val,
                "posts": len(saves_list),
                "median_completion": round(median(comp_list), 3) if comp_list else None,
                "median_saves": int(median(saves_list)) if saves_list else 0,
            })
        out.sort(key=lambda b: (b["median_completion"] or 0.0, b["median_saves"]), reverse=True)
        return out

    hypothesis_performance = {
        "by_hook_type": _bucket_summary("hook_type"),
        "by_funnel_stage": _bucket_summary("funnel_stage"),
        "by_objective": _bucket_summary("objective"),
    }

    return {
        "total_posted": len(rows),
        "posts": rows[:15],
        "by_pillar": by_pillar,
        "by_type": by_type,
        # Cross-type comparison + an explicit allocation recommendation so the
        # planner can weight content_mix by what's actually working (and seed the
        # types it has no data on). See _rank_content_types.
        "type_performance": type_performance,
        # Grades the plan's OWN bets (hook_type / funnel / objective) by the
        # completion+saves they earned, so the strategist learns strategy, not just
        # format. Buckets carry `posts` so thin samples read as low-confidence.
        "hypothesis_performance": hypothesis_performance,
        "top": top,
        "metric_note": "Optimise for completion_rate + saves + shares + bio_link_clicks, not likes.",
    }


def _rank_content_types(by_type: dict[str, dict]) -> dict:
    """Turn the per-type medians into an explicit, comparative recommendation the
    planner can act on directly (instead of inferring the comparison each turn).

    Ranks types by the conversion-leaning blend (completion first, then saves),
    splits them into PROVEN (enough posts to trust) vs UNPROVEN (too thin), and
    flags types with NO history at all. The guidance string encodes the
    explore+exploit policy: scale the proven leader, but always reserve a slot to
    test an unproven/untested type so a new format (e.g. video) can earn its data.
    """
    def _key(item: tuple[str, dict]) -> tuple[float, int]:
        m = item[1]
        return (m.get("median_completion") or 0.0, m.get("median_saves") or 0)

    ranked = [
        {
            "type": ptype,
            "posts": m.get("posts", 0),
            "median_completion": m.get("median_completion"),
            "median_saves": m.get("median_saves", 0),
            "median_views": m.get("median_views", 0),
            "confidence": "proven" if m.get("posts", 0) >= _MIN_CONFIDENT_POSTS else "unproven",
        }
        for ptype, m in sorted(by_type.items(), key=_key, reverse=True)
    ]
    leader = next((r["type"] for r in ranked if r["confidence"] == "proven"), None)
    unproven = [r["type"] for r in ranked if r["confidence"] == "unproven"]
    untested = [t for t in _ALL_POST_TYPES if t not in by_type]

    to_test = untested + unproven  # untested first — zero data is the biggest blind spot
    if leader and to_test:
        guidance = (
            f"Scale up '{leader}' (best proven completion+saves). Reserve ≥1 slot this week to "
            f"test {to_test} — don't starve a format you have little/no data on (that's how a new "
            f"type like video earns its place)."
        )
    elif leader:
        guidance = f"Scale up '{leader}' (best proven completion+saves); trim chronic underperformers."
    elif to_test:
        guidance = (
            f"Not enough history to crown a winner yet — spread tests across {to_test or list(by_type)} "
            f"and let completion+saves decide next week."
        )
    else:
        guidance = "Not enough history yet — plan a balanced mix and measure completion+saves."

    return {
        "ranked": ranked,
        "leader": leader,
        "untested_types": untested,
        "unproven_types": unproven,
        "guidance": guidance,
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
        views = metric_int(p.perf or {}, "views")
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
        views = metric_int(perf, "views")
        if views <= 0:
            continue
        interactions = (
            metric_int(perf, "likes")
            + metric_int(perf, "comments")
            + metric_int(perf, "shares")
            + metric_int(perf, "saves")
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
