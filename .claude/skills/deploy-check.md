---
name: deploy-check
description: Run pre-deploy verification checks on the static site before pushing to main
---

Runs read-only bash checks to verify the site is ready to deploy. Report each failure with the file and exact fix needed. Do not auto-fix — present findings and wait for confirmation.

## Checks

### 1. Canonical links present on all HTML files

```bash
grep -rL 'rel="canonical"' --include="*.html" .
```

Expected: empty output. Any file listed is missing a canonical tag.

### 2. All canonicals point to production domain

```bash
grep -r 'rel="canonical"' --include="*.html" . | grep -v 'https://getduct.ai'
```

Expected: empty output. Any match means a local URL or wrong domain is set.

### 3. No broken relative asset paths in blog/

```bash
grep -rn 'href="assets/' --include="*.html" blog/
grep -rn 'src="assets/' --include="*.html" blog/
```

Expected: empty output. Blog pages must use `../assets/`, not `assets/`.

### 4. config.js loaded before duct.js on all pages

```bash
grep -n 'config\.js\|duct\.js' index.html for-product-intelligence.html for-organic-growth.html blog/index.html
```

Verify the `config.js` line number is lower than the `duct.js` line number in each file.

### 5. GTM noscript present on all pages

```bash
grep -rL 'googletagmanager.com/ns.html' --include="*.html" .
```

Expected: empty output. Any file listed is missing the GTM noscript iframe.

### 6. All blog post slugs appear in blog/index.html and sitemap.xml

```bash
ls blog/posts/*.md
```

For each `.md` filename (slug), verify:
- A `href="post.html?slug=<slug>"` exists in `blog/index.html`
- A `<loc>` containing `?slug=<slug>` exists in `sitemap.xml`

### 7. No npm artifacts committed

```bash
ls package.json 2>/dev/null && echo "FAIL: package.json present" || echo "OK: no package.json"
ls -d node_modules 2>/dev/null && echo "FAIL: node_modules present" || echo "OK: no node_modules"
```

### 8. Sitemap URLs use production domain

```bash
grep '<loc>' sitemap.xml | grep -v 'https://getduct.ai'
```

Expected: empty output.

## Reporting

After running all checks, summarise:
- ✅ PASS — check passed
- ❌ FAIL — describe what's wrong and which file needs fixing

Only report failures that require action before deploying.
