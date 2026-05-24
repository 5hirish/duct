"""Unit tests for the MaxAura seed script's payload builders.

We exercise the pure functions (no DB) so the seed contract is regression-
protected: if apps.json changes shape, this test breaks loudly instead of
silently inserting half-empty brand JSONB blobs.

End-to-end Postgres seeding is covered by Phase 6's verification harness
(scripts/seed_maxaura.py against a real DB).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_MARKETING_DIR = Path("/home/user/nomadapps/marketing")
_HAS_SOURCE = (_MARKETING_DIR / "apps.json").exists()


pytestmark = pytest.mark.skipif(
    not _HAS_SOURCE,
    reason="nomadapps/marketing source not available in this environment",
)


def _load_app():
    from scripts.seed_maxaura import _load_app
    return _load_app(_MARKETING_DIR, "maxaura")


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def test_load_app_finds_maxaura():
    app = _load_app()
    assert app["id"] == "maxaura"
    assert app["name"] == "MaxAura"
    assert app["url"] == "maxauralab.com"


def test_content_brand_pulls_audience_voice_value_prop():
    from scripts.seed_maxaura import _build_content_brand
    brand = _build_content_brand(_load_app())
    assert "Self-Improver" in brand["audience"]
    assert "16-35" in brand["audience"]
    assert "confident" in brand["brand_voice"]
    assert brand["tone"] == "casual"
    assert brand["value_prop"]
    assert "Premium" in brand.get("pricing", "") or "$" in brand.get("pricing", "")
    assert isinstance(brand["proof_points"], list) and len(brand["proof_points"]) >= 1
    assert isinstance(brand["features"], list) and len(brand["features"]) == 4


def test_content_pillars_have_features_plus_conceptual_extras():
    from scripts.seed_maxaura import _build_content_pillars
    items = _build_content_pillars(_load_app())["items"]
    ids = {p["id"] for p in items}
    # Four declared features
    assert {"face_shape", "color_season", "hairstyle", "frames"}.issubset(ids)
    # Four conceptual pillars the orchestrator can dispatch research_pillar against
    assert {"confidence_arc", "ai_pov", "glow_up_identity", "color_aura"}.issubset(ids)


def test_content_visual_assets_pulls_palette():
    from scripts.seed_maxaura import _build_content_visual_assets
    visual = _build_content_visual_assets(_load_app())
    assert visual["primary_color"].startswith("#")
    assert visual["secondary_color"].startswith("#")
    assert visual["style"] == "editorial"
    assert visual["background_urls"] == []


def test_plan_loader_finds_thirty_days_plus_video():
    """The MaxAura thirty_day_plan.json starts at day 0 (UGC video) and has
    days 1-30 in slideshow form. Total = 31."""
    import json

    plan = json.loads((_MARKETING_DIR / "maxaura" / "tiktok" / "thirty_day_plan.json").read_text())
    days = plan.get("days", [])
    assert len(days) == 31
    assert days[0]["postType"] == "video"
    assert days[0]["pillar"] == "confidence_arc"


def test_post_dirs_resolve_to_existing_files():
    """Every day with a postDir must have meta.json on disk."""
    import json

    plan = json.loads((_MARKETING_DIR / "maxaura" / "tiktok" / "thirty_day_plan.json").read_text())
    posts_root = _MARKETING_DIR / "maxaura" / "tiktok" / "posts"
    for day in plan.get("days", []):
        post_dir = day.get("postDir")
        if not post_dir:
            continue
        slug = post_dir.rsplit("/", 1)[-1]
        meta_path = posts_root / slug / "meta.json"
        assert meta_path.exists(), f"meta.json missing for day {day.get('day')} ({slug})"


def test_slug_from_post_dir_handles_variants():
    from scripts.seed_maxaura import _slug_from_post_dir
    assert _slug_from_post_dir("posts/2026-05-15-001") == "2026-05-15-001"
    assert _slug_from_post_dir("2026-05-15-001") == "2026-05-15-001"
    assert _slug_from_post_dir("") is None
    assert _slug_from_post_dir(None) is None


def test_dry_run_invocation():
    """Smoke: running with --dry-run produces no DB writes and exits 0."""
    from scripts.seed_maxaura import main
    rc = main(["--source", str(_MARKETING_DIR), "--dry-run"])
    assert rc == 0


def test_image_prompts_round_trip_into_postdraft_shape():
    """Walking a real meta.json should produce image_prompts entries the
    PostDraft Pydantic shape accepts."""
    import json

    from agents.content.schema import ImagePrompt

    meta = json.loads((_MARKETING_DIR / "maxaura" / "tiktok" / "posts" / "2026-05-15-001" / "meta.json").read_text())
    image_prompts = []
    for slide_id, prompts in (meta.get("imagePrompts") or {}).items():
        for p in prompts:
            image_prompts.append({"slide_id": slide_id, "prompt": p, "aspect_ratio": "9:16"})
    # Every entry should validate against the Pydantic ImagePrompt shape
    for entry in image_prompts:
        ImagePrompt.model_validate(entry)
    assert len(image_prompts) >= 7  # there are at least 7 image slides


@pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="DATABASE_URL not set — full DB seed is skipped",
)
def test_seed_end_to_end_against_real_db():
    """Live seed against a real Postgres. Run with:

        DATABASE_URL=postgresql://… poetry run pytest tests/test_seed_maxaura.py::test_seed_end_to_end_against_real_db

    Verifies users / projects / content_plans / content_posts / content_formats
    / content_avatars rows land.
    """
    from sqlalchemy import select
    from sqlmodel import Session

    from db.session import get_engine
    from models.auth import User
    from models.content import ContentFormat, ContentPlan, ContentPost
    from models.project import Project
    from scripts.seed_maxaura import main

    rc = main(["--source", str(_MARKETING_DIR), "--email", "test+e2e@getduct.ai"])
    assert rc == 0

    with Session(get_engine()) as db:
        user = db.execute(select(User).where(User.email == "test+e2e@getduct.ai")).scalars().first()
        assert user is not None
        proj = db.execute(
            select(Project).where(Project.user_id == user.id, Project.slug == "maxaura")
        ).scalars().first()
        assert proj is not None
        assert proj.content_brand.get("audience")
        assert len(proj.content_pillars.get("items", [])) >= 4
        plan = db.execute(select(ContentPlan).where(ContentPlan.project_id == proj.id)).scalars().first()
        assert plan is not None
        assert len(plan.days) == 31
        posts = db.execute(select(ContentPost).where(ContentPost.plan_id == plan.id)).scalars().all()
        # At least one post (the source has 3) and slides_html should be inlined.
        assert len(posts) >= 1
        any_with_html = any(len(p.slides_html) > 1000 for p in posts)
        assert any_with_html
        formats = db.execute(
            select(ContentFormat).where(ContentFormat.project_id == proj.id)
        ).scalars().all()
        assert len(formats) >= 4
