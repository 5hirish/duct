"""Planning from shipped work (issue #561): what a feed run reads, and whether
it is worth a model call.

Content Studio plans from intent: pillars, goals, a typed direction. A feed
plan starts from what already happened instead, and reads two sources, both
already Duct's:

* **The repository**: merged pull requests, releases, commits on the default
  branch, README and changelog edits, through the GitHub connector's
  ``github_work_events`` entity (``agents/insights/fetchers.fetch_entity``),
  the same read Insights makes.
* **Duct's own record of the project**: briefs written, changes applied or
  rolled back, and what the project learned. No commit-to-post tool can cite
  "the agent proposed it, I approved it, here is what happened"; that is what
  makes this Duct and not a git digest.

Three steps run in code before the model sees anything, each a way the naive
version goes wrong:

1. **Collect** the window: from the end of the last feed plan's window, or a
   fixed look-back the first time. There is no watermark table; the window
   rides on the plan's strategy, and a ref already planned is left out.
2. **Filter**: bots, dependency bumps, ``ci``/``chore``/``test`` work, a
   squash commit that only repeats its pull request, and whatever the
   disclosure level keeps out. A private repository's file paths, open
   issues and diffs never reach the prompt, at any level: the docs patch the
   GitHub fetcher carries is dropped here, and only the file's name is kept.
3. **Gate**: a score over what is left. Below the bar there is no model call
   at all, and the person is told what was left out and why.

Every item that survives gets a short ref (``gh:pr-412``, ``art:…``,
``cs:…``, ``mem:…``) that a plan day cites in ``sources``; ``submit_plan``
and ``revise_plan_days`` refuse a feed day that cites nothing or cites a ref
this run was not shown (``source_problems``). The refs are the reflection
branch's (#270), kept so the two read the same way.

No agent framework here: the runner calls these off the event loop.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# The GitHub connector's one entity (agents/insights/catalog/github.py).
GITHUB_ENTITY = "github_work_events"

# The first feed plan has no previous window to start from.
DEFAULT_LOOK_BACK_DAYS = 14
MAX_LOOK_BACK_DAYS = 30
# How many days of a horizon a feed may take, by default and at most. Two of
# seven keeps a plan built from goals recognisably the person's plan.
DEFAULT_MAX_FEED_DAYS = 2
MAX_FEED_DAYS = 7
# How much reaches the prompt. A busy fortnight is hundreds of commits; the
# model needs the stories, and every ref it cites must be one it was shown.
MAX_ITEMS = 40
MAX_RECORD_ITEMS = 15
MAX_DETAIL_CHARS = 240

# The gate. A release alone is worth a post; three merged changes are; a
# change Duct applied, with its result, is. Memories support a story and
# never make one, so they score nothing.
GATE_SCORE = 3
WEIGHTS: dict[str, int] = {
    "release": 3,
    "change_set": 3,
    "pull_request": 1,
    "commit": 1,
    "docs_change": 1,
    "issue": 1,
    "artifact": 1,
    "memory": 0,
}

# Conventional-commit types that describe how the work was done, not what a
# user got. Work typed this way is left out; untyped work is kept.
NOISE_TYPES = frozenset({"ci", "chore", "test", "tests", "build", "style", "refactor", "deps", "docs", "revert"})
BOT_LOGINS = frozenset({"dependabot", "renovate", "github-actions", "pre-commit-ci", "snyk-bot", "mergify"})
# Root files a reader of the product might see. Everything under docs/ is the
# team's own and only shown at "everything".
PUBLIC_DOCS = frozenset({"README", "CHANGELOG", "ROADMAP"})
# What Duct did that a post can stand on: a change that landed, or was undone.
CHANGE_STATUSES = frozenset({"applied", "partial", "rolled_back"})
# Memory kinds that say what happened or what it taught.
MEMORY_KINDS = frozenset({"outcome", "conclusion", "event", "decision"})

_CONVENTIONAL = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?!?:\s")
_DEPENDENCY = re.compile(r"^(?:build\(deps[^)]*\):\s*)?(?:bump|update|upgrade)\s+\S+.*\bfrom\s+\S+\s+to\s+\S+", re.IGNORECASE)
_SQUASHED_PR = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_COMMIT = re.compile(r"^Merge (?:pull request|branch)\b", re.IGNORECASE)
_REF = re.compile(r"^(?:gh|art|cs|mem):[A-Za-z0-9._#/-]+$")


class Disclosure(StrEnum):
    """How much of the repository a feed may talk about."""

    RELEASES = "releases"      # releases only
    SHIPPED = "shipped"        # releases, merged PRs, default-branch commits, README/CHANGELOG edits
    EVERYTHING = "everything"  # also closed issues and docs/ changes


class LeftOut(StrEnum):
    """Why an event did not reach the prompt. Codes, not sentences: the app
    words them in the reader's language (lib/contentFeed.js), and
    ``LEFT_OUT_WORDS`` is the model's copy."""

    BOT = "bot"
    DEPENDENCY = "dependency"
    CHORE = "chore"
    SQUASHED = "squashed"
    ISSUE = "issue"
    PRERELEASE = "prerelease"
    INTERNAL_DOCS = "internal_docs"
    DISCLOSURE = "disclosure"
    ALREADY_PLANNED = "already_planned"
    OVER_CAP = "over_cap"


