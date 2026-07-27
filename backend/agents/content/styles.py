"""Shared TikTok slide style registry — the generic Format-D CSS engine.

This is the brand-agnostic CSS extracted from the original maxaura
`formats/css/*` files: the slide shell, safe zones, film grain, photo
layout, and the caption system. Brand-colored slides (bridge / cta /
body-dark) are intentionally NOT here yet — those need per-project tokens
and will land in a later tokenized pass.

Why a registry: the slide-builder sub-agent used to invent CSS on every
run, so captions drifted. Now a format links to a set of style keys, and
the agent inlines `base_css() + css_for(linked)` verbatim into one
<style> block instead of writing its own. The Library previews these the
same way.

Source of truth lives in code (curated, versioned) and is served read-only
via GET /api/content/styles.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base — always inlined. Slide shell, safe zones, grain, photo layout.
# No brand colors. Safe zones are TikTok-UI constants (identical for everyone).
# ---------------------------------------------------------------------------

BASE_CSS = """\
:root {
  --zoom: 1;
  /* TikTok safe zones — right 180px buttons, bottom 285px caption bar */
  --safe-right: 200px;
  --safe-bottom: 310px;
  --safe-left: 72px;
  --safe-top: 72px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #111;
  display: flex; flex-direction: column; align-items: center;
  gap: 24px; padding: 24px;
  font-family: system-ui, -apple-system, 'Helvetica Neue', sans-serif;
}
.slide {
  width: 1080px; height: 1920px;
  position: relative; overflow: hidden; flex-shrink: 0;
  zoom: var(--zoom);
}
/* Film grain on every slide */
.slide::after {
  content: ''; position: absolute; inset: 0; z-index: 30; pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
  opacity: 0.05; mix-blend-mode: overlay;
}
/* Full-bleed photo + bottom gradient for text legibility (photo slides 1-5) */
.slide-hook .bg {
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; object-position: center 15%;
  filter: brightness(0.94) saturate(0.88) contrast(1.02);
  z-index: 1;
}
.slide-hook .grad {
  position: absolute; bottom: 0; left: 0; width: 100%; height: 65%;
  background: linear-gradient(to top,
    rgba(0,0,0,0.84) 0%, rgba(0,0,0,0.52) 38%, rgba(0,0,0,0.18) 68%, transparent 100%);
  z-index: 2;
}
/* Caption block — anchored above the TikTok caption bar */
.cap-bottom {
  position: absolute; bottom: var(--safe-bottom);
  left: var(--safe-left); right: var(--safe-right);
  z-index: 10; text-align: center;
}
"""

# ---------------------------------------------------------------------------
# Linkable styles — a format picks from these; each is independently
# previewable. `preview` drives the Library gallery (sample text + backdrop).
# ---------------------------------------------------------------------------

STYLES: list[dict] = [
    {
        "key": "hook",
        "name": "Hook headline",
        "category": "hook",
        "description": "Big bold white headline + lighter sub-line, bottom-anchored over a photo. The scroll-stopping slide-1 statement.",
        "when_to_use": "Slide 1 — the hook. The face carries the emotion; the headline explains it.",
        "dont_use_on": "Quiet, intimate body slides — use a caption style instead.",
        "preview": {"text": "i did everything right", "sub": "(and it still went wrong)", "bg": "photo"},
        "css": """\
.hook-headline {
  display: block; font-size: 86px; font-weight: 800; line-height: 1.06;
  letter-spacing: -2.5px; color: #fff;
  text-shadow: 0 2px 14px rgba(0,0,0,0.95), 0 0 48px rgba(0,0,0,0.65);
}
.hook-sub {
  display: block; margin-top: 22px; font-size: 48px; font-weight: 400;
  line-height: 1.4; color: rgba(255,255,255,0.80);
  text-shadow: 0 2px 12px rgba(0,0,0,0.88);
}""",
    },
    {
        "key": "cap-stroke",
        "name": "Stroke",
        "category": "caption",
        "description": "Bold white text with a thick black outline — the most iconic TikTok text style. Readable on any photo, any lighting.",
        "when_to_use": "Hooks, hot takes, strong emotions, punchy moments. The default.",
        "dont_use_on": "Intimate/confessional moments (use Raw); long multi-line info (use Pill).",
        "preview": {"text": "a dermatologist told me<br>to stop doing this", "bg": "photo"},
        "css": """\
.cap-stroke {
  display: block; font-size: 80px; font-weight: 900; line-height: 1.08;
  letter-spacing: -2px; color: #ffffff;
  -webkit-text-stroke: 6px #000000; paint-order: stroke fill;
  text-align: center; text-wrap: balance;
}
.cap-stroke-sub {
  display: block; margin-top: 20px; font-size: 44px; font-weight: 700;
  line-height: 1.4; color: #ffffff;
  -webkit-text-stroke: 3px #000000; paint-order: stroke fill;
  text-align: center; text-wrap: balance;
}""",
    },
    {
        "key": "cap-pill",
        "name": "Pill",
        "category": "caption",
        "description": "Each line sits on its own solid black pill — like a highlighter. Reads clearly over bright or busy photos.",
        "when_to_use": "Information-heavy slides, named lists, measurements, light/high-contrast backgrounds.",
        "dont_use_on": "2–4 word lines (use Stroke); intimate vibes (pills feel transactional).",
        "preview": {"text": "round face? do this", "sub": "side part · soft layers · no blunt bangs", "bg": "photo"},
        "css": """\
