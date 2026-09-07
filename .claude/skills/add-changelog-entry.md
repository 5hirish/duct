---
name: add-changelog-entry
description: Write a new release entry on the public Duct changelog at site/changelog/ — from git history, in the voice of someone who uses the product
argument-hint: "[\"<release name>\"] [\"<date>\"] [\"<version badge>\"]"
---

Turns what shipped since the last published release into one human-readable entry
on `site/changelog/index.html`, plus the RSS item, the structured data, and the
sitemap.

## Usage

```
/add-changelog-entry                                  # everything since the newest published entry
/add-changelog-entry "Bring your own models" "Sep 2 2026" "Desktop 0.4.0"
```

All three arguments are optional:
- **release name** — omit it and you write one (see *Naming the release*).
- **date** — defaults to today, format `Mon D YYYY`.
- **version badge** — only pass one if a real version actually shipped. Omit it
  otherwise; an invented version number is worse than no badge.

---

## Phase 1: Find out what actually shipped

### 1a. Establish the range

The newest `<article class="cl-release" id="YYYY-MM-DD">` in
`site/changelog/index.html` is the last published release. That date is the
lower bound:

```bash
git log --since=<that date> --date=short --pretty='%ad %s%n%b' --no-merges
```

Read the bodies, not just the subjects. This repo's commit messages explain
*why* — that reasoning is usually the sentence a reader wants, one translation
away.

### 1b. Cut everything that is not user-visible

Delete from the candidate list:
- refactors, renames, test changes, CI and build plumbing, dependency bumps
- documentation, agent instruction files, repo hygiene
- work behind a flag that is still off, or a migration nobody will notice
- fixes to bugs that were never released — nobody experienced them

A dependency bump earns a line only when it closed a vulnerability that affected
users, and then the line is about the fix, not the version number.

### 1c. Verify each survivor

Every bullet you write must trace to a commit in the range. **Never write a line
because it would round out a section.** If a group has one bullet, ship one
bullet. If a release has nothing user-visible in it, say so and stop — a skipped
week is honest; a padded entry teaches readers to stop reading.

---

## Phase 2: Write it

### Naming the release

2–5 words, sentence case, concrete, no version numbers. It names the *theme* of
the release, and it is the `<h2>` — so it is also the thing search engines and
AI answers quote.

- Good: `Bring your own models` · `Duct starts remembering` · `From insight to execution`
- Bad: `August update` · `Improvements and bug fixes` · `v0.4.0`

If the release has no theme — three unrelated fixes — name the largest one and
let the rest sit under their groups.

### The lede

One or two sentences under the title, `<p class="cl-lede">`. State what changed
for the reader, not what was built. It is the RSS description and the social
preview, so it has to stand alone.

### Groups

Use these labels, in this order, skipping any that do not apply:

`Models & agents` · `Insights` · `Memory` · `Connectors` · `Execution` ·
`Workspace` · `Desktop` · `Reliability` · `Security`

At most 4 groups and 5 bullets per group. Past that, you are shipping a diff,
not a changelog — cut the weakest lines.

### Bullet voice

Each bullet is **a bold lead phrase naming the change**, then the detail in
plain prose. Same voice as the blog: direct, specific, no filler.

- `<strong>Three tiers, one job map.</strong> Choose a Heavy, Standard and Light model in settings. Every agent job picks the tier it needs, so you are not selecting a model feature by feature.`
- Not: `Added support for configurable model tier mapping in the agents module (#123).`

Rules:
- No commit hashes, PR numbers, file paths, module names, or internal jargon.
- Name real third-party tools — `Mixpanel`, `Google Ads`, `Microsoft Clarity`.
  Those are the terms people search for, and the reason this page ranks.
- A fix says what now works, not what was broken in the abstract: *"Connecting
  through the browser reports success as success"* beats *"fixed OAuth relay
  state bug"*.
- Do not promise anything not in the release. No roadmap, no "coming soon".

---

## Phase 3: Publish it

Five files, every time. A missed one is invisible until it is embarrassing.

### 3a. `site/changelog/index.html` — the entry

Insert as the **first** `<article>` inside `.cl-wrap`, above the previous newest:

```html
<!-- RELEASE: YYYY-MM-DD -->
<article class="cl-release" id="YYYY-MM-DD" aria-labelledby="r-YYYY-MM-DD">
<div class="cl-rail">
<span class="cl-date">Mon D, YYYY</span>
<span class="cl-version">Desktop 0.4.0</span>
<a class="cl-permalink" href="#YYYY-MM-DD" aria-label="Permalink to the Month D, YYYY release"># permalink</a>
</div>
<div class="cl-body">
<h2 class="cl-title" id="r-YYYY-MM-DD">Release name</h2>
<p class="cl-lede">One or two sentences.</p>

<div class="cl-group">
<p class="cl-group-label">Group label</p>
<ul class="cl-list">
<li><strong>Lead phrase.</strong> The detail.</li>
</ul>
</div>
</div>
</article>
```

