---
name: working-backwards
description: Amazon-style PR/FAQ for a user-facing Duct feature. A customer press release and FAQ written on the issue before any code, revised against what actually shipped at merge, then a launch triage that picks the outlet (a changelog line, a blog post through add-blog-post, an integration page, a landing page section) or records why there is none. A backfill mode runs the same triage over a window of merged work. Use for "write the PR/FAQ", "working backwards on #N", "launch this feature", "should this feature get a blog post", "what should the last four weeks become".
argument-hint: "<issue number> | ship <issue or PR number> | backfill [since YYYY-MM-DD]"
---

Every user-facing feature gets a **PR/FAQ**: a one-page press release and a
FAQ, written for the person who will use it, before the first commit. Not
every feature gets a **blog post**. The PR/FAQ is the thing that is always
written; a post is one of several places its words can end up, and most
features end up in the changelog alone.

That split is deliberate, and it is worth knowing why before arguing for "a
post per feature":

- **The blog already has a bar.** `add-blog-post` publishes nothing a reader
  could not get elsewhere, at one post every two weeks, because one cited page
  beats five thin ones. A feature post that clears that bar goes through it;
  one that does not is a page to maintain that nobody, reader or answer
  engine, has a reason to pick.
- **Search engines discount pages made in bulk.** Google's scaled content
  abuse policy is about many pages produced mainly to rank, whatever produced
  them. This repo already refuses pair pages on the integrations hub for the
  same reason (`site/AGENTS.md`, "Integrations"). An agent-written post for
  every merge is that pattern with a blog template on it.
- **Announcement posts cannibalize.** Few people search "Duct now does X".
  When one does collect links, it keeps ranking long after the feature
  changed, ahead of the integration or landing page that should own the query.

So the measure of this skill is not posts published. It is that every
feature was described in the customer's words before it was built, that the
description was checked against what shipped, and that the words went
wherever they do the most work.

## What counts as user-facing

Anything that changes what a person using Duct sees or can do: a new
connector, a new kind of insight, a new action Duct can take, a change to
approvals, models, pricing, the desktop app. Not: refactors, CI, internal
tooling, a flag still off, and bugs. A bug fix restores something already
promised; the changelog carries it and it needs no PR/FAQ.

## Mode 1: draft (before code)

Run it while the issue is being specced, as part of `prioritize`'s "Writing
it up" for an `enhancement` that is user-facing, and before the first commit.
Read first: the issue, [`README.md`](../../../README.md) for the job Duct
does, and [`site/AGENTS.md`](../../../site/AGENTS.md)'s "What the desktop app
actually is", because the press release is the first place a false promise
about the product gets written down.

### The press release

At most one page, around 300 to 400 words. Dated the milestone's due date and
written as though that day has come.

```markdown
## Press release

**<Headline: what the reader can now do, in their words, under 10 words>**
<Subhead: who it is for and the outcome, one sentence>

<Mon D YYYY>. <Summary: the reader, the job, what changed, in two or three
sentences. Someone who stops here knows everything that matters.>

<The problem: the situation today, in the tools they already use, with a
number where one exists. Two signals that disagree is the house shape:
"Search Console says impressions are up. GA4 says trials are flat.">

<The solution: what they do in Duct now, step by step, as they would
experience it. Name the third-party tools. Say where Duct waits for them to
approve.>

> "<What this persona would say after a week of using it.>"
> (hypothetical: <persona, role>)

<Getting started: one sentence, the first click.>
```

Rules, all checkable:

- **The reader's job, not the feature's name.** "See which pages are losing
  clicks before the monthly report does", not "Introducing Content Decay
  Alerts". If the headline cannot be written without the feature's internal
  name, nobody outside the repo has the problem in those words yet.
- **The quote is marked hypothetical** and never leaves the issue unless a
  real user says it, by name and with permission. A made-up customer quote in
  published copy is a fabricated review.
- **No file paths, module names, PR numbers or internal jargon.** This is the
  end-user document; the spec beside it is for the people building.
- **Nothing the milestone will not ship.** No roadmap, no "coming soon".
- **The house voice** ([`site/DESIGN.md`](../../../site/DESIGN.md), "Voice"):
  numbers over adjectives, the founder test, American spelling, and no em
  dashes, because these sentences become post and changelog copy. Words that
  fail review on sight: seamless, powerful, leverage, unlock, revolutionize,
  AI-powered, game-changing, excited to announce.

### Customer FAQ

Five to eight questions a person would ask before trying it, each answered
in 40 to 60 words that stand alone. That length is the blog's FAQ rule, so
the answers move into a post, an integration page or a landing page FAQ
without a rewrite. Always answer the ones that apply:

