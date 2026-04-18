# Duct — Free Tools Build Plan
**Version:** 1.0 — April 2026
**ICP:** Growth PMs and Performance Marketers at 20–200 person SaaS companies without a dedicated data team.

> Free tools are the highest-leverage organic growth mechanism in the plan. One tool page with genuine utility outperforms five blog posts in the first 90 days. Tools earn backlinks passively, rank faster due to engagement signals, and convert directly because the visitor is already doing the job Duct automates.

---

## Tool Roster

| # | Tool | URL | Primary Keyword | SV | Audience |
|---|---|---|---|---|---|
| 1 | UTM Builder | `/tools/utm-builder` | `utm builder` | 8,100 | All paid/organic teams |
| 2 | Paid Ads Budget Allocator | `/tools/ads-budget-calculator` | `facebook ads budget calculator` | 1,900 | Performance marketers |
| 3 | Google Ads Readiness Auditor | `/tools/google-ads-readiness` | `google ads quality score checker` | ~500 | Google Ads teams |
| 4 | SEO Auditor | `/tools/seo-auditor` | `free seo audit tool` | High | SEO / content leads |
| 5 | AIO Auditor | `/tools/aio-auditor` | `ai overview audit` | Emerging | SEO / content leads |

---

## Competitive Positioning

| Tool | Current #1 | Their weakness | Our edge |
|---|---|---|---|
| UTM Builder | DashThis (static form) | No live preview, no GA4 validation | Live URL preview + GA4 compliance validator + bulk mode |
| Budget Allocator | Single-channel calculators | Facebook-only, no multi-channel | Multi-channel allocation + scenario modeling + industry benchmarks |
| Google Ads Readiness | Nothing dominant | Gap in market | Quality Score factors + message match + load speed + trust signals |
| SEO Auditor | SEMrush free (limited), SEOptimer | Paywalled fast, generic advice | Comprehensive free: SEO + technical + mobile + performance + ads overlay |
| AIO Auditor | OtterlyAI, LLMClicks | No revenue/conversion connection | llms.txt + crawler rules + content signals + conversion context |

---

## Conversion Gate Design

**Simple tools (UTM, Budget):** Core logic free, no gate. Advanced features gated:
- UTM Builder: bulk CSV export + saved templates → email gate
- Budget Allocator: scenario modeling → email gate

**Auditor tools (Google Ads Readiness, SEO, AIO):** Post-results blur pattern:
1. User enters URL → backend fetches and analyses
2. **Free:** Score (0–100) + Top 3 critical issues — fully visible
3. **Gated:** Full report section — blurred with overlay
4. Overlay: "Unlock your full report — free" + email input + CTA
5. On submit → localStorage flag → unblurs section
6. Bottom CTA: always links to relevant product page

---

## Technical Architecture

**Tools 1 & 2 (UTM, Budget):** Pure HTML/CSS/JS. No backend. Same pattern as existing calculators.

**Tools 3, 4 & 5 (Auditors):**
- Frontend POSTs URL to `backend/` Python API endpoint
- Backend fetches URL server-side (no CORS), parses HTML, runs deterministic checks
- Gemini 2.0 Flash called for AI scoring layer (copy quality, recommendation priority, citation likelihood)
- Gemini API key in backend env vars — never in frontend
- Fallback: "paste HTML source" textarea if backend unreachable

---

## Tool 1: UTM Builder

**URL:** `getduct.ai/tools/utm-builder`

**Target keywords:**
- `utm builder` — 8,100 SV, DashThis is #1 with a static form
- `utm link builder`, `utm generator`, `google analytics utm builder`

