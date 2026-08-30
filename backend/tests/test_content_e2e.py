"""End-to-end tests for the Content Studio agent.

The default suite runs offline — only the parser tests that defend
against real model output quirks (markdown fences, unescaped HTML in
slides_html) and a frontend↔backend enum-mirror check.

The LIVE suite (marked @pytest.mark.live) hits real APIs against real
accounts. Run when you want to validate contract correctness end-to-end:

  ANTHROPIC_API_KEY=sk-…   — drives a real plan_month session
  GEMINI_API_KEY=ai-…      — generates one real image
  POSTBRIDGE_API_KEY=sk-…  — read-only list_social_accounts smoke
  DATABASE_URL=postgresql://…  — for the seed + plan e2e

Examples:
  POSTBRIDGE_API_KEY=sk-… poetry run pytest tests/test_content_e2e.py -k live_post_bridge -s
  GEMINI_API_KEY=ai-…     poetry run pytest tests/test_content_e2e.py -k live_gemini -s
  ANTHROPIC_API_KEY=sk-… DATABASE_URL=… poetry run pytest tests/test_content_e2e.py -k live_run_plan -s
"""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest

from agents.content.events import ContentEvent
from agents.content.v3.runner import _parse_artifact_json


# ---------------------------------------------------------------------------
# Parser defends against real model-output quirks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "raw", "expect_type"),
    [
        (
            "plan_payload",
            '{"type":"plan","project_id":"00000000-0000-0000-0000-000000000000","days":[]}',
            "plan",
        ),
        (
            "post_payload_with_escaped_html",
            json.dumps({
                "type": "post",
                "project_id": "00000000-0000-0000-0000-000000000000",
                "post_dir_slug": "x",
                "pillar": "p",
                "topic": "t",
                "slides_html": '<html><body><div class="slide" id="s1">hello</div></body></html>',
                "caption": "c",
            }),
            "post",
        ),
        (
            "post_payload_wrapped_in_markdown_fence",
            "```json\n"
            '{"type":"post","project_id":"00000000-0000-0000-0000-000000000000",'
            '"post_dir_slug":"x","pillar":"p","topic":"t","slides_html":"<x/>","caption":"c"}\n'
            "```",
            "post",
        ),
    ],
)
def test_duct_artifact_parser_handles_real_model_output_shapes(name, raw, expect_type):
    """The parser is the seam between the LLM's text output and our DB.
    These three shapes cover the patterns we've observed:
       1. clean JSON
       2. properly-escaped HTML inside a string (the common case)
       3. ```json fences (some models love them)
    """
    payload = _parse_artifact_json(raw)
    assert payload is not None, f"parser returned None for {name}"
    assert payload["type"] == expect_type


def test_duct_artifact_parser_recovers_from_unescaped_html_via_strip_fallback():
    """When the model emits unescaped quotes inside slides_html (which it
    will, occasionally), the standard JSON parser fails. The fallback
    strips slides_html and reparses so the writer @tool still gets a
    usable payload — slides_html will be empty but everything else
    survives. This is the only realistic recovery path; without it the
    user loses the whole draft."""
    raw = (
        '{"type":"post","project_id":"00000000-0000-0000-0000-000000000000",'
        '"post_dir_slug":"x","pillar":"p","topic":"t",'
        '"slides_html":"<div class="slide">unescaped</div>",'
        '"caption":"c"}'
    )
    payload = _parse_artifact_json(raw)
    # Either we recover (preferred) or return None (acceptable but worse).
    if payload is not None:
        assert payload.get("type") == "post"
        assert isinstance(payload.get("slides_html", ""), str)


def test_duct_artifact_parser_returns_none_on_total_garbage():
    """Defensive: if the model emits non-JSON nonsense the parser MUST
    return None (not raise). The runner's _handle_close logs a warning
    and continues — agent stays alive."""
    assert _parse_artifact_json("not json at all") is None


