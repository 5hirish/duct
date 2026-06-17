"""Pre-publish review math — pure Python, no model calls, no DB.

Two halves:

  compute_sanity(slides, caption, hashtags) -> list[SanityCheck]
      Deterministic "is this post complete and valid to publish?" checks
      (static-analysis style). Advisory — a failure is surfaced but never
      blocks Publish.

  compute_overall(markers, sanity) -> (overall, content_score, band)
      Blends the subjective content markers (scored in-session by the
      review_post sub-agent) into one number, penalised per failed sanity
      check.

The canonical marker weights/labels live here (NOT trusted from the agent):
submit_assessment fills each marker's label + weight from these tables so the
agent can score but cannot skew the weighting.

Kept dependency-light (only the schema models) so it unit-tests without a DB or
an event loop.
"""

from __future__ import annotations

import re

from agents.content.schema import ContentMarker, SanityCheck

# ---------------------------------------------------------------------------
# Subjective marker registry — the rubric's weighting, owned server-side.
# Weights sum to 1.0. Order is the canonical display order.
# ---------------------------------------------------------------------------

MARKER_IDS: tuple[str, ...] = (
    "hook_strength",
    "narrative_momentum",
    "save_worthiness",
    "shareability_resonance",
    "visual_quality",
    "cta_caption_fit",
)

MARKER_LABELS: dict[str, str] = {
    "hook_strength":          "Hook strength",
    "narrative_momentum":     "Narrative momentum",
    "save_worthiness":        "Save-worthiness",
    "shareability_resonance": "Shareability & resonance",
    "visual_quality":         "Visual quality",
    "cta_caption_fit":        "CTA & caption fit",
}

MARKER_WEIGHTS: dict[str, float] = {
    "hook_strength":          0.25,   # drives swipe-through
    "narrative_momentum":     0.20,   # drives completion
    "save_worthiness":        0.20,   # drives saves
    "shareability_resonance": 0.15,   # drives shares
    "visual_quality":         0.12,   # first-frame stop + retention
    "cta_caption_fit":        0.08,   # drives the closing action
}

# A failed completeness check knocks this many points off the overall, by
# severity: "hard" = the post would ship broken; "soft" = a quality nit.
HARD_PENALTY = 8
SOFT_PENALTY = 3

# Platform caption ceiling — the stricter of the two (Instagram 2,200; TikTok
# ~4,000), so a multi-platform post stays safe. Over-length is a soft fail.
_CAPTION_MAX = 2200

_PLACEHOLDER_RE = re.compile(
    r"\b(todo|fixme|tbd|lorem ipsum|placeholder|xxx|tk tk)\b", re.IGNORECASE
)
# Fill-in brackets only — [name], [insert hook], [your brand], [topic], [x] —
# NOT legitimate bracketed asides like "[swipe]" or "[results below]" or [2026].
_BRACKET_RE = re.compile(
    r"\[\s*(?:insert|your|name|brand|topic|product|company|audience|x|tk|"
    r"fill[\s-]?in|placeholder|tbd)\b[^\]\n]*\]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Sanity (deterministic completeness)
# ---------------------------------------------------------------------------

def _stale(d: dict) -> bool:
    """A generated image whose prompt has changed since it was produced."""
    if not (d.get("image_url") or "").strip():
        return False
    return (d.get("image_prompt") or "").strip() != (d.get("image_prompt_used") or "").strip()


def _text_fields(slides: list[dict]) -> list[tuple[str, str]]:
    """(slide_id, text) for every author-written caption surface on the post."""
    out: list[tuple[str, str]] = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("slide_id") or "")
        out.append((sid, s.get("headline") or ""))
        out.append((sid, s.get("subtext") or ""))
        for it in s.get("items") or []:
            if isinstance(it, dict):
                out.append((sid, it.get("label") or ""))
    return out


