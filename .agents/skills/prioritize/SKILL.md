---
name: prioritize
description: Product management for Duct — find what deserves attention, run it through the lean prioritization bar, file it as a properly-typed and scheduled GitHub issue, keep the board honest, and report where things stand.
argument-hint: "<idea, issue number, short description, or 'sweep' / 'readout'>"
---

Development here is 100% agent-executed, so implementation speed is not the
constraint — it never was the scarce resource, and treating it as one produces
a codebase that does everything and stands for nothing. The scarce resources
are: the attention of someone deciding whether to install Duct, and the
maintenance surface every shipped thing becomes forever. This skill exists so
that judgment gets applied the same way every time, by whoever's asking —
maintainer or agent — instead of re-derived from scratch or skipped.

## What needs the maintainer, and what doesn't

Two things go through the maintainer before they're final: **whether
something clears the bar**, and **the spec** for anything new — problem,
non-goals, smallest shippable version, done-means. That's where their
judgment sets what Duct becomes, and it's the one place worth slowing down
for.

**Propose in batches, not one at a time.** A sweep that surfaces nine
candidates gets one table — title, type, priority, milestone, one line of
why — and one approval, not nine round trips. Approval on the table is
approval to file the set.

Everything else is autonomous, and stays that way without asking again: type
and severity, area labels, which milestone something targets, every status
move, closing an already-discussed "not planned" item, and — just as much
the job as executing — proactively flagging what needs a decision: a stale
branch, a PR blocked on nothing but attention, a milestone whose due date is
closer than its open count suggests. Autonomous means acted-on and reported,
never acted-on and hidden.

This matters more here than in a typically-staffed repo, not less: with
minimal human review of individual diffs, the bar below is effectively the
only checkpoint for "should this exist at all" — nothing downstream catches
a bad scope call the way code review catches a bad diff.

## Before filing anything

Three gates, in order. Most candidates die at one of them, and that's the
point — an issue tracker's value is inversely proportional to how much of it
nobody reads.

1. **Does it already exist?** `gh issue list --state all --search "<terms>"`.
   Add a comment to the existing issue rather than opening a near-duplicate.
2. **Is the ticket more expensive than the fix?** In a repo where an agent
   does the work, a typo, a broken link, a missing label, a one-line copy fix
   is *cheaper to fix than to describe*. Fix it, mention it in the summary,
   let the changelog carry it. File only what needs a decision, needs
   sequencing, or needs to survive being forgotten.
3. **Is this one thing or five?** Split when the pieces ship independently
   and one could be dropped without the others (each gets its own
   done-means). Bundle when they only make sense delivered together —
   five sub-tasks nobody would ship alone are one issue with a checklist,
   not five tickets that all close on the same afternoon.

## The bar (new work only — a bug skips this)

Four questions, in order, for anything that adds scope: a feature, an idea,
a proposal. Stop as soon as one fails. **A bug doesn't go through this** —
something already promised not working isn't a scope question, it's triaged
by severity.

1. **Whose problem, specifically?** Name the user or persona, not "users."
   [`README.md`](../../../README.md) names Duct's actual job — cross-tool
   synthesis a single dashboard can't do. If you can't name who is blocked by
   its absence *today*, it doesn't belong in the current milestone, whatever
   else is true about it.
2. **What does it cost forever, not once?** A new connector, setting, or UI
   surface is a permanent line in `.env.example`, a permanent test, a
   permanent thing STYLE.md's review pass has to hold up against everything
   else. Agents make the first build free. They do not make the tenth year of
   maintaining it free.
3. **Is there a cheaper way to test the same hypothesis?** A `site/for-*.html`
   landing page validates demand before a feature does — see the `new-page`
   skill and [`site/AGENTS.md`](../../../site/AGENTS.md)'s "what's the
   hypothesis being tested?" rule. Prefer the version that answers the
   question fastest, not the one that's most complete.
4. **Does it match what Duct actually is?** Reads across tools, executes
   behind an approval gate, brings your own model. A well-argued feature that
   turns Duct into a bespoke single-tool dashboard for one user is scope creep
   even when every individual argument for it is sound — the failure mode
   [`CLAUDE.md`](../../../CLAUDE.md) names: changes that each argue for
   themselves while nothing argues for the whole.

## Type

Labels only. GitHub's native issue types exist for organizations, and this
repository belongs to a personal account, so `gh issue create --type` fails
with `type "Feature" not found; available types:` (an empty list). On
2026-09-24 that failed a whole batch of filings.

| What it is | Set it as |
|---|---|
| A real defect — should work, doesn't | label `bug` |
| Scoped, cleared the bar, ready to build | label `enhancement` |
| Internal work with no product-facing shape (refactor, CI, chore) | area label alone |
| Not yet scoped or agreed — exploratory | label `idea` |
| Needs an answer, not a decision | label `question` |
| Security hardening or tracking | label `security` |

