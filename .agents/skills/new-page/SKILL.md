---
name: new-page
description: Create a new audience-specific landing page following the for-*.html pattern
argument-hint: "<audience-slug> \"<title suffix>\" \"<hero headline>\" \"<hero subtext>\""
---

Creates a new `for-<audience-slug>.html` page for one audience. Keeps the site's
design, CSS and structure; only the copy and the shots change.

```
/new-page for-engineering-teams "for Engineering Teams" "Stop losing signal in the noise." "Duct connects Sentry, Linear and GA4 and answers why the error rate moved."
```

## Before writing: answer three questions

1. **What job does this audience hire Duct for?** The outcome, not the
   feature. "Know why activation dropped before standup", not "cross-tool
   aggregation".
2. **What is the specific pain?** Two conflicting signals in one sentence.
   "Search Console says impressions are up. GA4 says trials are flat."
3. **Which tools do they live in?** Name them in the subheadline. It is the
   highest-leverage line on the page.

And the one `AGENTS.md` asks first: **what is the hypothesis?** It goes in the
`<!-- EXPERIMENT: -->` comment after the GTM noscript.

## The page, in order

Copy `site/for-product-intelligence.html`. Every `for-*` page keeps this
sequence; each section earns the next.

```
Hero          Stop X. Start <em>Y</em>. Tools named in the sub. Download + Star on GitHub.
Shot          One README screenshot under the hero (.shot). The page's heaviest element.
Tool strip    The marquee: the tools this audience recognises.
Problem       "You're doing the right thing. But no one <em>connected it</em>." Three pain
              bullets, the disconnected-tools diagram, one "After Duct" sentence.
What it does  Three .job cards: a shot plus When / Today / With Duct.
How it works  Connect / Ask / Approve. Name the tools in step one. Keep the channel.
Who it's for  "The [role] who owns [thing] without a [resource]". Four fit cards,
              the last one "Not yet". Inline CTA: That's me — download Duct ↓
FAQ           Five or six real questions. The JSON-LD is rebuilt from the <details>.
CTA           The shared partial.
```

No testimonials, no stats band, no interactive demo. All three were on these
pages once and all three were removed: fake quotes, invented numbers, and a
mock brief that lost to a real screenshot.

## Section notes

**`<head>`.** Title `Duct <suffix> — <seven-word value line>`, canonical
`https://getduct.ai/for-<slug>`, `og:description` and `twitter:description`
120–140 characters and different from each other, `WebPage` plus `FAQPage`
JSON-LD.

**Hero.** Headline ≤60 characters, `<em>` on the aspiration, never on the pain.
No "powerful", "seamless", "all-in-one". Button copy is `Download Duct ↓` at the
top and the bottom, always `href="/download" data-duct-download`. Footnote:
`Free · No credit card · For [role] at [size] companies`, honest on both.

**Shot.** The hero shot is a session asked from this audience's side. Three
exist: `product-session` (why did activation drop), `paid-session` (where is
the budget leaking), `insights-session` (why are signups down); each ends on
its brief in the artifact pane, with the sidebar closed so the canvas is the
picture, and a `-mobile` phone capture served below 860px through
`<picture>`. A new audience gets a new one: its answer in `ANSWERS`, its brief
through `brief()` in the story, its stream in `scripts/shots/fixtures.mjs`, a
desktop and a phone scenario in `scenarios.mjs`, then shoot both.
The job cards take focused shots, never a whole window: `answer-<audience>`
(one question, the sources read, the answer; a new audience adds its entry to
`ANSWERS` in the story and gets the card for free), `review-card`,
`content-plan`, `memory-timeline`, `connectors`. Cap `.shot-frame` at the
image's 1x width so a 2x capture never upscales. Never draw a mock of a
screen that exists.

**Problem.** Mirror the audience's own words. The diagram keeps the window
chrome and the `dim` pattern; the "After Duct" line is
`[A] → [B] → [C] → [outcome]. One story, automatically connected.`

**Jobs.** Three cards, three different shots. *When* is a moment, *Today* is
the cost, *With Duct* is what it reads and what it proposes. Numbers beat
adjectives.

**How it works.** The bodies are shared across pages on purpose; only the tools
in step one change.

**Who it's for.** The "Not yet" card is the most trusted line on the page. Name
who this is not for.

**FAQ.** Write the answers in the page's voice; search engines quote them. The
money answer is the site's one sentence: *free with your own keys, always; a
paid plan later bundles the models; nothing open today moves behind it*, with a
link to `/open-source#pricing`.

**Icons.** Sprite only: `<svg class="ic" aria-hidden="true"><use
href="/assets/icons.svg#name"/></svg>`. A missing name goes into
`scripts/build_site_icons.py`.

**Accent.** One `<style>` block overriding `--orange` and `--orange-h`, nothing
else. Warm for urgency (orange, amber), cool for precision (indigo, slate,
teal), mid for growth (green, violet).

## Done means

- [ ] Hypothesis in the `EXPERIMENT` comment
- [ ] Headline ≤60 chars, tools named in the sub, both CTAs identical
- [ ] One shot, three job cards, no mock of a screen that exists
- [ ] "Not yet" card names who it is not for
- [ ] No emoji, no stats band, no testimonials, no demo
- [ ] Added to `site/sitemap.xml`; `make check-site` green
- [ ] Reviewed at 1440 and 390 px: two-line hero, nothing horizontal
