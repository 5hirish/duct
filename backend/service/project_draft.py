"""Where each project field came from, and what may overwrite what.

A project is filled from sources that deserve different trust: the person,
their site, the files they added, a model's guess. Every drafted field carries
a label naming its source (``projects.provenance``), and the rules here decide,
field by field, whether an incoming value lands.

They used to live only in the browser (``app/src/lib/projectDraft.js``, which
still runs them for an instant answer offline), while the server stored values
without labels and a save replaced the whole project. That was safe while the
app was the only writer. A writer on the server side (the MCP server, a GitHub
re-sync) needs the labels and the rules here, or the next save from a device
holding an older copy undoes what it wrote.

Two kinds of write reach a project, and they get different rules:

* **A draft** (``merge_draft``) is a machine speaking: the crawl, the person's
  documents, a model's inference, later an outside agent. It lands only where
  three rules allow:

  1. a value the person set (``user``) is never overwritten;
  2. a filled value gives way only to an equal or higher source (``RANK``):
     the site beats the person's files, because a deck goes stale and a
     homepage is current, and both beat a guess;
  3. a filled value with no label is the person's. Every project made before
     drafts existed is in that state, and typing was the only way a field got
     filled then.

* **A save** (``reconcile_save``) is the person speaking, through a client that
  sends the whole project. A field the person changed wins. A value the client
  only carried along, its copy of an earlier draft, may fill a blank or beat a
  lower source, but never replace an equal one and never blank a field: an
  equal one is most likely the newer draft that client has not seen yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PROVENANCE_USER = "user"
PROVENANCE_CRAWL = "crawl"
PROVENANCE_DOCUMENT = "document"
PROVENANCE_INFERRED = "inferred"

# What a draft may claim to be. "user" is not among them: a writer that is not
# the person cannot mark its value as the person's and so put it beyond the
# reach of every later draft.
DRAFT_SOURCES = frozenset({PROVENANCE_CRAWL, PROVENANCE_DOCUMENT, PROVENANCE_INFERRED})

# Rule 2's order. An unknown label ranks with "inferred": a source this build
# has never heard of gets the least trust, never the most.
RANK = {
    PROVENANCE_USER: 3,
    PROVENANCE_CRAWL: 2,
    PROVENANCE_DOCUMENT: 1,
    PROVENANCE_INFERRED: 0,
}

# The name a project carries until it has a real one (the app's
# UNTITLED_PROJECT). Nobody chose it, so it is not content.
UNTITLED_PROJECT = "Untitled project"


@dataclass(frozen=True)
class DraftField:
    """Where one draftable field lives on ``Project``: a column, or a key inside
    one of its JSON sections. ``kind`` is the type a draft must send."""

    column: str
    key: str | None = None
    kind: type = str


# The fields a draft may write, named as the audit's PROJECT_DRAFT event names
# them. The app also drafts ``favicon``, which it keeps on the device and never
# sends, so a draft naming it is ignored here like any unknown field.
FIELDS: dict[str, DraftField] = {
    "name": DraftField("name"),
    "company_name": DraftField("company_name"),
    "pitch": DraftField("pitch"),
    "website_url": DraftField("url"),
    "industry": DraftField("industry"),
    "business_model": DraftField("business_model"),
    "personas": DraftField("audience", "personas", list),
    "compare_against": DraftField("competition", "compare_against"),
    "competitors": DraftField("competition", "competitors", list),
    "brand_voice": DraftField("brand_channels", "brand_voice"),
    "active_channels": DraftField("brand_channels", "active_channels", list),
    "content_pillars": DraftField("brand_channels", "content_pillars", list),
}


def rank_of(label: str | None) -> int:
    return RANK.get(label or "", RANK[PROVENANCE_INFERRED])


def get_value(project: Any, name: str) -> Any:
    spec = FIELDS[name]
    raw = getattr(project, spec.column)
    return raw if spec.key is None else (raw or {}).get(spec.key)


def set_value(project: Any, name: str, value: Any) -> None:
    spec = FIELDS[name]
    if spec.key is None:
        setattr(project, spec.column, value)
        return
    # A new dict rather than an edit in place: SQLAlchemy sees a change to a
    # JSON column only when the attribute is reassigned.
    setattr(project, spec.column, {**(getattr(project, spec.column) or {}), spec.key: value})


def _blank_row(row: Any) -> bool:
    # Personas and competitors are rows keyed by name. The settings page seeds
    # one empty row ({"name": "", "priority": "primary"}) so the form has
    # something to type into; that row is not content.
    if isinstance(row, Mapping):
        return not str(row.get("name") or "").strip()
    if isinstance(row, str):
        return not row.strip()
    return row is None


def is_blank(name: str, value: Any) -> bool:
    """Whether a field counts as not filled in yet."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or (name == "name" and value == UNTITLED_PROJECT)
    if isinstance(value, list | tuple):
        return all(_blank_row(row) for row in value)
    return False


