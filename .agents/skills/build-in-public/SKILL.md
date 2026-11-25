---
name: build-in-public
description: Turn what Duct shipped in the last N days into X and LinkedIn posts in Shirish's name that teach a marketing idea, prove it with the shipped work, and bring marketers and small teams to try Duct or developers to contribute. Reads merged PRs, issues and launch notes, keeps the few items worth a post, writes a platform-native draft per network, makes the visuals (mosaic concept art from the image model, rendered diagram cards and LinkedIn carousels, real product shots), and hands over one batch file to paste, with how each post is measured. Use for "what should I post this week", "social posts from the last N days", "build in public", "a LinkedIn post about <feature>", "an X thread for <PR>".
argument-hint: "[days, default 7] [x|linkedin|both] [users|contributors|both]"
metadata:
  internal: "true"
---

Build in public, told from the marketing side: every post is a **free lesson
that happens to be true because we shipped it**. The shipped work is the
evidence, never the subject. A changelog read aloud ("we shipped X") is the
post nobody stops for; "here is why your Google Ads and GA4 numbers never
agree, and what I built after the third time it bit me" is the one they save.

> **The one rule:** delete every mention of Duct from the draft. If what is
> left is still worth reading, the post earns its slot. If nothing is left,
> it was an announcement, and announcements go in the changelog.

Read before drafting, every run:

- the **`founder-voice`** skill: every post here is in his name, and its
  rules, cut-on-sight list and pre-publish check all apply;
- the **`growth-playbook`** skill's community section and `lessons.md`;
- [`references/platforms.md`](references/platforms.md): what X and LinkedIn
  rank and demote as of its date, each claim marked primary or secondhand;
- the previous batches (Phase 5 says where), so no idea is posted twice and
  last run's "not posted, because" list is respected.

## Who reads, and what we want from them

| Reader | Who exactly | They stop for | The post ends on |
|---|---|---|---|
| **Users** (most posts) | one persona from [`docs/personas/`](../../../docs/personas/README.md) per post (`solo`, `team` or `marketer`), named in the batch; write in that page's "says" words | a manual job they hate, a number they cannot explain, a mistake they are making this week | one try path that works in a minute: `npx getduct check <their site>`, or the download |
| **Contributors** (at most one post in three) | developers who build agents or connectors | a real problem in a shipping agent, a clean seam, credit by name | one named `help wanted` issue |

The goal is people trying Duct on their own numbers, not stars. A contributor
post is a call to a specific issue, never "we're looking for contributors".

## Phase 1: what shipped

Fetch first and read `origin/main`, not the working tree (the root
`AGENTS.md`, "git hygiene"): a stale branch reports last month's work.

```bash
SINCE=$(date -v-${DAYS:-7}d +%F)     # macOS; GNU: date -d "-7 days" +%F
gh pr list --state merged --search "merged:>=$SINCE" --limit 100 \
  --json number,title,body,mergedAt,author,closingIssuesReferences
gh issue list --state closed --search "closed:>=$SINCE" --limit 100 --json number,title,labels
gh issue list --state open --label "help wanted" --json number,title,body   # contributor asks
git log origin/main --since=$SINCE --no-merges --date=short --pretty='%ad %s%n%b'
```

```bash
gh release list --limit 10                     # then gh release view <tag> for each in the window
git diff "$(git rev-list -1 --before=$SINCE origin/main)" origin/main -- CHANGELOG.md
```

`gh` fails with a certificate error inside the agent sandbox; that is the
sandbox, so rerun it outside. Then read what already turned the work into
words, because it is the best first draft:

- the **whole body** of every PR you might keep, not its title: the why, the
  before/after table, the numbers, and its **`Launch:` line**. That line is
  the maintainer's own launch decision; "changelog only until …" means no
  post, and the item goes to "not posted, because";
- release notes for every tag in the window, and the `CHANGELOG.md` diff;
- `## Launch: what shipped` comments on closed issues (the `working-backwards`
  skill writes them: the revised press release and FAQ);
- the newest entry in `site/changelog/index.html`;
- dated records in `docs/engineering/` and blog posts in the window;
- Duct's own record of getduct.ai (briefs, applied changes, what they did) and
  its analytics, for the "our own numbers" angle;
- what he already posted on X and LinkedIn (his profiles through the
  `social-research` skill, when credits allow), so no idea repeats a post.

