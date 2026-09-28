"""A small gettext PO reader and writer, enough for Lingui's catalogues and ours.

Not ``polib``: the site build runs in CI on a bare ``python3`` and this is the
only consumer. It understands what Lingui writes (``#.`` extracted comments,
``#:`` references, ``#,`` flags, ``msgctxt``, ``msgid``, ``msgstr``, the
``#~`` obsolete prefix, multi-line strings) and writes each file back in the
layout it was written in, so a round trip through ``fill.py`` produces a diff
of exactly the translations that changed. ``dump(parse(text)) == text`` holds
for every catalogue in the repo; keep it that way.
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


# The escapes Lingui's writer (pofile-ts) emits, and their inverse for reading.
_WRITE_ESCAPES = {
    "\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t",
    "\r": "\\r", "\a": "\\a", "\b": "\\b", "\v": "\\v", "\f": "\\f",
}
_ESCAPES = {seq[1]: ch for ch, seq in _WRITE_ESCAPES.items()}


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
    return '"' + "".join(_WRITE_ESCAPES.get(ch, ch) for ch in text) + '"'


# Which layout a catalogue is written back in depends on who owns it.
# `lingui check sync` compares the app's catalogues with what extract would
# write, byte for byte, so those must come back exactly as Lingui's writer
# (pofile-ts, folding off) lays them out: every string on one line however
# long, one `#:` line per reference. This used to write gettext's layout for
# everything, which fails that check on every file `fill.py` touches; nobody
# saw it because the old gate re-ran `lingui extract` over the files and could
# not fail. The site's catalogues are only ever compared with this module's
# own output (`build_site_i18n.py --check`), so they keep the gettext layout
# they were written in rather than reflowing thousands of lines for a tool
# that never reads them.
_LINGUI_GENERATOR = "X-Generator: @lingui/cli"


def _written_by_lingui(catalog: Catalog) -> bool:
    header = catalog.header
    return header is not None and _LINGUI_GENERATOR in header.msgstr


def _gettext_lines(keyword: str, text: str) -> list[str]:
    if not ("\n" in text and text.endswith("\n") and text.count("\n") > 1 or len(text) > 76):
        return [f"{keyword} {_quote(text)}"]
    # An empty first line, then one line per source line.
    parts = text.split("\n")
    tail = [_quote(parts[-1])] if parts[-1] else []
    return [f'{keyword} ""', *(_quote(part + "\n") for part in parts[:-1]), *tail]


def _lingui_lines(keyword: str, text: str) -> list[str]:
    if "\n" not in text:
        return [f"{keyword} {_quote(text)}"]
    # Break after each newline, keyword on the first segment unless the string
    # opens with a newline; a trailing empty segment is written, not dropped.
    parts = text.split("\n")
    segments = [_quote(part + "\n") for part in parts[:-1]] + [_quote(parts[-1])]
    if parts[0] == "":
        return [f'{keyword} ""', *segments]
    return [f"{keyword} {segments[0]}", *segments[1:]]


def _emit(keyword: str, text: str, obsolete: bool, lingui: bool) -> list[str]:
    prefix = "#~ " if obsolete else ""
    lines = _lingui_lines(keyword, text) if lingui else _gettext_lines(keyword, text)
    return [prefix + line for line in lines]


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
    lingui = _written_by_lingui(catalog)
    blocks: list[str] = []
    for e in catalog.entries:
        lines: list[str] = []
        lines += [f"# {c}" if c else "#" for c in e.translator_comments]
        lines += [f"#. {c}" if c else "#." for c in e.extracted_comments]
        if e.references:
            lines += [f"#: {ref}" for ref in e.references] if lingui else ["#: " + " ".join(e.references)]
        if e.flags:
            lines.append("#, " + ("," if lingui else ", ").join(e.flags))
        # Lingui writes its header the gettext way too.
        lingui_layout = lingui and not e.is_header
        if e.msgctxt is not None:
            lines += _emit("msgctxt", e.msgctxt, e.obsolete, lingui_layout)
        lines += _emit("msgid", e.msgid, e.obsolete, lingui_layout)
        lines += _emit("msgstr", e.msgstr, e.obsolete, lingui_layout)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def load(path: Path) -> Catalog:
    return parse(path.read_text(encoding="utf-8"))


def save(path: Path, catalog: Catalog) -> None:
    path.write_text(dump(catalog), encoding="utf-8")
