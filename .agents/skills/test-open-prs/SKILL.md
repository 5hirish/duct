---
name: test-open-prs
description: Put the latest main and every open, non-draft PR on one local branch, check it out, and say what to run before testing it by hand. Use for "test all the open PRs together", "one branch with everything", "let me try all of it locally".
argument-hint: ""
disable-model-invocation: true
---

Builds `local/open-prs`: `origin/main` with every open PR merged in, so the
maintainer can run the whole stack once and test everything that's waiting,
instead of switching branch per PR. The branch is a throwaway, rebuilt from
scratch each run. It is never pushed, committed onto, or shipped.

## 1. Build it

```bash
python3 scripts/test_open_prs.py    # unsandboxed: gh fails TLS in the sandbox
```

[`scripts/test_open_prs.py`](../../../scripts/test_open_prs.py) merges the
PRs oldest first without touching the working tree, then checks the branch
out. It leaves out drafts and PRs from forks (a contributor's code is read,
never run here), and skips a PR that conflicts, naming the files.

If tracked files are modified, it builds the branch and doesn't switch to it.
Those edits belong to someone: say what they are and ask before moving them.
Never stash or discard them to make room.

## 2. Get it running

Act on the script's closing lines, in order:

1. **Dependencies changed**: stop that area's dev server first, then the
   `make setup-<area>` it names, then restart. Installing under a live
   server is how `anyio` broke every sync route on 2026-09-20.
2. **New migrations**: apply them to the local database before starting the
   API (`backend/AGENTS.md` says how).
3. Start what changed: `make serve-app-api` for the app and API together,
   `make serve-site` for the site. If the servers are already running from
   the editor, they reload on their own; don't stop someone else's session.

## 3. Report

The table of what's in and what was skipped (and why), what to test for each
PR in one line (its title and body say what it changes), and the setup steps
taken or still needed. Then how to leave: `git switch <previous branch>`.

## Fixing something found while testing

Not on `local/open-prs`: it is rebuilt from scratch next run and can't be
pushed. Switch to the PR's own branch, fix it there, and ship it with
`/ship` or `/merge-green`; the next build picks it up.
