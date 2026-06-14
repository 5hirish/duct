"""Full end-to-end eval for the Content Studio agent (v3 engine) + judge.

This is the complete content pipeline under one test: the v3 Claude Agent SDK
runner drafts a real post, then generates a real image for every slide via its
own ``generate_image`` tool (Gemini), and a *Gemini* judge (vision) scores the
finished post + images against ``content_post_rubric`` to guard against model-
output degradation. The judge runs on Gemini (the v2/ADK stack) rather than
Claude so the grading call isn't gated by the Anthropic Messages API rate
limits. Unlike the offline parser tests, this exercises the real agent, real
image generation, and a real DB.

It is gated and skips cleanly unless everything it needs is present:

  DATABASE_URL                                 — Postgres for the ephemeral project
  CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY — drives the content agent (v3)
  GEMINI_API_KEY                               — slide image generation AND the judge
  the ``claude`` CLI on PATH                   — the Agent SDK subprocess

Run it:

  CLAUDE_CODE_OAUTH_TOKEN=… GEMINI_API_KEY=… DATABASE_URL=… \
    poetry run pytest -m live tests/test_content_post_e2e.py -s

A JSON scorecard is written (DUCT_EVAL_OUTPUT, default ./eval-scorecard.json)
and, in CI, appended to the GitHub step summary.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.eval import JudgeImage, assert_scorecard, evaluate, judge_available
from tests.eval.rubrics.content_post import build_content_post_artifact, content_post_rubric

# ---------------------------------------------------------------------------
# Tuning — kept fast on purpose: a 3-slide draft and a SINGLE image generation
# call. That exercises the whole pipeline (draft -> image tool -> judge) without
# paying for a full 7-slide post and ~8 images.
# ---------------------------------------------------------------------------
_DRAFT_TIMEOUT = 360.0    # wait for the draft to persist (post_id set)
_IMAGE_TIMEOUT = 180.0    # wait for the single image to attach
_CHAT_IDLE = 180.0        # how long the run waits between our driven turns
_HARD_TIMEOUT = 600.0     # overall ceiling for the whole drive
_POLL = 4.0
_MIN_IMAGES_TO_JUDGE = 1  # fast mode generates one image; that's enough to judge

_IMAGE_TURN = (
    "Approved. Now generate the image for the FIRST slide only: call "
    "generate_image once with that slide's slide_id and an image_prompt derived "
    "from it. One image is enough for this run — once slide 1 has an image the "
    "post is complete; do not ask for confirmation, just finish."
)

_TOPIC = (
    "the 3 grooming mistakes quietly weakening your jawline. TEST MODE: keep this "
    "SHORT — produce EXACTLY 3 single-image slides (set slide_count=3); no collage "
    "or before/after slides; do NOT number the slides or use list counters "
    "(no '1/4', '①', 'tip 3')."
)
_PILLAR = "jawline"


def _live_skip_reason() -> str | None:
    if not os.environ.get("DATABASE_URL"):
        return "DATABASE_URL not set"
    if not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")):
        return "no Claude credential (CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY) set"
    if not os.environ.get("GEMINI_API_KEY"):
        return "GEMINI_API_KEY not set"
    if shutil.which("claude") is None:
        return "the `claude` CLI is not on PATH (Agent SDK subprocess unavailable)"
    if not judge_available():
        return "judge unavailable (anthropic SDK missing or no credential)"
    return None


# ---------------------------------------------------------------------------
# Ephemeral project — self-seeded so the test doesn't depend on a seed script.
# ---------------------------------------------------------------------------

_BRAND = {
    "name": "MaxAura",
    "industry": "men's grooming",
    "brand_voice": "confident, direct — a knowledgeable friend, never preachy or clinical",
    "audience": "men 18–35 into self-improvement and aesthetics (looksmaxxing, grooming)",
    "value_prop": "a free app that reads your face from a photo and builds a personalised grooming routine",
    "do_not_say": "Never say 'AI' or 'AI-powered' on slides or in captions; no press-release tone; no medical claims",
}


def _brand_summary() -> str:
    return (
        f"{_BRAND['name']} — {_BRAND['industry']}. "
        f"Voice: {_BRAND['brand_voice']}. "
        f"Audience: {_BRAND['audience']}. "
        f"Value prop: {_BRAND['value_prop']}. "
        f"Do not say: {_BRAND['do_not_say']}."
    )


@pytest.fixture
def maxaura_project():
    """Create a throwaway User + Project with full content brand context, yield
    its id, and delete it (cascade) on teardown."""
    # Skip before any DB work when any live prerequisite is missing.
    reason = _live_skip_reason()
    if reason:
        pytest.skip(reason)

    from sqlmodel import Session

    from db.session import get_engine
    from models.auth import User
    from models.project import Project

    engine = get_engine()
    if engine is None:
        pytest.skip("DATABASE_URL not configured")

    user_id = None
    project_id = None
    with Session(engine) as db:
        user = User(email=f"e2e+{uuid4().hex[:12]}@getduct.ai", full_name="E2E Eval")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        project = Project(
            user_id=user.id,
            name="MaxAura E2E",
            slug="maxaura-e2e",
            tagline="Look your best, effortlessly",
            description="Grooming and self-improvement tools for men",
            url="https://maxaura.example",
            industry=_BRAND["industry"],
            audience={
                "primary_segment": _BRAND["audience"],
                "personas": [
                    {
                        "name": "Looksmaxxing Liam",
                        "description": "22, wants a sharper jawline and clearer skin, scrolls TikTok for tips",
                        "priority": "high",
                    }
                ],
            },
            brand_channels={"brand_voice": _BRAND["brand_voice"]},
            content_brand={
                "tone": "confident, encouraging, slightly contrarian",
                "value_prop": _BRAND["value_prop"],
                "content_goal": "drive app installs by teaching one save-worthy grooming insight per post",
                "do_say": "specific routines, named techniques, real measurements",
                "do_not_say": _BRAND["do_not_say"],
                "features": [
                    {"id": "face_analysis", "name": "Face analysis", "description": "photo-based face shape + skin read"},
                    {"id": "routine", "name": "Personalised routine", "description": "daily grooming steps tailored to the user"},
                ],
            },
            content_pillars={
                "items": [
                    {"id": "grooming", "name": "Grooming basics", "description": "skincare, hair and beard routines", "research_hint": "common mistakes men make"},
                    {"id": "jawline", "name": "Jawline & face", "description": "mewing, face exercises, definition", "research_hint": "what actually changes jaw definition"},
                    {"id": "style", "name": "Gear that works", "description": "tools and products worth buying"},
                ]
            },
            content_visual_assets={
                "primary_color": "#0E0E10",
                "secondary_color": "#C9A227",
                "style": "moody editorial, warm key light, masculine",
            },
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id

    try:
        yield project_id
    finally:
        # Cascades (projects→posts→assets, users→projects) clean the rest;
        # never let teardown failures mask the test result.
        with Session(engine) as db:
            try:
                proj = db.get(Project, project_id)
                if proj is not None:
                    db.delete(proj)
                    db.commit()
                usr = db.get(User, user_id)
                if usr is not None:
                    db.delete(usr)
                    db.commit()
            except Exception:
                db.rollback()


# ---------------------------------------------------------------------------
# DB readers
# ---------------------------------------------------------------------------


def _read_post(post_id):
    from sqlmodel import Session

    from db.session import get_engine
    from models.content import ContentPost

    with Session(get_engine()) as db:
        return db.get(ContentPost, post_id)


def _generated_assets(post_id) -> list[tuple[str, str]]:
    """(url, mime_type) for every image the agent generated for this post.

    Read from content_assets (post_id + asset_type='generated') — the source of
    truth for "images produced", independent of whether the agent also attached
    them onto a slide's image_url (which only happens when it passes slide_id)."""
    from sqlmodel import Session, select

    from db.session import get_engine
    from models.content import ContentAsset

    with Session(get_engine()) as db:
        rows = db.exec(
            select(ContentAsset)
            .where(ContentAsset.post_id == post_id)
            .where(ContentAsset.asset_type == "generated")
        ).all()
        return [(r.url, r.mime_type or "") for r in rows]