LEFT_OUT_WORDS: dict[str, str] = {
    LeftOut.BOT: "bots",
    LeftOut.DEPENDENCY: "dependency bumps",
    LeftOut.CHORE: "chores, CI and tests",
    LeftOut.SQUASHED: "commits already in a pull request",
    LeftOut.ISSUE: "issues",
    LeftOut.PRERELEASE: "pre-releases",
    LeftOut.INTERNAL_DOCS: "internal docs",
    LeftOut.DISCLOSURE: "outside the disclosure level",
    LeftOut.ALREADY_PLANNED: "already on a plan",
    LeftOut.OVER_CAP: "over the cap",
}


class FeedSource(StrEnum):
    GITHUB = "github"
    DUCT = "duct"


class FeedOptions(BaseModel):
    """The setup sheet's answers: what a feed run reads and how much it may change."""

    model_config = ConfigDict(extra="forbid")

    sources: list[FeedSource] = Field(default_factory=lambda: [FeedSource.GITHUB, FeedSource.DUCT], min_length=1)
    # None: from where the last feed plan's window ended.
    look_back_days: int | None = Field(default=None, ge=1, le=MAX_LOOK_BACK_DAYS)
    max_days: int = Field(default=DEFAULT_MAX_FEED_DAYS, ge=1, le=MAX_FEED_DAYS)
    disclosure: Disclosure = Disclosure.SHIPPED


class DaySource(BaseModel):
    """One thing a plan day was built from, as the board draws its chip."""

    model_config = ConfigDict(extra="ignore")

    ref: str = Field(description="The ref exactly as the feed listed it, e.g. gh:pr-412.")
    kind: str = ""
    title: str = ""
    url: str = ""


@dataclass
class FeedItem:
    ref: str
    kind: str
    title: str
    detail: str = ""
    url: str = ""
    at: str = ""
    state: str = ""

    def chip(self) -> dict[str, str]:
        return {"ref": self.ref, "kind": self.kind, "title": self.title, "url": self.url}


@dataclass
class FeedDigest:
    """What a feed run read, kept and left out, and whether it is worth a call."""

    window_from: date
    window_to: date
    options: FeedOptions
    items: list[FeedItem] = field(default_factory=list)
    left_out: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(WEIGHTS.get(i.kind, 0) for i in self.items)

    @property
    def worth_a_plan(self) -> bool:
        return self.score >= GATE_SCORE

    def refs(self) -> dict[str, FeedItem]:
        return {i.ref: i for i in self.items}

    def payload(self) -> dict[str, Any]:
        """What the read step carries to the app: the chips, the left-out line
        and the verdict. Titles and links only; no body text from the repo."""
        return {
            "window": {"from": self.window_from.isoformat(), "to": self.window_to.isoformat()},
            "worth_a_plan": self.worth_a_plan,
            "score": self.score,
            "gate": GATE_SCORE,
            "items": [i.chip() for i in self.items],
            "left_out": {str(k): n for k, n in self.left_out.items()},
            "notes": list(self.notes),
            "max_days": self.options.max_days,
            "disclosure": self.options.disclosure.value,
        }

    def strategy(self) -> dict[str, Any]:
        """What the plan keeps: the window it read, so the next feed run starts
        where this one ended."""
        return {
            "window_from": self.window_from.isoformat(),
            "window_to": self.window_to.isoformat(),
            "sources": [s.value for s in self.options.sources],
            "disclosure": self.options.disclosure.value,
            "max_days": self.options.max_days,
        }


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def feed_window(options: FeedOptions, plans: Iterable[Any], *, today: date) -> tuple[date, date]:
    """From the day after the last feed plan's window ended (a fixed look-back
    when the person asked for one, or the first time), up to today."""
    if options.look_back_days is not None:
        return today - timedelta(days=options.look_back_days - 1), today
    last = None
    for plan in plans:
        feed = (getattr(plan, "strategy", None) or {}).get("feed") or {}
        try:
            end = date.fromisoformat(str(feed.get("window_to") or "")[:10])
        except ValueError:
            continue
        last = end if last is None or end > last else last
    if last is None or last >= today:
        return today - timedelta(days=DEFAULT_LOOK_BACK_DAYS - 1), today
    start = max(last + timedelta(days=1), today - timedelta(days=MAX_LOOK_BACK_DAYS - 1))
    return start, today


