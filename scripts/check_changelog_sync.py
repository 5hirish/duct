#!/usr/bin/env python3
"""Hold the two changelogs to each other, and a release to its notes.

    python3 scripts/check_changelog_sync.py              # the public page matches CHANGELOG.md
    python3 scripts/check_changelog_sync.py --version 0.7.0   # that version has notes to publish

Why this exists: 0.5.0 and 0.7.0 were released on 9 and 15 September 2026 with
no `CHANGELOG.md` section between them. `release-notes.mjs` degrades to a
compare link when a section is missing, so both releases published thin notes
and nothing said so; `site/changelog/` kept showing 0.4.1 for eight days while
the download page — which asks GitHub at page load — offered 0.7.0. A reader
comparing the two pages saw a product whose public record was two releases
behind its installer.

The release fires on a push to main that bumps `tauri.conf.json`, so the notes
have to exist before the bump merges. `--version` is that gate, run as the
first job of `desktop-release.yml`: ten seconds, before three platforms build.

A bump alone is not a release (0.3.0 and 0.6.0 were both superseded in-tree and
never published), so nothing here is keyed on `tauri.conf.json`. A version
earns a section when it is released, and the newest section is what the public
page must be showing.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
PAGE = ROOT / "site/changelog/index.html"
FEED = ROOT / "site/changelog/feed.xml"

# "## [0.7.0] — 2026-09-15". An undated section is `[Unreleased]` and is skipped:
# it names no version a reader can install.
SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\][^\n]*?(\d{4}-\d{2}-\d{2})", re.M)
# The version badge on an entry, which the skill only allows for a real release.
BADGE = re.compile(r'class="cl-version"[^>]*>Desktop (\d+\.\d+\.\d+)<')
ENTRY = re.compile(r'<article class="cl-release" id="(\d{4}-\d{2}-\d{2})"')
ITEM = re.compile(r"<guid[^>]*>duct-changelog-(\d{4}-\d{2}-\d{2})</guid>")

WRITE_ONE = "Write it with the add-changelog-entry skill (.agents/skills/add-changelog-entry/)."


def released() -> list[tuple[str, str]]:
    """Every dated version in CHANGELOG.md, newest first (file order)."""
    return SECTION.findall(CHANGELOG.read_text(encoding="utf-8"))


def check_version(version: str) -> list[str]:
    if any(v == version for v, _ in released()):
        return []
    return [
        f"CHANGELOG.md has no dated section for {version}, so the release would "
        f"publish a compare link instead of notes.\n"
        f"  Add `## [{version}] — YYYY-MM-DD` before the bump merges, and the "
        f"matching entry on site/changelog/. {WRITE_ONE}"
    ]


def check_sync() -> list[str]:
    versions = released()
    if not versions:
        return ["CHANGELOG.md lists no released version — expected at least one `## [X.Y.Z] — DATE`."]
    newest, date = versions[0]

    page = PAGE.read_text(encoding="utf-8")
    badges = BADGE.findall(page)
    errors = []
    if not badges:
        errors.append(f"site/changelog/ badges no release at all; CHANGELOG.md's newest is {newest} ({date}).")
    elif badges[0] != newest:
        errors.append(
            f"site/changelog/ badges Desktop {badges[0]} as its newest release, CHANGELOG.md says {newest} ({date}).\n"
            f"  The download page resolves the real latest release at page load, so the site contradicts itself "
            f"until the entry is written. {WRITE_ONE}"
        )

    # The entry and the feed item are written together or the feed silently
    # stops being the changelog.
    entries = ENTRY.findall(page)
    items = ITEM.findall(FEED.read_text(encoding="utf-8"))
    if entries and items and entries[0] != items[0]:
        errors.append(
            f"site/changelog/ leads with {entries[0]} but feed.xml leads with {items[0]} — "
            f"the newest entry has no RSS item."
        )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", help="check that this version has release notes, and nothing else")
    args = ap.parse_args()

    errors = check_version(args.version) if args.version else check_sync()
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"changelog ok — {'notes exist for ' + args.version if args.version else 'the public page matches CHANGELOG.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
