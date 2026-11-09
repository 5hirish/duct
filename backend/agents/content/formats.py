"""The content format library: built-in recipes on disk plus a project's own.

A format is a skill file for the drafting agent: a Markdown recipe (slide
structure, hook rules, image prompt rules, failure modes) with a small header
saying what it applies to. The agent filters the library by the media kind it
is making and the channel it is drafting for, then follows the spec.

Two sources, one shape:

  - Built-ins live in ``backend/data/formats/<slug>.md`` with YAML frontmatter
    and ship with every project, read-only. The frontmatter follows the Agent
    Skills convention (``name`` is the slug, ``description`` says what and
    when), so a file here is also a valid SKILL.md and a SKILL.md can be
    dropped in here.
  - A project's own formats live in ``content_formats`` rows, ``data`` holding
    the same fields (``description``, ``media``, ``channels``,
    ``spec_markdown``). A row whose slug matches a built-in replaces it for
    that project; deleting the row brings the built-in back.

No YAML dependency: the header grammar is ``key: value``, ``key: [a, b]`` and
``key:`` followed by ``- item`` lines, which is all a format header needs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from agents.content.channels import Platform
from agents.content.platform_guides import MEDIA_KINDS

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "data" / "formats"

SOURCE_BUILTIN = "builtin"
SOURCE_CUSTOM = "custom"

# Agent Skills ``name`` rule: lowercase, digits, single hyphens, no edges.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION = 1024

# Keys from earlier shapes of ``data`` that nothing reads any more. A save
# through the API drops them so old rows converge on the current shape.
LEGACY_DATA_KEYS = ("default_slide_count", "linked_styles", "caption_classes", "format_style")

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
_PLATFORM_VALUES = frozenset(str(p) for p in Platform)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    return text


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into its header dict and the Markdown body.

    A file with no header parses as ``({}, text)`` so a plain spec still loads;
    the validator then says what is missing.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, Any] = {}
    key: str | None = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and key is not None:
            # A block list item under the key above. The key was set to [] when
            # its own line carried no value.
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        k, _, v = stripped.partition(":")
        key = k.strip()
        meta[key] = _scalar(v) if v.strip() else []
    return meta, text[m.end():]


def render_frontmatter(meta: dict[str, Any]) -> str:
    """The inverse of :func:`parse_frontmatter`, for export as a SKILL.md."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            text = str(v)
            if ":" in text or text.startswith(("[", "'", '"')):
                text = '"' + text.replace('"', '\\"') + '"'
            lines.append(f"{k}: {text}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Applicability
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return [str(x) for x in value]


def normalize_media(value: Any) -> list[str]:
    """The media kinds a format applies to, validated, in canonical order.
    Empty means every kind."""
    wanted = {v.strip().lower() for v in _as_list(value) if v.strip()}
    unknown = wanted - set(MEDIA_KINDS)
    if unknown:
        raise ValueError(f"unknown media kind(s): {', '.join(sorted(unknown))}; use {', '.join(MEDIA_KINDS)}")
    return [k for k in MEDIA_KINDS if k in wanted]


def normalize_channels(value: Any) -> list[str]:
    """The channels a format applies to, validated, in enum order. Empty means
    every channel."""
    wanted = {v.strip().lower() for v in _as_list(value) if v.strip()}
    unknown = wanted - _PLATFORM_VALUES
    if unknown:
        raise ValueError(f"unknown channel(s): {', '.join(sorted(unknown))}")
    return [str(p) for p in Platform if str(p) in wanted]


def applies(fmt: dict, *, media: str | None = None, channel: str | None = None) -> bool:
    """Whether a format record fits the media kind and channel asked for. An
    empty filter on either side matches everything, so a format that names no
    channels is offered everywhere and a caller that names no channel sees
    every format."""
    if media:
        kinds = fmt.get("media") or []
        if kinds and media not in kinds:
            return False
    if channel:
        chans = fmt.get("channels") or []
        if chans and channel not in chans:
            return False
    return True


def select(formats: list[dict], *, media: str | None = None, channel: str | None = None) -> list[dict]:
    return [f for f in formats if applies(f, media=media, channel=channel)]


# ---------------------------------------------------------------------------
# Data shape shared by both sources
# ---------------------------------------------------------------------------


def validate_data(data: dict) -> dict:
    """Normalise a format's ``data`` for storage: the four known fields, the
    filters validated, legacy keys dropped. Raises ValueError on an unknown
    media kind or channel so the API answers 422 rather than storing a filter
    nothing will ever match."""
    out = {k: v for k, v in (data or {}).items() if k not in LEGACY_DATA_KEYS}
    out["description"] = str(out.get("description") or "").strip()[:MAX_DESCRIPTION]
    out["media"] = normalize_media(out.get("media"))
    out["channels"] = normalize_channels(out.get("channels"))
    out["spec_markdown"] = str(out.get("spec_markdown") or "")
    return out


def _record(
    *,
    slug: str,
    name: str,
    data: dict,
    source: str,
    id: Any = None,
    created_at: str = "",
    updated_at: str = "",
) -> dict:
    return {
        "id": id,
        "slug": slug,
        "name": name or slug,
        "source": source,
        "description": str(data.get("description") or ""),
        "media": list(data.get("media") or []),
        "channels": list(data.get("channels") or []),
        "spec_markdown": str(data.get("spec_markdown") or ""),
        "data": data,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ---------------------------------------------------------------------------
# Built-ins
# ---------------------------------------------------------------------------


def load_builtin(path: Path) -> dict:
    """One built-in from its file. Raises ValueError naming the file when the
    header breaks a rule, which is how the test suite keeps the directory
    honest."""
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    slug = path.stem
    problems: list[str] = []
    if not SLUG_RE.match(slug):
        problems.append(f"file name {slug!r} is not a slug (lowercase, digits, single hyphens)")
    if meta.get("name") != slug:
        problems.append(f"frontmatter name must equal the file name {slug!r}")
    title = str(meta.get("title") or "").strip()
    if not title:
        problems.append("frontmatter needs a title")
    description = str(meta.get("description") or "").strip()
    if not 1 <= len(description) <= MAX_DESCRIPTION:
        problems.append(f"description must be 1 to {MAX_DESCRIPTION} characters")
    try:
        media = normalize_media(meta.get("media"))
        channels = normalize_channels(meta.get("channels"))
    except ValueError as exc:
        problems.append(str(exc))
        media, channels = [], []
    if not body.strip():
        problems.append("the spec body is empty")
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems))
    data = {
        "description": description,
        "media": media,
        "channels": channels,
        "spec_markdown": body.strip() + "\n",
    }
    return _record(slug=slug, name=title, data=data, source=SOURCE_BUILTIN)


