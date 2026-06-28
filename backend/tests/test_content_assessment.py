"""Unit tests for the pre-publish review math (agents/content/assessment.py).

Pure functions, no DB / no model — this is the deterministic half of the
pre-publish review (the subjective markers are scored by the review_post
sub-agent at runtime). Covers the sanity checks, the weighting + penalty math,
and the marker-metadata normalisation.
"""

from __future__ import annotations

from agents.content.assessment import (
    HARD_PENALTY,
    MARKER_IDS,
    MARKER_WEIGHTS,
    SOFT_PENALTY,
    apply_marker_metadata,
    band_for,
    compute_overall,
    compute_sanity,
)
from agents.content.schema import ContentMarker


def _complete_post():
    """A fully complete, valid post — every sanity check should pass."""
    slides = [
        {"slide_id": "slide-01", "kind": "photo", "headline": "I did everything right and still failed",
         "image_url": "u1", "image_prompt": "p1", "image_prompt_used": "p1"},
        {"slide_id": "slide-02", "kind": "photo", "headline": "Three things it flagged",
         "image_url": "u2", "image_prompt": "p2", "image_prompt_used": "p2"},
    ]
    return slides, "First line hooks. Then the rest.", ["#color", "#style"]


def test_marker_weights_sum_to_one():
    assert abs(sum(MARKER_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(MARKER_WEIGHTS) == set(MARKER_IDS)


def test_sanity_all_pass_on_complete_post():
    slides, caption, tags = _complete_post()
    checks = compute_sanity(slides, caption, tags)
    assert {c.id for c in checks} == {
        "slides_have_images", "images_fresh", "slides_have_headlines",
        "caption_present", "no_placeholder_text", "hashtags_present",
    }
    assert all(c.passed for c in checks), [(c.id, c.detail) for c in checks if not c.passed]


def test_sanity_flags_each_failure():
    slides = [
        # hook slide: stale image (prompt changed) + placeholder text
        {"slide_id": "slide-01", "kind": "photo", "headline": "[insert hook]",
         "image_url": "u", "image_prompt": "NEW", "image_prompt_used": "OLD"},
        # photo slide missing its image
        {"slide_id": "slide-02", "kind": "photo", "headline": "ok", "image_url": ""},
        # text slide with no copy
        {"slide_id": "slide-03", "kind": "text", "headline": ""},
    ]
    checks = {c.id: c for c in compute_sanity(slides, "", ["#a", "#A"])}

    assert not checks["images_fresh"].passed and "slide-01" in checks["images_fresh"].detail
    assert not checks["slides_have_images"].passed and "slide-02" in checks["slides_have_images"].detail
    assert not checks["slides_have_headlines"].passed and "slide-03" in checks["slides_have_headlines"].detail
    assert not checks["no_placeholder_text"].passed and "slide-01" in checks["no_placeholder_text"].detail
    assert not checks["caption_present"].passed              # empty caption
    assert not checks["hashtags_present"].passed             # #a / #A duplicate


def test_collage_cell_missing_image_is_flagged():
    slides = [{
        "slide_id": "slide-04", "kind": "collage", "headline": "grid",
        "items": [
            {"label": "a", "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"},
            {"label": "b", "image_url": ""},  # missing
        ],
    }]
    checks = {c.id: c for c in compute_sanity(slides, "cap", ["#x"])}
    assert not checks["slides_have_images"].passed
    assert "cell 2" in checks["slides_have_images"].detail


def test_text_slide_without_image_is_not_flagged():
    # A text slide legitimately has no image — it must not trip slides_have_images.
    slides = [{"slide_id": "slide-01", "kind": "text", "headline": "big statement"}]
    checks = {c.id: c for c in compute_sanity(slides, "cap", ["#x"])}
    assert checks["slides_have_images"].passed


def test_caption_over_platform_limit_fails():
    slides, _, tags = _complete_post()
    checks = {c.id: c for c in compute_sanity(slides, "x" * 2201, tags)}
    assert not checks["caption_present"].passed
    assert "2,200" in checks["caption_present"].detail


def test_compute_overall_weighted_average_and_band():
    markers = apply_marker_metadata([ContentMarker(id=m, score=80) for m in MARKER_IDS])
    # No failed checks → overall == content_score == 80 → "Strong".
    clean = compute_sanity(*_complete_post())
    overall, content, band = compute_overall(markers, clean)
    assert content == 80
    assert overall == 80
    assert band == "Strong"


def test_compute_overall_applies_severity_weighted_penalty():
    markers = apply_marker_metadata([ContentMarker(id=m, score=80) for m in MARKER_IDS])
    sanity = compute_sanity([{"slide_id": "slide-01", "kind": "photo", "headline": ""}], "", ["#x"])
    failed = [c for c in sanity if not c.passed]
    assert failed
    expected_penalty = sum(HARD_PENALTY if c.severity == "hard" else SOFT_PENALTY for c in failed)
    overall, content, _ = compute_overall(markers, sanity)
    assert content == 80
    assert overall == max(0, 80 - expected_penalty)


def test_soft_failure_costs_less_than_hard():
    markers = apply_marker_metadata([ContentMarker(id=m, score=90) for m in MARKER_IDS])
    slides_ok, caption_ok = [
        {"slide_id": "slide-01", "kind": "photo", "headline": "hook",
         "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"},
    ], "caption here"

    # Only a soft failure: duplicate hashtags.
    soft = compute_sanity(slides_ok, caption_ok, ["#a", "#A"])
    assert [c.id for c in soft if not c.passed] == ["hashtags_present"]
    overall_soft, _, _ = compute_overall(markers, soft)
    assert overall_soft == 90 - SOFT_PENALTY

    # Only a hard failure: missing image.
    hard = compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "headline": "hook", "image_url": ""}],
        caption_ok, ["#a"],
    )
    assert [c.id for c in hard if not c.passed] == ["slides_have_images"]
    overall_hard, _, _ = compute_overall(markers, hard)
    assert overall_hard == 90 - HARD_PENALTY
    assert HARD_PENALTY > SOFT_PENALTY


