"""Earlier states of a post's slides, so a change can be taken back.

A slide changes many times while a post is made: a new picture, a caption
rewrite, a design pass. When the person prefers an earlier one, regenerating
it costs a model call and rarely gives the same picture back; on 2026-11-27
there was no way back at all. Every writer of ``ContentPost.slides`` hands its
before-state to ``record_changes``, which keeps the previous state of each
slide that changed. ``restore`` puts one back, and keeps the state it
replaced, so a restore is undone the same way.

Plain Python on purpose: the agent's tool, the restore route and the PATCH
route all call it.
"""

from __future__ import annotations

import json

from utils.dates import now_iso

# Per slide. A design slide's snapshot can be tens of kilobytes, and the
# payload carries them to the app on every update.
MAX_VERSIONS = 6


def _canonical(slide: dict) -> str:
    """A slide as the renderer reads it, so a round trip that only reorders
    keys or adds a default is not mistaken for a change."""
    from agents.content.schema import Slide

    try:
        slide = Slide.model_validate(slide).model_dump(mode="json")
    except Exception:
        pass
    return json.dumps(slide, sort_keys=True, default=str)


def _by_id(slides: list) -> dict[str, dict]:
    return {
        str(s.get("slide_id")): s
        for s in slides or []
        if isinstance(s, dict) and s.get("slide_id")
    }


def record_changes(row, before: list, *, by: str) -> list[str]:
    """Keep the previous state of every slide of ``row`` that differs from
    ``before``. Returns the ids that changed. The caller commits."""
    previous = _by_id(before)
    history = dict(row.slide_versions or {})
    changed: list[str] = []
    for slide in row.slides or []:
        if not isinstance(slide, dict):
            continue
        sid = str(slide.get("slide_id") or "")
        old = previous.get(sid)
        if old is None or _canonical(old) == _canonical(slide):
            continue
        entry = {"slide": old, "at": now_iso(), "by": by}
        history[sid] = (list(history.get(sid) or []) + [entry])[-MAX_VERSIONS:]
        changed.append(sid)
    if changed:
        row.slide_versions = history
    return changed


def restore(row, slide_id: str, back: int = 1) -> bool:
    """Put back the state ``back`` versions ago (1 is the one just before
    the current). The current state becomes the newest version. False when
    the slide or the version does not exist. The caller re-renders and commits."""
    history = dict(row.slide_versions or {})
    versions = list(history.get(slide_id) or [])
    if not 1 <= back <= len(versions):
        return False
    slides = list(row.slides or [])
    at = next(
        (i for i, s in enumerate(slides) if isinstance(s, dict) and str(s.get("slide_id")) == slide_id),
        None,
    )
    if at is None:
        return False
    target = versions.pop(len(versions) - back)
    versions.append({"slide": slides[at], "at": now_iso(), "by": "restore"})
    slides[at] = {**target["slide"], "slide_id": slide_id}
    history[slide_id] = versions[-MAX_VERSIONS:]
    row.slides = slides
    row.slide_versions = history
    return True
