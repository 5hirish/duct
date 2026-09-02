"""The insights brief — what the agent writes, and how it becomes an artifact.

The agent delivers a brief by streaming it inside ``<duct_artifact>`` rather
than by calling a submit tool, which is a deliberate trade. The tag streams, so
the reader watches the brief being written in the pane beside the chat; a tool
call would carry the whole document as one JSON string argument, arriving all
at once and losing the lot to a single escaping mistake in a long markdown
document.

The cost of streaming prose is that the payload has no schema, so the title has
to travel *inside* it. A front-matter fence carries it:

    ---
    title: Why CPA rose through August
    format: markdown
    ---
    # ...

Nothing here trusts the model to comply. A payload with no fence still becomes
a brief: the title falls back to the first heading and then to a generic one.
Losing a brief the model actually wrote is the single outcome this module
exists to prevent, so every parse failure degrades rather than raises.

**The content decides the format, never the declaration.** ``format:`` is
recorded as what the model intended, but the content type comes from reading
the bytes — a markdown document served as ``text/html`` renders as garbage in
an iframe, and the bytes are the only evidence that cannot be wrong. The user's
preference steers what the model *writes* (it rides in the user turn); this
function reports what actually arrived.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from service.artifact_store import HTML, MARKDOWN, ArtifactVersion
from utils.strings import slugify

# Formats a brief can be written in. See agents/preferences.py for why
# "dashboard" is not among them yet.
FORMATS: tuple[str, ...] = ("markdown", "html")
DEFAULT_FORMAT = "markdown"

CONTENT_TYPE: dict[str, str] = {"markdown": MARKDOWN, "html": HTML}

DEFAULT_TITLE = "Growth brief"

# models.artifact.Artifact.kind for a brief. Deliberately not "report": the
# report-specific paths in routes/artifacts.py rehydrate structured audit JSON,
# and a brief is prose. `kind` names what the artifact is.
ARTIFACT_KIND = "brief"

# A leading `---` … `---` fence. Anchored at the start so a horizontal rule in
# the body can never be mistaken for front matter.
_FENCE = re.compile(r"\A\s*---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_KEY_VALUE = re.compile(r"\A([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)\Z")

# Openers that mean "this is a document, not prose". Checked case-insensitively
# against the first non-space characters.
_HTML_OPENERS = ("<!doctype", "<html", "<head", "<body", "<div", "<section", "<article", "<style")

_MD_HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
_HTML_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HTML_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Brief:
    """One brief as the agent wrote it, ready to become an artifact version."""

    title: str
    format: str
    body: str
    label: str = ""
    # What the front matter *claimed*, when it claimed anything. Kept apart
    # from ``format`` so a disagreement is visible in the stored metadata
    # rather than silently resolved.
    declared_format: str = ""

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE.get(self.format, MARKDOWN)


def _front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Split a leading `---` fence off the payload. Missing fence → ({}, raw)."""
    match = _FENCE.match(raw)
    if match is None:
        return {}, raw
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        kv = _KEY_VALUE.match(line.strip())
        if kv is not None:
            fields[kv.group(1).lower()] = kv.group(2).strip().strip("\"'")
    return fields, raw[match.end():]


def sniff_format(body: str) -> str:
    """The format the bytes actually are. Never raises, never returns unknown."""
    head = body.lstrip()[:200].lower()
    return "html" if head.startswith(_HTML_OPENERS) else "markdown"


def _derive_title(body: str, fmt: str) -> str:
    """A title from the document itself, when the front matter gave none."""
    if fmt == "html":
        for pattern in (_HTML_TITLE, _HTML_H1):
            match = pattern.search(body)
            if match is not None:
                text = _TAGS.sub("", match.group(1)).strip()
                if text:
                    return text
        return DEFAULT_TITLE
    match = _MD_HEADING.search(body)
    return match.group(1).strip() if match is not None else DEFAULT_TITLE


def parse_brief(raw: str) -> Brief:
    """Read one ``<duct_artifact>`` payload into a ``Brief``. Never raises."""
    fields, body = _front_matter(raw or "")
    body = body.strip("\n")
    declared = (fields.get("format") or "").strip().lower()
    fmt = sniff_format(body)
    title = (fields.get("title") or "").strip() or _derive_title(body, fmt)
    return Brief(
        title=title[:200],
        format=fmt,
        body=body,
        label=(fields.get("label") or "").strip()[:120],
        declared_format=declared if declared in FORMATS else "",
    )


def brief_artifact_version(body: dict) -> ArtifactVersion:
    """ARTIFACT_VERSION adapter for insights — see service/artifact_store.py.

    Reads the structured payload the runner emits (already parsed, so the SSE
    consumers and the store see the same fields) rather than re-parsing the
    raw tag payload here.
    """
    payload = body.get("payload") or {}
    version = int(body.get("version_id") or 1)
    label = str(body.get("label") or f"Version {version}")
    title = str(payload.get("title") or DEFAULT_TITLE)
    fmt = str(payload.get("format") or DEFAULT_FORMAT)
    content = str(payload.get("content") or "")
    stem = slugify(title) or "growth-brief"
    meta = {"label": label, "format": fmt, "chars": len(content)}
    declared = str(payload.get("declared_format") or "")
    if declared and declared != fmt:
        # Recorded, not corrected. A model that says HTML and writes markdown
        # is worth knowing about; a brief rendered by its declaration instead
        # of its content is not.
        meta["declared_format"] = declared
    return ArtifactVersion(
        content_type=CONTENT_TYPE.get(fmt, MARKDOWN),
        title=title,
        slug_stem=stem,
        file_stem=stem,
        data=content.encode("utf-8"),
        meta=meta,
        source_text=content,
        noun="growth brief",
        summary_focus=(
            "what it concluded and recommended, the numbers it rests on and the "
            "window they cover, and what it says could not be verified"
        ),
    )
