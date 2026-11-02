#!/usr/bin/env python3
"""Build one local branch holding main plus every open PR, to test them together.

`local/open-prs` is rebuilt from `origin/main` on every run, each open PR merged
in by number, oldest first, so a stacked PR lands after the one below it. The
merges are computed with `git merge-tree` and recorded with `git commit-tree`:
nothing touches the working tree until the finished branch is checked out, and
a PR that conflicts is skipped and named instead of leaving a half-merged tree
to clean up.

Left out, and why:
- drafts: work their author hasn't offered yet;
- PRs from forks: a contributor's code is read, never run on this machine
  (root AGENTS.md, "Git practice").

The branch never leaves this machine. Its commits are unsigned throwaways, it
has no upstream, and its pushRemote names a remote that doesn't exist, so a
bare `git push` from it fails.

It checks the branch out only when no tracked file is modified, because a
checkout would carry or refuse those edits; otherwise it builds the branch and
says how to switch. It ends by naming what changed against main that needs a
step before running: a lock file (reinstall, with that area's dev server
stopped: an install under a live server is how `anyio` broke every sync route
on 2026-09-20) and new migrations.

Usage (unsandboxed: gh cannot verify TLS inside the agent sandbox):
    python3 scripts/test_open_prs.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "local/open-prs"
NO_PUSH_REMOTE = "no-push"
LOCKFILES = {
    "backend/poetry.lock": "make setup-backend",
    "app/package-lock.json": "make setup-app",
    "site/package-lock.json": "make setup-site",
    "desktop/package-lock.json": "make setup-desktop",
    "desktop/src-tauri/Cargo.lock": "make setup-desktop",
}
MIGRATIONS = "backend/alembic/versions/"


def run(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def gh_json(*args: str):
    # strict=False: PR bodies carry raw control characters, which strict
    # parsing (and jq) rejects.
    return json.loads(run("gh", *args), strict=False)


def git(*args: str) -> str:
    return run("git", *args).strip()


def merge(head: str, ref: str, message: str) -> tuple[str | None, list[str]]:
    """Merge ref into head without a working tree: (new commit, []) or (None, conflicts)."""
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", head, ref],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    lines = result.stdout.split("\n")
    if result.returncode == 1:
        return None, [line for line in lines[1:] if line]
    if result.returncode != 0:
        raise SystemExit(f"git merge-tree failed on {ref}: {result.stderr.strip()}")
    return git("commit-tree", lines[0], "-p", head, "-p", ref, "-m", message), []


def main() -> int:
    git("fetch", "-q", "--prune", "origin")
    base = git("rev-parse", "origin/main")
    prs = gh_json("pr", "list", "--state", "open", "--limit", "100",
                  "--json", "number,title,headRefName,isDraft,isCrossRepository")

    head, rows = base, []
    for pr in sorted(prs, key=lambda p: p["number"]):
        number, title = pr["number"], pr["title"]
        if pr["isDraft"]:
            rows.append((number, "skipped", title, "draft"))
            continue
        if pr["isCrossRepository"]:
            rows.append((number, "skipped", title, "from a fork: read it on GitHub, never run it"))
            continue
        ref = f"origin/{pr['headRefName']}"
        ancestor = ["git", "merge-base", "--is-ancestor", ref, head]
        included = subprocess.run(ancestor, cwd=ROOT, check=False)
        if included.returncode == 0:
            rows.append((number, "included", title, "already in, via a PR stacked on it"))
            continue
        commit, conflicts = merge(head, ref, f"Merge #{number}: {title}")
        if commit is None:
            rows.append((number, "skipped", title, "conflicts in " + ", ".join(conflicts[:3])))
            continue
        head = commit
        rows.append((number, "merged", title, ""))

    current = git("branch", "--show-current")
    clean = not git("status", "--porcelain", "--untracked-files=no")
    if current == BRANCH and not clean:
        print(f"{BRANCH} is checked out with uncommitted edits; nothing was changed.")
        return 1
    if current != BRANCH:
        git("branch", "-f", BRANCH, head)
    checked_out = False
    if clean:
        try:
            git("checkout", "-q", "-B", BRANCH, head)
            checked_out = True
        except subprocess.CalledProcessError as exc:
            print(f"Built {BRANCH} but couldn't check it out: {exc.stderr.strip()}")
    git("config", f"branch.{BRANCH}.pushRemote", NO_PUSH_REMOTE)

    merged = sum(1 for r in rows if r[1] == "merged")
    where = "checked out" if checked_out else f"built; switch with `git switch {BRANCH}`"
    print(f"{BRANCH} = origin/main {base[:8]} + {merged} PR(s), {where}\n")
    for number, outcome, title, reason in rows:
        print(f"  #{number:<5} {outcome:<9} {title[:64]}" + (f"  ({reason})" if reason else ""))

    changed = git("diff", "--name-only", base, head).splitlines()
    areas = Counter(path.split("/")[0] for path in changed)
    print("\nChanged from main: " + (", ".join(f"{a} ({n})" for a, n in areas.most_common()) or "nothing"))
    for lockfile, command in LOCKFILES.items():
        if lockfile in changed:
            print(f"Dependencies changed: {lockfile}. Stop that area's dev server, `{command}`, restart it.")
    new_migrations = [p for p in git("diff", "--name-only", "--diff-filter=A", base, head).splitlines()
                      if p.startswith(MIGRATIONS)]
    if new_migrations:
        print(f"New migrations ({len(new_migrations)}): apply them to your local database "
              "before starting the API.")
    if checked_out and current and current != BRANCH:
        print(f"Back to where you were: `git switch {current}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
