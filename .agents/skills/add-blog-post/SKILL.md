---
name: add-blog-post
description: Research, write, illustrate and publish a post on the Duct blog that ranks in search and gets cited by answer engines (ChatGPT, Perplexity, Google AI Overviews, Claude). Runs a research arm first (demand, the pages answer engines cite today, primary sources, Duct's first-hand evidence), then writes for extraction, draws the hero, renders, lists and verifies the post, and keeps the publishing cadence. Use for "write a blog post", "next post", "blog about <topic or URL>", or a blog content calendar.
argument-hint: "<topic, question or source URL> [Engineering|Design|Growth|Announcement|Story]"
---

A post exists to be **found, quoted and trusted**: found by search, quoted by
answer engines, trusted by the reader who clicks through. Answer engines matter
more than blue links now. A reader who asks ChatGPT, Perplexity or an AI
Overview gets an answer assembled from a handful of pages, with those pages
cited. Being one of the handful is the goal, and the evidence on what earns it
is in [`references/aio.md`](references/aio.md). Read it once.

The short version: engines lift **self-contained, specific, sourced passages**
from **crawlable pages** that **other places already mention**. Every phase
below serves one of those three.

## The value bar: no post without it

A post earns its place only if a reader leaves able to **do something they
could not before** (a checklist they will use, a decision they can now make,
a mistake they will now avoid) or **knowing something they could not find
elsewhere** (a measurement, a comparison nobody made, a correction, what we
learned shipping it). The brief names both in one sentence each. If it
cannot, the post is not written: a rewrite of what already ranks adds a page
to maintain and gives no one, reader or engine, a reason to pick it.

Genuine value also means **true**. Every number is sourced and was seen on its
page; every claim about Duct is checked against the code, not the pitch (the
harness post first said a person approves "anything that spends money", and
the execution policy said otherwise; the post was corrected before it
shipped). Say what does not work yet: an honest gap is more quotable than a
polished claim.

## Who the blog is for

Two audiences, two clusters. The closer the generator ends a post with follows
its category (below); `audience` in the front matter overrides it.

| Cluster | Reader | What they came for | The post ends on |
|---|---|---|---|
| `growth` | the founder, marketer or PM running growth without a data team | a manual job they want to stop doing (read three tools, find the gap, explain the drop) | the product: Download |
| `builders` | engineers building agents | how a shipping agent actually solves a problem, with the code | the repo: Star on GitHub |

The builders cluster is Duct building in public. `docs/engineering/` holds
dated research records written for our own decisions (evals, memory freshness,
approvals, code execution); each one is a post waiting to be written for
outsiders, with first-hand evidence no one else has. That folder is the
cadence's supply line.

### Category and tags

Every post has **one category**, from a fixed set the generator enforces
(`CATEGORIES` in `scripts/build_blog.py`), and **1–6 tags**. The category is
the shelf the post sits on; tags are what it is about.

| Category | For | Default closer |
|---|---|---|
| `Engineering` | how Duct's agent and product are built, with the code | builders |
| `Design` | interface and product design decisions, and why | builders |
| `Growth` | practical guides for running growth without a data team | growth |
| `Announcement` | launches and releases worth more than a changelog line | growth |
| `Story` | why Duct exists, what building it in public taught us | growth |

Tags are lowercase topics as a reader would search them (`harness engineering`,
`agent memory`, `search console`), reused across posts rather than invented per
post. They show under the post, and become the `BlogPosting`'s `keywords` and
`article:tag` meta. There are no tag pages: with a handful of posts each would
be a thin page competing with the posts themselves. Add them when a tag has
five posts. A new category is a deliberate change to `CATEGORIES`, not a
front-matter typo the generator accepts.

## Cadence

- **One post every two weeks, alternating clusters.** Research-heavy posts at a
  rate a solo maintainer plus agents sustain. For answer engines one cited page
  beats five thin ones: citations concentrate on the best page for a question.
- **The calendar is the GitHub Project, not a file.** Each planned post is an
  issue titled `post: <working title>`, labelled `site`, with the research
  brief (Phase 1) as its body and the milestone that holds its publish date.
  File them with the `prioritize` skill's `gh issue create` form; the Project's
  `Priority` orders the queue.
- **Refresh at 90 days.** Re-run Phase 1's answer-engine check, fix anything
  that moved (numbers, links, a newer primary source), and set `updated:` in
  the front matter. Freshness is shown to the reader and in `dateModified`;
  bump it only for a substantive change, never to fake recency.
- **One question per post.** If the brief finds two, it is two posts.

## Phase 1: research arm (output: the brief)

Do all of this before writing a word. The brief is the deliverable of this
phase; the post is written from it.

### 1a. Demand: how people phrase it

```bash
python3 .agents/skills/add-blog-post/research.py "<topic>" --also "<other phrasing>"
```

Google autocomplete expanded into questions, comparisons and phrasings, Hacker
News stories from the last year, and the GitHub repositories the topic orbits.
Needs network: in the agent sandbox pass `suggestqueries.google.com`,
`hn.algolia.com` and `api.github.com` as allowed domains. Free sources only:
the Ahrefs connector answers "Insufficient plan" on every endpoint, so do not
plan around volumes. Then web-search the topic, and `site:reddit.com <topic>`
(Reddit blocks the script), for the pages ranking today and the questions
practitioners ask in their own words.

From this, pick the **primary question** (the one the post answers first,
usually "what is X" or "how do I X"), 4–8 **secondary questions** (they become
H2s and the FAQ), and the **comparisons** people search ("X vs Y"; each gets a
table row or an H2).

### 1b. The citation gap: who answer engines cite now

Ask the primary question and two secondary ones the way a reader would: in
web search, and in whichever answer engine the session can reach (Perplexity,
ChatGPT search, Gemini, Claude with search). Record, per question, the pages
cited. Then answer: **what do all of them say, and what does none of them
say?** The post must contain the second thing, or it has no reason to be cited
over pages that already are.

### 1c. Primary sources

Open every source you will cite. Record the exact title, author or
organisation, date, and one verbatim quote under 25 words that you saw on the
page. A number goes in the post only with its source; an unverified claim is
cut, not softened. Prefer the original (the lab's post, the paper, the spec)
over a summary of it, and cite the summary only for what it added.

### 1d. First-hand evidence: the part only Duct has

This is what makes a post worth citing. Look for it in this order:

- `docs/engineering/` records and `docs/engineering/agent-engineering.md`: decisions, measurements, rejected options
- the code and its tests: the file that enforces a rule is the proof it exists
- eval and replay results (`make agent-eval`, session audits): real numbers from real runs
- Duct's own analytics, read through Duct: the getduct.ai Search Console and GA4 (Duct runs Duct)
- the product itself: a shot from `site/assets/media/` showing the thing working

Link code on GitHub (`https://github.com/5hirish/duct/blob/main/<path>`), not
a local path: it is the reader's proof and a link to the repo.

### 1e. The brief

```markdown
## Brief: <working title>
- Category: <one of the five>. Tags: <1–6>. Reader: <one sentence, a real person>
- The value: after reading they can <…>; and they learn <…> nowhere else says
- Primary question: <as people type it>. Answer in one sentence: <…>
- Secondary questions (H2s / FAQ): <…>
- Comparisons: <X vs Y, …>
- Cited today (1b): <page — what it says>; the gap none of them fill: <…>
- Duct's first-hand evidence: <file, test, number, shot>
- Sources (verified): <title, author, date, url, quote>
- Where it will be mentioned after publishing: <thread, list, repo, community>
- Slug, title (Title Case), seoTitle (≤60), description (140–160)
```

## Phase 2: structure for extraction

An answer engine retrieves passages, not pages. Structure so that any section
lifted alone still answers something.

- **Answer first.** Under the title, before any story: a 40–60 word direct
  answer to the primary question. Definitions are stated plainly ("Harness
  engineering is…"), not built up to.
- **H2s are the questions**, phrased as people ask them (from 1a). Front-load
  the words that carry meaning.
- **Each section opens with its answer** in the first two sentences, then
  earns it. A section that needs the previous one to make sense is two
  sections merged or one section split wrong.
- **Specifics beat adjectives.** A number with its source, a named tool, a
  date, a file. "Up to 40% more visibility" with the paper linked is quotable;
  "significantly better" is not.
- **Tables for anything compared or mapped.** They are the most extractable
  structure there is. A comparison post without one is not done.
- **Quote primary sources** with attribution, sparingly: a quote is evidence,
  not decoration.
- **A FAQ section** (`## FAQ`, each question an `###`) with 3–5 of the
  secondary questions, each answered in 40–60 words that stand alone. The
  generator turns it into `FAQPage` data from the same text.
- **Length follows the question**, not a target: a definition-plus-practice
  post runs 1,500–2,500 words; a narrow how-to 800–1,200. Past 8 minutes the
  generator adds a contents list.

## Phase 3: write

The house voice is in [`site/DESIGN.md`](../../../site/DESIGN.md) (Voice,
Blog). For posts specifically:

- **Open in the reader's situation** or with the answer, never with a
  definition of the topic's category or "In today's…".
- **Short paragraphs** (1–3 sentences), one bolded phrase at most per paragraph.
- **An informed opinion, stated.** Posts take positions ("do this, not that,
  because…") and say where Duct's own choice differs from the source.
- **No em dashes** in post prose: readers take them as the mark of generated
  text. Commas, colons, parentheses, full stops.
- **American spelling**, sentence case in headings, Title Case in the title.
- **No pitch.** The generator closes every post with the bridge for its
  audience. Duct appears in the body only as evidence (the file, the test,
  the shot), never as a sales line.

### Links

- **Cite inline**, at the claim, with the source's own name as the anchor
  ("Anthropic's *Building effective agents*"), never "here" or "this post".
  Every outside link lands in the `BlogPosting`'s `citation` list.
- **2–3 internal links**: another post, the relevant landing page
  (`/for-organic-growth`, `/open-source`, `/doctrine`), the repo.
- **Link out generously to primary sources.** A page that cites well is a page
  worth citing; outbound links cost nothing.

## Phase 4: illustrate

Illustration is how a post shows the idea instead of only saying it. Every
post gets a **hero**; beyond that, pick the form by **what the idea is**, not
by what is quick to make. One strong visual per major section is plenty; a
visual that repeats the paragraph beside it is decoration and goes.

| The idea is… | Form | Example |
|---|---|---|
| **how a system is built**: parts and what flows between them | **system / architecture diagram** | the harness around the model: context, model, tools, authority, with evals and traces around them |
| **a sequence over time**: who does what, in what order | **sequence or flow diagram** | propose → policy → approve → apply → roll back, with the branch where a person decides |
| **a choice between options** | **comparison**: a table first (it is what engines extract), plus a side-by-side visual when the difference is spatial | two memory designs, or two approval flows, next to each other |
| **a quantity or a gap** | **chart**, the one form that fits the question (a dumbbell for before/after, a bar for ranking, a line for a trend) | same model, different harness: the gap between the dots is the harness |
| **an abstract principle** | **representative or analogical illustration**: the idea as a physical thing | the mosaic hero: a water mill, where the water does the work and the channel, gate and wheel decide where it goes |
| **a state or a change over time** | **timeline or before/after** | a remembered fact from "enabled" to "superseded", with the dates it held |
| **the product doing it** | **product shot**, annotated when one detail matters | the approval card, the memory timeline |
| **a structure the reader will copy** | **code block or annotated file tree** | an `AGENTS.md` skeleton, the harness in five files |

How each is made:

- **Hero, and any analogical illustration**: a mosaic scene in the brand style.
  Follow the `mosaic-panel` skill's six stones, ground and border, but 16:9,
  no inscription, one subject that is the post's metaphor. Pass one of
  `app/art-src/mosaic/*.jpg` as the style reference to
  `mcp__gemini-image-generation__generate_image` (`gemini-3-pro-image-preview`,
  `aspect_ratio: 16:9`, `image_size: 2K`). A hero stands alone, so a naive
  oblique view is allowed where it reads better; app panels stay flat. Expect
  one re-roll; keep the better image, not the more rule-abiding one.
- **Diagrams and charts**: hand-written SVG in the site's colours (navy
  `#0d0f1a`, grey `#4b5068`, borders `#d9dbe3`, the orange `#ff5c00` for the one
  thing that matters) and fonts (Georgia headings, system sans labels), with
  `<title>` and `<desc>`. Draw on a 1000px-wide canvas with labels at 19px or
  more: the figure renders at 652px, and anything smaller is unreadable on the
  page. Render it at page size with `sharp` and look before committing. For
  charts, the `dataviz` skill's method for choosing the form and the colours.
  Never an image model for anything with words or numbers in it: generated
  text is wrong often enough to cost more than it saves.
- **Product shots**: an existing shot from `site/assets/media/` (its `-768` and
  `-1536` variants join the srcset automatically). If the right one is
  missing, add a scenario to `scripts/shots/shoot.mjs`; never a hand
  screenshot, never a generated picture of a UI.

Alt text says what the image shows, in one sentence a listener could picture;
the caption says what to take from it. Convert a generated image to WebP at
1320px wide (2x the 652px measure) plus a `-768` variant, with the `sharp` in
`app/node_modules` (`scripts/build_og_images.mjs` shows how to require it).
Budget: hero under 300 KB, a variant under 120 KB; mosaic tiles are
high-frequency detail and do not compress much below that.

## Phase 5: files

### Front matter

```yaml
---
title: "What Is Harness Engineering? A Field Guide From a Shipping Agent"
seoTitle: "Harness Engineering: A Field Guide From a Shipping Agent"   # <title>, ≤60 chars
date: Sep 29 2026
updated: Oct 14 2026          # optional; only for a substantive revision
author: Shirish Kadam
category: Engineering         # Engineering | Design | Growth | Announcement | Story
tags: harness engineering, agent harness, evals   # 1–6, lowercase
audience: builders            # optional; defaults from the category
excerpt: "The card line on the index: a specific claim that makes someone click."
description: "The meta description, 140–160 characters, with the primary question's words in it."
hero: assets/<slug>/hero.webp # relative to site/blog/
heroAlt: "What the hero shows, in one sentence"
readTime: 12
---
```

### Markdown the generator accepts

The full list is in the docstring of `scripts/build_blog.py`; anything outside
it raises. Beyond paragraphs, lists, bold, *italics*, `code` and links:

```markdown
## Question-shaped heading          (h2; ### for h3; each gets an anchor id)
![Alt text](assets/<slug>/diagram.svg "Caption")
| Column | Column |
|---|---|
| cell | cell |
> The quoted words, verbatim.
> -- [Author, Title](https://source)
[!github](https://github.com/owner/repo "What the repository is, one line")
```

The `[!github]` card is drawn at build time: no widget, no request to GitHub
from the reader's browser. `[!youtube](https://www.youtube.com/watch?v=ID "Title,
speaker, length")` is a click-to-play facade: the page fetches nothing from
YouTube (no thumbnail, no script) until the reader presses play, then loads the
privacy-enhanced player. Embed a talk only when it adds something the post
cannot say; one per post at most. Anything else that would load a third-party
script on page view (a tweet widget, a CodePen) is not supported, because
nothing loads outside the consent gate (`site/AGENTS.md`): link to it.

### Render and list

```bash
node scripts/build_og_images.mjs                  # the card: kicker, title, and the hero on it
python3 scripts/build_blog.py --fetch-thumbnails  # only if the post embeds a video (network)
python3 scripts/build_blog.py                     # the post page, and the blog index's grid
```

`build_og_images.mjs` redraws every card and the non-blog ones come out with
new bytes and no visible change; restore those (`git checkout -- site/assets/og/<page>.jpg`)
so the diff holds only the cards the post touched.

The index card and the category filter are generated from the front matter,
so there is nothing to add there by hand. Add the post to the three
hand-kept listings; `build_blog.py` fails until all three have it:

1. `site/sitemap.xml`: `<loc>https://getduct.ai/blog/<slug></loc>` with `<lastmod>` in `YYYY-MM-DD`, and bump the `/blog/` entry's `lastmod`
2. `site/blog/feed.xml`: an `<item>` with an RFC 822 `pubDate` and the category as `<category>`; bump `lastBuildDate`
3. `site/llms.txt`: a line under "Blog posts", `- [Title](url): one sentence on what it answers`

## Phase 6: verify

```bash
python3 scripts/build_blog.py --check
python3 .github/scripts/check-pages.py
make check-site
```

Then look at it: the site dev server (`python3 dev_server.py --port 8090` in
`site/`), and Playwright at 1280 and 390 wide. Check the hero, every figure,
the table's scroll on a phone, the quote, the GitHub card, the contents list,
and the closer. Read the JSON-LD blocks in the page source once: headline,
dates, `citation`, and the FAQ text matching the page.

Attack the post as a reviewer would: every number has a source, every quote
was seen on its page, the answer-first paragraph survives being read alone,
and nothing in it is false about the product (`site/AGENTS.md`, "What the
desktop app actually is").

## Phase 7: distribute and measure

Publishing is half the job; answer engines cite pages that are already
mentioned elsewhere. After the merge deploys, the brief's "where it will be
mentioned" list is the to-do. Every item is outward-facing, so each one is
proposed to the maintainer, drafted in full, and sent only on a yes:

- a pull request to a relevant awesome list or index, in its own format and
  under its own rules (read its CONTRIBUTING first)
- a Hacker News or community post where the topic is already being discussed
- a reply in an existing thread where the post answers the question asked
- the maintainer's own channels (X, LinkedIn, the YouTube channel)

The venue rules and the wider plan live with the GTM plan, kept outside this
repository.

Measure at 30 and 90 days: Search Console queries and position for the post
(through Duct, which reads getduct.ai's own Search Console), GA4 referrals
from `chatgpt.com`, `perplexity.ai`, `gemini.google.com`, `claude.ai` and
`copilot.microsoft.com`, and the 1b questions re-asked to see whether the post
is now cited. Record the result on the post's issue; it is what the next
refresh starts from.

## Done means

- [ ] Brief written; it names the value, the gap the cited pages leave, and Duct's evidence
- [ ] Every claim about Duct checked against the code; category from the five; 1–6 tags
- [ ] Answer-first paragraph; question-shaped H2s; each section opens with its answer
- [ ] Every number and quote sourced and seen; outbound links to primary sources
- [ ] At least one table where anything is compared or mapped; FAQ of 3–5
- [ ] Hero, plus the visual each major idea calls for (Phase 4's table), legible at 652px
- [ ] Front matter complete; `seoTitle` ≤60; `description` 140–160
- [ ] Card drawn, page and index rendered, three listings added, `--check` green
- [ ] Looked at in a browser at desktop and phone width
- [ ] Distribution list drafted for the maintainer; issue updated with the brief and the publish date
