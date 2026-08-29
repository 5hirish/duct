"""Offline unit tests for the agent evaluation harness (tests/eval).

These run in the normal (no-network) suite — they guard the scoring logic, the
rubric rendering, the credential resolution, and the content rubric/artifact
helpers so the harness itself can't silently regress. The live judge call is
exercised separately in test_content_post_e2e.py (@pytest.mark.live).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.eval import (
    Dimension,
    DimensionScore,
    JudgeVerdict,
    Marker,
    MarkerVerdict,
    Rubric,
    build_scorecard,
    resolve_judge_api_key,
)
from tests.eval.client import judge_available
from tests.eval.judge import _parse_verdict
from tests.eval.prompts import render_rubric
from tests.eval.rubrics.content_post import build_content_post_artifact, content_post_rubric


def _rubric() -> Rubric:
    return Rubric(
        name="demo",
        pass_threshold=3.5,
        dimensions=[
            Dimension("a", "Axis A", "desc a", weight=2.0, min_score=3),
            Dimension("b", "Axis B", "desc b", weight=1.0, min_score=1),
        ],
        markers=[
            Marker("must", "a required thing", kind="required"),
            Marker("nope", "a forbidden thing", kind="forbidden"),
        ],
    )


def _verdict(a: int, b: int, *, must: bool, nope: bool) -> JudgeVerdict:
    return JudgeVerdict(
        dimensions=[
            DimensionScore(key="a", score=a, rationale="r"),
            DimensionScore(key="b", score=b, rationale="r"),
        ],
        markers=[
            MarkerVerdict(key="must", satisfied=must, evidence="e"),
            MarkerVerdict(key="nope", satisfied=nope, evidence="e"),
        ],
        summary="s",
    )


def test_scorecard_passes_when_all_gates_clear():
    sc = build_scorecard(_rubric(), _verdict(4, 5, must=True, nope=False))
    # weighted overall = (2*4 + 1*5) / 3 = 4.333
    assert sc.passed is True
    assert round(sc.overall, 2) == 4.33
    assert sc.failures == []
    assert sc.dimension_scores == {"a": 4, "b": 5}


# Four independent gates, each of which alone must fail the scorecard. Every row
# is otherwise a passing verdict, so the named gate is the only thing under test.
@pytest.mark.parametrize(
    ("gate", "scores", "must", "nope", "failure_text"),
    [
        ("dimension min score", (2, 5), True, False, "scored 2 < required minimum 3"),
        ("required marker unsatisfied", (4, 4), False, False, "required marker 'must'"),
        ("forbidden marker present", (4, 4), True, True, "forbidden marker 'nope'"),
        # a=3 clears its min, but b=1 drags the weighted overall to (6+1)/3=2.33
        ("weighted overall below threshold", (3, 1), True, False, "pass threshold"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_scorecard_fails_on(gate, scores, must, nope, failure_text):
    sc = build_scorecard(_rubric(), _verdict(*scores, must=must, nope=nope))
    assert sc.passed is False, gate
    assert any(failure_text in f for f in sc.failures), (gate, sc.failures)


def test_scorecard_flags_missing_dimension():
    verdict = JudgeVerdict(
        dimensions=[DimensionScore(key="a", score=4, rationale="r")],  # 'b' missing
        markers=[
            MarkerVerdict(key="must", satisfied=True, evidence="e"),
            MarkerVerdict(key="nope", satisfied=False, evidence="e"),
        ],
        summary="s",
    )
    sc = build_scorecard(_rubric(), verdict)
    assert sc.passed is False
    assert any("dimension 'b' missing" in f for f in sc.failures)


def test_scorecard_markdown_and_dict_roundtrip():
    sc = build_scorecard(_rubric(), _verdict(4, 5, must=True, nope=False))
    md = sc.as_markdown()
    assert "Eval scorecard — demo" in md and "PASS" in md
    d = sc.as_dict()
    assert d["passed"] is True and d["overall"] == 4.33 and d["rubric"] == "demo"


def test_render_rubric_lists_every_key():
    text = render_rubric(_rubric())
    for key in ("`a`", "`b`", "`must`", "`nope`"):
        assert key in text


def test_judge_system_prompt_embeds_persona():
    from tests.eval.prompts import build_judge_system_prompt

    assert "Evaluate as this end user" not in build_judge_system_prompt("")
    with_persona = build_judge_system_prompt("a sound-off TikTok scroller")
    assert "a sound-off TikTok scroller" in with_persona
    assert "Evaluate as this end user" in with_persona


def test_parse_verdict_handles_json_fence():
    # Gemini responses expose the text via resp.text; tolerate a ```json fence.
    resp = SimpleNamespace(text=(
        '```json\n{"dimensions":[{"key":"a","score":3,"rationale":"r"}],'
        '"markers":[],"summary":"ok"}\n```'
    ))
    verdict = _parse_verdict(resp)
    assert verdict.dimensions[0].key == "a" and verdict.dimensions[0].score == 3


def test_resolve_judge_api_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-123")
    assert resolve_judge_api_key() == "g-123"


def test_judge_unavailable_without_any_credential(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # Neutralise any backend/.env fallback so this asserts the no-cred path.
    monkeypatch.setattr("tests.eval.client._config_cred", lambda _name: "")
    assert judge_available() is False


def test_content_rubric_shape_is_stable():
    rubric = content_post_rubric()
    keys = set(rubric.dimension_keys())
    assert {"hook", "image_quality", "image_fidelity", "cohesion"}.issubset(keys)
    assert {"mentions_ai", "single_hook_emotion"}.issubset(set(rubric.marker_keys()))
    # Hook and image quality carry the heaviest weight — they're what degrades first.
    weights = {d.key: d.weight for d in rubric.dimensions}
    assert weights["hook"] >= 1.5 and weights["image_quality"] >= 1.5
    # The content judge evaluates as a short-form viewer persona.
    assert rubric.persona and "scroll" in rubric.persona.lower()


def test_build_content_post_artifact_renders_copy_and_flags_missing_images():
    post = SimpleNamespace(
        pillar="grooming", topic="jawline mistakes", layout="full-bleed",
        hook_emotion="frustration", hook_type="identity_challenge",
        hook_text="You did everything right and still…", save_cta="(save for slide 3)",
        bridge_text="I found this free app", emotional_arc="build → reveal",
        strategic_note="loops the pillar", visual_brief="soft daylight",
        caption="the mistake nobody told you", hashtags=["#grooming", "#jawline"],
        tiktok_title="3 mistakes", slides=[
            {"slide_id": "slide-01", "role": "hook", "kind": "photo",
             "headline": "Still no jawline?", "image_prompt": "man, soft light", "image_url": "/uploads/x.png"},
            {"slide_id": "slide-02", "role": "finding", "kind": "photo",
             "headline": "Three things", "image_prompt": "closeup"},  # no image_url → MISSING
        ],
    )
    artifact = build_content_post_artifact(post, brand_summary="MaxAura — men's grooming", images=[])
    assert "Still no jawline?" in artifact.body
    assert "image=yes" in artifact.body and "image=MISSING" in artifact.body
    assert artifact.title.startswith("jawline mistakes")
