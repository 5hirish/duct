"""A project's formats, as the plan, the draft and the writers read them.

A format is a recipe in the library (Library → Formats): a spec the agent
reads, a default slide count, and the caption styles it links from the shared
registry (``agents/content/styles.py``). Until this module the library was
decoration. The plan prompt was always handed an empty list and told to use
Format D, a post could not be started in a format, and the renderer loads
every style, so the styles a format linked changed nothing anyone saw.

So the library now binds in three places:

* the plan sees each format (``format_summaries``) and names one per day;
* a draft started in a format, or from a plan day that names one, files the
  post under it and tells the agent to build to its spec;
* ``style_problems`` holds a post's captions to the styles its format links,
  which ``submit_post_draft`` and ``edit_slide`` refuse on, like a banned word.

Plain functions over a session, no agent framework.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from agents.content.styles import list_styles
from models.content import ContentFormat

# Only a photo slide draws its caption in the slide's caption_style; a text
# card is always the body card and a collage, a before-after and an editorial
# frame set their own type (templates.py). Holding those to a format's
# caption styles would refuse a slide for a field nothing renders.
_STYLED_KIND = "photo"

# The registry's categories a photo caption can take. A format's body style
# says how its text cards look, which no caption_style changes.
_CAPTION_CATEGORIES = frozenset({"hook", "caption"})

_CATEGORY = {s["key"]: s["category"] for s in list_styles()}


@dataclass(frozen=True)
class FormatSummary:
    slug: str
    name: str
    slide_count: int | None
    styles: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "name": self.name, "slide_count": self.slide_count, "styles": list(self.styles)}


def linked_styles(data: dict | None) -> list[str]:
    """The style keys a format links (``caption_classes`` is the old name)."""
    blob = data or {}
    raw = blob.get("linked_styles") or blob.get("caption_classes") or []
    return [k for k in raw if isinstance(k, str) and k in _CATEGORY]


def _summary(row: ContentFormat) -> FormatSummary:
    data = row.data or {}
    count = data.get("default_slide_count")
    return FormatSummary(
        slug=row.slug,
        name=row.name or row.slug,
        slide_count=count if isinstance(count, int) and not isinstance(count, bool) else None,
        styles=tuple(linked_styles(data)),
    )


def format_summaries(db: Session, project_id: UUID) -> list[FormatSummary]:
    rows = db.exec(
        select(ContentFormat).where(ContentFormat.project_id == project_id).order_by(ContentFormat.slug)
    ).all()
    return [_summary(r) for r in rows]


def find_format(db: Session, project_id: UUID, slug: str) -> FormatSummary | None:
    slug = (slug or "").strip().lower()
    if not slug:
        return None
    row = db.exec(
        select(ContentFormat).where(ContentFormat.project_id == project_id, ContentFormat.slug == slug)
    ).first()
    return _summary(row) if row else None


def style_problems(fmt: FormatSummary, slides: Iterable[Any]) -> list[str]:
    """Each photo slide whose caption style the format does not link, as a
    sentence for the agent. Empty when the format links no caption style at
    all: a format that only names a body card leaves captions free."""
    allowed = [k for k in fmt.styles if _CATEGORY.get(k) in _CAPTION_CATEGORIES]
    if not allowed:
        return []
    off = [
        f"{s.slide_id} uses {s.caption_style}"
        for s in slides
        if s.kind == _STYLED_KIND and (s.headline or s.subtext) and s.caption_style not in allowed
    ]
    if not off:
        return []
    return [
        f"This post is in the format {fmt.name} ({fmt.slug}), whose captions use "
        f"{', '.join(allowed)}; {', '.join(off)}."
    ]