**What the tool does:**
- Inputs: Website URL, Source, Medium, Campaign, Term (optional), Content (optional)
- Live URL preview: updates on every keystroke
- GA4 compliance validator per field: green ✓ / amber ⚠ (uppercase, spaces) / red ✗ (reserved word, invalid chars)
- Copy in 3 formats: Raw URL / Display-friendly / Spreadsheet row (tab-separated)
- Recent history: last 5 URLs in localStorage (free)
- Bulk mode (email-gated): paste multiple campaign names → generate all → copy all / download CSV
- Expandable FAQ: "What each UTM parameter means in GA4" (featured snippet target)

**Conversion hook:**
> "You're building UTMs manually. Duct auto-tags every campaign and maps each to product outcomes in your weekly brief."

**CTA:** "See how →" → `/for-paid-ads`

---

## Tool 2: Paid Ads Budget Allocator

**URL:** `getduct.ai/tools/ads-budget-calculator`

**Target keywords:**
- `facebook ads budget calculator` — 1,900 SV
- `paid ads budget calculator`, `google ads budget calculator`, `ad spend calculator`

**What the tool does:**
- Inputs: Total monthly budget, primary goal (Awareness/Lead Gen/Conversions/Sales), active channels (Google Search, Display, Meta, LinkedIn, TikTok, YouTube), industry
- Free output: recommended budget split (% + amount), estimated clicks/reach per channel, ROAS target per channel (colour-coded)
- Gated output (email): scenario comparison table, "what if +20% to Google?" delta, channel efficiency ranking

**Conversion hook:**
> "Duct connects all these channels and shows your actual blended ROAS every Monday morning — automatically."

**CTA:** "Get early access →" → `/for-paid-ads`

---

## Tool 3: Google Ads Readiness Auditor

**URL:** `getduct.ai/tools/google-ads-readiness`

**Target keywords:**
- `google ads quality score checker`
- `landing page quality score`, `google ads landing page audit`, `ads landing page checker`

**Why separate from SEO Auditor:** Completely different audience (paid ads managers), different job ("Am I about to waste money because my landing page isn't ready?"). Quality Score is Google Ads-specific and affects CPC directly.

**What it checks:**

| Category | Weight | Checks |
|---|---|---|
| Message match | 25% | H1 action-oriented, above-fold headline present, value prop clarity |
| Landing page experience | 30% | Clear primary CTA with action verb, form field count, no interstitial signals |
| Load speed indicators | 20% | Render-blocking script count, inline CSS weight, image count without lazy-load, viewport meta |
| Mobile-friendliness | 15% | Viewport meta, no fixed-width containers, font-size hints |
| Trust signals | 10% | SSL (HTTPS), privacy policy link, testimonial/review pattern |

**Free output:** Google Ads Readiness Score (0–100) + Top 3 QS risk factors

**Gated output (email):** Full 20-point QS checklist, "how to fix" per issue, estimated QS impact ("Fixing these 3 issues could improve QS by 2–3 points, reducing CPC by ~15–25%")

**Conversion hook:**
> "Every point of Quality Score you're missing costs you in CPC. Duct tracks your landing page performance against your ad spend automatically each week."

**CTA:** "Get early access →" → `/for-paid-ads`

---

## Tool 4: SEO Auditor

**URL:** `getduct.ai/tools/seo-auditor`

**Target keywords:**
- `free seo audit tool`, `free seo auditor`, `seo checker`, `website seo audit`

**Why we beat SEOptimer and Ubersuggest:** They gate fast and give generic fixes. We give a full audit free and layer in paid-ads conversion readiness — a differentiator no pure-SEO tool has.

**What it checks:**

| Category | Checks |
|---|---|
| On-page SEO | Title (50–60 chars), description (140–160 chars), H1 present + single, H2/H3 hierarchy, image alt tags |
| Technical | Canonical, robots meta, schema type detected, OG tags, Twitter tags |
| Performance indicators | Render-blocking scripts, external CSS/JS count, image count, estimated resource weight |
| Mobile | Viewport meta, no fixed-width containers, tap-target signals |
| Conversion overlay | CTA button, above-fold action, form presence, trust signal count — unique to Duct |

