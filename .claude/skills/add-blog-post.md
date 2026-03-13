---
name: add-blog-post
description: Add a new SEO-optimized blog post to the Duct Insights blog
argument-hint: "\"<title>\" \"<category>\" \"<excerpt>\" <read-time-minutes> \"<date>\""
---

Adds a new blog post: plans it for SEO, writes it, creates the Markdown file, adds the blog card to the index, and updates the sitemap.

## Usage

```
/add-blog-post "<title>" "<category>" "<excerpt>" <minutes> "<date>"
```

Example:
```
/add-blog-post "How to Audit Your Conversion Funnel in 30 Minutes" "Product Analytics" "Most funnel audits take days. Here is the three-step process that surfaces the drop-off in under an hour." 4 "Mar 20 2026"
```

---

## Phase 1: SEO planning (do this before writing)

### 1a. Classify the search intent

Before writing a single word, identify the intent type of the target keyword:

| Type | User goal | Right format |
|---|---|---|
| **Informational** | Learn how something works | Guide, explainer, step-by-step |
| **Commercial** | Evaluate tools or approaches | Comparison, "best X for Y", pros/cons |
| **Transactional** | Ready to act | Landing page content, "get started" |
| **Navigational** | Find a specific brand/page | Not a blog post — skip |

The format of the post must match the dominant SERP format for that intent. If the top 5 results for the keyword are listicles, write a listicle. If they're step-by-step guides, write a guide. Fighting the SERP format means fighting the ranking signal.

### 1b. Identify the primary keyword and 5–8 secondary keywords

The title argument is a draft title, not necessarily the SEO title. Derive:
- **Primary keyword** — the exact phrase this post should rank for (usually 2–5 words)
- **Secondary / LSI keywords** — related terms, entity names, and variations that signal topical coverage; these appear naturally in H2s and body copy, never forced

### 1c. Determine funnel stage and CTA

| Stage | Post type | CTA type |
|---|---|---|
| **TOFU** (awareness) | "What is X", "How does X work" | Newsletter / related post |
| **MOFU** (evaluation) | "X vs Y", "Best X for Y", "How to choose X" | Free trial / join beta |
| **BOFU** (conversion) | "Alternatives to X", "[Tool] for [use case]", "[Tool] pricing" | Direct: "Start free trial" / "Join waitlist" |

BOFU content converts 3–5× better than TOFU. When there is a choice between a BOFU and TOFU angle on the same topic, default to BOFU or MOFU. Always match the CTA to the stage — a "Book a Demo" button on a TOFU post will not convert.

### 1d. Plan the H2 structure

H2s are the skeleton of the post. They must:
- Address distinct user questions or content territory (not just topic labels)
- Use question-shaped phrasing where the keyword allows: "How to X" beats "X Overview"
- Cover what SERP competitors cover, plus at least one gap they miss
- Map to a logical user journey from problem recognition → solution → action

**H2 planning rule:** Write out the full H2 list before starting the body. Confirm it covers the primary intent and at least one differentiating angle competitors lack.

For comparison or "alternatives" posts, always include:
- A feature matrix table (covers: comparison intent, featured snippet opportunity)
- An explicit "Who [X] is best for" section per tool/option
- A clear editorial recommendation — don't hedge

---

## Phase 2: Writing the article

### Voice and style (Duct blog standards)

Study the existing posts in `blog/posts/` before writing. The Duct voice is:
- **Direct and specific** — concrete scenarios, not vague claims. "You spend Monday mornings pulling data from five tools" beats "data aggregation is time-consuming."
- **Credibility through specificity** — name actual tools (Ahrefs, Search Console, Mixpanel, GA4), real metrics, realistic timeframes
- **Short paragraphs** — 1–3 sentences. Readers scan; subheadings every 200–300 words
- **No filler openers** — never start with "In today's fast-paced digital landscape..." Jump straight to the substance
- **Branded product tie-in at the end** — the final section or a `---` separator block shows how Duct solves the problem, with a link to `https://getduct.ai`

### Article structure (follow this sequence)

**Opening (first 100 words) — most critical:**
- Answer the primary question or state the core thesis immediately
- Hook with a specific, relatable scenario the reader has experienced
- Do not start with a generic definition of the topic ("Keyword gap analysis is the process of...")
- Instead, start in media res: the situation the reader is already in

**Body sections (H2s):**
- Each H2 covers one distinct sub-question or stage of the journey
- H3s break complex H2 sections into scannable chunks (one H3 per ~300 words of content under that H2)
- Use bullet lists for 3+ parallel items; numbered lists for sequential steps
- Bold the most important phrase in each paragraph — one per paragraph maximum
- If stating a statistic or external claim, add `[STAT NEEDED: brief description]` as a placeholder rather than inventing a number

**FAQ section (include in most posts):**
- Pull 3–5 real People Also Ask questions from the SERP for the primary keyword
- Answer each in 40–60 words maximum — tight, direct, no padding
- Format as `### Q: [question]` followed by a direct paragraph answer
- This section doubles as structured data input and improves AIO (AI Overview) inclusion

