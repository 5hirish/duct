---
name: add-blog-post
description: Add a new blog post to the Duct Insights blog
argument-hint: "\"<title>\" \"<category>\" \"<excerpt>\" <read-time-minutes> \"<date>\""
---

Adds a new blog post: creates the Markdown file, adds the blog card to the index, and updates the sitemap.

## Usage

```
/add-blog-post "<title>" "<category>" "<excerpt>" <minutes> "<date>"
```

Example:
```
/add-blog-post "How to Audit Your Conversion Funnel in 30 Minutes" "Product Analytics" "Most funnel audits take days. Here is the three-step process that surfaces the drop-off in under an hour." 4 "Mar 20 2026"
```

## Steps

### 1. Generate the slug

Lowercase the title, replace spaces with hyphens, remove apostrophes and special characters.

Example: `"How to Audit Your Conversion Funnel in 30 Minutes"` → `how-to-audit-your-conversion-funnel-in-30-minutes`

### 2. Create `blog/posts/<slug>.md`

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

<article body in Markdown>
```

Front matter rules:
- `title` and `excerpt` must be quoted strings
- `date` format: `Mon DD YYYY` (e.g. `Mar 20 2026`) — no quotes
- `readTime` is a bare integer — no quotes
- `author` is always `Duct Team` unless specified otherwise
- Do not add `heroImage` unless an image file exists in `blog/assets/`

Write a substantive article body — not a placeholder. The article should be useful, specific, and on-brand with the existing posts in `blog/posts/`.

### 3. Add card to `blog/index.html`

Insert a new `<a class="blog-card reveal">` inside `.blog-grid`. Cards are ordered newest first. Add `style="transition-delay:.Xs"` incrementing by `.08s` per card position (first card has no delay, second has `.08s`, third `.16s`, etc.).

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

Pick a gradient and emoji that fits the topic. Examples from existing cards:
- SEO → `#e6f4ec, #c8e6d4` + 📊
- Content Strategy → `#fff0e5, #fdd9b5` + 🔑
- Product Analytics → `#e8f0fe, #c5d8fd` + 📈

### 4. Add to `sitemap.xml`

```xml
<url>
  <loc>https://getduct.ai/blog/post.html?slug=<slug></loc>
  <changefreq>monthly</changefreq>
  <priority>0.7</priority>
</url>
```

## Checklist before done

- [ ] Front matter has all six required keys with correct types
- [ ] Slug is consistent across: filename, blog card `href`, sitemap `<loc>`
- [ ] Blog card is in `blog/index.html`, ordered newest first
- [ ] Article body is substantive (not a placeholder)
- [ ] Added to `sitemap.xml`
- [ ] No `<script>` tags in the Markdown body
