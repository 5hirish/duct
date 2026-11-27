"""Pre-publish review math — pure Python: no model call, no DB, no framework.

Two halves, joined by one rule: **the agent scores, the server weighs.**

  compute_sanity(slides, caption, hashtags, replies=, channel=) -> list[SanityCheck]
      Deterministic "would this ship broken?" checks. Advisory: a failure is
      shown and costs points, it never disables Publish. The channel decides
      the length limit and whether hashtags are expected at all — an X post
      is not short of hashtags, it is right not to have them.

  compute_overall(markers, checks) -> (overall, content_score, band)
      The six markers the reviewer scored, blended at MARKER_WEIGHTS, less a
      penalty per failed check.

The weights live here and nowhere a model can reach. submit_assessment's
argument schema (``MarkerScore``) has no weight field, and ``weigh_markers``
stamps each marker from this table on the way in — including when a stored
review is read back, so a change to the table re-weighs old reviews too.

Ported from the unmerged June Content Studio branch minus two things: its
video checks and its English labels — the app words every check and marker
from its id, so the panel is translated. A video post (issue #284) has no
slides, so its review is the caption and hashtag checks; publishing is what
refuses a video post with no clip (agents/content/video.publish_asset).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from agents.content.channels import primary_channel, resolve as resolve_channel
from agents.content.schema import (
    CheckSeverity,
    ContentMarker,
    HOOK_MAX,
    MAX_HOOK_OPTIONS,
    MAX_PERSONA_REACTIONS,
    MarkerScore,
    PanelCheck,
    PersonaReaction,
    PersonaVerdict,
    PublishAssessment,
    ReviewBand,
    ReviewMarker,
    SanityCheck,
    SanityCheckId,
)

# What each marker is worth to the overall, by what it drives. Sums to 1.0.
MARKER_WEIGHTS: dict[ReviewMarker, float] = {
    ReviewMarker.HOOK_STRENGTH:          0.25,   # swipe-through
    ReviewMarker.NARRATIVE_MOMENTUM:     0.20,   # completion
    ReviewMarker.SAVE_WORTHINESS:        0.20,   # saves
    ReviewMarker.SHAREABILITY_RESONANCE: 0.15,   # shares
    ReviewMarker.VISUAL_QUALITY:         0.12,   # first-frame stop + retention
    ReviewMarker.CTA_CAPTION_FIT:        0.08,   # the closing action
}

# Points off the overall per failed check. A hard failure ships a broken post,
# so it outweighs a soft one — but neither blocks: the owner decides.
PENALTY: dict[CheckSeverity, int] = {CheckSeverity.HARD: 8, CheckSeverity.SOFT: 3}

# Lower bounds of each band, highest first.
BANDS: tuple[tuple[int, ReviewBand], ...] = (
    (80, ReviewBand.STRONG),
    (60, ReviewBand.GOOD),
    (40, ReviewBand.NEEDS_WORK),
    (0, ReviewBand.NOT_READY),
)

# A visual post's ceiling: the stricter of Instagram (2,200) and TikTok
# (4,000), so a carousel bound for both is safe on both. A text channel's post
# goes out on that channel alone and is held to its own limit
# (agents/content/channels.RULES).
CAPTION_MAX = 2200

_PLACEHOLDER_RE = re.compile(
    r"\b(todo|fixme|tbd|lorem ipsum|placeholder|xxx|tk tk)\b", re.IGNORECASE
)
# Fill-in brackets only — [name], [insert hook], [your brand] — never an aside
# a post means to show, like "[swipe]", "[results below]" or "[2026]".
_BRACKET_RE = re.compile(
    r"\[\s*(?:insert|your|name|brand|topic|product|company|audience|x|tk|"
    r"fill[\s-]?in|placeholder|tbd)\b[^\]\n]*\]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Sanity — what is mechanically incomplete
# ---------------------------------------------------------------------------


def _stale(target: dict) -> bool:
    """A generated image whose prompt was edited after it was made — the same
    rule as ``Slide.is_image_stale``, over the stored dict."""
    if not (target.get("image_url") or "").strip():
        return False
    return (target.get("image_prompt") or "").strip() != (target.get("image_prompt_used") or "").strip()


def _has_placeholder(text: str) -> bool:
    return bool(text) and bool(_PLACEHOLDER_RE.search(text) or _BRACKET_RE.search(text))


def _check(check_id: SanityCheckId, offenders: list[str], *, failed: bool | None = None,
           severity: CheckSeverity = CheckSeverity.HARD) -> SanityCheck:
    passed = not offenders if failed is None else not failed
    return SanityCheck(id=check_id, passed=passed, severity=severity, offenders=offenders)


def reply_id(index: int) -> str:
    """How a reply is named in a check's offenders: ``reply-1`` for the first.
    The app words it ("reply 1") the way it words ``slide-01``."""
    return f"reply-{index}"


def compute_sanity(
    slides: list,
    caption: str,
    hashtags: list,
    *,
    replies: list | None = None,
    channel: str | None = None,
) -> list[SanityCheck]:
    """The deterministic checks, against a post's stored fields.

    ``slides`` is the stored JSON list: dicts, multi-image slides carrying
    ``items``. Offenders are slide ids — a cell's failure names its slide,
    because the slide is what the owner navigates to — or ``caption`` and
    ``reply-N`` for the words. A text post has no slides, so the slide checks
    pass by having nothing to fail on.
    """
    slides = [s for s in (slides or []) if isinstance(s, dict)]
    caption = (caption or "").strip()
    replies = [r for r in (replies or []) if isinstance(r, str)]
    ch = resolve_channel(channel)
    limit = ch.rules.max_chars if ch.text_first else CAPTION_MAX

    no_image: list[str] = []
    stale: list[str] = []
    no_copy: list[str] = []
    placeholder: list[str] = []
    for i, s in enumerate(slides):
        sid = str(s.get("slide_id") or f"slide-{i + 1:02d}")
        cells = [c for c in (s.get("items") or []) if isinstance(c, dict)]
        # A text slide and a design slide (the agent's own layout) have no
        # picture by design; every other slide, or each of its cells, needs
        # one. Design slides used to fail this, which cost a post's score for
        # its best slides and sent the review after pictures nobody wanted.
        if s.get("kind") not in ("text", "design") and (
            any(not (c.get("image_url") or "").strip() for c in cells)
            if cells else not (s.get("image_url") or "").strip()
        ):
            no_image.append(sid)
        if _stale(s) or any(_stale(c) for c in cells):
            stale.append(sid)
        # The hook slide and a text slide are copy or they are nothing.
        if (i == 0 or s.get("kind") == "text") and not (s.get("headline") or "").strip():
            no_copy.append(sid)
        texts = [s.get("headline") or "", s.get("subtext") or ""] + [c.get("label") or "" for c in cells]
        if any(_has_placeholder(t) for t in texts):
            placeholder.append(sid)
    if _has_placeholder(caption):
        placeholder.append("caption")
    too_long = ["caption"] if len(caption) > limit else []
    for i, reply in enumerate(replies, start=1):
        if _has_placeholder(reply):
            placeholder.append(reply_id(i))
        if len(reply) > limit:
            too_long.append(reply_id(i))

    tags = [t.strip().lower().lstrip("#") for t in (hashtags or []) if isinstance(t, str) and t.strip()]
    repeated = sorted({f"#{t}" for t in tags if tags.count(t) > 1})

    checks = [
        _check(SanityCheckId.SLIDES_HAVE_IMAGES, no_image),
        _check(SanityCheckId.IMAGES_FRESH, stale),
        _check(SanityCheckId.SLIDES_HAVE_HEADLINES, no_copy),
        _check(SanityCheckId.CAPTION_PRESENT, [], failed=not caption),
        # Hard on a text channel: past the limit, X and LinkedIn refuse the
        # post outright. Soft for a carousel, whose ceiling is a cross-post.
        _check(SanityCheckId.CAPTION_LENGTH, too_long,
               severity=CheckSeverity.HARD if ch.text_first else CheckSeverity.SOFT),
        _check(SanityCheckId.NO_PLACEHOLDER_TEXT, placeholder),
    ]
    # A channel whose playbook writes no hashtags is not short of them.
    if ch.rules.hashtags:
        checks += [
            _check(SanityCheckId.HASHTAGS_PRESENT, [], failed=not tags, severity=CheckSeverity.SOFT),
            _check(SanityCheckId.HASHTAGS_UNIQUE, repeated, severity=CheckSeverity.SOFT),
        ]
    return checks


# ---------------------------------------------------------------------------
# Scoring — what the reviewer judged, at the server's weights
# ---------------------------------------------------------------------------


def weigh_markers(scores: Iterable[MarkerScore]) -> list[ContentMarker]:
    """Stamp each score with its weight, in canonical order. A marker scored
    twice keeps the later score — a reviewer correcting itself."""
    by_id: dict[ReviewMarker, MarkerScore] = {}
    for score in scores:
        by_id[score.id] = score
    return [
        ContentMarker(**by_id[marker].model_dump(), weight=weight)
        for marker, weight in MARKER_WEIGHTS.items()
        if marker in by_id
    ]


def band_for(overall: int) -> ReviewBand:
    return next(band for floor, band in BANDS if overall >= floor)


def compute_overall(markers: list[ContentMarker], checks: list[SanityCheck]) -> tuple[int, int, ReviewBand]:
    """``(overall, content_score, band)``.

    content_score is the weight-normalised mean of the markers present, so a
    partial set is still a 0-100 figure; overall is that less the penalty for
    each failed check, clamped to 0-100. The weights are read from
    MARKER_WEIGHTS by id, never from the marker itself.
    """
    weight_sum = sum(MARKER_WEIGHTS[m.id] for m in markers)
    content_score = round(sum(MARKER_WEIGHTS[m.id] * m.score for m in markers) / weight_sum) if weight_sum else 0
    penalty = sum(PENALTY[c.severity] for c in checks if not c.passed)
    overall = max(0, min(100, content_score - penalty))
    return overall, content_score, band_for(overall)


def fingerprint(slides: list, caption: str, hashtags: list, replies: list | None = None) -> str:
    """A digest of what a reviewer reads. When it moves, the score is from
    before the change — a new image counts, since the visuals were judged.
    Replies join the digest only when there are some, so every review stored
    before replies existed keeps the digest it was given."""
    parts: list = [slides or [], (caption or "").strip(), hashtags or []]
    if replies:
        parts.append(list(replies))
    body = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def assess(
    slides: list,
    caption: str,
    hashtags: list,
    scores: Iterable[MarkerScore] = (),
    *,
    replies: list | None = None,
    channel: str | None = None,
    notes: str = "",
    personas: Iterable[PersonaReaction] = (),
    baseline: PersonaReaction | None = None,
    hooks: Iterable[str] = (),
    panel_check: PanelCheck | None = None,
    scored_at: str = "",
    scored_fingerprint: str = "",
) -> PublishAssessment:
    """The review of a post as it is now: fresh checks, and — when there are
    scores — the overall they add up to. ``scored_fingerprint`` is the digest
    the scores were given against; omitted, the scores are about now."""
    checks = compute_sanity(slides, caption, hashtags, replies=replies, channel=channel)
    markers = weigh_markers(scores)
    current = fingerprint(slides, caption, hashtags, replies)
    overall = content_score = band = None
    if markers:
        overall, content_score, band = compute_overall(markers, checks)
    options = clean_hooks(hooks)
    return PublishAssessment(
        overall=overall,
        content_score=content_score,
        band=band,
        markers=markers,
        checks=checks,
        notes=notes,
        personas=[_picked_from(r, options) for r in list(personas)[:MAX_PERSONA_REACTIONS]],
        baseline=_picked_from(baseline, options) if baseline else None,
        hooks=options,
        panel_check=panel_check,
        scored_at=scored_at,
        fingerprint=scored_fingerprint or current,
        stale=bool(markers) and bool(scored_fingerprint) and scored_fingerprint != current,
    )


def clean_hooks(hooks: Iterable[str]) -> list[str]:
    """The openings the panel chose between, as stored: trimmed, non-empty,
    at most MAX_HOOK_OPTIONS, the draft's own first."""
    out = [str(h).strip()[:HOOK_MAX] for h in hooks or () if str(h or "").strip()]
    return out[:MAX_HOOK_OPTIONS]


