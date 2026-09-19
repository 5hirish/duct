"""A small gettext PO reader and writer, enough for Lingui's catalogues and ours.

Not ``polib``: the site build runs in CI on a bare ``python3`` and this is the
only consumer. It understands what Lingui writes (``#.`` extracted comments,
``#:`` references, ``#,`` flags, ``msgctxt``, ``msgid``, ``msgstr``, the
``#~`` obsolete prefix, multi-line strings) and writes it back in the same
shape, so a round trip through ``fill.py`` produces a diff of exactly the
translations that changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Entry:
    msgid: str
    msgstr: str = ""
    msgctxt: str | None = None
    extracted_comments: list[str] = field(default_factory=list)
    translator_comments: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    obsolete: bool = False

    @property
    def key(self) -> tuple[str | None, str]:
        return (self.msgctxt, self.msgid)

    @property
    def is_header(self) -> bool:
        return self.msgid == "" and self.msgctxt is None

    @property
    def needs_translation(self) -> bool:
        return not self.is_header and not self.obsolete and self.msgstr == ""


@dataclass
class Catalog:
    entries: list[Entry] = field(default_factory=list)

    @property
    def header(self) -> Entry | None:
        return next((e for e in self.entries if e.is_header), None)

    def find(self, msgid: str, msgctxt: str | None = None) -> Entry | None:
        return next((e for e in self.entries if e.key == (msgctxt, msgid)), None)

    def untranslated(self) -> list[Entry]:
        return [e for e in self.entries if e.needs_translation]


_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}


def _unquote(text: str) -> str:
    text = text.strip()
    if not (text.startswith('"') and text.endswith('"')):
        raise ValueError(f"expected a quoted string, got {text!r}")
    out, i, body = [], 0, text[1:-1]
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(_ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def _emit(keyword: str, text: str, obsolete: bool) -> list[str]:
    prefix = "#~ " if obsolete else ""
    if "\n" in text and text.endswith("\n") and text.count("\n") > 1 or len(text) > 76:
        # gettext's own layout for long or multi-line strings: an empty first
        # line, then one line per source line.
        lines = [f"{prefix}{keyword} \"\""]
        parts = text.split("\n")
        for idx, part in enumerate(parts):
            if idx < len(parts) - 1:
                lines.append(f"{prefix}{_quote(part + chr(10))}")
            elif part:
                lines.append(f"{prefix}{_quote(part)}")
        return lines
    return [f"{prefix}{keyword} {_quote(text)}"]


def parse(text: str) -> Catalog:
    catalog = Catalog()
    current: Entry | None = None
    target: str | None = None  # which string a continuation line appends to

    def flush() -> None:
        nonlocal current, target
        if current is not None:
            catalog.entries.append(current)
        current, target = None, None

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        obsolete = line.startswith("#~")
        if obsolete:
            line = line[2:].lstrip()
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("#") and not obsolete:
            if current is not None and target is not None:
                # a comment after strings starts a new entry
                flush()
            if current is None:
                current = Entry(msgid="")
            kind, _, body = stripped.partition(" ")
            if kind == "#.":
                current.extracted_comments.append(body)
            elif kind == "#:":
                current.references.extend(body.split())
            elif kind == "#,":
                current.flags.extend(f.strip() for f in body.split(","))
            else:
                current.translator_comments.append(stripped[1:].lstrip())
            continue
        if stripped.startswith('"'):
            if current is None or target is None:
                raise ValueError(f"stray string: {raw!r}")
            setattr(current, target, getattr(current, target) + _unquote(stripped))
            continue
        keyword, _, rest = stripped.partition(" ")
        if keyword == "msgctxt":
            if current is not None and target is not None:
                flush()
            if current is None:
                current = Entry(msgid="")
            current.msgctxt = _unquote(rest)
            target = "msgctxt"
        elif keyword == "msgid":
            if current is not None and target in ("msgid", "msgstr"):
                flush()
            if current is None:
                current = Entry(msgid="")
            current.msgid = _unquote(rest)
            target = "msgid"
        elif keyword == "msgstr":
            if current is None:
                raise ValueError(f"msgstr before msgid: {raw!r}")
            current.msgstr = _unquote(rest)
            target = "msgstr"
        else:
            raise ValueError(f"unrecognised PO line: {raw!r}")
        if obsolete and current is not None:
            current.obsolete = True
    flush()
    return catalog


def dump(catalog: Catalog) -> str:
    blocks: list[str] = []
    for e in catalog.entries:
        lines: list[str] = []
        lines += [f"# {c}" if c else "#" for c in e.translator_comments]
        lines += [f"#. {c}" for c in e.extracted_comments]
        if e.references:
            lines.append("#: " + " ".join(e.references))
        if e.flags:
            lines.append("#, " + ", ".join(e.flags))
        if e.msgctxt is not None:
            lines += _emit("msgctxt", e.msgctxt, e.obsolete)
        lines += _emit("msgid", e.msgid, e.obsolete)
        lines += _emit("msgstr", e.msgstr, e.obsolete)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def load(path: Path) -> Catalog:
    return parse(path.read_text(encoding="utf-8"))


def save(path: Path, catalog: Catalog) -> None:
    path.write_text(dump(catalog), encoding="utf-8")