def planned_refs(plans: Iterable[Any]) -> set[str]:
    """Every ref a plan day already cites, so a story is told once."""
    refs: set[str] = set()
    for plan in plans:
        for day in getattr(plan, "days", None) or []:
            for src in (day or {}).get("sources") or []:
                ref = (src or {}).get("ref") if isinstance(src, dict) else None
                if ref:
                    refs.add(str(ref))
    return refs


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


def _clip(text: Any, limit: int = MAX_DETAIL_CHARS) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def conventional_type(title: str) -> str:
    match = _CONVENTIONAL.match(title or "")
    return match.group("type").lower() if match else ""


def is_bot(author: Any) -> bool:
    login = str(author or "").lower()
    return login.endswith("[bot]") or login in BOT_LOGINS


def _github_ref(kind: str, raw_ref: str) -> str:
    raw = str(raw_ref or "").strip()
    if kind == "pull_request":
        return f"gh:pr-{raw.lstrip('#')}"
    if kind == "issue":
        return f"gh:i-{raw.lstrip('#')}"
    if kind == "release":
        return f"gh:r-{re.sub(r'[^A-Za-z0-9._-]', '-', raw)[:40]}"
    if kind == "commit":
        return f"gh:c-{raw[:7]}"
    if kind == "docs_change":
        return f"gh:doc-{re.sub(r'[^A-Za-z0-9._/-]', '-', raw)[:60]}"
    return f"gh:{kind}-{raw[:12]}"


def _docs_visible(path: str, disclosure: Disclosure) -> bool:
    if disclosure is Disclosure.EVERYTHING:
        return True
    return "/" not in path and path.split(".", 1)[0].upper() in PUBLIC_DOCS


def github_items(
    rows: list[dict],
    disclosure: Disclosure,
    *,
    already: set[str],
) -> tuple[list[FeedItem], Counter]:
    """The repository's events that could carry a post, and why the rest did
    not. ``rows`` is ``fetch_github``'s list, newest first."""
    left: Counter = Counter()
    merged_prs = {
        str(r.get("ref") or "").lstrip("#")
        for r in rows if r.get("kind") == "pull_request"
    }
    kept: list[FeedItem] = []
    for row in rows:
        kind = str(row.get("kind") or "")
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        if disclosure is Disclosure.RELEASES and kind != "release":
            left[LeftOut.DISCLOSURE] += 1
            continue
        if kind == "issue" and (disclosure is not Disclosure.EVERYTHING or row.get("state") != "completed"):
            left[LeftOut.ISSUE] += 1
            continue
        if kind == "release" and row.get("state") == "prerelease" and disclosure is not Disclosure.EVERYTHING:
            left[LeftOut.PRERELEASE] += 1
            continue
        if is_bot(row.get("author")):
            left[LeftOut.BOT] += 1
            continue
        if _DEPENDENCY.match(title):
            left[LeftOut.DEPENDENCY] += 1
            continue
        if kind in ("commit", "pull_request") and conventional_type(title) in NOISE_TYPES:
            left[LeftOut.CHORE] += 1
            continue
        if kind == "commit":
            squashed = _SQUASHED_PR.search(title)
            if _MERGE_COMMIT.match(title) or (squashed and squashed.group(1) in merged_prs):
                left[LeftOut.SQUASHED] += 1
                continue
        if kind == "docs_change":
            path = str(row.get("ref") or "")
            if not _docs_visible(path, disclosure):
                left[LeftOut.INTERNAL_DOCS] += 1
                continue
            # The patch is the file's text; a plan needs to know it changed.
            detail = ""
        else:
            detail = _clip(row.get("body"))
        ref = _github_ref(kind, str(row.get("ref") or ""))
        if ref in already:
            left[LeftOut.ALREADY_PLANNED] += 1
            continue
        kept.append(FeedItem(
            ref=ref, kind=kind, title=_clip(title, 200), detail=detail,
            url=str(row.get("url") or ""), at=str(row.get("at") or "")[:10],
            state=str(row.get("state") or ""),
        ))
    return kept, left


