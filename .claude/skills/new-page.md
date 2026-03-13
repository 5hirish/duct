---
name: new-page
description: Create a new audience-specific landing page following the for-*.html pattern
argument-hint: "<audience-slug> \"<title suffix>\" \"<hero headline>\" \"<hero subtext>\""
---

Creates a new `for-<audience-slug>.html` variant page for a specific audience segment.

## Usage

```
/new-page <audience-slug> "<title suffix>" "<hero headline>" "<hero subtext>"
```

Example:
```
/new-page for-engineering-teams "for Engineering Teams" "Stop losing signal in the noise." "Duct connects Jira, Linear, Sentry, and Datadog into a weekly engineering brief."
```

## Steps

### 1. Copy the base template

Copy `for-product-intelligence.html` → `for-<audience-slug>.html` at the repo root.

### 2. Update `<head>`

- `<title>` → `Duct <title-suffix> — AI product intelligence`
- `<link rel="canonical">` → `https://getduct.ai/for-<audience-slug>`
- `og:url` → same as canonical
- `og:title` and `twitter:title` → match `<title>`
- `og:description` and `twitter:description` → write fresh copy (120–140 chars)
- JSON-LD `name` field → match `<title>`, `url` field → match canonical

### 3. Update nav subtitle

Change the `<span>` next to the Duct logo to reflect the new audience (e.g. `for engineering teams`).

### 4. Update hero section

- `<h1>` → new headline
- `.hero-sub` paragraph → new subtext
- Keep the email `<input>` and submit `<button>` — confirm `data-form-url` and `data-entry-id` match the desired Google Form (copy from `for-product-intelligence.html` if using the same form)

### 5. Update accent colour (optional)

If the audience warrants a different brand accent, add a `<style>` block overriding CSS variables. Follow the green override pattern in `for-organic-growth.html` (lines 30–59). Common overrides:
- `--orange` → a different accent hue
- Gradient stops in `.hero`, `.hero-img`

### 6. Update audience cards

Swap the `.aud-card` role titles and descriptions for the target audience personas.

### 7. Add to `sitemap.xml`

```xml
<url>
  <loc>https://getduct.ai/for-<audience-slug></loc>
  <changefreq>weekly</changefreq>
  <priority>0.9</priority>
</url>
```

## Checklist before done

- [ ] Canonical URL is correct and unique (matches no other page)
- [ ] All `og:` and `twitter:` text tags updated (not copied from base)
- [ ] `data-form-url` and `data-entry-id` are present on both submit buttons
- [ ] Nav subtitle updated
- [ ] Hero headline and subtext are audience-specific
- [ ] Added to `sitemap.xml`
- [ ] No `<!-- TODO -->` or placeholder text remaining