@lru_cache(maxsize=1)
def builtin_formats() -> tuple[dict, ...]:
    """Every built-in, loaded once per process. Order is the file name order,
    which is also the slug order."""
    if not BUILTIN_DIR.is_dir():
        return ()
    return tuple(load_builtin(p) for p in sorted(BUILTIN_DIR.glob("*.md")))


def builtin_by_slug(slug: str) -> dict | None:
    for f in builtin_formats():
        if f["slug"] == slug:
            return f
    return None


# ---------------------------------------------------------------------------
# The merged library
# ---------------------------------------------------------------------------


def custom_record(row: Any) -> dict:
    """A ``ContentFormat`` row as a library record. Reads any shape ``data``
    has had, since rows predate the filters."""
    data = dict(row.data or {})
    try:
        media = normalize_media(data.get("media"))
    except ValueError:
        media = []
    try:
        channels = normalize_channels(data.get("channels"))
    except ValueError:
        channels = []
    data["media"], data["channels"] = media, channels
    rec = _record(
        slug=row.slug,
        name=row.name,
        data=data,
        source=SOURCE_CUSTOM,
        id=row.id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )
    rec["overrides_builtin"] = builtin_by_slug(row.slug) is not None
    return rec


def library(rows: list[Any]) -> list[dict]:
    """The project's library: its own rows, then every built-in no row
    replaces, sorted by name so built-ins and customs read as one list."""
    out = [custom_record(r) for r in rows]
    taken = {r["slug"] for r in out}
    out.extend(f for f in builtin_formats() if f["slug"] not in taken)
    out.sort(key=lambda f: (f["name"].lower(), f["slug"]))
    return out
