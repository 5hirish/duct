"""The pre-publish review: its math, the tool that stores it, the route that serves it.

The property worth pinning above the rest is the one in the issue title: the
agent scores, the server weighs. It holds three ways — the tool's argument
schema has no weight to send, ``weigh_markers`` stamps the weight from the
server's table, and a stored review is re-weighed on every read — and each has
a test here. The checks are advisory and recomputed on read, so a fix shows in
the panel without another model call.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from agents.content.assessment import (
    CAPTION_MAX,
    MARKER_WEIGHTS,
    PENALTY,
    assess,
    band_for,
    compute_overall,
    compute_sanity,
    reassess,
    weigh_markers,
)
from agents.content.schema import (
    CheckSeverity,
    MarkerScore,
    ReviewBand,
    ReviewMarker,
    SanityCheckId,
    make_session,
)
from models.content import ContentPost
from tests.conftest import make_sqlite_engine


def _complete_post():
    """Every check passes on this one."""
    slides = [
        {"slide_id": "slide-01", "kind": "photo", "headline": "I did everything right and still failed",
         "image_url": "u1", "image_prompt": "p1", "image_prompt_used": "p1"},
        {"slide_id": "slide-02", "kind": "photo", "headline": "Three things it flagged",
         "image_url": "u2", "image_prompt": "p2", "image_prompt_used": "p2"},
    ]
    return slides, "First line hooks. Then the rest.", ["#color", "#style"]


def _scores(value: int = 80) -> list[MarkerScore]:
    return [MarkerScore(id=m, score=value, fix=f"fix {m.value}") for m in ReviewMarker]


def _by_id(checks):
    return {c.id: c for c in checks}


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------


def test_the_weights_cover_every_marker_and_sum_to_one():
    assert set(MARKER_WEIGHTS) == set(ReviewMarker)
    assert abs(sum(MARKER_WEIGHTS.values()) - 1.0) < 1e-9


def test_a_complete_post_passes_every_check():
    checks = compute_sanity(*_complete_post())
    assert [c.id for c in checks] == list(SanityCheckId)
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_each_failure_names_what_failed():
    slides = [
        # hook: outdated image + a fill-in left in the headline
        {"slide_id": "slide-01", "kind": "photo", "headline": "[insert hook]",
         "image_url": "u", "image_prompt": "NEW", "image_prompt_used": "OLD"},
        {"slide_id": "slide-02", "kind": "photo", "headline": "ok", "image_url": ""},
        {"slide_id": "slide-03", "kind": "text", "headline": ""},
    ]
    checks = _by_id(compute_sanity(slides, "", ["#a", "#A"]))

    assert checks[SanityCheckId.IMAGES_FRESH].offenders == ["slide-01"]
    assert checks[SanityCheckId.SLIDES_HAVE_IMAGES].offenders == ["slide-02"]
    assert checks[SanityCheckId.SLIDES_HAVE_HEADLINES].offenders == ["slide-03"]
    assert checks[SanityCheckId.NO_PLACEHOLDER_TEXT].offenders == ["slide-01"]
    assert not checks[SanityCheckId.CAPTION_PRESENT].passed
    assert checks[SanityCheckId.HASHTAGS_UNIQUE].offenders == ["#a"]
    assert checks[SanityCheckId.HASHTAGS_PRESENT].passed


def test_a_collage_cell_without_an_image_names_its_slide():
    slides = [{
        "slide_id": "slide-04", "kind": "collage", "headline": "grid",
        "items": [
            {"label": "a", "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"},
            {"label": "b", "image_url": ""},
        ],
    }]
    assert _by_id(compute_sanity(slides, "cap", ["#x"]))[SanityCheckId.SLIDES_HAVE_IMAGES].offenders == ["slide-04"]


def test_a_text_slide_needs_no_image():
    slides = [{"slide_id": "slide-01", "kind": "text", "headline": "big statement"}]
    assert _by_id(compute_sanity(slides, "cap", ["#x"]))[SanityCheckId.SLIDES_HAVE_IMAGES].passed


def test_a_caption_over_the_ceiling_is_its_own_soft_failure():
    slides, _, tags = _complete_post()
    checks = _by_id(compute_sanity(slides, "x" * (CAPTION_MAX + 1), tags))
    assert checks[SanityCheckId.CAPTION_PRESENT].passed
    assert not checks[SanityCheckId.CAPTION_LENGTH].passed
    assert checks[SanityCheckId.CAPTION_LENGTH].severity is CheckSeverity.SOFT


def test_placeholders_are_fill_ins_not_every_bracket():
    ok = _by_id(compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "headline": "the results [swipe]",
          "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"}],
        "here's what happened [results below] in [2026]", ["#x"],
    ))
    assert ok[SanityCheckId.NO_PLACEHOLDER_TEXT].passed

    bad = _by_id(compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "headline": "ok",
          "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"}],
        "TODO write the caption", ["#x"],
    ))
    assert bad[SanityCheckId.NO_PLACEHOLDER_TEXT].offenders == ["caption"]


# ---------------------------------------------------------------------------
# Scoring — the agent scores, the server weighs
# ---------------------------------------------------------------------------


def test_the_overall_is_the_weighted_score_on_a_clean_post():
    overall, content, band = compute_overall(weigh_markers(_scores(80)), compute_sanity(*_complete_post()))
    assert (overall, content, band) == (80, 80, ReviewBand.STRONG)


def test_each_failed_check_costs_its_severity():
    markers = weigh_markers(_scores(90))
    slides = [{"slide_id": "slide-01", "kind": "photo", "headline": "hook",
               "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"}]

    soft = compute_sanity(slides, "caption", ["#a", "#A"])
    assert [c.id for c in soft if not c.passed] == [SanityCheckId.HASHTAGS_UNIQUE]
    assert compute_overall(markers, soft)[0] == 90 - PENALTY[CheckSeverity.SOFT]

    hard = compute_sanity([{**slides[0], "image_url": ""}], "caption", ["#a"])
    assert [c.id for c in hard if not c.passed] == [SanityCheckId.SLIDES_HAVE_IMAGES]
    assert compute_overall(markers, hard)[0] == 90 - PENALTY[CheckSeverity.HARD]
    assert PENALTY[CheckSeverity.HARD] > PENALTY[CheckSeverity.SOFT]


def test_the_weight_comes_from_the_server_table_not_the_marker():
    """A stored or submitted weight is dropped on the way in; the reviewer's
    only lever is the score."""
    skewed = MarkerScore.model_validate({"id": "visual_quality", "score": 100, "weight": 0.99})
    (marker,) = weigh_markers([skewed])
    assert marker.weight == MARKER_WEIGHTS[ReviewMarker.VISUAL_QUALITY]
    assert "weight" not in MarkerScore.model_json_schema()["properties"]


def test_markers_come_back_in_canonical_order_and_a_rescore_wins():
    markers = weigh_markers([
        MarkerScore(id=ReviewMarker.VISUAL_QUALITY, score=50),
        MarkerScore(id=ReviewMarker.HOOK_STRENGTH, score=40),
        MarkerScore(id=ReviewMarker.HOOK_STRENGTH, score=90),
    ])
    assert [(m.id, m.score) for m in markers] == [
        (ReviewMarker.HOOK_STRENGTH, 90), (ReviewMarker.VISUAL_QUALITY, 50),
    ]


def test_a_partial_set_still_normalises_to_a_0_100_score():
    markers = weigh_markers([MarkerScore(id=ReviewMarker.HOOK_STRENGTH, score=60)])
    assert compute_overall(markers, [])[:2] == (60, 60)


def test_band_thresholds():
    assert [band_for(n) for n in (80, 79, 60, 59, 40, 39, 0)] == [
        ReviewBand.STRONG, ReviewBand.GOOD, ReviewBand.GOOD, ReviewBand.NEEDS_WORK,
        ReviewBand.NEEDS_WORK, ReviewBand.NOT_READY, ReviewBand.NOT_READY,
    ]


def test_an_unscored_post_has_checks_and_no_score():
    result = assess(*_complete_post())
    assert result.overall is None and result.band is None and not result.markers
    assert len(result.checks) == len(SanityCheckId)


# ---------------------------------------------------------------------------
# Reading a stored review back
# ---------------------------------------------------------------------------


def test_a_stored_review_is_reread_against_the_post_as_it_is_now():
    slides, caption, tags = _complete_post()
    stored = assess(slides, caption, tags, _scores(80), scored_at="2026-09-25T10:00:00+00:00").model_dump(mode="json")
    stored["markers"][0]["weight"] = 0.99          # tampered in storage
    stored["markers"].append({"id": "retired_marker", "score": 100})

    same = reassess(slides, caption, tags, stored)
    assert (same.overall, same.stale) == (80, False)
    assert same.markers[0].weight == MARKER_WEIGHTS[ReviewMarker.HOOK_STRENGTH]
    assert len(same.markers) == len(ReviewMarker)

    # The owner deletes the caption: the check fails now, the score drops by
    # its penalty, and the reviewer's judgement is flagged as from before.
    edited = reassess(slides, "", tags, stored)
    assert not _by_id(edited.checks)[SanityCheckId.CAPTION_PRESENT].passed
    assert edited.overall == 80 - PENALTY[CheckSeverity.HARD]
    assert edited.stale is True


def test_nothing_stored_reads_as_unscored():
    assert reassess(*_complete_post(), None).overall is None


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine()
    monkeypatch.setattr("agents.content.tools.get_engine", lambda: engine)
    return engine


def _post(engine, **fields):
    slides, caption, tags = _complete_post()
    row = ContentPost(project_id=fields.pop("project_id", uuid4()), post_dir_slug="launch",
                      topic="Why your colours look off", slides=slides, caption=caption,
                      hashtags=tags, status="draft", **fields)
    with Session(engine) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _submit(session, emit, payload):
    from agents.content.tools import build_content_tools_lc

    tools = {t.name: t for t in build_content_tools_lc(session.project_id, emit, session)}
    return json.loads(asyncio.run(tools["submit_assessment"].ainvoke(payload)))


def _wire(scores):
    return [s.model_dump(mode="json") for s in scores]


def test_the_tool_stores_the_review_and_shows_it(engine, emitted):
    row = _post(engine)
    session = make_session("s", row.project_id, "draft_post")
    session.post_id = row.id

    result = _submit(session, emitted, {"markers": _wire(_scores(70)), "notes": "Solid, hook is soft."})

    assert result["status"] == "ok" and result["overall"] == 70 and result["band"] == "good"
    assert result["failed_checks"] == []
    assert len(result["weakest"]) == 2
    with Session(engine) as db:
        stored = db.get(ContentPost, row.id).last_assessment
    assert stored["overall"] == 70 and stored["notes"] == "Solid, hook is soft." and stored["scored_at"]
    (event,) = emitted.events
    assert event["event"] == "post_draft_updated"
    assert event["payload"]["assessment"]["overall"] == 70


def test_the_tool_wants_all_six_markers(engine, emitted):
    row = _post(engine)
    session = make_session("s", row.project_id, "draft_post")
    session.post_id = row.id

    result = _submit(session, emitted, {"markers": _wire(_scores()[:4])})

    assert result["status"] == "error" and "visual_quality" in result["message"]
    assert not emitted.events


def test_the_tool_cannot_review_another_projects_post(engine, emitted):
    row = _post(engine)
    session = make_session("s", uuid4(), "draft_post")   # not the post's project
    session.post_id = row.id

    assert _submit(session, emitted, {"markers": _wire(_scores())})["status"] == "error"


def test_the_tool_schema_has_no_weight_and_nothing_gemini_refuses(emitted):
    """No weight anywhere the model can write one. And the schema is sent to
    every provider as a function declaration: one empty enum member makes
    Gemini reject the whole tool set."""
    from agents.content.tools import build_content_tools_lc

    session = make_session("s", uuid4(), "draft_post")
    tool = {t.name: t for t in build_content_tools_lc(session.project_id, emitted, session)}["submit_assessment"]
    schema = tool.args_schema.model_json_schema()

    def enums(node):
        if isinstance(node, dict):
            if "enum" in node:
                yield node["enum"]
            for value in node.values():
                yield from enums(value)
        elif isinstance(node, list):
            for value in node:
                yield from enums(value)

    assert sorted(next(enums(schema))) == sorted(m.value for m in ReviewMarker)
    assert all("" not in e and None not in e for e in enums(schema))
    assert '"weight"' not in json.dumps(schema)


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest.fixture
def member_client(engine):
    from db.session import get_session as get_session_dep
    from models.auth import User
    from models.membership import ProjectMember
    from models.project import Project
    import routes.content as content_routes
    import service.auth as auth_service
    from service.membership import ROLE_OWNER

    db = Session(engine)
    user = User(email="owner@example.com")
    db.add(user)
    db.commit()
    project = Project(user_id=user.id, name="Brand")
    db.add(project)
    db.commit()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ROLE_OWNER))
    db.commit()

    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    yield TestClient(app, raise_server_exceptions=False), project
    db.close()


def test_the_post_route_serves_the_review_as_it_stands(engine, member_client):
    client, project = member_client
    slides, caption, tags = _complete_post()
    row = _post(engine, project_id=project.id,
                last_assessment=assess(slides, caption, tags, _scores(80)).model_dump(mode="json"))

    served = client.get(f"/api/content/posts/{row.id}").json()["assessment"]
    assert (served["overall"], served["band"], served["stale"]) == (80, "strong", False)

    # An edit through the app: the same response carries the recomputed review.
    edited = client.patch(f"/api/content/posts/{row.id}", json={"hashtags": []}).json()["assessment"]
    assert edited["overall"] == 80 - PENALTY[CheckSeverity.SOFT]
    assert edited["stale"] is True
    assert [c["id"] for c in edited["checks"] if not c["passed"]] == ["hashtags_present"]


def test_the_board_listing_carries_no_review(engine, member_client):
    client, project = member_client
    _post(engine, project_id=project.id)
    (listed,) = client.get(f"/api/content/posts?project_id={project.id}").json()
    assert listed["assessment"] is None


# ---------------------------------------------------------------------------
# The app's mirror
# ---------------------------------------------------------------------------

APP_MIRROR = Path(__file__).resolve().parents[2] / "app" / "src" / "lib" / "contentReview.js"


@pytest.mark.parametrize("enum", [ReviewMarker, SanityCheckId, ReviewBand])
def test_the_app_words_every_id_the_backend_sends(enum):
    """The backend sends ids and the app owns the words, so an id on one side
    only is a check the panel prints raw, or a label nothing ever shows."""
    source = APP_MIRROR.read_text()
    block = re.search(rf"export const {enum.__name__} = Object\.freeze\(\{{(.*?)\}}\);", source, re.S)
    assert block, f"{enum.__name__} not found in contentReview.js"
    assert set(re.findall(r':\s*"([^"]+)"', block.group(1))) == {m.value for m in enum}