- The `id` is the ISO date and is permanent — it is the shareable link. Never
  renumber or reuse one.
- Drop the `<span class="cl-version">` line entirely when no version shipped.
- Escape `&` as `&amp;` and use `&rsquo;` / `&ldquo;` / `&rdquo;` for quotes and
  apostrophes, matching the existing entries.
- The year strip is a `<div role="navigation">`, not a `<nav>` — the bare `nav`
  rule in `duct.css` is the fixed site header and will hijack a second one.

### 3b. `site/changelog/index.html` — the structured data

In the `application/ld+json` block:
- Prepend a `ListItem` to `mainEntity.itemListElement` with the new release name
  and `https://getduct.ai/changelog/#YYYY-MM-DD`, then renumber `position` on
  every item (1 = newest).
- Update `about.softwareVersion` when a version shipped.

### 3c. `site/changelog/feed.xml`

Prepend an `<item>` above the current newest and update `<lastBuildDate>`:

```xml
    <item>
      <title>Release name</title>
      <link>https://getduct.ai/changelog/#YYYY-MM-DD</link>
      <guid isPermaLink="false">duct-changelog-YYYY-MM-DD</guid>
      <pubDate>Day, DD Mon YYYY 09:00:00 GMT</pubDate>
      <description>The lede, expanded to 2–3 sentences. Plain text, no markup.</description>
    </item>
```

`pubDate` is RFC 822 (`Wed, 02 Sep 2026 09:00:00 GMT`) — a feed reader will
reject anything else. Validate with `xmllint --noout site/changelog/feed.xml`.

### 3d. `site/sitemap.xml`

Update `<lastmod>` on the `https://getduct.ai/changelog/` entry to the release
date in `YYYY-MM-DD`. The entry already exists — do not add a second one, and do
not give release anchors their own URLs.

### 3e. `site/llms.txt`

Only when the shape of the page changes — a new archive year, a new feed. The
per-release lines do not belong there.

Nothing here is generated: `scripts/build_blog.py` renders posts, not releases,
so there is no `--check` to run and no build output to commit.

---

## Year rollover (the older-releases archive)

In January, last year's entries move off the index so it stays about the current
year:

1. Copy `site/changelog/index.html` to `site/changelog/<lastyear>.html`.
2. In the archive copy: keep only that year's `<article>` blocks; set
   `<title>` and `<h1>` to name the year (`Duct changelog — 2026`); set the
   canonical and `og:url` to `https://getduct.ai/changelog/2026`; mark that
   year's chip `aria-current="page"` and drop `aria-current` from the index
   chip; rebuild the `ItemList` from the entries that remain on that page.
3. Remove those `<article>` blocks from `index.html` and add
   `<a class="cl-year" href="/changelog/2026">2026</a>` to the year strip on
   **both** pages, newest year first.
4. Add the archive URL to `site/sitemap.xml` (`priority` 0.5, `changefreq`
   yearly) and to the `## Core pages` list in `site/llms.txt`.
5. Leave the feed alone — it carries recent items, not history.

Every entry keeps its `#YYYY-MM-DD` anchor, so an old link still resolves once
the reader lands on the archive page.

If a single year ever grows past ~40 releases and the page starts to feel like a
scroll test, split it in half (`/changelog/2027-h1`) and add the half to the
strip. Do not paginate — one long page is what earns the links.

---

## Verify before you call it done

```bash
python3 .github/scripts/check-pages.py   # what CI runs over the page itself
cd site && python3 dev_server.py --port 8090
```

- [ ] `check-pages.py` passes — canonical without `.html`, JSON-LD parses, OG
      and Twitter tags complete
- [ ] `/changelog/` renders and the new entry is first
- [ ] The permalink `#YYYY-MM-DD` scrolls to the entry, clear of the fixed nav
- [ ] `/changelog/feed.xml` parses and the new item is on top
- [ ] The JSON-LD block still parses and its positions run 1..N
- [ ] No `.html` in any link you added — this site uses clean URLs, and a smoke
      test asserts it
- [ ] Every bullet traces to a commit in the range
- [ ] Nothing internal leaked: no hashes, PR numbers, file paths, module names
- [ ] Mobile at 390px: date and version chip sit on one row above the title