def github_note(fetched: dict) -> tuple[list[dict], str]:
    """The rows from a ``fetch_entity`` answer, and a sentence when there are none."""
    status = fetched.get("status")
    if status != "ok":
        message = str(fetched.get("message") or "").strip()
        return [], f"GitHub is not readable for this project ({status}). {message}".strip()
    data = fetched.get("data") or {}
    rows = [r for r in (data.get("rows") or []) if isinstance(r, dict)]
    return rows, "" if rows else "GitHub shows no activity in this window."


# ---------------------------------------------------------------------------
# Duct's own record
# ---------------------------------------------------------------------------


def _short(value: Any) -> str:
    return str(value or "")[:8]


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def duct_items(db: Any, project_id: UUID, start: date, end: date, *, already: set[str]) -> list[FeedItem]:
    """Briefs Duct wrote, changes it applied or rolled back, and what the
    project learned, inside the window. Shared memory only: a teammate's
    private memory is not a source for a public post."""
    from sqlmodel import select

    from models.artifact import Artifact
    from models.execution import ExecutionChangeSet
    from models.memory import ProjectMemory
    from service.memory import shared_rows

    lo, hi = _bounds(start, end)
    out: list[FeedItem] = []

    artifacts = db.exec(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.created_at >= lo, Artifact.created_at < hi)
        .order_by(Artifact.created_at.desc())
    ).all()
    seen_groups: set[Any] = set()
    for a in artifacts:
        ctype = (a.content_type or "").lower()
        if ctype.startswith(("image/", "video/")) or a.group_id in seen_groups:
            continue
        seen_groups.add(a.group_id)
        if len(seen_groups) > MAX_RECORD_ITEMS:
            break
        out.append(FeedItem(
            ref=f"art:{a.slug or _short(a.id)}", kind="artifact", title=_clip(a.title, 200),
            detail=_clip(a.summary), url=f"/artifacts/{a.id}", at=a.created_at.date().isoformat(),
            state=a.kind,
        ))

    changes = db.exec(
        select(ExecutionChangeSet)
        .where(ExecutionChangeSet.project_id == project_id,
               ExecutionChangeSet.updated_at >= lo, ExecutionChangeSet.updated_at < hi,
               ExecutionChangeSet.status.in_(CHANGE_STATUSES))
        .order_by(ExecutionChangeSet.updated_at.desc())
    ).all()
    for c in changes[:MAX_RECORD_ITEMS]:
        out.append(FeedItem(
            ref=f"cs:{_short(c.id)}", kind="change_set",
            title=_clip(f"{c.title} ({c.connector_type}, {c.status})", 200),
            detail=_clip(c.context), at=c.updated_at.date().isoformat(), state=c.status,
        ))

    memories = db.exec(
        select(ProjectMemory)
        .where(shared_rows(project_id), ProjectMemory.recorded_at >= lo, ProjectMemory.recorded_at < hi,
               ProjectMemory.superseded_by.is_(None), ProjectMemory.kind.in_(MEMORY_KINDS))
        .order_by(ProjectMemory.recorded_at.desc())
    ).all()
    for m in memories[:MAX_RECORD_ITEMS]:
        out.append(FeedItem(
            ref=f"mem:{_short(m.id)}", kind="memory", title=_clip(m.title, 200),
            detail=_clip(m.body), at=m.recorded_at.date().isoformat(), state=m.kind,
        ))
    return [i for i in out if i.ref not in already]


# ---------------------------------------------------------------------------
# Assembly, prompt and checks
# ---------------------------------------------------------------------------


