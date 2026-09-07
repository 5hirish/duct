#!/usr/bin/env bash
#
# Keep the local `main` ref in step with `origin/main`, and say where this
# branch stands relative to it.
#
# Why this exists: on 2026-09-07 local `main` sat 204 commits behind
# `origin/main` — PRs #49–#113, all merged. Every `git ls-tree main -- <path>`
# run against it answered for September 2nd, so four features that had shipped
# read as missing, and a session spent its time explaining an outage that had
# never happened. A stale ref does not announce itself; it just answers wrong.
#
# Run by the SessionStart hook in .claude/settings.json, and safe to run by
# hand. It never touches the working tree and never rewrites a ref that has
# commits of its own — the worst case is that it fast-forwards nothing and says
# so.
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Emit the SessionStart JSON envelope and leave. Always exits 0: a hook that
# fails a session because the network is down is worse than a stale ref.
report() {
  python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":sys.argv[1]}}))' "$1"
  exit 0
}

if ! git fetch --quiet --prune origin 2>/dev/null; then
  report "git fetch origin failed (offline, or credentials). origin/main may be stale — do not conclude anything is 'missing from main' until a fetch succeeds."
fi

git show-ref --verify --quiet refs/remotes/origin/main || exit 0

head_branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")
note=""

if git show-ref --verify --quiet refs/heads/main; then
  behind=$(git rev-list --count main..origin/main 2>/dev/null || echo 0)
  ahead=$(git rev-list --count origin/main..main 2>/dev/null || echo 0)

  if [ "$ahead" -gt 0 ]; then
    # Unpushed commits on main. Never rewrite that ref — it is the only copy.
    note="local main has $ahead commit(s) not on origin/main and is $behind behind; left alone. Compare against origin/main, not main."
  elif [ "$behind" -gt 0 ]; then
    if [ "$head_branch" = "main" ]; then
      # Checked out, so the working tree is involved: --ff-only refuses rather
      # than merging, and a dirty tree simply declines.
      if git merge --ff-only origin/main >/dev/null 2>&1; then
        note="fast-forwarded main $behind commit(s) to origin/main."
      else
        note="main is $behind behind origin/main and could not fast-forward (uncommitted changes?). Compare against origin/main."
      fi
    else
      # Not checked out: moving the ref cannot touch any file.
      git update-ref refs/heads/main "$(git rev-parse origin/main)" &&
        note="fast-forwarded main $behind commit(s) to origin/main (not checked out; no files touched)."
    fi
  fi
fi

# Where the branch actually being worked on stands. This is the number that
# decides whether a fresh branch is cheaper than a rebase.
if [ -n "$head_branch" ] && [ "$head_branch" != "main" ]; then
  gap=$(git rev-list --count "HEAD..origin/main" 2>/dev/null || echo 0)
  if [ "$gap" -gt 0 ]; then
    note="${note:+$note }Branch '$head_branch' is $gap commit(s) behind origin/main."
  fi
fi

[ -n "$note" ] && report "$note"
exit 0
