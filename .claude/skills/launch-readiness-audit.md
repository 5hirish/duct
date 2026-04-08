---
name: launch-readiness-audit
description: Audit a page or blog post for launch readiness across SEO, mobile responsiveness, AI crawler discoverability, and UX copy quality. Use when the user asks for an audit, readiness review, or pre-launch checklist for site/blog content.
argument-hint: "<target-path-or-url> [\"<audience/context>\"]"
---

Runs a structured launch-readiness audit for one page/post using the Duct GTM audit standard in `docs/gtm/ads-launch-readiness-audit.md`.

## Usage

```
/launch-readiness-audit <target-path-or-url> ["<audience/context>"]
```

Examples:

```
/launch-readiness-audit site/for-paid-ads.html
/launch-readiness-audit site/blog/post.html "SEO operators in SaaS"
```

---

## Scope and goal

Evaluate the target against four categories:

1. SEO tags and indexability
2. Mobile responsiveness and loading risk
3. AI crawler / AEO discoverability
4. UX copy (story, first fold, CTA quality)

Deliver a decision-ready output:
- verdict (Go / Conditional Go / Hold)
- category scorecard
- highest-impact fixes in priority order

---

## Phase 1 - Collect evidence first

Do not score before gathering concrete evidence from the target file(s).

For every audit:
- Identify canonical URL target and page type (home, vertical, blog index, blog post).
- Extract current title, meta description, canonical, OG/Twitter tags, robots directives.
- Verify CTA text, first-fold headline/subheadline, and trust/proof elements.
- Check internal link quality and whether copy matches likely search intent.
- Capture mobile-specific behavior (layout fit, readability, tap-target spacing, visual hierarchy).
- Note any script/font/media patterns that may create avoidable load risk.

If the target is a template page (for example `site/blog/post.html`), call out template-level risks separately from content-specific risks.

---

## Phase 2 - Score with this rubric

Use 0-10 scoring in each category, then compute an overall weighted score:

- UX copy quality: 35%
- SEO tags/indexability: 25%
- Mobile responsiveness/loading risk: 20%
- AI crawler discoverability: 20%

Status mapping:
- 8.0-10.0 = Green
- 6.0-7.9 = Yellow
- 4.0-5.9 = Yellow-Red
- below 4.0 = Red

Verdict mapping:
- Go: no Red categories and overall >= 7.5
- Conditional Go: overall 5.5-7.4 with clear mitigation path
- Hold: any category below 4.0 or overall < 5.5

---

## Category checklists

### 1) SEO tags and indexability

Check:
- unique, intent-aligned `<title>`
- useful meta description (specific value, not generic)
- correct canonical (stable URL, no accidental duplicates)
- OG/Twitter tags present and aligned
- robots directives and sitemap fit
- internal links use descriptive anchor text
- blog/article URLs are consistent and index-friendly

Red flags:
- missing or duplicated canonical
- vague homepage-style title on a paid-intent or long-tail page
- weak meta description that does not communicate outcome

### 2) Mobile responsiveness and loading risk

Check at small viewport (375px baseline):
- no horizontal overflow or clipped hero copy
- body text remains readable without zooming
- CTA is clearly visible and thumb-friendly
- first fold communicates "who this is for" and "what they get"
- no avoidable heavy assets/scripts affecting first impression

Red flags:
- primary CTA below confusing/oversized content blocks
- tiny text or cramped interaction areas
- unnecessary script work before user intent signals

### 3) AI crawler / AEO discoverability

Check:
- answer-first copy blocks that can be quoted by LLMs
- explicit entity/context language (who, use case, tools, outcomes)
- crawlability signals in robots/sitemap/canonicals
- FAQ or direct Q/A sections where appropriate
- publicly discoverable proof or concrete claims (without fabricated numbers)

Red flags:
- marketing-only abstraction with no answer-style content
- weak off-page referenceability and low factual density
- unclear page purpose for retrieval systems

### 4) UX copy quality (story, first fold, CTA)

Check:
- first fold clearly states audience, outcome, and next step
- headline/subheadline are specific (not broad platform language)
- CTA is value-specific, not generic "learn more" style
- proof/trust appears early enough for cold traffic
- narrative flow moves problem -> mechanism -> outcome -> action

Red flags:
- broad claim without concrete payoff
- CTA reflects waitlist intent when commercial intent is expected
- delayed or missing proof for paid traffic pages

---

## Output format (required)

Use this exact output structure:

```markdown
# Launch Readiness Audit: <target>

## Verdict
**<Go | Conditional Go | Hold>**
One-sentence rationale.

## Scorecard
| Area | Status | Score | Why it scored this way |
|---|---|---:|---|
| UX copy quality | <status> | <x/10> | ... |
| SEO tags/indexability | <status> | <x/10> | ... |
| Mobile responsiveness/loading risk | <status> | <x/10> | ... |
| AI crawler discoverability | <status> | <x/10> | ... |
| **Overall (weighted)** | **<status>** | **<x/10>** | ... |

## Critical fixes before launch
1. <highest impact issue and specific fix>
2. <next issue and fix>
3. <next issue and fix>

## Quick wins (same day)
- <fast fix>
- <fast fix>
- <fast fix>

## Evidence snapshots
- `<path or section>`: <key observed fact>
- `<path or section>`: <key observed fact>
- `<path or section>`: <key observed fact>
```

---

## Quality bar

Before finalizing:
- Every score must cite at least one concrete observed fact.
- Do not invent performance numbers or conversion data.
- Distinguish template-level issues from page-instance issues.
- Recommendations must be specific enough to implement immediately.
- Keep the tone direct and decision-oriented.
