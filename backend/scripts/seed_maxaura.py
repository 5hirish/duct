"""Dev seed script — populate MaxAura content data from nomadapps/marketing/.

Reads:
  /home/user/nomadapps/marketing/apps.json
  /home/user/nomadapps/marketing/maxaura/tiktok/thirty_day_plan.json
  /home/user/nomadapps/marketing/maxaura/tiktok/formats.json
  /home/user/nomadapps/marketing/maxaura/tiktok/avatars.json
  /home/user/nomadapps/marketing/maxaura/tiktok/posts/<dir>/meta.json
  /home/user/nomadapps/marketing/maxaura/tiktok/posts/<dir>/slides.html

Writes:
  users                — one row, email=test+maxaura@getduct.ai
  projects             — one row, slug=maxaura, with content_brand /
                         content_pillars / content_visual_assets populated
                         from apps.json
  content_plans        — one row per app, days[] = full 30-day plan
  content_posts        — one row per posts/<dir>/, slides_html inlined
                         from the .html file. PNG/JPEG binaries are NOT
                         migrated (Phase 4b's generate_image tool can
                         regenerate any image on demand).
  content_formats      — one row per formats.json item
  content_avatars      — one row per avatars.json item

Usage:
  cd backend && poetry run python -m scripts.seed_maxaura
    [--source /path/to/marketing] [--email shirishkadam35@gmail.com]
    [--reset] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

logger = logging.getLogger(__name__)


_DEFAULT_SOURCE_DIR = "/home/user/nomadapps/marketing"
_DEFAULT_EMAIL      = "test+maxaura@getduct.ai"


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        level=logging.INFO,
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict | list:
    with path.open() as fh:
        return json.load(fh)


def _read_text(path: Path) -> str:
    with path.open() as fh:
        return fh.read()


def _load_app(source: Path, app_id: str = "maxaura") -> dict:
    apps = _read_json(source / "apps.json").get("apps", [])
    matches = [a for a in apps if a.get("id") == app_id]
    if not matches:
        raise SystemExit(f"App {app_id!r} not found in {source / 'apps.json'}")
    return matches[0]


# ---------------------------------------------------------------------------
# Project payload builders
# ---------------------------------------------------------------------------


def _build_content_brand(app_ctx: dict) -> dict:
    ctx = app_ctx.get("context", {}) or {}
    brand = ctx.get("brand",  {}) or {}
    vp    = ctx.get("valueProp", {}) or {}
    aud   = ctx.get("audience",  {}) or {}
    goal  = ctx.get("contentGoal", {}) or {}

    voice_words = brand.get("voice") or []
    voice = ", ".join(voice_words) if isinstance(voice_words, list) else str(voice_words)

    age_min = aud.get("ageMin")
    age_max = aud.get("ageMax")
    audience_str = aud.get("persona") or ""
    if age_min is not None and age_max is not None:
        audience_str = f"{audience_str} ({aud.get('gender', '')}, age {age_min}-{age_max})".strip()

    features = app_ctx.get("features") or []

    return {
        "audience":     audience_str,
        "brand_voice":  voice,
        "tone":         brand.get("tone", ""),
        "do_say":       brand.get("doSay", ""),
        "do_not_say":   brand.get("doNotSay", ""),
        "sounds_like":  brand.get("soundsLike", ""),
        "value_prop":   vp.get("differentiator") or vp.get("transformation") or "",
        "content_goal": goal.get("ctaText") or goal.get("goalType") or "",
        "cta_url":      goal.get("ctaUrl", ""),
        "pricing":      vp.get("pricing", ""),
        "proof_points": vp.get("proofPoints", []),
        "pain_point":   aud.get("painPoint", ""),
        "aspiration":   aud.get("aspiration", ""),
        "features":     features,
    }


def _build_content_pillars(app_ctx: dict) -> dict:
    """Project.content_pillars is JSONB-typed but we use the conventional
    {items: [...]} envelope so the orchestrator's loader picks it up."""
    features = app_ctx.get("features") or []
    items = [
        {
            "id":          f["id"],
            "name":        f["name"],
            "description": f.get("description", ""),
        }
        for f in features
        if isinstance(f, dict) and "id" in f
    ]
    # Confidence_arc is a recurring pillar in the source thirty_day_plan but
    # not declared as a feature — surface it explicitly so the agent's
    # research_pillar dispatch matches.
    items.append({
        "id":          "confidence_arc",
        "name":        "Confidence Arc",
        "description": "Personal-journey narrative — before/after, transformation moments, the day everything changed.",
    })
    items.append({
        "id":          "ai_pov",
        "name":        "AI POV",
        "description": "MaxAura's own analysis output as content. Real AI insights from the product itself as source material.",
    })
    items.append({
        "id":          "glow_up_identity",
        "name":        "Glow Up / Identity",
        "description": "Kibbe types, archetypes, identity-anchored style. Underused by competitors.",
    })
    items.append({
        "id":          "color_aura",
        "name":        "Colour Aura",
        "description": "12 Blueprints + Sci/Art seasonal colour analysis. Warm/cool/neutral undertones and palette rules.",
    })
    return {"items": items}