def _picked_from(reaction: PersonaReaction, options: list[str]) -> PersonaReaction:
    # A pick names an opening by its place; with fewer openings than that it
    # names nothing, and a dangling index would show as "Hook C" over a blank.
    if reaction.pick is not None and reaction.pick >= len(options):
        return reaction.model_copy(update={"pick": None})
    return reaction


def _reaction(raw: Any) -> PersonaReaction | None:
    try:
        return PersonaReaction.model_validate(raw)
    except ValidationError:
        return None


def reassess(
    slides: list,
    caption: str,
    hashtags: list,
    stored: dict | None,
    *,
    replies: list | None = None,
    channel: str | None = None,
) -> PublishAssessment:
    """A stored review read against the post now. The checks are recomputed
    and the stored scores re-weighed, so neither can be out of date; only the
    reviewer's judgement can, and ``stale`` says when it is."""
    stored = stored if isinstance(stored, dict) else {}
    scores: list[MarkerScore] = []
    for raw in stored.get("markers") or []:
        try:
            scores.append(MarkerScore.model_validate(raw))
        except ValidationError:
            continue  # a marker retired since it was scored; the rest still stand
    # One unreadable reaction never costs the review the others.
    reactions = [r for raw in stored.get("personas") or [] if (r := _reaction(raw))]
    baseline = _reaction(stored["baseline"]) if stored.get("baseline") else None
    try:
        check = PanelCheck.model_validate(stored["panel_check"]) if stored.get("panel_check") else None
    except ValidationError:
        check = None
    return assess(
        slides,
        caption,
        hashtags,
        scores,
        replies=replies,
        channel=channel,
        notes=str(stored.get("notes") or ""),
        personas=reactions,
        baseline=baseline,
        hooks=[h for h in stored.get("hooks") or [] if isinstance(h, str)],
        panel_check=check,
        scored_at=str(stored.get("scored_at") or ""),
        scored_fingerprint=str(stored.get("fingerprint") or ""),
    )