**Never file a live vulnerability as an issue.** `security` is for hardening
and for things already disclosed and being fixed. An exploitable, unfixed
problem — including an open Dependabot or code-scanning finding — goes
through [`SECURITY.md`](../../../SECURITY.md) as a private advisory, or gets
fixed directly. A public issue publishes the exploit.

Add the area label — reuse what exists (`backend`, `app`, `desktop`, `site`,
`design`, `content`, `agents`, `ci`, `mcp`, `documentation`), never invent a
near-synonym. Assign `5hirish` by default.

## Priority and milestone

Priority answers *how much it matters*; milestone answers *when*. The
priority rubric depends on the type:

**Feature / idea** — who is actually waiting:
- `P0` — someone specific is blocked right now, inside the current window.
- `P1` — clearly valuable, not urgent.
- `P2` — interesting, not yet worth the permanent surface.

**Bug** — impact × severity, not strength of annoyance:
- `P0` — breaks a core flow, loses or exposes data, or blocks the release.
- `P1` — degrades a real workflow but has a workaround, or hits a minority
  of users or paths.
- `P2` — cosmetic, edge case, or low-traffic path.

| Bucket | Milestone | Status | Typical priority |
|---|---|---|---|
| **This release** — release blocker | nearest open milestone | `Ready` | `P0` |
| **Next release** — not blocking this release, priority right after | the following milestone | `Ready` | `P1` |
| **Roadmap** — concretely want it, not this quarter | none yet | `Ready` | `P1` |
| **Backlog** — want it, don't know when | none | `Backlog` | `P1`/`P2` |

The milestone says *which release*; the sprint (below) says *which two
weeks*. They were once both called "iteration" here, and the board's
"Current iteration" view sat empty for a month because the skill set
milestones and the view filtered on the Iteration field.

Auto-add drops every new issue into `Backlog`, milestoned or not. Move a
milestoned one to `Ready` by hand, or the board shows this quarter's work
as undecided.

Milestones are real GitHub milestones with due dates, not labels; the
Project mirrors whatever the issue is assigned. Create the next one only
when there's a real target after it — don't invent quarters speculatively.

```bash
gh api repos/5hirish/duct/milestones --jq '.[] | "\(.title) — \(.open_issues) open / \(.closed_issues) closed, due \(.due_on)"'
```

## The sprint

The Project's **Iteration** field is a two-week sprint, starting on a
Wednesday. The "Current iteration" and "Next iteration" views filter on it
(`iteration:@current`, `iteration:@next`), so an item with no iteration is
invisible there however well it is milestoned. The sprint is what stops
work being put off indefinitely: everything in it is a commitment for the
next two weeks, and everything outside it is explicitly not.

**What goes in the current sprint**, in this order, until it holds ten
items. Ten is the cap because build time isn't the constraint — the
maintainer's review attention is, and ten open PRs in two weeks is already
more than gets read.

1. Anything `In progress` or `In review` — in-flight work is in the sprint
   by definition.
2. Every open issue in the nearest milestone whose due date falls inside
   or before the sprint. These are `P0` by the rubric above, and `Ready`.
3. `P1` bugs with status `Ready`.
4. `Ready` `P1` items in the nearest milestone that share a theme with
   in-flight work — same area label and the same title prefix (the
   `Content Studio:` set, the `GA4` set). Finishing a theme beats starting
   a new one.
5. Remaining `Ready` `P1` items in the nearest milestone, **lowest issue
   number first** — the one that has waited longest goes next, which is
   the rule that keeps "later" from meaning "never".

`Backlog` items never enter a sprint. Moving one in means first deciding it
is `Ready` (spec complete, milestone set), which is the maintainer's call
under "What needs the maintainer".

**Refresh at the start of every sprint**, and top up whenever an item
finishes mid-sprint. The refresh is one pass:

- Unfinished items roll into the new sprint (they still lead the order
  above). Each roll leaves a comment on the issue — `Rolled into Iteration
  N (2nd time)` — because the Iteration field holds one value and that
  comment trail is the only place the count survives. An item rolling for
  the **second** time is named in the readout as stalled; on the **third**,
  it leaves the sprint, moves to the following milestone, and the comment
  says so — a thing that sat through six weeks of sprints was not a
  commitment, and pretending otherwise hides the real ones.
- `Ready` items with a milestone whose due date has passed move to the
  next milestone, with a comment. Closed issues still showing `Backlog` or
  `Ready` are set to `Done` (the auto-close automation misses issues that
  were on the board before it was enabled).
- End with the readout below.

