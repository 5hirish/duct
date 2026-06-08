"""Deterministic slide → HTML renderer for the Content Marketing Agent.

The orchestrator authors structured `Slide` objects (copy + an image prompt);
this module renders the final `slides_html` document. The model NEVER writes
raw HTML — that removes the old "parse JSON containing a 10KB HTML string"
fragility and keeps every post on the same vetted slide engine + caption CSS.

Design, mirroring the reporting agent's structured-content → template pattern:

  - One renderer per slide `kind` (photo / text; collage + before-after land in
    Phase 5). The post-level `layout` selects the template family + aesthetic.
  - Captions are HTML OVERLAYS (the cap-* / hook / body-* classes from
    styles.py), never baked into the image. So a pure caption edit re-renders
    instantly and the generated image stays valid.
  - When a slide has no image yet, its image slot renders a PLACEHOLDER that
    displays the image prompt — so the user reviews/edits the prompt in-preview
    before any image is generated (soft-gated image generation).

CSS is the full style registry (`css_for(None)` = base engine + every caption
style), so any `caption_style` the agent picks always resolves regardless of a
format's curated `linked_styles`.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from agents.content.styles import css_for

if TYPE_CHECKING:  # avoid a hard import cycle at module load
    from agents.content.schema import Slide, SlideLayout


# ---------------------------------------------------------------------------
# Renderer-owned CSS — the image placeholder. Everything else comes from the
# shared style registry so the Library preview and the live preview match.
# ---------------------------------------------------------------------------

_PLACEHOLDER_CSS = """\
/* Image placeholder — shown until the slide's image is generated. The prompt
   IS the placeholder content so it can be reviewed/edited before image gen. */