def _build_content_visual_assets(app_ctx: dict) -> dict:
    visual = (app_ctx.get("context") or {}).get("visual", {}) or {}
    return {
        "logo_url":         app_ctx.get("logoPath") or "",
        "background_urls":  [],
        "primary_color":    visual.get("primaryColor", ""),
        "secondary_color":  visual.get("secondaryColor", ""),
        "style":            visual.get("style", ""),
    }


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------


def _upsert_user(db: Session, email: str):
    from models.auth import User
    existing = db.execute(select(User).where(User.email == email)).scalars().first()
    if existing:
        logger.info("user  %s already exists (id=%s)", email, existing.id)
        return existing
    user = User(email=email, full_name="MaxAura Seed")
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("user  created %s (id=%s)", email, user.id)
    return user


def _upsert_project(db: Session, user_id: UUID, app_ctx: dict):
    from models.project import Project
    slug = app_ctx.get("id") or "maxaura"
    existing = db.execute(
        select(Project).where(Project.user_id == user_id, Project.slug == slug)
    ).scalars().first()
    content_brand         = _build_content_brand(app_ctx)
    content_pillars       = _build_content_pillars(app_ctx)
    content_visual_assets = _build_content_visual_assets(app_ctx)

    fields = dict(
        name=app_ctx.get("name") or slug,
        slug=slug,
        tagline=app_ctx.get("tagline") or "",
        description=app_ctx.get("description") or "",
        url=app_ctx.get("url") or "",
        content_brand=content_brand,
        content_pillars=content_pillars,
        content_visual_assets=content_visual_assets,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        logger.info("project updated %s (id=%s, pillars=%d)", slug, existing.id, len(content_pillars["items"]))
        return existing

    proj = Project(user_id=user_id, **fields)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    logger.info("project created %s (id=%s, pillars=%d)", slug, proj.id, len(content_pillars["items"]))
    return proj


def _upsert_formats(db: Session, project_id: UUID, source: Path) -> int:
    from models.content import ContentFormat
    payload = _read_json(source / "maxaura" / "tiktok" / "formats.json")
    formats = payload.get("formats", [])
    count = 0
    for f in formats:
        slug = f.get("slug") or f.get("id") or ""
        if not slug:
            continue
        existing = db.execute(
            select(ContentFormat).where(
                ContentFormat.project_id == project_id,
                ContentFormat.slug == slug,
            )
        ).scalars().first()
        data = {k: v for k, v in f.items() if k not in ("slug", "name")}
        if existing:
            existing.name = f.get("name") or existing.name
            existing.data = data
        else:
            db.add(ContentFormat(project_id=project_id, slug=slug, name=f.get("name") or "", data=data))
        count += 1
    db.commit()
    logger.info("formats upserted %d", count)
    return count


def _upsert_avatars(db: Session, project_id: UUID, source: Path) -> int:
    from models.content import ContentAvatar
    payload = _read_json(source / "maxaura" / "tiktok" / "avatars.json")
    avatars = payload.get("avatars", [])
    count = 0
    for a in avatars:
        name = a.get("name") or a.get("id") or ""
        if not name:
            continue
        existing = db.execute(
            select(ContentAvatar).where(
                ContentAvatar.project_id == project_id,
                ContentAvatar.name == name,
            )
        ).scalars().first()
        data = {k: v for k, v in a.items() if k != "name"}
        if existing:
            existing.data = data
        else:
            db.add(ContentAvatar(project_id=project_id, name=name, data=data))
        count += 1
    db.commit()
    logger.info("avatars upserted %d", count)
    return count


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _parse_iso_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _slug_from_post_dir(dir_str: str) -> str | None:
    """`posts/2026-05-15-001` → `2026-05-15-001`."""
    if not dir_str:
        return None
    return dir_str.rsplit("/", 1)[-1] or None


def _upsert_plan_and_posts(
    db: Session, project_id: UUID, source: Path,
) -> tuple[UUID, int]:
    """Insert one plan + N posts. Returns (plan_id, posts_count)."""
    from models.content import ContentPlan, ContentPost
    plan_json = _read_json(source / "maxaura" / "tiktok" / "thirty_day_plan.json")
    days_raw  = plan_json.get("days", [])
    character = plan_json.get("character", {}) or {}

    # Normalise days[] into the duct shape (snake_case keys + Platform list).
    norm_days: list[dict] = []
    for d in days_raw:
        if not isinstance(d, dict):
            continue
        norm_days.append({
            "day":          d.get("day"),
            "topic_id":     d.get("topicId"),
            "topic":        d.get("topic") or "",
            "pillar":       d.get("pillar") or "",
            "status":       d.get("status") or "pending",
            "post_type":    d.get("postType") or "slideshow",
            "post_dir":     d.get("postDir"),
            "slide_count":  d.get("slideCount") or 0,
            "platforms":    ["tiktok"],
            # carry the source perf payload through verbatim — useful for
            # analytics-tab seed data
            "perf":         d.get("perf"),
            "posted_at":    d.get("postedAt"),
        })

    plan = ContentPlan(
        project_id=project_id,
        name="MaxAura — 30-day TikTok plan",
        start_date=_parse_iso_date("2026-05-15"),
        character=character,
        days=norm_days,
        status="draft",
    )
    # Upsert by (project_id, name) — there's no unique constraint, so we look
    # for a previous seed row and delete it before re-inserting.
    previous = db.execute(
        select(ContentPlan).where(
            ContentPlan.project_id == project_id,
            ContentPlan.name == plan.name,
        )
    ).scalars().first()
    if previous:
        db.delete(previous)
        db.commit()
        logger.info("plan  deleted previous seed row %s", previous.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    logger.info("plan  created %s (%d days)", plan.id, len(norm_days))

    # Walk posts/<dir>/ for every day that has a postDir
    posts_root = source / "maxaura" / "tiktok" / "posts"
    count = 0
    for idx, day in enumerate(norm_days):
        slug = _slug_from_post_dir(day.get("post_dir") or "")
        if not slug:
            continue
        post_dir = posts_root / slug
        meta_path  = post_dir / "meta.json"
        slides_path = post_dir / "slides.html"
        if not meta_path.exists():
            logger.warning("post  skipping %s (no meta.json)", slug)
            continue

        meta = _read_json(meta_path)
        slides_html = _read_text(slides_path) if slides_path.exists() else ""

        # image_prompts in the source is {slide-XX: [str, ...]} — convert to
        # [{slide_id, prompt, aspect_ratio}] so it round-trips through
        # PostDraft validation.
        image_prompts = []
        for slide_id, prompts in (meta.get("imagePrompts") or {}).items():
            if isinstance(prompts, list):
                for p in prompts:
                    image_prompts.append({
                        "slide_id":     slide_id,
                        "prompt":       p,
                        "aspect_ratio": "9:16",
                    })

        status = day.get("status") or "draft"
        if status not in {"pending", "draft", "posted", "discarded"}:
            status = "draft"

        existing = db.execute(
            select(ContentPost).where(
                ContentPost.project_id == project_id,
                ContentPost.post_dir_slug == slug,
            )
        ).scalars().first()
        values = dict(
            project_id=project_id,
            plan_id=plan.id,
            day_index=day.get("day"),
            post_dir_slug=slug,
            pillar=meta.get("pillar") or day.get("pillar") or "",
            topic=meta.get("topic") or day.get("topic") or "",
            topic_id=meta.get("topicId") if isinstance(meta.get("topicId"), int) else None,
            post_type=meta.get("postType") or day.get("post_type") or "slideshow",
            format_style=meta.get("formatStyle") or "D",
            slide_count=meta.get("slideCount") or day.get("slide_count") or 0,
            status=status,
            slides_html=slides_html,
            caption=meta.get("caption") or "",
            hashtags=meta.get("hashtags") or [],
            tiktok_title=meta.get("tiktokTitle") or "",
            hook_type=meta.get("hookType") or "",
            hook_text=meta.get("hookText") or "",
            image_prompts=image_prompts,
            audio_note=meta.get("audioNote") or "",
            platforms=["tiktok"],
            perf=day.get("perf") or {},
            posted_at=_parse_iso_dt(day.get("posted_at")),
        )
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            db.add(existing)
        else:
            db.add(ContentPost(**values))
        count += 1

    db.commit()
    logger.info("posts upserted %d", count)
    return plan.id, count


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed MaxAura content data into the duct DB.")
    parser.add_argument("--source", default=_DEFAULT_SOURCE_DIR,
                        help="Path to nomadapps/marketing/ (default: %(default)s)")
    parser.add_argument("--email",  default=_DEFAULT_EMAIL,
                        help="User email for the seed project (default: %(default)s)")
    parser.add_argument("--app-id", default="maxaura", help="apps.json id to seed (default: maxaura)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the project payload + day count and exit without writing.")
    args = parser.parse_args(argv)

    _setup_logging()

    source = Path(args.source).expanduser().resolve()
    if not (source / "apps.json").exists():
        raise SystemExit(f"apps.json not found under {source}")

    app_ctx = _load_app(source, args.app_id)
    logger.info("source %s", source)
    logger.info("app    id=%s name=%s", app_ctx.get("id"), app_ctx.get("name"))

    if args.dry_run:
        logger.info("DRY RUN — would upsert:")
        logger.info("  content_brand:         %s", json.dumps(_build_content_brand(app_ctx), indent=2)[:400])
        logger.info("  content_pillars items: %d", len(_build_content_pillars(app_ctx)["items"]))
        plan_path = source / "maxaura" / "tiktok" / "thirty_day_plan.json"
        days = _read_json(plan_path).get("days", [])
        with_dir = sum(1 for d in days if d.get("postDir"))
        logger.info("  days in plan: %d (%d with postDir)", len(days), with_dir)
        return 0

    # Lazy DB engine import — only when we're actually writing.
    from db.session import get_engine
    engine = get_engine()
    if engine is None:
        raise SystemExit("DATABASE_URL is not configured. Set it and try again.")

    with Session(engine) as db:
        user = _upsert_user(db, args.email)
        proj = _upsert_project(db, user.id, app_ctx)
        _upsert_formats(db, proj.id, source)
        _upsert_avatars(db, proj.id, source)
        plan_id, posts_count = _upsert_plan_and_posts(db, proj.id, source)

    logger.info("DONE   project=%s plan=%s posts=%d", proj.id, plan_id, posts_count)
    print(f"\nUSER_EMAIL  = {args.email}")
    print(f"PROJECT_ID  = {proj.id}")
    print(f"PLAN_ID     = {plan_id}")
    print(f"POSTS_COUNT = {posts_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