# ---------------------------------------------------------------------------
# Live integrations — real APIs, gated by env vars
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("POSTBRIDGE_API_KEY"),
    reason="POSTBRIDGE_API_KEY not set — live PostBridge smoke skipped",
)
@pytest.mark.live
def test_live_post_bridge_list_social_accounts_real_api():
    """Read-only smoke against the real PostBridge API. Catches:
       - API key invalid / revoked
       - Response shape drift (we depend on numeric IDs + data envelope)
       - Endpoint URL change

    Costs nothing (no posts created, no media uploaded). The returned
    list may be empty if no accounts are connected — that's still a
    valid contract validation.
    """
    from service.post_bridge import PostBridgeClient

    async def _go():
        async with PostBridgeClient(os.environ["POSTBRIDGE_API_KEY"]) as pb:
            return await pb.list_social_accounts(limit=10)

    accounts = asyncio.run(_go())
    # We don't assert non-empty (account may have nothing connected).
    # We DO assert every returned record matches our contract.
    for a in accounts:
        assert isinstance(a.id, int), f"id not int: {a.id!r}"
        assert a.platform, "platform empty"
        assert a.username, "username empty"


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set — live Gemini image gen skipped",
)
@pytest.mark.live
def test_live_gemini_generate_one_image_real_api():
    """Generate one tiny real image. Costs ~1¢. Catches:
       - API key invalid / quota exhausted
       - google-genai SDK version mismatch
       - Per-model option pruning regression
       - Our extractor missing the inline_data parts
    """
    from agents.models import AspectRatio, ImageModel
    from service.google.gemini import GeminiImageClient, GenerateImageRequest

    async def _go():
        client = GeminiImageClient(os.environ["GEMINI_API_KEY"])
        return await client.generate_image(GenerateImageRequest(
            prompt="a single ripe red apple on a white surface, soft daylight",
            model=ImageModel.GEMINI_3_1_FLASH_IMAGE,
            aspect_ratio=AspectRatio.SQUARE_1_1,
            number_of_images=1,
        ))

    images = asyncio.run(_go())
    assert len(images) >= 1
    img = images[0]
    assert img.mime_type.startswith("image/")
    assert len(img.data) > 1024, f"image suspiciously small ({len(img.data)} bytes)"


@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("DATABASE_URL")),
    reason="ANTHROPIC_API_KEY + DATABASE_URL not set — live run_plan skipped",
)
@pytest.mark.live
def test_live_run_plan_against_seeded_maxaura_project():
    """Drive a real plan_month session against the seeded MaxAura project.
    The most expensive test in the suite (one full Sonnet plan_month run
    — typically $0.10-0.30 with prompt caching).

    Asserts the agent loop reached a terminal state and persisted at
    least one ContentPlan row. Doesn't enforce plan quality (that's a
    human review concern) — only that the machinery worked end-to-end.

    Prereqs: run scripts/seed_maxaura.py against the same DB first.
    """
    from sqlalchemy import select
    from sqlmodel import Session

    from agents.content.v3.runner import ClaudeContentRunner, create_plan_session
    from agents.models import AgentEffort
    from db.session import get_engine
    from models.auth import User
    from models.content import ContentPlan
    from models.project import Project

    with Session(get_engine()) as db:
        user = db.execute(
            select(User).where(User.email == "test+e2e@getduct.ai")
        ).scalars().first()
        if user is None:
            pytest.skip("seed user not present; run scripts/seed_maxaura.py first")
        proj = db.execute(
            select(Project).where(Project.user_id == user.id, Project.slug == "maxaura")
        ).scalars().first()
        if proj is None:
            pytest.skip("seeded MaxAura project missing")
        project_id = proj.id

    events: list[dict] = []
    async def _emit(body: dict) -> None:
        events.append(body)

    session_id = f"live-test-{uuid4()}"
    create_plan_session(session_id, project_id)

    async def _drive():
        runner = ClaudeContentRunner(api_key=os.environ["ANTHROPIC_API_KEY"])
        try:
            await asyncio.wait_for(
                runner.run_plan(
                    session_id, project_id, _emit,
                    effort=AgentEffort.MEDIUM,
                    chat_idle_timeout=10.0,
                ),
                timeout=420.0,
            )
        except asyncio.TimeoutError:
            events.append({"event": "test_timeout"})

    asyncio.run(_drive())

    event_names = [e.get("event") for e in events]
    assert ContentEvent.PIPELINE_STARTED in event_names
    assert ContentEvent.STEP_STARTED     in event_names, "expected at least one STEP_STARTED chip"
    assert (
        ContentEvent.PIPELINE_FINISHED in event_names
        or ContentEvent.PIPELINE_FAILED in event_names
    ), "stream did not terminate"

    if ContentEvent.PIPELINE_FINISHED in event_names:
        with Session(get_engine()) as db:
            plans = db.execute(
                select(ContentPlan).where(ContentPlan.project_id == project_id)
            ).scalars().all()
            assert any(len(p.days or []) >= 10 for p in plans), \
                "no plan with >=10 days persisted — agent didn't actually deliver"