def test_bracket_regex_ignores_legit_asides_flags_fillins():
    # Legit bracketed asides must NOT trip the placeholder check.
    ok = {c.id: c for c in compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "headline": "the results [swipe]",
          "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"}],
        "here's what happened [results below] in [2026]", ["#x"],
    )}
    assert ok["no_placeholder_text"].passed

    # Real fill-in templates must trip it.
    bad = {c.id: c for c in compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "headline": "hi [insert hook]",
          "image_url": "u", "image_prompt": "p", "image_prompt_used": "p"}],
        "cap", ["#x"],
    )}
    assert not bad["no_placeholder_text"].passed


# ---------------------------------------------------------------------------
# Video-post sanity (post_type="video") — checks the storyboard + clip, not slides.
# ---------------------------------------------------------------------------

def _complete_video():
    """A fully animated video post — every video sanity check should pass."""
    beats = [
        {"beat_id": "beat-01", "role": "hook", "on_screen_text": "wrong cut era",
         "image_url": "u1", "image_prompt": "p1", "image_prompt_used": "p1"},
        {"beat_id": "beat-02", "role": "reveal", "on_screen_text": "right cut",
         "image_url": "u2", "image_prompt": "p2", "image_prompt_used": "p2",
         "end_image_url": "e2", "end_image_prompt": "ep2", "end_image_prompt_used": "ep2"},
    ]
    return beats, "First line hooks. Then the rest.", ["#hair", "#bangs"]


def _video_kwargs(beats, video_url="clip.mp4", video_prompt="slow push in"):
    return dict(
        post_type="video", video_url=video_url,
        video_storyboard=beats, video_prompt=video_prompt,
    )


def test_video_sanity_all_pass_on_complete_clip():
    beats, caption, tags = _complete_video()
    checks = compute_sanity([], caption, tags, **_video_kwargs(beats))
    assert {c.id for c in checks} == {
        "video_present", "keyframes_generated", "keyframes_fresh",
        "caption_present", "no_placeholder_text", "hashtags_present",
    }
    assert all(c.passed for c in checks), [(c.id, c.detail) for c in checks if not c.passed]


def test_video_sanity_flags_missing_clip_and_keyframes():
    beats = [
        # hook beat: keyframe never generated + placeholder overlay text
        {"beat_id": "beat-01", "role": "hook", "on_screen_text": "[insert hook]",
         "image_prompt": "p1", "image_url": ""},
        # reveal beat: stale first keyframe + missing after-frame
        {"beat_id": "beat-02", "role": "reveal", "on_screen_text": "ok",
         "image_url": "u", "image_prompt": "NEW", "image_prompt_used": "OLD",
         "end_image_prompt": "ep", "end_image_url": ""},
    ]
    checks = {c.id: c for c in compute_sanity(
        [], "", ["#a", "#A"], **_video_kwargs(beats, video_url="")
    )}
    assert not checks["video_present"].passed
    assert not checks["keyframes_generated"].passed and "beat-01" in checks["keyframes_generated"].detail
    assert "after-frame" in checks["keyframes_generated"].detail   # beat-02 end frame missing
    assert not checks["keyframes_fresh"].passed and "beat-02" in checks["keyframes_fresh"].detail
    assert not checks["no_placeholder_text"].passed and "beat-01" in checks["no_placeholder_text"].detail
    assert not checks["caption_present"].passed                    # empty caption
    assert not checks["hashtags_present"].passed                   # #a / #A duplicate


def test_video_sanity_ignores_slides_and_slideshow_uses_beats_safely():
    # A video post never trips slide checks even if a stray slides list is passed.
    beats, caption, tags = _complete_video()
    checks = {c.id: c for c in compute_sanity(
        [{"slide_id": "slide-01", "kind": "photo", "image_url": ""}],  # would fail slideshow
        caption, tags, **_video_kwargs(beats),
    )}
    assert "slides_have_images" not in checks
    assert checks["video_present"].passed


def test_video_placeholder_scans_motion_brief():
    beats, caption, tags = _complete_video()
    checks = {c.id: c for c in compute_sanity(
        [], caption, tags, **_video_kwargs(beats, video_prompt="push in on [insert subject]")
    )}
    assert not checks["no_placeholder_text"].passed
    assert "video_prompt" in checks["no_placeholder_text"].detail


def test_apply_marker_metadata_fills_and_filters():
    markers = apply_marker_metadata([
        ContentMarker(id="visual_quality", score=50),
        ContentMarker(id="hook_strength", score=90),
        ContentMarker(id="bogus_id", score=100),  # dropped
    ])
    assert [m.id for m in markers] == ["hook_strength", "visual_quality"]  # canonical order
    assert all(m.weight > 0 and m.label for m in markers)


def test_partial_markers_normalise_weighting():
    # Only one marker scored → content_score equals that marker's score.
    markers = apply_marker_metadata([ContentMarker(id="hook_strength", score=60)])
    overall, content, _ = compute_overall(markers, [])
    assert content == 60 and overall == 60


def test_band_thresholds():
    assert band_for(80) == "Strong"
    assert band_for(79) == "Good"
    assert band_for(60) == "Good"
    assert band_for(59) == "Needs work"
    assert band_for(40) == "Needs work"
    assert band_for(39) == "Not ready"
