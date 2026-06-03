"""Tests for scripts/seed_maxaura — the dev seed against real fixtures.

These tests run against actual nomadapps/marketing/ JSON files, not
synthetic data. If the source files change shape (or our mapping
diverges), they fail loudly so the seed never silently inserts
half-populated rows.

The live DB seed is at the bottom — gated by DATABASE_URL.
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
# Builder coverage — single test asserting the full project payload shape
# ---------------------------------------------------------------------------


def test_seed_builders_pull_real_maxaura_data():
    """One test covers the entire app → Project mapping. If apps.json
    changes shape this fails clearly and identifies the broken field."""
    from scripts.seed_maxaura import (
        _build_content_brand,
        _build_content_pillars,
        _build_content_visual_assets,
    )
    app = _load_app()
    assert app["id"] == "maxaura"
    assert app["name"] == "MaxAura"

    brand = _build_content_brand(app)
    assert "Self-Improver" in brand["audience"]
    assert "16-35"          in brand["audience"]
    assert "confident"      in brand["brand_voice"]
    assert brand["tone"]    == "casual"
    assert brand["value_prop"]
    assert isinstance(brand["features"], list) and len(brand["features"]) == 4

    items = _build_content_pillars(app)["items"]
    ids = {p["id"] for p in items}
    # Declared features...
    assert {"face_shape", "color_season", "hairstyle", "frames"}.issubset(ids)
    # ...plus the conceptual pillars the orchestrator needs to dispatch against.
    assert {"confidence_arc", "ai_pov", "glow_up_identity", "color_aura"}.issubset(ids)

    visual = _build_content_visual_assets(app)
    assert visual["primary_color"].startswith("#")
    assert visual["secondary_color"].startswith("#")
    assert visual["style"] == "editorial"


# ---------------------------------------------------------------------------
# Real-fixture integrity — protects against rot in nomadapps/marketing
# ---------------------------------------------------------------------------


def test_real_plan_has_31_days_and_every_post_dir_resolves():
    """The MaxAura plan is the seed source-of-truth — if a posts/<dir>/
    is renamed or removed, the seed silently skips it. This test fails
    instead."""
    import json
    plan = json.loads((_MARKETING_DIR / "maxaura" / "tiktok" / "thirty_day_plan.json").read_text())
    days = plan.get("days", [])
    assert len(days) == 31  # day 0 (video) + days 1-30 (slideshows)
    assert days[0]["postType"] == "video"

    posts_root = _MARKETING_DIR / "maxaura" / "tiktok" / "posts"
    for day in days:
        post_dir = day.get("postDir")
        if not post_dir:
            continue
        slug = post_dir.rsplit("/", 1)[-1]
        assert (posts_root / slug / "meta.json").exists(), f"meta.json missing for day {day['day']}"


def test_real_image_prompts_validate_against_postdraft_shape():
    """Every prompt in a real meta.json must be a valid ImagePrompt.
    Catches: source field rename, missing prompts, malformed entries."""
    import json
    from agents.content.schema import ImagePrompt

    meta = json.loads((_MARKETING_DIR / "maxaura" / "tiktok" / "posts" / "2026-05-15-001" / "meta.json").read_text())
    count = 0
    for slide_id, prompts in (meta.get("imagePrompts") or {}).items():
        for p in prompts:
            ImagePrompt.model_validate({"slide_id": slide_id, "prompt": p, "aspect_ratio": "9:16"})
            count += 1
    assert count >= 7  # at least 7 image slides in the source


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_seed_dry_run_exits_clean_without_db():
    """--dry-run must not touch the DB and must exit 0 with the source
    summary printed. This is how a new developer first runs the seed."""
    from scripts.seed_maxaura import main
    rc = main(["--source", str(_MARKETING_DIR), "--dry-run"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Live e2e — gated by DATABASE_URL
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="DATABASE_URL not set — live DB seed is skipped",
)
@pytest.mark.live
def test_seed_writes_full_project_against_real_postgres():
    """The real e2e: seed → real Postgres → row counts + relationships
    match what the agent will read at runtime.

    Run with:
        DATABASE_URL=postgresql://... poetry run pytest \\
            tests/test_seed_maxaura.py -k real_postgres -s
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
        user = db.execute(
            select(User).where(User.email == "test+e2e@getduct.ai")
        ).scalars().first()
        assert user is not None

        proj = db.execute(
            select(Project).where(Project.user_id == user.id, Project.slug == "maxaura")
        ).scalars().first()
        assert proj is not None
        assert proj.content_brand.get("audience")
        assert len(proj.content_pillars.get("items", [])) >= 8  # 4 features + 4 conceptual

        plan = db.execute(
            select(ContentPlan).where(ContentPlan.project_id == proj.id)
        ).scalars().first()
        assert plan is not None
        assert len(plan.days) == 31

        posts = db.execute(
            select(ContentPost).where(ContentPost.plan_id == plan.id)
        ).scalars().all()
        assert len(posts) >= 1
        # slides.html got inlined — the chief value of the seed.
        assert any(len(p.slides_html) > 1000 for p in posts)

        formats = db.execute(
            select(ContentFormat).where(ContentFormat.project_id == proj.id)
        ).scalars().all()
        assert len(formats) >= 4