def build_digest(
    options: FeedOptions,
    window: tuple[date, date],
    *,
    github_rows: list[dict] | None,
    github_note_text: str = "",
    duct: list[FeedItem] | None,
    already: set[str],
) -> FeedDigest:
    """Filter, cap and score. Releases and Duct's applied changes go first,
    because when the cap bites those are the stories to keep."""
    digest = FeedDigest(window_from=window[0], window_to=window[1], options=options)
    items: list[FeedItem] = []
    if github_rows is not None:
        kept, left = github_items(github_rows, options.disclosure, already=already)
        items += kept
        digest.left_out.update(left)
    if github_note_text:
        digest.notes.append(github_note_text)
    if duct is not None:
        items += duct
    order = {"release": 0, "change_set": 1, "pull_request": 2, "artifact": 3, "commit": 4,
             "docs_change": 5, "issue": 6, "memory": 7}
    # Newest first inside a kind.
    items.sort(key=lambda i: (order.get(i.kind, 9), _neg_date(i.at)))
    if len(items) > MAX_ITEMS:
        digest.left_out[LeftOut.OVER_CAP] += len(items) - MAX_ITEMS
        items = items[:MAX_ITEMS]
    digest.items = items
    return digest


def _neg_date(at: str) -> int:
    try:
        return -date.fromisoformat(at[:10]).toordinal()
    except ValueError:
        return 0


def render_digest(digest: FeedDigest) -> str:
    """One line per item, the ref first so the model cites it verbatim."""
    lines = []
    for item in digest.items:
        state = f" [{item.state}]" if item.state else ""
        when = f" {item.at}" if item.at else ""
        detail = f": {item.detail}" if item.detail else ""
        lines.append(f"- {item.ref} · {item.kind}{state}{when} · {item.title}{detail}")
    left = "; ".join(f"{LEFT_OUT_WORDS.get(why, why)}: {n}" for why, n in digest.left_out.most_common()) or "nothing"
    notes = "".join(f"\nNote: {n}" for n in digest.notes)
    return (
        f"Window: {digest.window_from.isoformat()} to {digest.window_to.isoformat()}. "
        f"Left out by Duct before you: {left}.{notes}\n"
        + ("\n".join(lines) or "(nothing)")
    )


def source_problems(
    days: list[Any],
    known: dict[str, FeedItem],
    *,
    max_days: int,
) -> list[str]:
    """What a plan from shipped work must fix before it is proposed: a ref the
    run was not shown, a source with no ref, or more feed days than allowed."""
    problems: list[str] = []
    feed_days = 0
    for index, day in enumerate(days):
        sources = getattr(day, "sources", None) or []
        if not sources:
            continue
        feed_days += 1
        for src in sources:
            ref = getattr(src, "ref", "") or ""
            if not _REF.match(ref):
                problems.append(f"Day {index + 1}: {ref!r} is not a ref. Cite refs exactly as listed, e.g. gh:pr-412.")
            elif ref not in known:
                problems.append(f"Day {index + 1}: {ref} is not in this run's feed. Cite only refs you were shown.")
    if feed_days > max_days:
        problems.append(
            f"{feed_days} days cite the feed; this plan may give it at most {max_days}. "
            "Keep the strongest stories and leave the other days as they were."
        )
    return problems


def resolve_sources(days: list[Any], known: dict[str, FeedItem]) -> None:
    """Fill each cited source's title, kind and link from the feed, so the
    chip shows what the source is, not what the model called it."""
    for day in days:
        for src in getattr(day, "sources", None) or []:
            item = known.get(getattr(src, "ref", ""))
            if item is not None:
                src.kind, src.title, src.url = item.kind, item.title, item.url


__all__ = [
    "DEFAULT_LOOK_BACK_DAYS",
    "DEFAULT_MAX_FEED_DAYS",
    "GATE_SCORE",
    "GITHUB_ENTITY",
    "DaySource",
    "Disclosure",
    "FeedDigest",
    "FeedItem",
    "FeedOptions",
    "FeedSource",
    "LEFT_OUT_WORDS",
    "LeftOut",
    "build_digest",
    "conventional_type",
    "duct_items",
    "feed_window",
    "github_items",
    "github_note",
    "is_bot",
    "planned_refs",
    "render_digest",
    "resolve_sources",
    "source_problems",
]
