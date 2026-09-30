"""The Daily Reflection (issue #270): what a day of work taught, cited.

The unit of work is the reflection, not the post. It reads two sources, both
already Duct's, and nothing on the user's machine:

* **The repository**: the day's commits, merged pull requests, issues,
  releases and doc changes, through the GitHub connector's
  ``github_work_events`` entity (``agents/insights/fetchers.fetch_entity``),
  the same read Insights makes.
* **Duct's own record of the project**: the briefs and audits written that
  day (``artifacts``), the changes proposed, approved, applied or rolled back
  (``execution_change_sets``) and what the project learned (the memories
  observed that day). No other tool can cite "the agent proposed a budget
  shift, I approved it", which is what makes this Duct and not a git digest.

Every item gets a short ref (``gh:…``, ``art:…``, ``cs:…``, ``mem:…``) the
model cites instead of restating, so a claim in the reflection points at the
thing it came from and a ref the day did not contain is refused. A number
may appear only if a source carries it; that is the prompt's rule, and the
refs are how a reader checks it.

The reflection is stored as an artifact of kind ``reflection`` (versioned,
permalinked, in the library like any brief), with its sections kept in
``structured_json`` so the app can show each claim's sources as chips and
hang the drafts off the section they came from (``content_posts.reflection``).

No agent framework here: the tool bodies in ``tools.py`` call these.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Artifact.kind for a reflection; also the conversation's artifact_type.
REFLECTION_KIND = "reflection"
# The GitHub connector's one entity (agents/insights/catalog/github.py).
GITHUB_ENTITY = "github_work_events"
# Streams, not events: a day rarely holds more than three things worth a
# lesson, and a reflection with seven sections is a changelog.
MAX_SECTIONS = 3
# How much of each list reaches the prompt. A busy repo day has hundreds of
# commits; the model needs the shape of the day, and every ref it cites must
# be one it was shown.
MAX_EVENTS = 60
MAX_RECORD_ITEMS = 30

_REF = re.compile(r"\[((?:gh|art|cs|mem):[A-Za-z0-9._#/-]+)\]")


# ---------------------------------------------------------------------------
# What the model writes (the save_reflection tool's input)
# ---------------------------------------------------------------------------


class FieldAnchor(BaseModel):
    """One current source from outside: it confirms, quantifies or
    contradicts the stream. Quoted, so the reader judges the anchor rather
    than trusting it."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="The page the quote is from.")
    title: str = Field(default="", description="The page or publication's name.")
    quote: str = Field(description="The line itself, verbatim, as it appears on the page.")


class ReflectionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description='"s1", "s2" or "s3", in order.')
    title: str = Field(description="The work stream in a few words.")
    happened: str = Field(
        description="What happened, as short markdown. Every claim ends with the "
        "ref it came from in square brackets, e.g. [gh:pr-412] or [cs:3f2a9c1d].",
    )
    field: FieldAnchor | None = Field(default=None, description="What the field says, from web_search.")
    lesson: str = Field(description="The why, as reflection: directional, never the winning mechanism.")

    @field_validator("id")
    @classmethod
    def _section_id(cls, value: str) -> str:
        if not re.fullmatch(r"s[1-9]", value or ""):
            raise ValueError('a section id is "s1", "s2" or "s3"')
        return value


class ReflectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="The day in one line: the thing worth remembering about it.")
    sections: list[ReflectionSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    label: str = Field(default="", description='What changed, for a revision: "Corrected the cause in s2".')


# ---------------------------------------------------------------------------
# The day's sources
# ---------------------------------------------------------------------------


def parse_day(raw: str | None, *, today: date | None = None) -> date:
    """The reflection's date: an ISO day, or today (UTC) when none is given.
    A future day is refused: there is nothing to reflect on yet."""
    today = today or datetime.now(timezone.utc).date()
    if not raw:
        return today
    day = date.fromisoformat(str(raw)[:10])
    if day > today:
        raise ValueError(f"{day.isoformat()} hasn't happened yet.")
    return day


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _short(value: Any) -> str:
    return str(value or "")[:8]


def github_sources(fetched: dict) -> tuple[list[dict], str]:
    """The GitHub read as sources, and a note when there are none: the
    connector missing, or a day with no activity, reads differently to the
    model and to the person."""
    status = fetched.get("status")
    if status != "ok":
        message = str(fetched.get("message") or "").strip()
        return [], f"GitHub is not readable for this project ({status}). {message}".strip()
    data = fetched.get("data") or {}
    rows = [r for r in (data.get("rows") or []) if isinstance(r, dict)]
    out: list[dict] = []
    for row in rows[:MAX_EVENTS]:
        kind = str(row.get("kind") or "event")
        ref = str(row.get("ref") or "").lstrip("#")
        slug = {"pull_request": "pr", "commit": "c", "issue": "i", "release": "r", "docs_change": "doc"}.get(kind, kind)
        out.append({
            "ref": f"gh:{slug}-{ref[:12]}" if ref else f"gh:{slug}-{len(out) + 1}",
            "kind": kind,
            "title": str(row.get("title") or "").strip()[:200],
            "detail": str(row.get("body") or "").strip()[:280],
            "url": str(row.get("url") or ""),
            "state": str(row.get("state") or ""),
        })
    note = "" if out else "GitHub shows no activity on this day."
    if data.get("truncated") or len(rows) > MAX_EVENTS:
        note = f"GitHub shows more than {MAX_EVENTS} events; the first {MAX_EVENTS} are listed."
    return out, note


def duct_sources(db: Any, project_id: UUID, day: date) -> list[dict]:
    """What Duct itself did and learned on the project that day: briefs and
    audits written, changes proposed or applied, memories recorded. A
    reflection's own earlier versions are not a source for itself."""
    from sqlmodel import select

    from models.artifact import Artifact
    from models.execution import ExecutionChangeSet
    from models.memory import ProjectMemory

    start, end = _day_bounds(day)
    out: list[dict] = []

    artifacts = db.exec(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.created_at >= start,
               Artifact.created_at < end, Artifact.kind != REFLECTION_KIND)
        .order_by(Artifact.created_at)
    ).all()
    for a in artifacts[:MAX_RECORD_ITEMS]:
        label = f"{a.kind} v{a.version}" if a.version > 1 else a.kind
        out.append({
            "ref": f"art:{a.slug or _short(a.id)}", "kind": "artifact",
            "title": f"{a.title} ({label})", "detail": (a.summary or "")[:280],
            "url": f"/artifacts/{a.id}", "state": "",
        })

    changes = db.exec(
        select(ExecutionChangeSet)
        .where(ExecutionChangeSet.project_id == project_id,
               ExecutionChangeSet.updated_at >= start, ExecutionChangeSet.updated_at < end)
        .order_by(ExecutionChangeSet.updated_at)
    ).all()
    for c in changes[:MAX_RECORD_ITEMS]:
        out.append({
            "ref": f"cs:{_short(c.id)}", "kind": "change_set",
            "title": f"{c.title} ({c.connector_type}, {c.status})",
            "detail": (c.context or "")[:280], "url": "", "state": c.status,
        })

    memories = db.exec(
        select(ProjectMemory)
        # Every artifact is also mirrored into memory as kind "artifact"; it
        # is already a source above, and twice would read as two things.
        .where(ProjectMemory.project_id == project_id, ProjectMemory.recorded_at >= start,
               ProjectMemory.recorded_at < end, ProjectMemory.superseded_by.is_(None),
               ProjectMemory.kind != "artifact")
        .order_by(ProjectMemory.recorded_at)
    ).all()
    for m in memories[:MAX_RECORD_ITEMS]:
        out.append({
            "ref": f"mem:{_short(m.id)}", "kind": "memory",
            "title": m.title, "detail": (m.body or "")[:280], "url": "", "state": m.kind,
        })
    return out


def render_sources(items: list[dict]) -> str:
    """One line per source, the ref first so the model cites it verbatim."""
    lines = []
    for item in items:
        state = f" [{item['state']}]" if item.get("state") else ""
        detail = f" — {item['detail']}" if item.get("detail") else ""
        lines.append(f"- {item['ref']} · {item['kind']}{state}: {item['title']}{detail}")
    return "\n".join(lines) or "(none)"


# ---------------------------------------------------------------------------
# Checking and rendering what the model wrote
# ---------------------------------------------------------------------------


def cited_refs(text: str) -> list[str]:
    return _REF.findall(text or "")


def reflection_problems(draft: ReflectionDraft, known: set[str]) -> list[str]:
    """What the model must fix before the reflection is saved: a claim with
    no ref, a ref the day did not contain, a lesson with nothing under it."""
    problems: list[str] = []
    ids = [s.id for s in draft.sections]
    if len(set(ids)) != len(ids):
        problems.append("Two sections share an id.")
    for s in draft.sections:
        refs = cited_refs(s.happened)
        if not refs:
            problems.append(f"{s.id}: \"What happened\" cites nothing. End each claim with its ref, e.g. [gh:pr-412].")
        unknown = sorted({r for r in refs if r not in known})
        if unknown:
            problems.append(f"{s.id}: {', '.join(unknown)} is not in today's sources. Cite only refs you were given.")
        if not s.lesson.strip():
            problems.append(f"{s.id}: the lesson is empty.")
    return problems