- What does it read, and what can it change? Does a change wait for me?
- What does it cost me? On the user's own model keys a run lands on their
  provider bill: say roughly how much per run, not "it depends".
- Where does my data go? (The downloaded app talks to Duct's cloud; say so.)
- How is this different from what <the third-party tool> does on its own?
- What does it not do yet?

### Internal FAQ: only what the spec does not already say

`prioritize`'s spec already holds the options considered, non-goals, the
smallest shippable version and done-means. Do not restate them. The internal
FAQ adds the questions that spec format skips:

- **Unit cost.** What one run costs in tokens and third-party API quota, and
  who pays: the user's keys, or Duct's hosted account. Show the arithmetic.
- **The metric that moves**, and the event it is read from (PostHog or GA4),
  so done-means is observable and not a feeling.
- **Search demand for the job**, not the feature:
  `python3 .agents/skills/add-blog-post/research.py "<the job, as people type it>"`.
  It costs a minute now and decides the launch triage in Mode 2 early.
- **The riskiest assumption**, and the cheapest way to test it before the
  build (`prioritize`'s third question).

The repository is public and so are its issues. No revenue, no customer
names without consent, nothing from the private GTM plan.

### The draft is a test

If the problem paragraph cannot name a person who has this problem today,
the feature fails `prioritize`'s first question. Say so, and close or park
the issue under `prioritize`'s rules. That is the PR/FAQ doing its job, not
failing at it: Amazon writes these before building precisely so that some of
them stop the build.

### Where it goes

On the issue, in its body: `## Press release` and `## Customer FAQ` above the
spec sections, `## Internal FAQ` below them. `gh issue edit <n> --body-file
<file>`, or the GitHub MCP `issue_write` tool where `gh` is not available.

## Mode 2: ship (at merge)

Run it when the pull request that closes the issue is merged or ready to
merge. The PR template's **Launch** line asks for the result.

### 2a. Diff the promise against what shipped

Read the merged diff, not the PR description. For every sentence of the press
release and every FAQ answer, mark it true, changed or cut, checked against
the code: the harness post once said a person approves "anything that spends
money", the execution policy said otherwise, and only reading the policy
caught it.

Post the revised press release and FAQ as a comment on the issue, headed
`## Launch: what shipped`. Leave the draft in the body as it was written: the
distance between what was promised and what shipped is worth seeing later,
and an edited draft hides it.

### 2b. Before choosing: can the outcome be measured, and what is the quarter for?

Two reads, both free, before any outlet is picked. Skipping them is how
the first backfill run nearly planned four posts nobody could have measured.

- **The conversion is counted.** The site's one action is the desktop
  download, which sends `download_started` through `ductTrack` from the
  `/download` page (`site/assets/duct-download.js`). Through the PostHog MCP,
  confirm the event arrived in the last 30 days. If it did not, that is the first
  finding of the run and goes to the maintainer before any post: an outlet
  whose result cannot be read is a guess, however good its keyword.
- **The quarter's goals.** `get_project_context` for the getduct.ai project
  holds the current goal, the seeded and parked keyword clusters, and a
  research log of numbers already bought. Read it first, and reuse any
  number logged in the last 30 days rather than buying it again. An outlet
  that serves a stated goal outranks one that does not, and a feature
  shipped *before* the window counts when it serves one: the first backfill
  found its best post (the ChatGPT Ads measurement guide) in a connector
  older than the window it was reviewing.

### 2c. Pick the outlet

Every user-visible change gets its changelog line through
`add-changelog-entry`, at the next release; the shipped headline is usually
that bullet's lead phrase. Beyond the changelog, pick **at most one**:

| The feature… | Outlet | Through |
|---|---|---|
| adds a connector | its integration page copy, which is the page that should own "<tool> + Duct" searches | `scripts/integrations/connectors.py`, `build_integrations.py` |
| automates a job people already search for (Mode 1's demand check found the phrasing) | a **Growth** post that teaches the job, with the feature as the evidence | `add-blog-post`, category Growth |
| changes what Duct is for someone deciding whether to install: a new class of capability, a new platform, a change to how models or pricing work | an **Announcement** post | `add-blog-post`, category Announcement |
| sharpens the pitch to an audience that already has a page | a section or FAQ entry on that `for-*` page | `site/AGENTS.md`, "New landing page" |
| none of the above | the changelog line, and the decision recorded | nothing else |

A post is chosen only when all three hold:

1. It clears `add-blog-post`'s value bar: the reader can do or knows
   something after it they could not before.
2. Its primary query is not already owned by another page on getduct.ai.
   Check `site:getduct.ai <query>`, the sitemap, and Search Console through
   Duct. If a page owns it, improve that page instead. One primary query per
   URL.
3. It fits the calendar. It is filed as a `post: <working title>` issue and
   takes the next slot for its cluster under `add-blog-post`'s cadence. Several
   features in one milestone share **one** Announcement post; the
   changelog's release name is usually its theme. The calendar is shared
   with Engineering posts, which this skill does not write but which take
   the alternate slots: a builders post is often the better use of a slot
   (on 2026-10-20 the harness post was the only blog page with search
   impressions), so file it beside the feature posts rather than letting
   feature posts fill every slot.

Record the decision on the issue in one line, so nobody re-asks:

```
Launch: changelog only | post #<n> | integration page | for-<page> section, because <one line>
```

"Changelog only, because the feature has no search demand and no page owns
its job yet" is a finished outcome, the same kind of artifact as a published
post.

### 2d. Hand a post to add-blog-post

The PR/FAQ is the brief's first draft, not a replacement for the research.
Open the `post:` issue with these fields filled, then run `add-blog-post`
from Phase 1b (who answer engines cite today) onward:

| Brief field (`add-blog-post`, 1e) | From the PR/FAQ |
|---|---|
| Reader | the subhead's persona |
| Primary question | the job's search phrasing from Mode 1, never the feature name |
| Secondary questions | the Customer FAQ |
| The value | the solution paragraph, as shipped |
| Duct's first-hand evidence | the merged PR, the metric from the internal FAQ, a product shot (`scripts/shots/shoot.mjs`) |
| What it does not do | the "not yet" answer |

A post that starts here is for the person using Duct, not for contributors,
which changes a few of `add-blog-post`'s defaults:

- **The title is the job**, the same rule as the headline.
- **Evidence is the product, not the code.** A product shot and the integration
  page, not a link to a source file. Code links belong to Engineering posts,
  which this skill does not write.
- **Announcement is the one category where Duct is the subject.** The no-pitch
  rule still holds as no superlatives and no "excited to announce": say what
  the reader can now do, show it, and say what it cannot do yet.

## Mode 3: backfill (a window of merged work)

Run it when features shipped without Mode 2, or on a regular review
("what did the last four weeks ship, and what should it become?"). It is
Mode 2 over a range, with one entry and one plan at the end instead of a
decision per merge.

1. **The range.** From the newest `<article>` date in
   `site/changelog/index.html`, `git log origin/main --since=<date>
   --no-merges`, minus dependency bumps. Read the bodies of the
   non-merge commits: a squash's merge commit often has none.
2. **Changelog debt first.** Everything user-visible in the range and in
   neither `site/changelog/` nor `CHANGELOG.md`'s `[Unreleased]` becomes
   one entry through `add-changelog-entry`, dated when the last of it
   merged. That entry is the launch for most of the range.
3. **2b once, for the whole window**, then the outlet table per feature,
   in one table: feature, outlet, and the reason with its number (search
   volume and difficulty from `get_keyword_metrics`, one batched call; the
   live results page from `get_serp_results` only for the candidates that
   survive).
4. **The plan.** The surviving posts, in cadence order, alternating
   clusters, each filed as a `post:` issue with the brief filled per 2d
   (`prioritize`'s mechanics). Propose the table and the order to the
   maintainer once; approval on the table is approval to file the set.

A PR/FAQ is not written retroactively for a feature already shipped:
there is no build decision left for it to test. The issue comment from 2a
is written only for the features that get a post, where the post needs
the verified claims.

## Done means

**Draft**
- [ ] Press release under one page; the headline is the reader's job; the quote is marked hypothetical
- [ ] Customer FAQ of 5 to 8, each answer 40 to 60 words and standalone; cost and data answered plainly
- [ ] Internal FAQ holds only unit cost, the metric, search demand and the riskiest assumption
- [ ] Every claim true of the product as `site/AGENTS.md` describes it; nothing private in a public issue
- [ ] On the issue body; or the feature stopped at `prioritize`'s first question, and that is recorded

**Ship**
- [ ] Every sentence checked against the merged code; `## Launch: what shipped` posted; draft left as written
- [ ] Outlet chosen from the table, at most one beyond the changelog, and the `Launch:` line recorded on the issue and the PR
- [ ] The download is a counted key event, and the project context's goals and research log were read
- [ ] For a post: the three tests pass, the `post:` issue is filed with the brief filled, and `add-blog-post` takes it from 1b

**Backfill**
- [ ] Every user-visible change in the range is in one changelog entry, or already was
- [ ] One table of feature, outlet and reason with its number; the posts filed in cadence order after one approval