def _mime_for(url: str) -> str:
    lower = url.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/png"


def _load_post_images(post_id) -> list[JudgeImage]:
    """Load every generated image for the post as bytes via the storage layer
    (resolves local /uploads, R2/CDN, or bundled refs identically)."""
    from service import storage

    images: list[JudgeImage] = []
    for i, (url, mime) in enumerate(_generated_assets(post_id), 1):
        data = storage.get_bytes(url)
        if data:
            images.append(JudgeImage(label=f"generated image {i}", mime_type=mime or _mime_for(url), data=data))
    return images


# ---------------------------------------------------------------------------
# Driver — run the draft, then conduct the image phase via the chat queue.
# ---------------------------------------------------------------------------


async def _drive(runner, session, session_id, project_id) -> list[dict]:
    events: list[dict] = []
    state = {"done": False, "error": None}

    async def emit(body: dict) -> None:
        events.append(body)

    async def _run_agent() -> None:
        try:
            await runner.run_draft(
                session_id,
                project_id,
                emit,
                topic=_TOPIC,
                pillar=_PILLAR,
                channel="tiktok",
                effort=_effort(),
                adaptive_thinking=True,
                chat_idle_timeout=_CHAT_IDLE,
            )
        except Exception as exc:  # captured; re-raised after gather
            state["error"] = exc
        finally:
            state["done"] = True

    async def _wait(predicate, timeout: float, *, soft: bool = False) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if predicate():
                return
            if time.monotonic() > deadline:
                if soft:
                    return
                raise TimeoutError(f"condition not met within {timeout:.0f}s")
            await asyncio.sleep(_POLL)

    async def _conduct() -> None:
        try:
            # Phase 1 — wait for the draft to persist (or the run to end early).
            await _wait(lambda: session.post_id is not None or state["done"], _DRAFT_TIMEOUT)
            if session.post_id is None:
                return  # nothing drafted — the test asserts + reports below
            # Phase 2 — drive the image phase.
            await session.chat_queue.put({"role": "user", "content": _IMAGE_TURN})
            # Phase 3 — wait until the agent has generated at least one image
            # (fast mode generates a single image), or time out, then end.
            def _has_image() -> bool:
                return state["done"] or len(_generated_assets(session.post_id)) >= 1
            await _wait(_has_image, _IMAGE_TIMEOUT, soft=True)
        finally:
            # Always release the run loop, even on early return / error.
            await session.chat_queue.put(None)

    await asyncio.gather(_run_agent(), _conduct())
    if state["error"] is not None:
        raise state["error"]
    return events