**The story is usually in the code, not the PR.** Dated failures live in
comments and `AGENTS.md` files ("on 2026-11-08 a plan put 9 of 23 days on a
hook one post had tried"). `git grep -n "2026-" -- <files the PR touched>`
finds the true story with a date and a number that the post needs.

Rank candidates by what they teach, never by how recent they are: the best
item in a window is often its oldest.

**Keep** what a user can see today, plus, for contributor posts, the work
builders care about (the agent harness, evals, skills, an architecture
decision with its reason). **Cut** dependency bumps, CI, refactors with no
story, fixes to bugs nobody experienced, anything not deployed yet (a post
sends people to a thing that must work today), and any security fix (no
detail, ever, in public).

## Phase 2: the gate, one line each

For every survivor, write five lines. A blank line is a cut.

1. **Reader and pain:** who, and what this cost them this week, in their words.
2. **The idea:** what they can do or know after reading, without clicking.
3. **Proof:** the file, test, shot or measured number that makes it true,
   opened today. A claim checked against the pitch instead of the code is
   how a past blog post nearly said the opposite of the execution policy.
4. **The visual:** one form from Phase 4's table.
5. **The pasteable line:** the one sentence someone else would quote. Reach
   for an open-source launch came from strangers repeating one line, not
   from the founder's post (growth-playbook `lessons.md`, 2026-11-10).

Then choose **three to five** for the window, and pick an angle for each:

| Angle | Shape | Fits |
|---|---|---|
| **Concept explainer** | name a marketing idea, explain it with one analogy or diagram, show where it bites, Duct in the last line | LinkedIn carousel; X post with one image |
| **The manual job, gone** | the Monday ritual before (minutes, tabs, copy-paste), the result after, one shot | X post with a shot or clip |
| **The decision and why** | a design choice, the option rejected, the failure that forced it | LinkedIn text post; X thread |
| **Our own numbers** | what happened when Duct ran getduct.ai's stack; only our numbers, never a client's | both |
| **The owned failure** | what broke, what it cost, what changed | both; the highest-trust shape |
| **The contributor seam** | one `help wanted` issue: what it unlocks for users, where the seam is, credit by name | X; link to the issue |
| **Thanks by name** | a merged outside contribution: what they built and why it matters | both, after asking them before tagging |

A thin window gives one post or none. Say so; a padded week teaches
followers to scroll past.

## Phase 3: write one idea as two native posts

The same idea, written twice. Pasting one network's post into the other is the
most common build-in-public mistake, and each network punishes it
differently. The evidence behind each rule is in
[`references/platforms.md`](references/platforms.md).

**X**

- The first line is the whole post for most readers: the outcome or the
  surprising fact. Plan for 280 characters unless he says he has Premium.
- One post with one strong visual beats a thread. Thread only when each post
  stands alone, four to seven of them, the first carrying the visual.
- Link in the post when the click is the point; X said in July 2026 links are
  no longer held back and the published ranking code has no link penalty.
  Otherwise put it in a reply. Note which in the batch, so we learn.
- Replies are the strongest action the ranker predicts, so end on a real,
  specific question only when the answers would teach us something. "Reply
  YES for the link" is bait, and mutes and "not interested" count against.
- At most one original post a day: the ranker discounts the same author's
  second and later posts in a session.

**LinkedIn**

- The first two lines (about 200 characters before "see more") carry the
  outcome; nothing about Duct in them.
- Concept explainers ship as a **document post** (a PDF carousel, Phase 4):
  6 to 10 pages, one idea a page, the outcome on the cover, the one ask last.
- Link in the first comment by default; a body link was measured at about a
  fifth less median reach (secondhand; see the reference). Note which.
- Stay on three topics, so the feed model learns who to show him to:
  marketing numbers for small teams, AI agents that ask before acting, and
  building Duct in the open.
- LinkedIn's own 2026 feed update demotes "comment to agree" prompts,
  recycled posts, videos that do not match their text, pods and automated
  comments. None of those, ever.

**Both**

- Outcome first, in the reader's words, with their tools named (Google Ads,
  GA4, Search Console, Stripe). Never open with "Duct is…" or "We shipped…".
- One ask. Every link carries
  `?utm_source=<x|linkedin>&utm_medium=social&utm_campaign=bip-<batch date>&utm_content=<post slug>`.
- Nothing private: no app or API host, no port, no private repository, no
  exploit detail, no client figure even anonymised, no unreleased feature.
- Stagger the pair: the LinkedIn and X versions of an idea go out on
  different days.

## Phase 4: make the media

Pick the form by what the idea is, as `add-blog-post` Phase 4 does. Every
post gets exactly one visual (a carousel counts as one).