**Free output:** SEO Score (0–100) + Top 5 issues across all categories

**Gated output (email):** Full 30-point audit, AI recommendations (Gemini: top 3 highest-impact changes), paid-ads readiness overlay per issue

**Conversion hook:**
> "Ranking well but not converting? Duct shows the gap between your organic performance and paid readiness — automatically, every week."

**CTA:** "See how →" → `/for-organic-growth`

---

## Tool 5: AIO Auditor

**URL:** `getduct.ai/tools/aio-auditor`

**Target keywords:**
- `ai overview audit`, `llms.txt checker`, `ai readiness checker`, `aio optimization tool`

**Why first-mover matters:** OtterlyAI and LLMClicks exist but neither connects AIO presence to conversion or revenue. Duct owns that angle.

**What it checks:**

| Check | What it verifies |
|---|---|
| llms.txt | Fetches `{domain}/llms.txt` — present / missing / malformed |
| AI crawler permissions | robots.txt — GPTBot, ClaudeBot, PerplexityBot, Amazonbot allowed or blocked |
| Structured data | JSON-LD present, type identified |
| Heading structure | H1–H6 hierarchy, numbered sections present |
| FAQ / Q&A pattern | `<details>` or FAQ schema detected |
| Definition signals | "is a", "means", "refers to" patterns |
| Statistic signals | Numbers + % + year patterns (citable data) |
| Entity clarity | Page title matches domain/brand entity |

**Free output:** AIO Readiness Score (0–100) + Top 3 issues + llms.txt status

**Gated output (email):** Full 12-point checklist, AI assessment (Gemini: "What queries is this page likely cited for?"), generated `llms.txt` template, robots.txt AI-crawler snippet

**Conversion hook:**
> "Duct monitors which of your pages appear in AI responses and tracks whether those visits convert."

**CTA:** "Get early access →" → `/for-organic-growth`

---

## Build Order

| # | Tool | Rationale |
|---|---|---|
| 1 | UTM Builder | Highest SV (8,100), pure JS, no backend, ships immediately |
| 2 | Budget Allocator | Pure JS, fast build, clear multi-channel differentiation |
| 3 | AIO Auditor | First-mover category, backend needed, deterministic checks are well-defined |
| 4 | Google Ads Readiness | Backend needed, distinct ICP, strong conversion story |
| 5 | SEO Auditor | Most checks — builds on patterns from tools 3 & 4 |

---

## Internal Linking Map

```
UTM Builder         → /for-paid-ads + /blog/automated-reporting-guide
Budget Allocator    → /for-paid-ads + /blog/automated-reporting-guide
Google Ads Readiness → /for-paid-ads + UTM Builder (cross-link)
SEO Auditor         → /for-organic-growth + /blog/seo-intelligence-guide
AIO Auditor         → /for-organic-growth + SEO Auditor (cross-link)
```

All tools appear in:
- `site/partials/nav-tools.html` — Free Tools dropdown
- `site/partials/footer-expanded.html` — Free Tools column
- `site/assets/duct.js` — `tools[]` array + `relatedByTool` map
- `site/sitemap.xml` — `<url>` entries (priority 0.8, changefreq monthly)

---

## 90-Day Placement (per seo-content-plan.md calendar)

These tools ship in parallel with Week 1–2 blog work and before cluster posts:

| Week | Tool | Why |
|---|---|---|
| 1 | UTM Builder | Highest volume, instant value, fast to build |
| 2 | Budget Allocator | Pairs with Week 2 Automated Reporting pillar page |
| 3 | AIO Auditor | First-mover advantage, pairs with SEO Intelligence cluster start (Week 5) |
| 4 | Google Ads Readiness | Pairs with paid ads content and for-paid-ads landing page |
| 5 | SEO Auditor | Pairs with SEO Intelligence pillar (Week 5 publish) |

---

*Last updated: April 2026 | Companion to: seo-content-plan.md*
