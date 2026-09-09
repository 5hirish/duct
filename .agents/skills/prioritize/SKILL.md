---
name: prioritize
description: Run an idea, bug, or feature request through Duct's lean prioritization bar and turn the outcome into a scoped GitHub issue — or an explicit, written "not now, because" decision.
argument-hint: "<idea, issue number, or short description>"
---

Development here is 100% agent-executed, so implementation speed is not the
constraint — it never was the scarce resource, and treating it as one produces
a codebase that does everything and stands for nothing. The scarce resources
are: the attention of someone deciding whether to install Duct, and the
maintenance surface every shipped thing becomes forever. This skill exists so
that judgment call gets made the same way every time, by whoever's asking —
maintainer or agent — instead of re-derived from scratch or skipped.

## The bar

Four questions, in order. Stop as soon as one fails.

1. **Whose problem, specifically?** Name the user or persona, not "users."
   [`README.md`](../../../README.md) names Duct's actual job — cross-tool
   synthesis a single dashboard can't do. If you can't name who is blocked by
   its absence *today*, this is not `P0`, whatever else is true about it.
2. **What does it cost forever, not once?** A new connector, setting, or UI
   surface is a permanent line in `.env.example`, a permanent test, a
   permanent thing STYLE.md's review pass has to hold up against everything
   else. Agents make the first build free. They do not make the tenth year of
   maintaining it free — that bill still lands on the person who has to read
   the whole codebase, not just the diff that added it.
3. **Is there a cheaper way to test the same hypothesis?** A `site/for-*.html`
   landing page validates demand before a feature does — see the `new-page`
   skill and [`site/AGENTS.md`](../../../site/AGENTS.md)'s "what's the
   hypothesis being tested?" rule. Prefer the version that answers the
   question fastest, not the version that is most complete.
4. **Does it match what Duct actually is?** Reads across tools, executes
   behind an approval gate, brings your own model. A well-argued feature that
   turns Duct into a bespoke single-tool dashboard for one user is scope creep
   even when every individual argument for it is sound — that's the failure
   mode [`CLAUDE.md`](../../../CLAUDE.md) calls out: changes that each argue
   for themselves and nothing argues for the whole.

## What comes out

Priority and status live on the GitHub Project (**#10**, owner `5hirish` —
[projects/10](https://github.com/users/5hirish/projects/10)), not as repo
labels — one place, so the board is never out of sync with what an issue
says about itself. Its title carries the current release name and window;
read that before calling something `P0` — "blocked this week" means
something different with three weeks left in the window than with ten.

**If it clears the bar**, file the issue and put it on the board:

```bash
gh issue create --repo 5hirish/duct --title "…" --body "…" --label <area>
# area label: reuse what exists (backend, app, desktop, site, design,
# content, agents, ci) — never invent a near-synonym

gh project item-add 10 --owner 5hirish --url <issue-url>
# → prints the item id, needed below

gh project item-edit --id <item-id> --project-id PVT_kwHOAGxEyM4Bi8Ot \
  --field-id PVTSSF_lAHOAGxEyM4Bi8OtzhhydDY \
  --single-select-option-id <79628723|0a877460|da944a9c>   # P0 | P1 | P2

gh project item-edit --id <item-id> --project-id PVT_kwHOAGxEyM4Bi8Ot \
  --field-id PVTSSF_lAHOAGxEyM4Bi8OtzhhycIY \
  --single-select-option-id f75ad846   # Backlog, the default starting column
```

(Field and option ids are stable for this project; re-derive them with
`gh project field-list 10 --owner 5hirish` only if the project is ever
recreated.) `P0` = someone specific is blocked inside the current window,
`P1` = clearly valuable, not urgent, `P2` = interesting, not yet worth the
permanent surface.

The issue body is a lean spec, four sections, each one or two sentences:
- **Problem** — who, and what breaks or is missing today.
- **Non-goals** — what this deliberately does not do. Write this before
  scope creeps into it; a feature without a stated non-goal absorbs whatever
  gets requested next.
- **Smallest shippable version** — the cheapest thing that is customer-
  observable, not the cheapest thing that is code-complete.
- **Done means** — the customer-observable signal that it worked, not
  "merged" or "deployed." If there's no way to tell it worked, that's a
  reason to reconsider the shippable version, not to skip this section.

**If it doesn't clear the bar**, say so in writing instead of leaving it
ambiguous — close the issue with a reason (`gh issue close <n> --reason
"not planned" --comment "…"`, or file one just to close it if the idea only
existed in conversation), naming the specific question above it failed on. A
written "not now, because X" is not a rejection to soften; it's the same
kind of artifact as a shipped feature, and it's what stops the same idea
from being re-litigated from zero in six months. Declined ideas don't go on
the board — the board is for what's actually in flight or being weighed, not
an archive.

## Release timelines

There is no separate release-scheduling step to run here: `main` deploys on
merge (see root [`CLAUDE.md`](../../../CLAUDE.md), "Deployment — always via
CI/CD"), so a `P0` issue that clears review ships the same day —
[`add-changelog-entry`](../add-changelog-entry/SKILL.md) is the only thing
that turns "merged" into a dated, human-readable release note. The roadmap is
whatever is sitting in the Project with `P0`/`P1` open — read it from there
rather than maintaining a second copy of it in a document, which would just
drift the way the old root `AGENTS.md` preferences file did.