def _same(name: str, a: Any, b: Any) -> bool:
    return a == b or (is_blank(name, a) and is_blank(name, b))


def _gives_way(name: str, value: Any, label: str | None, incoming: str, *, equal_wins: bool) -> bool:
    """Whether a field as it stands yields to a value from ``incoming``."""
    if label == PROVENANCE_USER:
        return False
    if is_blank(name, value):
        return True
    if label is None:
        return False
    if rank_of(incoming) == rank_of(label):
        return equal_wins
    return rank_of(incoming) > rank_of(label)


def clean_labels(raw: Mapping[str, Any] | None) -> dict[str, str] | None:
    """A client's labels, keeping only fields and sources this build knows.

    ``None`` stays ``None``: it means a client from before the server kept
    labels, which ``reconcile_save`` treats differently from an empty map.
    """
    if raw is None:
        return None
    return {
        name: label for name, label in raw.items()
        if name in FIELDS and isinstance(label, str) and label in RANK
    }


def merge_draft(project: Any, fields: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Land a draft's fields under the three rules. Returns the fields that
    changed. ``fields`` is the PROJECT_DRAFT shape: ``{name: {value, provenance}}``.
    """
    labels = dict(project.provenance or {})
    landed: list[str] = []
    for name, field in fields.items():
        if name not in FIELDS:
            continue
        source, value = field.get("provenance"), field.get("value")
        if source not in DRAFT_SOURCES:
            raise ValueError(f"a draft cannot claim provenance {source!r}")
        if is_blank(name, value):
            continue
        if not _gives_way(name, get_value(project, name), labels.get(name), source, equal_wins=True):
            continue
        set_value(project, name, value)
        labels[name] = source
        landed.append(name)
    project.provenance = labels
    return landed


def snapshot(project: Any | None) -> dict[str, Any]:
    """Every draftable field's value, taken before a save overwrites them.
    ``None`` for a project that does not exist yet."""
    return {name: None if project is None else get_value(project, name) for name in FIELDS}


def reconcile_save(
    project: Any,
    before: Mapping[str, Any],
    before_labels: Mapping[str, str],
    sent_labels: Mapping[str, str] | None,
) -> None:
    """Settle a whole-project save field by field, after it has been written.

    ``before`` and ``before_labels`` are the project as it stood; the save has
    already replaced every column, and this puts back each draftable field the
    save only carried along without the right to change it.
    """
    labels = dict(before_labels)
    for name in FIELDS:
        old, new = before[name], get_value(project, name)
        mine = labels.get(name)
        theirs = None if sent_labels is None else sent_labels.get(name)
        if _same(name, old, new):
            if theirs == PROVENANCE_USER and not is_blank(name, new):
                labels[name] = PROVENANCE_USER  # a chip confirmed, value unchanged
            elif mine is None and theirs in DRAFT_SOURCES and not is_blank(name, new):
                # Drafted on a device before the server kept labels: the
                # browser knows where the value came from and the server does not.
                labels[name] = theirs
            continue
        if sent_labels is None:
            # A client that sends no labels predates them. Its save is last
            # write wins, as every save was, and what it wrote is the person's.
            labels.pop(name, None)
            continue
        if theirs == PROVENANCE_USER or (theirs is None and not is_blank(name, new)):
            # Changed, and either marked as typed or carrying no draft label:
            # a value the client never got from a draft is one the person typed.
            labels[name] = PROVENANCE_USER
            continue
        if not is_blank(name, new) and _gives_way(name, old, mine, theirs, equal_wins=False):
            labels[name] = theirs
            continue
        set_value(project, name, old)
    project.provenance = labels
