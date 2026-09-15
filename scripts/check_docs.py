#!/usr/bin/env python3
"""Hold every document in docs/ to the naming and metadata rule.

Two kinds of document, told apart by the filename (docs/README.md, "Naming"):

  records     YYYY-MM-DD-<slug>.md|html  — a review, plan, research report or
              decision, frozen on the day it was written. Carries
              `Author:` and `Date:`; the date must match the filename.
  references  <slug>.md                  — a runbook, contract or inventory
              that has to be true now. Carries `Author:` and `Updated:`, and
              the `Updated:` date may not fall behind the last commit that
              touched the file — editing a reference without moving its date
              is the failure this exists to catch.

An .html document must earn its markup: it is allowed only when it carries a
figure (an <svg>, <img>, <figure>, <canvas> or mermaid block). Everything
else is markdown, which diffs in review, renders on GitHub and costs no
styling to write or read.

A document may also list repository paths in `files: [...]` arrays (the
architecture page does, one per node). Every such path must exist, so a
rename fails the check instead of leaving a dead link on the map.

Exempt: docs/guides/ (third-party material with its own provenance headers),
every folder README.md (an index), assets/, and the generated agent prompts.

    python3 scripts/check_docs.py            # make check-docs; docs.yml in CI
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("docs/engineering", "docs/design", "docs/archive")
#: Documents that sit at the docs root rather than in a folder.
ROOT_DOCS = ("docs/architecture.html",)
#: Folders whose every document must be a record.
RECORDS_ONLY = ("docs/archive",)
EXEMPT = frozenset({"docs/engineering/agent-prompts.md"})  # generated, CI-diffed
DOC_EXTENSIONS = frozenset({".md", ".html"})

RECORD_NAME = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9.-]*$")
MD_META = re.compile(
    r"\*\*Author:\*\* (?P<author>[^·\n]+?) · \*\*(?P<kind>Date|Updated):\*\* (?P<date>\d{4}-\d{2}-\d{2})"
)
HTML_META = re.compile(
    r"<b>Author</b>\s*(?P<author>[^<·\n]+?)\s*(?:</span>|·)", re.DOTALL
)
FIGURE = re.compile(r"<(svg|img|figure|canvas)\b|class=\"mermaid\"|```mermaid", re.IGNORECASE)
HTML_DATE = re.compile(r"<b>(?P<kind>Date|Updated)</b>\s*(?P<date>\d{4}-\d{2}-\d{2})")
FILE_LISTS = re.compile(r"files:\s*\[([^\]]*)\]")
QUOTED = re.compile(r'"([^"]+)"')


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def last_change(rel: str) -> dt.date | None:
    """The date the file was last changed: today if it has uncommitted edits,
    else its last commit date, else None when git cannot say."""
    if git("status", "--porcelain", "--", rel):
        return dt.date.today()
    committed = git("log", "-1", "--format=%cs", "--", rel)
    return dt.date.fromisoformat(committed) if committed else None


def metadata(path: Path) -> tuple[str, str, str] | None:
    """(author, kind, date) from the document's header line, or None."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".md":
        m = MD_META.search(text)
        return (m["author"], m["kind"], m["date"]) if m else None
    head = text[:20000]
    author = HTML_META.search(head)
    date = HTML_DATE.search(head)
    if not (author and date):
        return None
    return author["author"].strip(), date["kind"], date["date"]


def check(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    stem, ext = path.stem, path.suffix.lower()
    record = RECORD_NAME.match(stem)
    problems: list[str] = []

    if ext not in DOC_EXTENSIONS:
        # A binary next to a record (the .docx twin of a design document)
        # must carry the same dated name, so it sorts and ages with it.
        if not record:
            problems.append("not a document, so it needs a dated filename or a home under assets/")
        return problems

    if any(rel.startswith(f) for f in RECORDS_ONLY) and not record:
        problems.append("everything in the archive is a record: name it YYYY-MM-DD-<slug>")

    if ext == ".html" and not FIGURE.search(path.read_text(encoding="utf-8", errors="replace")):
        problems.append(
            "an HTML document with no figure (<svg>, <img>, <figure>, <canvas> or mermaid): write it as markdown"
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    for block in FILE_LISTS.findall(text):
        for listed in QUOTED.findall(block):
            if not (ROOT / listed).exists():
                problems.append(f"lists {listed}, which does not exist — the map is stale")

    meta = metadata(path)
    if meta is None:
        problems.append(
            "no author/date line — add `**Author:** <git user> · **Date:** YYYY-MM-DD` "
            "(record) or `**Updated:** YYYY-MM-DD` (reference) under the title"
        )
        return problems
    author, kind, date = meta
    if not author.strip():
        problems.append("author is empty")

    if record:
        if kind != "Date":
            problems.append("a dated file is a record and carries `Date:`, not `Updated:`")
        elif date != record["date"]:
            problems.append(f"Date: {date} disagrees with the filename's {record['date']}")
    else:
        if kind != "Updated":
            problems.append("an undated file is a reference and carries `Updated:`, not `Date:`")
        else:
            changed = last_change(rel)
            if changed and dt.date.fromisoformat(date) < changed:
                problems.append(
                    f"Updated: {date} but the file changed on {changed} — bump the date, "
                    "or make it a dated record if it is not meant to be kept current"
                )
    return problems


def documents():
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXEMPT or path.name == "README.md" or "assets" in path.relative_to(ROOT).parts:
                continue
            if path.name.startswith("."):
                continue
            yield path
    for rel in ROOT_DOCS:
        if (ROOT / rel).is_file():
            yield ROOT / rel


def main() -> int:
    failures = 0
    for path in documents():
        rel = path.relative_to(ROOT).as_posix()
        for problem in check(path):
            failures += 1
            print(f"{rel}: {problem}")
    if failures:
        print(f"\n{failures} problem(s). The rule is in docs/README.md under Naming.", file=sys.stderr)
        return 1
    print("docs: every record is dated and every reference carries its update date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