.cap-pill-wrap { display: block; text-align: center; line-height: 1.75; }
.cap-pill {
  display: inline; font-size: 68px; font-weight: 800; line-height: 1.75;
  letter-spacing: -1px; color: #ffffff; background: rgba(0,0,0,0.88);
  padding: 4px 24px; border-radius: 10px;
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}
.cap-pill-sub { display: block; margin-top: 24px; text-align: center; line-height: 1.6; }
.cap-pill-sub span {
  display: inline; font-size: 44px; font-weight: 600; line-height: 1.75;
  color: #ffffff; background: rgba(0,0,0,0.78); padding: 2px 18px; border-radius: 8px;
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}""",
    },
    {
        "key": "cap-raw",
        "name": "Raw",
        "category": "caption",
        "description": "Clean white text, no outline, no background — looks like the native TikTok text tool. Feels personal, undesigned.",
        "when_to_use": "Intimate/confessional reveals, the emotional peak, disbelief or sadness. Needs a dark-enough photo for contrast.",
        "dont_use_on": "Bright photos (text disappears); high-energy content (use Stroke).",
        "preview": {"text": "nobody told me<br>it was this simple", "bg": "dark"},
        "css": """\
.cap-raw {
  display: block; font-size: 88px; font-weight: 800; line-height: 1.1;
  letter-spacing: -2.5px; color: #ffffff;
  text-shadow: 0 2px 20px rgba(0,0,0,0.80), 0 0 40px rgba(0,0,0,0.45);
  text-align: center; text-wrap: balance;
}
.cap-raw-sub {
  display: block; margin-top: 20px; font-size: 50px; font-weight: 400;
  line-height: 1.48; color: rgba(255,255,255,0.88);
  text-shadow: 0 1px 14px rgba(0,0,0,0.85); text-align: center; text-wrap: balance;
}""",
    },
    {
        "key": "cap-whisper",
        "name": "Whisper",
        "category": "caption",
        "description": "Genuinely small, low-weight text — reads as accidental, like a timestamp. The image IS the content; text barely exists.",
        "when_to_use": "When the photo alone tells the story and text just names it. Single-word or 3-word labels.",
        "dont_use_on": "Bright photos (invisible); any slide where the viewer must read a sentence.",
        "preview": {"text": "the power of a bob", "bg": "dark"},
        "css": """\
.cap-whisper {
  display: block; font-size: 36px; font-weight: 400; line-height: 1.4;
  letter-spacing: 0.02em; color: rgba(255,255,255,0.80); text-align: center;
}
.cap-whisper-sub {
  display: block; margin-top: 10px; font-size: 28px; font-weight: 300;
  line-height: 1.4; color: rgba(255,255,255,0.50); text-align: center;
}""",
    },
    {
        "key": "body-neutral",
        "name": "Text card (neutral)",
        "category": "body",
        "description": "Pure black background + white text — looks like the TikTok app's native text card. Fallback when no photo could be generated.",
        "when_to_use": "Text-only slides when a photo isn't available. Prefer photo slides when possible.",
        "dont_use_on": "When a photo exists — a real image always outperforms a text card.",
        "preview": {"text": "the 3 things<br>nobody tells you", "sub": "save this before it's gone", "bg": "light"},
        "css": """\
.slide-body { background: #0D0D0D; }
.body-content {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -55%);
  width: 900px; z-index: 5; text-align: center;
}
.body-statement {
  display: block; font-size: 116px; font-weight: 900; line-height: 0.95;
  letter-spacing: -4px; color: #FFFFFF;
}
.body-sub {
  display: block; margin-top: 44px; font-size: 54px; font-weight: 500;
  line-height: 1.45; color: rgba(255,255,255,0.58);
}""",
    },
]

_STYLE_BY_KEY = {s["key"]: s for s in STYLES}


def base_css() -> str:
    """The always-on slide engine CSS (no brand colors)."""
    return BASE_CSS


def list_styles() -> list[dict]:
    """All linkable styles, full payload (for the API + Library gallery)."""
    return STYLES


def style_keys() -> list[str]:
    return [s["key"] for s in STYLES]


def css_for(keys: list[str] | None) -> str:
    """base_css + the CSS for each linked style key (unknown keys skipped).

    When `keys` is falsy, every style is included so a format with no
    explicit links still renders.
    """
    selected = STYLES if not keys else [_STYLE_BY_KEY[k] for k in keys if k in _STYLE_BY_KEY]
    return "\n\n".join([BASE_CSS, *[s["css"] for s in selected]])