def render_markdown(draft: ReflectionDraft, day: date, sources: list[dict]) -> str:
    """The reflection as a document, citations turned into links. This is
    the artifact's content; the structured sections ride beside it."""
    by_ref = {s["ref"]: s for s in sources}

    def linked(text: str) -> str:
        def repl(match: re.Match) -> str:
            ref = match.group(1)
            url = (by_ref.get(ref) or {}).get("url") or ""
            return f"[{ref}]({url})" if url else f"`{ref}`"
        return _REF.sub(repl, text)

    parts = [f"# {draft.title}", "", f"*Daily reflection · {day.isoformat()}*", ""]
    for s in draft.sections:
        parts += [f"## {s.title}", "", "**What happened**", "", linked(s.happened.strip()), ""]
        if s.field is not None:
            name = s.field.title or s.field.url
            parts += ["**What the field says**", "", f"> {s.field.quote.strip()}", "", f"— [{name}]({s.field.url})", ""]
        parts += ["**The lesson**", "", s.lesson.strip(), ""]
    return "\n".join(parts).rstrip() + "\n"


def structured(draft: ReflectionDraft, day: date, sources: list[dict]) -> dict:
    """What ``structured_json`` holds: the sections, and every source the day
    offered with its title and link. The app draws a chip for each ref a
    section cites without re-reading GitHub, and a revision in a later
    session can cite a source the first version did not (``restore_sources``)."""
    return {
        "date": day.isoformat(),
        "sections": [s.model_dump(mode="json") for s in draft.sections],
        "sources": {s["ref"]: {k: s.get(k, "") for k in ("kind", "title", "detail", "url", "state")}
                    for s in sources},
    }


def restore_sources(structured_json: dict | None) -> tuple[str, list[dict]]:
    """The day and its sources, read back from a saved reflection, so a
    resumed session revises against exactly what the first one was shown."""
    data = structured_json or {}
    sources = [{"ref": ref, **fields} for ref, fields in (data.get("sources") or {}).items()
               if isinstance(fields, dict)]
    return str(data.get("date") or ""), sources


def save_version(
    db: Any,
    *,
    project_id: UUID,
    user_id: UUID | None,
    conversation_id: UUID | None,
    group_id: UUID | None,
    draft: ReflectionDraft,
    day: date,
    sources: list[dict],
) -> Any:
    """Store the reflection as the next version of its group (v1 when there
    is none yet) and return the new row. The sections go to structured_json,
    which the generic revise path drops for a stored file, so this writes
    each version itself through the one write path every artifact takes."""
    from uuid import uuid4

    from service.artifact_store import ensure_unique_slug, latest_of_group, persist_artifact_version

    content = render_markdown(draft, day, sources)
    head = latest_of_group(db, group_id) if group_id else None
    version = (head.version + 1) if head else 1
    slug = head.slug if head else ensure_unique_slug(db, project_id, reflection_slug(day))
    return persist_artifact_version(
        project_id=project_id,
        user_id=user_id,
        agent_type="tiktok_studio",
        kind=REFLECTION_KIND,
        content_type="text/markdown",
        title=draft.title,
        filename=f"{day.isoformat()}_{slug}_v{version}.md",
        group_id=head.group_id if head else uuid4(),
        version=version,
        conversation_id=conversation_id,
        data=content.encode("utf-8"),
        structured_json=structured(draft, day, sources),
        meta={"label": draft.label or ("Initial version" if version == 1 else f"Version {version}"),
              "date": day.isoformat()},
        slug=slug,
    )


def reflection_slug(day: date) -> str:
    """A day's reflection is one artifact group, found again by its slug."""
    return f"reflection-{day.isoformat()}"


def group_for_day(db: Any, project_id: UUID, day: date) -> UUID | None:
    """The reflection group already written for this day, if any, so a second
    run on the same day revises it instead of starting a rival."""
    from sqlmodel import select

    from models.artifact import Artifact

    row = db.exec(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.kind == REFLECTION_KIND,
               Artifact.slug == reflection_slug(day))
        .order_by(Artifact.version.desc())
    ).first()
    return row.group_id if row is not None else None


def post_link(group_id: UUID, section_id: str, day: date) -> dict:
    """What ``content_posts.reflection`` holds for a derived draft."""
    return {"group_id": str(group_id), "section_id": section_id, "date": day.isoformat()}


__all__ = [
    "FieldAnchor",
    "GITHUB_ENTITY",
    "MAX_SECTIONS",
    "REFLECTION_KIND",
    "ReflectionDraft",
    "ReflectionSection",
    "cited_refs",
    "duct_sources",
    "github_sources",
    "group_for_day",
    "parse_day",
    "post_link",
    "reflection_problems",
    "reflection_slug",
    "render_markdown",
    "render_sources",
    "restore_sources",
    "save_version",
    "structured",
]