**Closing / Duct tie-in:**
- Summarise the core insight or recommendation in 1–2 sentences
- Transition naturally to how Duct addresses the remaining friction
- Use a `---` separator then a bold Duct callout with a `[Join the beta →](https://getduct.ai)` link
- Match the CTA intensity to the funnel stage (see Phase 1c table)

### Internal linking (2–4 links per post)

Every post must link to 1–2 other Duct blog posts using descriptive anchor text. Rules:
- Anchor text must describe the destination page, not be generic ("read more", "click here")
- Good: `[how to read cross-tool SEO signals together](../posts/why-your-seo-metrics-arent-telling-you-the-full-story.md)`
- Link placement: in-line within body copy, at a natural reading moment — not appended at the end as a list
- Also link to the relevant Duct landing page when the topic matches (e.g. organic growth content → `for-organic-growth.html`)

### Word count target

Set the target ~15% above the average of the top 5 SERP results for the primary keyword. Do not use a flat target without considering the SERP. General guidance:
- Narrow "how to" posts: 800–1,200 words
- Comparison / evaluation posts: 1,200–2,000 words
- Comprehensive guides / cluster pillars: 2,000–3,500 words

---

## Phase 3: File creation

### 3a. Generate the slug

Lowercase the title, replace spaces with hyphens, remove apostrophes and special characters.

Example: `"How to Audit Your Conversion Funnel in 30 Minutes"` → `how-to-audit-your-conversion-funnel-in-30-minutes`

### 3b. Create `blog/posts/<slug>.md`

Use this front matter format exactly (verified against existing posts):

```
---
title: "<title>"
date: <date>
author: Duct Team
category: <category>
excerpt: "<excerpt>"
readTime: <minutes>
---

<article body>
```

Front matter rules:
- `title` and `excerpt` must be quoted strings
- `date` format: `Mon DD YYYY` (e.g. `Mar 20 2026`) — no quotes
- `readTime` is a bare integer — no quotes
- `author` is always `Duct Team` unless specified otherwise
- Do not add `heroImage` unless an image file exists in `blog/assets/`

**Excerpt quality bar:** The excerpt appears on the blog card. It must be 1–2 sentences that create genuine curiosity or convey a specific, interesting claim. Not a generic description of the topic. Compare:
- Weak: "Learn how keyword gap analysis works and why it matters for your SEO strategy."
- Strong: "The old way: export Ahrefs, paste into Sheets, cross-reference manually. The new way: know the gap before your Monday standup."

### 3c. Add card to `blog/index.html`

Insert a new `<a class="blog-card reveal">` inside `.blog-grid`. Cards are ordered newest first. Add `style="transition-delay:.Xs"` incrementing by `.08s` per card position.

Card template:
```html
<a href="post.html?slug=<slug>" class="blog-card reveal" style="transition-delay:<Ns>">
  <div class="blog-card-img" style="background:linear-gradient(135deg,#COLOR1,#COLOR2);display:flex;align-items:center;justify-content:center;font-size:48px"><EMOJI></div>
  <div class="blog-card-body">
    <span class="tag"><category></span>
    <h3 class="blog-card-title"><title></h3>
    <p class="blog-card-excerpt"><excerpt></p>
    <div class="blog-card-meta"><span><date></span><span><minutes> min read</span></div>
  </div>
</a>
```

Gradient and emoji should match the topic mood. Existing reference:
- SEO / data → `#e6f4ec, #c8e6d4` + 📊
- Content strategy → `#fff0e5, #fdd9b5` + 🔑
- Product analytics → `#e8f0fe, #c5d8fd` + 📈
- Growth / conversion → `#fef9e7, #fdebd0` + 🚀

### 3d. Add to `sitemap.xml`

```xml
<url>
  <loc>https://getduct.ai/blog/post.html?slug=<slug></loc>
  <changefreq>monthly</changefreq>
  <priority>0.7</priority>
</url>
```

---

## SEO quality checklist before done

**Intent and structure**
- [ ] Intent type identified; post format matches dominant SERP format
- [ ] Funnel stage identified; CTA matches stage (TOFU/MOFU/BOFU)
- [ ] H2s are question-shaped and cover the primary intent + one differentiating angle
- [ ] Comparison posts include feature matrix table and "who it's best for" per option

**Writing quality**
- [ ] First 100 words answer the primary question or hook with a specific scenario
- [ ] No generic opener ("In today's fast-paced..." etc.)
- [ ] Short paragraphs (1–3 sentences); subheadings every 200–300 words
- [ ] No invented statistics — any claim needing a source uses `[STAT NEEDED: ...]`
- [ ] FAQ section present with 3–5 PAA-derived questions, answers ≤60 words each
- [ ] Duct tie-in at the end with a CTA link to `https://getduct.ai`

**SEO elements**
- [ ] Primary keyword in: title, first 100 words, at least one H2, meta description
- [ ] 2–4 internal links with descriptive anchor text (not "click here")
- [ ] Excerpt is specific and curiosity-generating (not a generic topic description)

**Technical**
- [ ] Front matter has all six required keys with correct types
- [ ] Slug is consistent across: filename, blog card `href`, sitemap `<loc>`
- [ ] Blog card added to `blog/index.html`, ordered newest first
- [ ] Added to `sitemap.xml`
- [ ] No `<script>` tags in the Markdown body