```bash
# the current iteration id (iterations rotate; the field id is stable)
gh api graphql -f query='{ user(login:"5hirish"){ projectV2(number:10){
  field(name:"Iteration"){ ... on ProjectV2IterationField {
    configuration { iterations { id title startDate duration } } } } } } }' \
  --jq '.data.user.projectV2.field.configuration.iterations[0] | "\(.id) \(.title) from \(.startDate)"'
# ^ iterations[] lists only current and future, oldest first, so [0] is @current

gh project item-edit --id <item-id> --project-id PVT_kwHOAGxEyM4Bi8Ot \
  --field-id PVTIF_lAHOAGxEyM4Bi8OtzhhydDk --iteration-id <iteration-id>

# take an item out of every sprint (item-edit cannot clear a field)
gh api graphql -f query='mutation($p:ID!,$i:ID!,$f:ID!){
  clearProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f}){ projectV2Item { id } } }' \
  -f p=PVT_kwHOAGxEyM4Bi8Ot -f i=<item-id> -f f=PVTIF_lAHOAGxEyM4Bi8OtzhhydDk
```

A **local** Claude Code Desktop scheduled task (`duct-sprint-refresh`, on
the maintainer's Mac) runs this refresh every Wednesday morning. Its prompt
is versioned at `.claude/scheduled-tasks/duct-sprint-refresh/SKILL.md`, and
Desktop's own copy at `~/.claude/scheduled-tasks/duct-sprint-refresh/SKILL.md`
is a symlink to it, so edit the repo file and the next run picks it up. The
schedule, folder, model and permission mode live in Desktop, not in the file.
The sprint
boundary is every second Wednesday and the run in between is a top-up, so
the sprint exists whether or not anyone opened a session that week. It is local on
purpose: in Anthropic-hosted cloud sessions every GitHub request goes through
a proxy that serves only a pinned set of pull-request GraphQL operations,
and Projects v2 is GraphQL-only, so a cloud routine gets a 403 on every
board edit however its token is supplied. A cloud routine was tried and
disabled on 2026-09-28 for exactly that reason; don't recreate one. It edits board fields, comments
and milestones, and nothing else: no commits, no PRs, no new issues, no
priority changes, and it never promotes `Backlog` into a sprint. It
posts its readout as a **Project status update** (the "Add status update"
button on the board; `createProjectV2StatusUpdate` in GraphQL), which is
where the board's own history lives, and nowhere else:

```bash
gh api graphql -f query='mutation($p:ID!,$b:String!,$s:ProjectV2StatusUpdateStatus!){
  createProjectV2StatusUpdate(input:{projectId:$p, body:$b, status:$s}){ statusUpdate { id } } }' \
  -f p=PVT_kwHOAGxEyM4Bi8Ot -f b="$(cat readout.md)" -f s=ON_TRACK   # AT_RISK / OFF_TRACK
```

**A milestone needs exit criteria, not just a date.** If its description
doesn't say what has to be true to call it shipped, that's the first thing
to fix — otherwise "stable release" means whatever is merged when the date
arrives.

## Writing it up

Crisp, and from the product side — not a technical writeup of the code.
These get read many in a row; the reader shouldn't have to open a diff or a
log to understand what's being asked.

**Bug:** what's happening (as a user would describe it, not as the traceback
would) · impact (who, how often, how bad) · evidence (screenshot, URL, log
line, reference — something that pins it down) · repro steps only if they
aren't obvious from the above.

**Feature / idea:** problem (who, what's missing today) · context (why now,
one sentence, if not obvious) · options considered — *only* where there's a
genuine fork, two to four lines of pros and cons or a small table, never an
essay comparing things nobody would pick · non-goals (write them before
scope creeps in; a feature without stated non-goals absorbs whatever gets
requested next) · smallest shippable version (cheapest thing that's
customer-observable, not code-complete) · done-means (the observable signal
it worked — if there isn't one, reconsider the shippable version rather than
skipping the line).

**Question:** the question and the context that makes it answerable. No
spec, no priority. Closed when answered.

Skip any section that would only restate its heading. Two honest sentences
beat five that pad.

## Mechanics

The project already runs its own automations — **auto-add to project**,
**item closed → Done**, **PR merged → Done**, **PR linked to issue**. Don't
duplicate them: a filed issue usually lands on the board by itself, and
`Done` sets itself when the issue closes or its PR merges. What's left to do
by hand is `Priority`, the sprint (`Iteration`), and nudging `In progress`
when work actually starts.

"PR linked to issue" means a closing keyword — `Closes #N`, `Fixes #N`,
`Resolves #N` — in the PR body or a commit on it. `Refs #N` links nothing
GitHub acts on: the issue stays open and the board never moves it (#127
shipped and sat in `In progress` for a week that way). When you find a
shipped issue still open, close it with a comment naming the commits, as
`gh issue close <n> --reason completed --comment "…"`.