| The idea is… | Form | How |
|---|---|---|
| an abstract marketing principle | **mosaic illustration**: the idea as a Roman water system (a channel, a gate, a dry basin, a split aqueduct) | `mcp__gemini-image-generation__generate_image`, `gemini-3-pro-image` as the blog heroes use (about 13 US cents an image; a dollar sign followed by a digit here is read as a skill argument), `image_size: 2K`, `output_dir` set to the batch's `media/`, the absolute path of one `app/art-src/mosaic/*.jpg` in `input_image_paths` as the style reference, the `mosaic-panel` skill's stones, ground and border, **no lettering**. `aspect_ratio` `16:9` for X, `4:5` for LinkedIn. Engineering Rome, never togas or laurels. One re-roll at most |
| a flow, a comparison, a number, a checklist | **card** in the site's brand | an HTML file of `.card` elements, rendered by `render.mjs` (below). Never the image model for anything with words or numbers: it misspells them |
| a step-by-step explainer | **carousel** (LinkedIn document) | the same HTML, one `.card` per page, `render.mjs --pdf` |
| the product doing it | **product shot** | a scenario in `scripts/shots/shoot.mjs`; never a generated UI, never real customer data |
| the product moving | **15 to 30 s clip** | a composition in `design/motion` if one fits; otherwise a shot list he records himself: result in the first two seconds, captions burned in, uploaded natively |

```bash
cp .agents/skills/build-in-public/cards.html <batch>/media/1-cards.html   # edit the copy
node .agents/skills/build-in-public/render.mjs <batch>/media/1-cards.html <batch>/media/1 --pdf
```

`cards.html` holds the brand (Georgia display over system sans, navy,
off-white, the orange for the one thing that matters, the italic accent on
the second beat of a headline) at 1080×1350. Add `wide` to a card for X's
1600×900, `cover` to centre a single headline, `dark` for the closing card,
and an `<img class="art">` to put a mosaic or shot inside one. Body text at
40 px or more, labels never under 26 px, 80 px clear of every edge: at phone
width a 1080 px card shows at about a third of its size. Look at every
rendered card; a half-empty card gets less copy at a larger size, not more
copy.

Look at every image before it goes in the batch, and write its alt text
after looking: one sentence a listener could picture, never the prompt.

## Phase 5: hand over the batch

Drafts in his name, plans and numbers do not go in this public repository.
They go in the private GTM repository, under
`docs/gtm/social/<YYYY-MM-DD>/` (`posts.md` and `media/`). If that checkout
is not on the machine, write to the scratchpad and say so.

`posts.md` opens with the window, what shipped in it (one line per kept item,
with its PR), then each post:

```markdown
## 1 · <working title> · LinkedIn · users · Tue 25 Nov
Shipped: #<PR>, <what, in one line> · Proof: <file, test or shot>, opened today
Idea: <what the reader can do afterwards, one sentence>
Pasteable line: "<the sentence someone else would quote>"

<the post, ready to paste>

Media: media/1.pdf (8 pages) · alt: "<one sentence>"
First comment: <link with UTM>
Measure at 48 h and 7 d: impressions, real comments, profile visits, link clicks (GA4 by utm_content), downloads and CLI runs that day
```

Close with a **schedule** (one table: day, network, post) and a **not posted,
because** list of the items cut in Phase 2, so the next run does not offer
them again.

He reads every post and posts it himself. Nothing goes out from an agent, and
no tool posts in his name. Run the `founder-voice` pre-publish check on every
draft before handing over; a "no" is a rewrite, not a note.

## Phase 6: learn

At 48 hours and 7 days, ask him for the numbers (or read GA4 and PostHog for
the clicks and downloads) and fill them into the batch. A post **works** when
it beats his median of the last ten posts on that network on comments plus
link clicks; set that bar in the first batch and keep it.

After four batches, compare angles and formats. One that misses twice is
dropped, and the reason is written down:

- a lesson about any product's posts goes in `growth-playbook`'s
  `references/lessons.md`;
- one about how he sounds goes in `founder-voice`'s `references/lessons.md`;
- one about Duct's audience or numbers stays in the private GTM repository;
- a change in what a network ranks goes in `references/platforms.md`, dated,
  with its source.

## Before handing over

- [ ] Window read from `origin/main`; every kept item is deployed today
- [ ] Every post passes the one rule: worth reading with Duct deleted
- [ ] Every product claim names its proof, opened today; no client figure
- [ ] At most one contributor post in three, each naming one issue
- [ ] X and LinkedIn versions written separately, on different days
- [ ] One visual per post, looked at, alt text written after looking; no
      words or numbers from the image model
- [ ] One ask per post; every link has its UTM
- [ ] `founder-voice` check passed; no em dash anywhere
- [ ] Batch written to the private GTM repository, with the schedule and the
      "not posted, because" list