__all__ = [
    "BANDS",
    "CAPTION_MAX",
    "MARKER_WEIGHTS",
    "PENALTY",
    "assess",
    "band_for",
    "clean_hooks",
    "compute_overall",
    "compute_sanity",
    "draft_verdict",
    "fingerprint",
    "opening_kept_fresh",
    "reassess",
    "reassess_post",
    "reply_id",
    "weigh_markers",
]


def reassess_post(row) -> PublishAssessment:
    """``reassess`` over a stored post row — the one call every reader makes,
    so none of them can forget the replies or the channel."""
    return reassess(
        row.slides or [], row.caption or "", row.hashtags or [], row.last_assessment,
        replies=row.replies or [], channel=primary_channel(row.platforms),
    )


# ---------------------------------------------------------------------------
# The draft check: the review, run on a new draft before the person reads it
# ---------------------------------------------------------------------------

# Below this content score a draft goes back for one revision before anyone
# sees it. The content score, not the overall: a draft has no pictures yet,
# and the image checks would sink every one of them.
DRAFT_BAR = 70

# What a persona would do that says the post was for them.
_TAKES_PART = ("comment", "save", "share")


def draft_verdict(result: PublishAssessment) -> dict[str, Any]:
    """What the draft check says to do next, from a review's numbers.

    ``audience_miss``: more than half the personas would neither stop for it
    nor comment, save or share, which is how "this isn't my question" reads in
    verdicts. ``better_opening``: another of the review's openings won more of
    the panel's picks than the draft's own (a tie keeps the draft's).
    ``revise``: either of those, or a content score under the bar.
    """
    people = list(result.personas)
    missed = [
        r for r in people
        if r.stop != PersonaVerdict.YES and not any(getattr(r, k) == PersonaVerdict.YES for k in _TAKES_PART)
    ]
    audience_miss = bool(people) and len(missed) * 2 > len(people)

    hooks = list(result.hooks)
    voters = [r for r in (result.baseline, *people) if r is not None]
    votes = [0] * len(hooks)
    for r in voters:
        if r.pick is not None and 0 <= r.pick < len(hooks):
            votes[r.pick] += 1
    better = None
    if len(hooks) > 1:
        best = max(range(1, len(hooks)), key=lambda i: votes[i])
        if votes[best] > votes[0]:
            better = {"index": best, "text": hooks[best], "votes": votes[best], "of": len(voters)}

    score = result.content_score or 0
    below = score < DRAFT_BAR
    return {
        "bar": DRAFT_BAR,
        "content_score": score,
        "below_bar": below,
        "audience_miss": audience_miss,
        "better_opening": better,
        "revise": below or audience_miss or better is not None,
    }