def _effort():
    from agents.models import AgentEffort

    return AgentEffort.MEDIUM


def _judge_skip_reason(exc: Exception) -> str | None:
    """Classify a Gemini judge-call exception as an infra issue to SKIP on
    (rate limit / quota / transient 5xx) vs. a real failure to raise. A rate
    limit is environment, not content degradation, so it skips."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    blob = f"{getattr(exc, 'status', '')} {getattr(exc, 'message', '') or exc}".lower()
    transient = any(
        token in blob
        for token in ("resource_exhausted", "rate limit", "rate_limit", "quota", "unavailable", "overloaded")
    )
    if code in (429, 500, 502, 503, 504) or transient:
        return (
            f"judge hit a transient Gemini error ({code or 'rate/quota'}) — "
            "re-run later or raise the Gemini quota"
        )
    return None


def _emit_scorecard(scorecard) -> None:
    out_path = os.environ.get("DUCT_EVAL_OUTPUT", "eval-scorecard.json")
    try:
        Path(out_path).write_text(json.dumps(scorecard.as_dict(), indent=2))
    except Exception:
        pass
    markdown = scorecard.as_markdown()
    print("\n" + markdown + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("\n\n" + markdown + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_content_draft_post_with_images_passes_judge(maxaura_project, tmp_path, monkeypatch):
    """Draft a full post with images via the v3 agent, then gate it on the judge.

    Asserts the machinery ran end-to-end (post persisted, images generated) and
    that the finished deliverable clears the content rubric — the degradation
    guard. The scorecard is written/printed regardless of pass/fail.
    """
    reason = _live_skip_reason()
    if reason:
        pytest.skip(reason)

    # Force the local image-storage backend at a temp dir and refresh cached
    # config. (No R2 creds in CI, but pin it explicitly so a stray R2 env can't
    # send the images to a bucket the judge-image loader would then re-fetch.)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    import config

    config.get_configs.cache_clear()

    from agents.content.v3.runner import (
        ClaudeContentRunner,
        close_session,
        create_draft_session,
    )

    project_id = maxaura_project
    session_id = f"eval-{uuid4()}"
    session = create_draft_session(session_id, project_id)
    # Empty api_key is fine when a CLAUDE_CODE_OAUTH_TOKEN is configured.
    runner = ClaudeContentRunner(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    try:
        asyncio.run(asyncio.wait_for(_drive(runner, session, session_id, project_id), timeout=_HARD_TIMEOUT))
    except asyncio.TimeoutError:
        pytest.fail(f"content pipeline did not finish within {_HARD_TIMEOUT:.0f}s")
    finally:
        with contextlib.suppress(Exception):
            close_session(session_id)
        config.get_configs.cache_clear()

    # --- Machinery assertions: did we actually get a post with images? --------
    assert session.post_id is not None, "agent finished without persisting a post draft"
    post = _read_post(session.post_id)
    assert post is not None, "persisted post not found in the database"
    assert post.slides, "post has no slides"

    total = len(post.slides or [])
    images = _load_post_images(session.post_id)
    assert len(images) >= _MIN_IMAGES_TO_JUDGE, (
        f"image phase under-delivered: agent generated {len(images)} image(s) for a "
        f"{total}-slide post (need >= {_MIN_IMAGES_TO_JUDGE} to judge)"
    )

    # --- The judge: score the finished post + images against the rubric. ------
    # Fast mode generates one image on purpose; tell the judge so it grades the
    # image dimensions on the image(s) present and doesn't penalise slides that
    # were intentionally left without an image.
    eval_note = (
        f"This is a fast pipeline smoke check, not a full post: the agent was asked for "
        f"a SHORT {total}-slide post and generated {len(images)} image(s) on purpose. "
        "Calibrate structural expectations (e.g. multi-slide 'mystery architecture') to "
        "this short format, judge the image dimensions on the image(s) actually present, "
        "and do not penalise the post for being short or for slides without an image."
    )
    artifact = build_content_post_artifact(
        post, brand_summary=_brand_summary(), images=images, eval_note=eval_note
    )
    try:
        scorecard = evaluate(content_post_rubric(), artifact)
    except Exception as exc:
        reason = _judge_skip_reason(exc)
        if reason:
            pytest.skip(f"{reason}: {exc}")
        raise

    _emit_scorecard(scorecard)
    assert_scorecard(scorecard)
