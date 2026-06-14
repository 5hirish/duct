"""Rubric + artifact renderer for the Content Studio agent's post deliverable.

The dimensions and markers below are lifted straight from the agent's own
success criteria in ``agents/content/prompts.py`` (the quality standard, the
mandatory single hook emotion, the mystery architecture, the actionable-content
placement, and the "never say AI / no slide counters" rules). Grading against
the same bar the prompt sets is what lets this catch degradation: if a future
model drifts off these, the scores drop even though the JSON still validates.
"""

from __future__ import annotations

from typing import Any

from tests.eval.judge import JudgeArtifact, JudgeImage
from tests.eval.rubric import Dimension, Marker, Rubric


def content_post_rubric() -> Rubric:
    """The grading rubric for a finished TikTok/short-form post (copy + images)."""
    return Rubric(
        name="content_post_tiktok",
        pass_threshold=3.6,
        dimensions=[
            Dimension(
                "hook",
                "Hook strength",
                "Slide 1 commits to ONE clear emotion (frustration / shock / disbelief / "
                "anger / sadness) and is legible to a sound-off skimmer. It stops the scroll "
                "without being clickbait the post can't pay off.",
                weight=1.5,
                min_score=3,
            ),
            Dimension(
                "mystery_architecture",
                "Mystery architecture",
                "Slide 2 opens a numbered loop and defers the most powerful item; the post "
                "reads as an unfolding story, NOT a clean list the viewer can exit after any "
                "slide. The actionable payoff lands around slide 3–4 and the full reveal later.",
                weight=1.0,
                min_score=2,
            ),
            Dimension(
                "actionability",
                "Actionability & specificity",
                "Payload slides carry named techniques, exact phrases, numbers or "
                "measurements — concrete enough to screenshot and act on tomorrow. Vague, "
                "generic advice scores low.",
                weight=1.0,
                min_score=3,
            ),
            Dimension(
                "brand_alignment",
                "Brand & audience fit",
                "Topic, voice, and angle match the brand's audience, value proposition and "
                "voice, and respect its do-not-say constraints. Off-brand or generic content "
                "scores low.",
                weight=1.0,
                min_score=3,
            ),
            Dimension(
                "copy_quality",
                "Caption & metadata quality",
                "The caption, hashtags and title are natural, on-platform, and reinforce the "
                "hook — not keyword-stuffed, not robotic, not a press release.",
                weight=0.5,
                min_score=2,
            ),
            Dimension(
                "image_quality",
                "Image quality",
                "The generated images are coherent, well-composed, and legible at thumbnail "
                "size — not garbled, duplicated-limbs, warped-text, watermarked, or obviously "
                "AI-artifacted. Judge the actual pixels.",
                weight=1.5,
                min_score=3,
            ),
            Dimension(
                "image_fidelity",
                "Image ↔ slide fidelity",
                "Each image matches its slide's intent and image prompt and supports that "
                "slide's copy; the set is consistent in subject, lighting and style across "
                "slides (looks like one shoot, not seven strangers).",
                weight=1.0,
                min_score=3,
            ),
            Dimension(
                "cohesion",
                "End-to-end cohesion",
                "Copy and images together tell one coherent story across the stated emotional "
                "arc, from hook through the slide-6 bridge to the CTA.",
                weight=1.0,
                min_score=3,
            ),
        ],
        markers=[
            Marker(
                "no_ai_mention",
                "The slides or caption explicitly say 'AI' / 'AI-powered', or describe an "
                "AI/LLM analysing something. The brand voice forbids naming AI on-platform.",
                kind="forbidden",
            ),
            Marker(
                "no_slide_counters",
                "Slides use list counters such as '1/4', '2/5' or 'tip 3' that signal a list "
                "and invite the viewer to exit after each slide.",
                kind="forbidden",
            ),
            Marker(
                "single_hook_emotion",
                "Slide 1 commits to a single clear emotional frame rather than a muddled mix.",
                kind="required",
            ),
            Marker(
                "save_worthy_payoff",
                "There is a concrete, save-worthy payoff (a self-test, a measurement, or an "
                "exact phrase to use) that a viewer would screenshot.",
                kind="required",
            ),
        ],
    )


def _slide_has_image(slide: dict) -> bool:
    if slide.get("image_url"):
        return True
    return any((cell or {}).get("image_url") for cell in (slide.get("items") or []))


def build_content_post_artifact(
    post: Any,
    *,
    brand_summary: str,
    images: list[JudgeImage],
    eval_note: str = "",
) -> JudgeArtifact:
    """Render a persisted ``ContentPost`` (duck-typed) into a judge artifact.

    ``post`` only needs the ContentPost attributes (``slides``, ``caption``, …);
    the model class itself is not imported here so the rubric stays decoupled
    from the DB layer. ``images`` are the already-loaded slide images.
    ``eval_note``, when set, is surfaced to the judge first (e.g. to explain a
    reduced fast-mode run so it doesn't penalise intentionally-missing images).
    """
    lines: list[str] = []
    if eval_note:
        lines += [f"EVALUATION NOTE: {eval_note}", ""]
    lines += [
        "BRAND CONTEXT:",
        brand_summary,
        "",
        f"PILLAR: {post.pillar}",
        f"TOPIC: {post.topic}",
        f"LAYOUT: {post.layout}",
        f"CLAIMED HOOK EMOTION: {post.hook_emotion}",
        f"HOOK TYPE: {post.hook_type}",
        f"HOOK TEXT: {post.hook_text}",
        f"SAVE CTA: {post.save_cta}",
        f"BRIDGE (slide 6): {post.bridge_text}",
        f"EMOTIONAL ARC: {post.emotional_arc}",
        f"STRATEGIC NOTE: {post.strategic_note}",
        f"VISUAL BRIEF: {post.visual_brief}",
        f"CAPTION: {post.caption}",
        f"HASHTAGS: {' '.join(post.hashtags or [])}",
        f"TIKTOK TITLE: {post.tiktok_title}",
        "",
        "SLIDES (in order):",
    ]
    for slide in (post.slides or []):
        sid = slide.get("slide_id", "?")
        has_img = "yes" if _slide_has_image(slide) else "MISSING"
        lines.append(
            f"  [{sid}] role={slide.get('role', '')} kind={slide.get('kind', '')} "
            f"caption_style={slide.get('caption_style', '')} image={has_img}"
        )
        if slide.get("headline"):
            lines.append(f"      headline: {slide['headline']}")
        if slide.get("subtext"):
            lines.append(f"      subtext: {slide['subtext']}")
        if slide.get("image_prompt"):
            lines.append(f"      image_prompt: {slide['image_prompt']}")
        for j, cell in enumerate(slide.get("items") or []):
            cell = cell or {}
            cell_img = "yes" if cell.get("image_url") else "MISSING"
            lines.append(
                f"      cell[{j}] label={cell.get('label', '')} marker={cell.get('marker', '')} "
                f"image={cell_img} prompt={cell.get('image_prompt', '')}"
            )

    return JudgeArtifact(
        title=f"{post.topic} — {post.pillar}",
        body="\n".join(lines),
        images=images,
    )