def _as_read(slide: Any) -> dict:
    """A stored slide as the renderer reads it, so a write that only fills in
    defaults is not taken for a change."""
    from agents.content.schema import Slide

    try:
        return Slide.model_validate(slide).model_dump(mode="json")
    except (ValidationError, TypeError):
        return dict(slide) if isinstance(slide, dict) else {}


def opening_kept_fresh(
    stored: dict | None, before: list, after: list, caption: str, hashtags: list, replies: list | None = None,
) -> dict | None:
    """The stored review, still current after slide 1 took one of the
    openings that same review compared; None when it does not apply.

    The panel read each of its openings against the rest of the post, so
    putting the winner on slide 1 changes nothing it judged. Marking the
    review out of date for it would ask for the same review again.
    """
    if not stored or not stored.get("fingerprint") or not before or len(before) != len(after):
        return None
    if stored["fingerprint"] != fingerprint(before, caption, hashtags, replies):
        return None  # already out of date before this edit
    if any(_as_read(b) != _as_read(a) for b, a in zip(before[1:], after[1:])):
        return None
    first_before, first_after = _as_read(before[0]), _as_read(after[0])
    for key in ("headline", "subtext"):
        first_before.pop(key, None)
        first_after.pop(key, None)
    if first_before != first_after:
        return None
    hooks = {" ".join(str(h).split()).casefold() for h in stored.get("hooks") or []}
    if " ".join(str(after[0].get("headline") or "").split()).casefold() not in hooks:
        return None
    return {**stored, "fingerprint": fingerprint(after, caption, hashtags, replies)}