def compute_sanity(
    slides: list[dict],
    caption: str,
    hashtags: list[str],
) -> list[SanityCheck]:
    """Run the deterministic completeness checks against a post's stored state.

    `slides` is the JSONB list (each slide a dict, multi-image slides carry
    `items`). Pure function — safe to unit-test with hand-built dicts.
    """
    slides = [s for s in (slides or []) if isinstance(s, dict)]
    checks: list[SanityCheck] = []

    # 1 — every shippable slide / cell has an image.
    missing: list[str] = []
    for s in slides:
        if s.get("kind") == "text":
            continue
        items = s.get("items") or []
        if items:
            for j, it in enumerate(items):
                if isinstance(it, dict) and not (it.get("image_url") or "").strip():
                    missing.append(f"{s.get('slide_id')} cell {j + 1}")
        elif not (s.get("image_url") or "").strip():
            missing.append(str(s.get("slide_id")))
    checks.append(SanityCheck(
        id="slides_have_images",
        label="All slides have images",
        passed=not missing,
        detail="" if not missing else "Missing image: " + ", ".join(missing),
    ))

    # 2 — no stale images (prompt edited after the image was generated).
    stale: list[str] = []
    for s in slides:
        if _stale(s):
            stale.append(str(s.get("slide_id")))
        for j, it in enumerate(s.get("items") or []):
            if isinstance(it, dict) and _stale(it):
                stale.append(f"{s.get('slide_id')} cell {j + 1}")
    checks.append(SanityCheck(
        id="images_fresh",
        label="Images up to date",
        passed=not stale,
        detail="" if not stale else "Image outdated since its prompt changed: " + ", ".join(stale),
    ))

    # 3 — the slides that must carry copy actually do (text slides + the hook).
    no_copy: list[str] = []
    for i, s in enumerate(slides):
        needs_copy = s.get("kind") == "text" or i == 0
        if needs_copy and not (s.get("headline") or "").strip():
            no_copy.append(str(s.get("slide_id")))
    checks.append(SanityCheck(
        id="slides_have_headlines",
        label="Key slides have copy",
        passed=not no_copy,
        detail="" if not no_copy else "No headline on: " + ", ".join(no_copy),
    ))

    # 4 — the feed caption exists and fits the platform ceiling.
    cap = (caption or "").strip()
    if not cap:
        checks.append(SanityCheck(
            id="caption_present", label="Caption present",
            passed=False, detail="The post has no caption.",
        ))
    elif len(cap) > _CAPTION_MAX:
        checks.append(SanityCheck(
            id="caption_present", label="Caption present",
            passed=False, severity="soft",
            detail=f"Caption is {len(cap)} chars — over the {_CAPTION_MAX:,} char limit (safe for all platforms).",
        ))
    else:
        checks.append(SanityCheck(
            id="caption_present", label="Caption present", passed=True, detail="",
        ))

    # 5 — no leftover placeholder text anywhere on the post.
    placeholders: set[str] = set()
    for sid, txt in _text_fields(slides) + [("caption", caption or "")]:
        if txt and (_PLACEHOLDER_RE.search(txt) or _BRACKET_RE.search(txt)):
            if sid:
                placeholders.add(sid)
    ph = sorted(placeholders)
    checks.append(SanityCheck(
        id="no_placeholder_text",
        label="No placeholder text",
        passed=not ph,
        detail="" if not ph else "Placeholder/fill-in text in: " + ", ".join(ph),
    ))

    # 6 — at least one hashtag, none duplicated.
    tags = [t for t in (hashtags or []) if isinstance(t, str) and t.strip()]
    norm = [t.strip().lower().lstrip("#") for t in tags]
    dups = sorted({t for t in norm if norm.count(t) > 1})
    if not tags:
        checks.append(SanityCheck(
            id="hashtags_present", label="Hashtags present",
            passed=False, severity="soft", detail="No hashtags.",
        ))
    elif dups:
        checks.append(SanityCheck(
            id="hashtags_present", label="Hashtags present",
            passed=False, severity="soft",
            detail="Duplicate hashtags: " + ", ".join("#" + d for d in dups),
        ))
    else:
        checks.append(SanityCheck(
            id="hashtags_present", label="Hashtags present",
            passed=True, severity="soft", detail="",
        ))

    return checks


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def apply_marker_metadata(markers: list[ContentMarker]) -> list[ContentMarker]:
    """Stamp each marker with its canonical label + weight, drop unknown ids,
    and return them in canonical display order. The agent supplies the scores;
    the weighting is ours."""
    order = {mid: i for i, mid in enumerate(MARKER_IDS)}
    out = [
        m.model_copy(update={"label": MARKER_LABELS[m.id], "weight": MARKER_WEIGHTS[m.id]})
        for m in markers
        if m.id in MARKER_WEIGHTS
    ]
    out.sort(key=lambda m: order.get(m.id, 99))
    return out


def band_for(overall: int) -> str:
    if overall >= 80:
        return "Strong"
    if overall >= 60:
        return "Good"
    if overall >= 40:
        return "Needs work"
    return "Not ready"


def compute_overall(
    markers: list[ContentMarker],
    sanity: list[SanityCheck],
) -> tuple[int, int, str]:
    """Return (overall, content_score, band).

    content_score = weight-normalised average of the markers present (0–100).
    overall       = content_score − Σ(penalty per failed sanity check), where a
                    "hard" failure costs HARD_PENALTY and a "soft" one costs
                    SOFT_PENALTY. Clamped to 0–100.
    """
    weight_sum = sum(MARKER_WEIGHTS[m.id] for m in markers if m.id in MARKER_WEIGHTS)
    acc = sum(MARKER_WEIGHTS[m.id] * m.score for m in markers if m.id in MARKER_WEIGHTS)
    content_score = round(acc / weight_sum) if weight_sum else 0

    penalty = sum(
        (SOFT_PENALTY if c.severity == "soft" else HARD_PENALTY)
        for c in sanity if not c.passed
    )
    overall = max(0, min(100, content_score - penalty))
    return overall, content_score, band_for(overall)
