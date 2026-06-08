"""Renderer structural contract — guards against templates.py drifting from its
JS mirror (app/src/lib/slideDoc.js, the live-preview renderer).

If preview ≠ published render, the user edits one thing and ships another. This
test locks the Python renderer's structure; app/scripts/check-slide-parity.mjs
asserts the SAME contract on the JS side. Change a renderer's structure → change
BOTH this file and that script.
"""

from agents.content.schema import Slide, SlideItem
from agents.content.templates import render_slides_html

# (slide, tokens that MUST appear in the rendered markup). Keep in lockstep with
# app/scripts/check-slide-parity.mjs.
CASES = [
    (
        Slide(slide_id="s1", kind="photo", caption_style="hook",
              headline="hi", subtext="sub", image_prompt="p"),
        ["slide-hook", "hook-headline", "hook-sub", "img-placeholder", "cap-bottom"],
    ),
    (
        Slide(slide_id="s2", kind="photo", caption_style="cap-pill",
              headline="x", image_url="/u/a.png", image_prompt="q", image_prompt_used="q"),
        ["slide-hook", "cap-pill", 'class="bg"'],
    ),
    (
        Slide(slide_id="s3", kind="text", headline="stmt"),
        ["slide-body", "body-statement"],
    ),
    (
        Slide(slide_id="s4", kind="collage", headline="title",
              items=[SlideItem(label="a", image_prompt="x")]),
        ["slide-collage", "collage-grid", "ctitle", "cell-label", "cell-ph"],
    ),
    (
        Slide(slide_id="s5", kind="before-after",
              items=[SlideItem(marker="dont", image_prompt="d"), SlideItem(marker="do", image_prompt="o")]),
        ["slide-ba", "ba-half", "ba-marker dont", "ba-marker do"],
    ),
    (
        Slide(slide_id="s6", kind="editorial", headline="Edit", subtext="sub", image_prompt="x"),
        ["slide-editorial", "ed-frame", 'class="et"', 'class="es"'],
    ),
]


def test_render_structural_contract():
    for slide, must in CASES:
        html = render_slides_html("full-bleed", [slide])
        for token in must:
            assert token in html, f"{slide.kind}: renderer missing {token!r}"