```bash
# 1. file it
gh issue create --repo 5hirish/duct --title "…" --body "…" \
  --label <bug|enhancement,><area>[,idea|question|security] \
  --assignee 5hirish --milestone "<title>"        # omit --milestone for roadmap/backlog

# 2. get its board item id. item-add is idempotent: it returns the existing
#    item when auto-add got there first. (Piping item-list into jq breaks on
#    issue bodies with control characters, so don't.)
gh project item-add 10 --owner 5hirish --url <issue-url> --format json --jq .id

# 3. set the fields that aren't automatic
gh project item-edit --id <item-id> --project-id PVT_kwHOAGxEyM4Bi8Ot \
  --field-id <field-id> --single-select-option-id <option-id>
```

| Field | Field id | Options |
|---|---|---|
| Priority | `PVTSSF_lAHOAGxEyM4Bi8OtzhhydDY` | P0 `79628723` · P1 `0a877460` · P2 `da944a9c` |
| Status | `PVTSSF_lAHOAGxEyM4Bi8OtzhhycIY` | Backlog `f75ad846` · Ready `e18bf179` · In progress `47fc9ee4` · In review `aba860b9` · Done `98236657` |
| Iteration | `PVTIF_lAHOAGxEyM4Bi8OtzhhydDk` | rotates every two weeks — query it, see "The sprint" |

Ids are stable unless the project is recreated; re-derive with `gh project
field-list 10 --owner 5hirish`. Status moves at the moment the event
happens, in whichever session is doing the work — first commit → `In
progress` **and into the current sprint if it wasn't already**, PR opened →
`In review`, and the rest handles itself. It's
mechanical: move it and say so, don't ask.

**If it doesn't clear the bar** (features and ideas only — bugs are
deprioritized, never declined), say so in writing rather than leaving it
ambiguous: `gh issue close <n> --reason "not planned" --comment "…"`, naming
the question it failed on. File one just to close it if the idea only ever
existed in conversation. A written "not now, because X" is the same kind of
artifact as a shipped feature — it's what stops the idea being re-litigated
from zero in six months. Declined ideas get no milestone and no board slot.

## Where the work comes from

A PM that only files what it's handed is a typist. Sweep these — on request,
and whenever the board looks thinner than reality:

```bash
gh api "repos/5hirish/duct/dependabot/alerts?state=open" \
  --jq 'group_by(.security_advisory.severity)[] | "\(.[0].security_advisory.severity): \(length)"'
gh api "repos/5hirish/duct/code-scanning/alerts?state=open" --jq 'length'
# ^ both are private findings — fix or advise, never a public issue

gh run list --branch main --status failure --limit 5      # main went red
gh pr list --state open --json number,title,updatedAt     # waiting on attention alone
git for-each-ref --format='%(refname:short)' refs/remotes/origin \
  | while read b; do n=$(git rev-list --count origin/main.."$b"); \
    [ "$n" -gt 0 ] && echo "$n $b"; done | sort -rn        # stranded, unmerged work
git grep -InE "(TODO|FIXME|HACK)[: ]" -- backend app/src desktop/src
git log --oneline "$(git log -1 --format=%H -- CHANGELOG.md)..main"  # unreleased notes debt
```

Stranded branches deserve particular suspicion: a branch far ahead of `main`
is either value that never shipped or work already superseded, and both are
decisions, not backlog. Say which you think it is.

## The readout

When asked where things stand — and unprompted when a milestone's due date
is near — answer in this shape, five lines, no preamble:

- **Milestone** — name, days left, open/closed count.
- **Sprint** — which iteration, items in it, what rolled over and how many
  times.
- **Shipped** — what merged since the last readout, in user terms.
- **In flight** — what's `In progress` or `In review`, and who it waits on.
- **Blocked** — anything stalled, and the specific thing that would unstall it.
- **Needs you** — the decisions only the maintainer can make. If there are
  none, say so in three words rather than manufacturing one.

## Release timelines

There's no separate release-scheduling step: `main` deploys on merge (root
[`CLAUDE.md`](../../../CLAUDE.md), "Deployment — always via CI/CD"), so a
`P0` in the current milestone that clears review ships the same day.
[`add-changelog-entry`](../add-changelog-entry/SKILL.md) is the only thing
that turns "merged" into a dated, human-readable release note. The milestone
due date is the real deadline; the Project's title is just a label for it.
The roadmap is what's open across the current and next milestones plus
`Status: Ready` — read it from there rather than keeping a second copy in a
document, which would drift the way the old root `AGENTS.md` preferences
file did.