.img-placeholder {
  position: absolute; inset: 0; z-index: 1;
  background:
    radial-gradient(120% 80% at 50% 0%, #1b1e25 0%, #101216 70%),
    repeating-linear-gradient(135deg, transparent, transparent 30px,
      rgba(255,255,255,0.018) 30px, rgba(255,255,255,0.018) 60px);
  display: flex; align-items: center; justify-content: center;
  padding: 140px var(--safe-left) calc(var(--safe-bottom) + 48px);
}
.img-placeholder.is-stale { outline: 8px solid rgba(245,158,66,0.55); outline-offset: -8px; }
.img-placeholder-inner {
  max-width: 780px; text-align: center;
  border: 3px dashed rgba(255,255,255,0.22); border-radius: 30px;
  padding: 52px 44px; background: rgba(0,0,0,0.30);
}
.img-ph-badge {
  display: inline-block; margin-bottom: 26px; padding: 9px 22px;
  border-radius: 999px; background: rgba(255,255,255,0.10);
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 26px; font-weight: 700; letter-spacing: 2.5px; text-transform: uppercase;
  color: rgba(255,255,255,0.60);
}
.img-ph-badge.is-stale { background: rgba(245,158,66,0.20); color: rgba(245,158,66,0.95); }
.img-ph-prompt {
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 34px; line-height: 1.5; font-weight: 400; color: rgba(255,255,255,0.84);
}
.img-ph-prompt.is-empty { color: rgba(255,255,255,0.40); font-style: italic; }
/* Banner over a generated image whose prompt changed after it was made. */
.img-stale-flag {
  position: absolute; top: var(--safe-top); left: 50%; transform: translateX(-50%);
  z-index: 25; max-width: 80%; text-align: center;
  padding: 14px 28px; border-radius: 999px;
  background: rgba(245,158,66,0.92); color: #1a1205;
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 28px; font-weight: 800; letter-spacing: 0.3px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.35);
}
"""

# ---------------------------------------------------------------------------
# Multi-image layout scaffolding (collage / before-after / editorial). Kept
# with the renderer rather than the caption-style registry — this is structural
# layout CSS, not a previewable caption style.
# ---------------------------------------------------------------------------

_LAYOUT_CSS = """\
/* Compact image cell (collage grid cell, before/after half, editorial frame) */
.cell { position: relative; overflow: hidden; background: #15171c; }
.cell .cell-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.cell-ph {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  padding: 26px; text-align: center;
  background:
    radial-gradient(120% 80% at 50% 0%, #1b1e25 0%, #101216 70%),
    repeating-linear-gradient(135deg, transparent, transparent 22px,
      rgba(255,255,255,0.02) 22px, rgba(255,255,255,0.02) 44px);
}
.cell-ph.is-stale { outline: 6px solid rgba(245,158,66,0.55); outline-offset: -6px; }
.cell-ph-text { font-family: 'Inter', system-ui, sans-serif; font-size: 23px; line-height: 1.45; color: rgba(255,255,255,0.80); }
.cell-ph-text.is-empty { color: rgba(255,255,255,0.4); font-style: italic; }
.cell-stale-flag {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%); z-index: 6;
  padding: 7px 18px; border-radius: 999px; background: rgba(245,158,66,0.94); color: #1a1205;
  font-family: 'Inter', system-ui, sans-serif; font-size: 19px; font-weight: 800; white-space: nowrap;
}

/* Collage — 2×2 grid with serif cell labels + optional serif title */
.slide-collage { background: #0d0d0d; display: flex; flex-direction: column; }
.collage-title { padding: 90px var(--safe-left) 26px; text-align: center; z-index: 10; }
.collage-title .ctitle {
  font-family: 'Playfair Display', serif; font-style: italic; font-weight: 700;
  font-size: 70px; line-height: 1.08; color: #fff;
}
.collage-grid {
  flex: 1; display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 1fr;
  gap: 10px; padding: 0 32px calc(var(--safe-bottom) - 80px);
}
.collage-grid .cell { border-radius: 18px; }
.cell-label {
  position: absolute; bottom: 0; left: 0; right: 0; z-index: 3; padding: 30px 22px 18px;
  background: linear-gradient(to top, rgba(0,0,0,0.80), transparent);
  font-family: 'Playfair Display', serif; font-style: italic; font-weight: 600;
  font-size: 38px; color: #fff; text-align: center;
}

/* Before / after — two stacked halves with ✕ DON'T / ✓ DO markers */
.slide-ba { background: #0d0d0d; display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.slide-ba .ba-half { position: relative; flex: 1; overflow: hidden; border-radius: 20px; }
.ba-marker {
  position: absolute; top: 26px; left: 26px; z-index: 6; padding: 12px 26px; border-radius: 999px;
  font-family: 'Inter', system-ui, sans-serif; font-size: 38px; font-weight: 900; letter-spacing: 1px;
}
.ba-marker.dont { background: rgba(220,38,38,0.95); color: #fff; }
.ba-marker.do   { background: rgba(22,163,74,0.95); color: #fff; }
.ba-half .cell-label {
  font-family: 'Inter', system-ui, sans-serif; font-style: normal; font-weight: 800;
  font-size: 44px; padding: 44px 30px 28px;
}

/* Editorial — single image on an ivory matte, Playfair serif caption */
.slide-editorial {
  background: #f4efe7; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 120px 92px calc(var(--safe-bottom) - 30px);
}
.slide-editorial .ed-frame {
  position: relative; width: 100%; flex: 1; max-height: 1180px;
  border-radius: 8px; overflow: hidden; box-shadow: 0 30px 80px rgba(60,40,20,0.20);
}
.slide-editorial .ed-title { margin-top: 46px; text-align: center; }
.slide-editorial .ed-title .et {
  font-family: 'Playfair Display', serif; font-weight: 700; font-size: 76px; line-height: 1.06; color: #2a2118;
}
.slide-editorial .ed-title .es {
  display: block; margin-top: 18px; font-family: 'Inter', system-ui, sans-serif;
  font-size: 36px; font-weight: 400; letter-spacing: 2px; text-transform: uppercase; color: #6b5d4a;
}
"""

_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Inter:wght@300;400;500;600;700;800;900&"
    "family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap\" rel=\"stylesheet\">"
)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """HTML-escape attribute/text content."""
    return html.escape(text or "", quote=True)


def _esc_caption(text: str) -> str:
    """Escape caption copy but honour intentional line breaks.

    The agent may use a literal newline OR a `<br>` to force a wrap (the style
    previews use `<br>`). We escape everything, then restore those two cases so
    no other markup can be injected.
    """
    safe = html.escape(text or "", quote=False)
    safe = safe.replace("\n", "<br>")
    safe = safe.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br>").replace("&lt;br /&gt;", "<br>")
    return safe


# ---------------------------------------------------------------------------
# Caption block — maps a caption_style to the registry's markup contract
# ---------------------------------------------------------------------------


def _caption_inner(caption_style: str, headline: str, subtext: str) -> str:
    """Inner markup for a `.cap-bottom` block, per the style's CSS contract."""
    h = _esc_caption(headline)
    s = _esc_caption(subtext)

    if caption_style == "hook":
        out = f'<span class="hook-headline">{h}</span>'
        if subtext:
            out += f'<span class="hook-sub">{s}</span>'
        return out

    if caption_style == "cap-pill":
        out = f'<span class="cap-pill-wrap"><span class="cap-pill">{h}</span></span>'
        if subtext:
            out += f'<span class="cap-pill-sub"><span>{s}</span></span>'
        return out

    # cap-stroke / cap-raw / cap-whisper share the <main> + <main>-sub contract.
    style = caption_style if caption_style in ("cap-stroke", "cap-raw", "cap-whisper") else "cap-stroke"
    out = f'<span class="{style}">{h}</span>'
    if subtext:
        out += f'<span class="{style}-sub">{s}</span>'
    return out


# ---------------------------------------------------------------------------
# Image slot — real <img> once generated, else the prompt-as-placeholder
# ---------------------------------------------------------------------------


def _image_layer(slide: "Slide") -> str:
    alt = _esc(slide.image_prompt or slide.headline or slide.slide_id)
    if slide.image_url:
        img = f'<img class="bg" src="{_esc(slide.image_url)}" alt="{alt}">'
        if slide.is_image_stale():
            img += '<div class="img-stale-flag">image outdated — regenerate to match the new prompt</div>'
        return img

    stale_cls = ""
    badge = f"image · {_esc(slide.aspect_ratio.value)}"
    if slide.role:
        badge += f" · {_esc(slide.role)}"
    if slide.image_prompt.strip():
        prompt_html = f'<div class="img-ph-prompt">{_esc_caption(slide.image_prompt)}</div>'
    else:
        prompt_html = '<div class="img-ph-prompt is-empty">no image prompt yet</div>'
    return (
        f'<div class="img-placeholder{stale_cls}">'
        f'<div class="img-placeholder-inner">'
        f'<div class="img-ph-badge{stale_cls}">{badge}</div>'
        f"{prompt_html}"
        f"</div></div>"
    )


# ---------------------------------------------------------------------------
# Per-kind slide renderers
# ---------------------------------------------------------------------------


def _render_photo_slide(slide: "Slide", n: int) -> str:
    """Full-bleed photo (or placeholder) + bottom-anchored caption overlay."""
    caption = ""
    if slide.headline or slide.subtext:
        caption = f'<div class="cap-bottom">{_caption_inner(slide.caption_style, slide.headline, slide.subtext)}</div>'
    return (
        f'<div class="slide slide-hook" id="slide-{n:02d}">'
        f"{_image_layer(slide)}"
        f'<div class="grad"></div>'
        f"{caption}"
        f"</div>"
    )


def _render_text_slide(slide: "Slide", n: int) -> str:
    """Dark text card — the native-TikTok-text fallback (body-neutral)."""
    body = f'<span class="body-statement">{_esc_caption(slide.headline)}</span>'
    if slide.subtext:
        body += f'<span class="body-sub">{_esc_caption(slide.subtext)}</span>'
    return (
        f'<div class="slide slide-body" id="slide-{n:02d}">'
        f'<div class="body-content">{body}</div>'
        f"</div>"
    )


def _img_or_ph(image_url: str, image_prompt: str, image_prompt_used: str) -> str:
    """A compact image cell: the real <img> (with an 'outdated' chip when its
    prompt changed) or a prompt-as-placeholder. Shared by collage cells,
    before/after halves, and the editorial frame."""
    stale = bool(image_url) and (image_prompt or "").strip() != (image_prompt_used or "").strip()
    if image_url:
        out = f'<img class="cell-img" src="{_esc(image_url)}" alt="{_esc(image_prompt)}">'
        if stale:
            out += '<div class="cell-stale-flag">outdated</div>'
        return out
    if (image_prompt or "").strip():
        return f'<div class="cell-ph"><div class="cell-ph-text">{_esc_caption(image_prompt)}</div></div>'
    return '<div class="cell-ph"><div class="cell-ph-text is-empty">no prompt yet</div></div>'


def _render_collage_slide(slide: "Slide", n: int) -> str:
    """2×2 grid of image cells with serif labels + an optional serif title."""
    title = ""
    if slide.headline:
        title = f'<div class="collage-title"><span class="ctitle">{_esc_caption(slide.headline)}</span></div>'
    cells = []
    for it in slide.items[:4]:
        label = f'<div class="cell-label">{_esc_caption(it.label)}</div>' if it.label else ""
        cells.append(
            f'<div class="cell">{_img_or_ph(it.image_url, it.image_prompt, it.image_prompt_used)}{label}</div>'
        )
    return (
        f'<div class="slide slide-collage" id="slide-{n:02d}">'
        f"{title}"
        f'<div class="collage-grid">{"".join(cells)}</div>'
        f"</div>"
    )


_BA_DEFAULT_MARKERS = ("dont", "do")


def _render_before_after_slide(slide: "Slide", n: int) -> str:
    """Two stacked halves with ✕ DON'T / ✓ DO markers."""
    halves = []
    for i, it in enumerate(slide.items[:2]):
        marker = it.marker or (_BA_DEFAULT_MARKERS[i] if i < 2 else "")
        if marker == "dont":
            mk = "<div class=\"ba-marker dont\">✕ DON'T</div>"
        elif marker == "do":
            mk = '<div class="ba-marker do">✓ DO</div>'
        else:
            mk = ""
        label = f'<div class="cell-label">{_esc_caption(it.label)}</div>' if it.label else ""
        halves.append(
            f'<div class="ba-half cell">{_img_or_ph(it.image_url, it.image_prompt, it.image_prompt_used)}{mk}{label}</div>'
        )
    return f'<div class="slide slide-ba" id="slide-{n:02d}">{"".join(halves)}</div>'


def _render_editorial_slide(slide: "Slide", n: int) -> str:
    """Single image on an ivory matte with a Playfair serif caption."""
    frame = f'<div class="ed-frame cell">{_img_or_ph(slide.image_url, slide.image_prompt, slide.image_prompt_used)}</div>'
    title = ""
    if slide.headline or slide.subtext:
        t = f'<span class="et">{_esc_caption(slide.headline)}</span>' if slide.headline else ""
        s = f'<span class="es">{_esc_caption(slide.subtext)}</span>' if slide.subtext else ""
        title = f'<div class="ed-title">{t}{s}</div>'
    return f'<div class="slide slide-editorial" id="slide-{n:02d}">{frame}{title}</div>'


def _render_slide(slide: "Slide", n: int) -> str:
    if slide.kind == "text":
        return _render_text_slide(slide, n)
    if slide.kind == "collage" and slide.items:
        return _render_collage_slide(slide, n)
    if slide.kind == "before-after" and slide.items:
        return _render_before_after_slide(slide, n)
    if slide.kind == "editorial":
        return _render_editorial_slide(slide, n)
    # photo (default) + any multi-image kind missing its items.
    return _render_photo_slide(slide, n)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_slides_html(
    layout: "SlideLayout | str",
    slides: list["Slide"],
    *,
    resolved_css: str | None = None,
) -> str:
    """Render a self-contained slides document from structured slides.

    Args:
      layout: the post layout family (informational for now; the per-slide
        `kind` drives the template in Phase 1).
      slides: ordered structured slides.
      resolved_css: optional CSS override. Defaults to the FULL registry
        (`css_for(None)` = base engine + every caption style) so any
        caption_style resolves regardless of a format's linked_styles.

    Returns the `<!doctype html>…</html>` string stored as ContentPost.slides_html.
    """
    css = resolved_css if resolved_css is not None else css_for(None)
    body = "\n".join(_render_slide(s, i + 1) for i, s in enumerate(slides))
    layout_val = getattr(layout, "value", layout) or "full-bleed"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="duct-layout" content="{_esc(str(layout_val))}">\n'
        f"{_FONTS_LINK}\n"
        f"<style>\n{css}\n{_PLACEHOLDER_CSS}\n{_LAYOUT_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>"
    )


def derive_image_prompts(slides: list["Slide"]) -> list[dict]:
    """Flat ImagePrompt-shaped list derived from slides (back-compat for the
    content_posts.image_prompts column + the existing frontend brief panel).
    Multi-image slides contribute one entry per cell, slide_id 'slide-NN#i'."""
    out: list[dict] = []
    for s in slides:
        if s.items:
            for i, it in enumerate(s.items):
                if it.image_prompt.strip():
                    out.append({
                        "slide_id": f"{s.slide_id}#{i}",
                        "prompt": it.image_prompt,
                        "aspect_ratio": it.aspect_ratio.value,
                    })
        elif s.image_prompt.strip():
            out.append({
                "slide_id": s.slide_id,
                "prompt": s.image_prompt,
                "aspect_ratio": s.aspect_ratio.value,
            })
    return out
