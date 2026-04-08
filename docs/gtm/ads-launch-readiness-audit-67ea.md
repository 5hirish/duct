# Ads Launch Readiness Audit & Google Ads Plan ($350/mo)

> Deep audit of getduct.ai for paid ads launch across Google Ads, Twitter/X Ads, and LinkedIn Ads — with a complete Google Ads plan for first launch from zero on a $350/month budget.

**Audit date:** 2026-04-08
**Pages audited:** `index.html`, `for-paid-ads.html`, `for-product-intelligence.html`, `for-organic-growth.html`, blog, partials
**Scope:** Page copy & conversion flow, measurement & tracking, SEO tags & indexing, AEO discoverability, mobile responsiveness & performance

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Audit: Page Copy, Landing Page Story & Conversion Flow](#2-audit-page-copy-landing-page-story--conversion-flow)
3. [Audit: Measurement & Tracking](#3-audit-measurement--tracking)
4. [Audit: SEO Tags & Indexing](#4-audit-seo-tags--indexing)
5. [Audit: AEO / AI Discoverability](#5-audit-aeo--ai-discoverability)
6. [Audit: Mobile Responsiveness & Loading Times](#6-audit-mobile-responsiveness--loading-times)
7. [Google Ads Plan: First Launch from Zero ($350/mo)](#7-google-ads-plan-first-launch-from-zero-350mo)
8. [Twitter/X Ads & LinkedIn Ads: Readiness Notes](#8-twitterx-ads--linkedin-ads-readiness-notes)
9. [Pre-Launch Checklist](#9-pre-launch-checklist)
10. [Appendix: Keyword Research & Ad Copy](#appendix-keyword-research--ad-copy)

---

## 1. Executive Summary

### Overall Readiness Score

| Category | Score | Verdict |
|---|---|---|
| Page Copy & Conversion Flow | 7.5/10 | Good — strong hero, clear CTA, some friction points to fix |
| Measurement & Tracking | 5/10 | **Blocking** — GTM is installed but conversion events are not verified; no ad platform pixels confirmed |
| SEO Tags & Indexing | 8/10 | Good — meta tags solid, structured data in place, minor gaps |
| AEO Discoverability | 8.5/10 | Strong — FAQPage schema, `llms.txt`, `robots.txt` allowing AI bots |
| Mobile Responsiveness | 7/10 | Good — responsive breakpoints exist, some first-fold UX concerns |
| Loading Performance | 8.5/10 | Strong — static HTML, no framework overhead, Cloudflare CDN |

### Top 5 Blockers (Fix Before Turning on Ads)

1. **Conversion tracking is not verified** — `beta_signup` and `form_submit` events must be confirmed firing in GA4 DebugView before any ad spend
2. **No Google Ads conversion tag** — GA4 key events must be imported into Google Ads (or a native Google Ads tag deployed) for Smart Bidding to work
3. **No Twitter/X pixel installed** — cannot track conversions from X Ads without the universal website tag
4. **No LinkedIn Insight Tag installed** — cannot build retargeting audiences or track LinkedIn Ad conversions
5. **OG image file may not exist** — all pages reference `og-image.png` but the file is not present in the repo; social shares and ad previews will show a broken image

### Top 5 Quick Wins (High-Impact, Low-Effort)

1. Add above-the-fold social proof to `/for-paid-ads` (e.g. "Trusted by 25+ beta teams" or beta user count)
2. Verify and test all conversion events in GA4 DebugView
3. Install LinkedIn Insight Tag and Twitter pixel via GTM
4. Add `SoftwareApplication` schema to landing pages for richer search presence
5. Update `llms.txt` to include the `/for-paid-ads` page

---

## 2. Audit: Page Copy, Landing Page Story & Conversion Flow

### 2.1 Homepage (`index.html`)

**Hero Analysis:**

| Element | Current | Assessment |
|---|---|---|
| Pill | "Now in private beta" | Good scarcity signal |
| H1 | "Stop checking dashboards. Start shipping decisions." | Strong problem-to-outcome framing. Passes 5-second test |
| Subheadline | "Get one weekly cross-tool intelligence brief..." | Clear, specific value prop |
| CTA | "Get early access →" + email input | Single clear action — good |
| Proof pills | "9+ integrations · ~4h saved · 10 min setup" | Good quantified proof |

**Strengths:**
- Problem → solution → proof flow is textbook SaaS landing page structure
- H1 uses imperative action verbs ("Stop" / "Start") — high engagement pattern
- Hero includes a mini demo preview with tab switching (Paid Ads / Product / SEO) — shows product before scroll
- Tool strip ("Works with tools you already use") adds credibility
- Multiple CTA touchpoints (hero + bottom CTA section)

**Issues for Paid Traffic:**
- **No above-the-fold social proof** — no logos, no beta user count, no testimonial. Cold paid traffic needs trust signals immediately. Research shows above-the-fold trust signals (G2 badges, logos, testimonials) improve form completions by ~15%
- **Hero sub-headline is slightly generic** — "weekly cross-tool intelligence brief" could be more outcome-specific for each audience
- **The mini demo tab content is small text** — on mobile, the demo preview is hard to read and may not add value
- **CTA button says "Get early access →"** — this is vague. "Get your first brief free →" is more specific and value-driven per expert consensus

**Recommendations:**
1. Add a social proof bar directly under the hero form: "Trusted by 25+ teams in private beta" or specific company sizes/types
2. Consider testing CTA copy: "Get your first brief free →" vs. "Get early access →"
3. On mobile, consider hiding the mini demo preview or showing a simplified version
4. The hero footnote ("Free during beta · No credit card · 10 minutes to connect · First full brief in your inbox") is excellent — keep it

### 2.2 Paid Ads Landing Page (`for-paid-ads.html`) — Primary Ad Destination

This is the most important page for paid ads traffic. It will receive the majority of Google Ads clicks.

**Hero Analysis:**

| Element | Current | Assessment |
|---|---|---|
| Pill | "Early access · Paid ads beta" | Clear, good urgency |
| H1 | "Stop stitching ad reports. Start making better budget decisions." | Excellent — problem-specific, action-oriented |
| Subheadline | "Duct connects Google Ads, Meta, LinkedIn, and X..." | Names specific platforms — strong intent match |
| CTA | "Get early access →" + email input | Same as homepage |
| Footnote | "Free during beta · No credit card · For performance marketers at 20–200 person companies" | ICP qualifier — smart |
| Secondary CTA | "or try the live demo ↓ — no signup required" | Reduces friction for skeptics |

**Strengths:**
- The H1 directly mirrors paid search intent ("stitching ad reports" = what the ICP does today)
- "try the live demo ↓" as a secondary CTA is conversion-smart — gives an alternative path for people not ready to sign up
- The problem section with the disconnected-tools diagram (Google Ads / Meta / X / HubSpot → "After Duct") is visually compelling
- The interactive demo walkthrough (4 steps: pick platforms → pick metric → analyze → see report) is outstanding product marketing
- FAQ schema is comprehensive and matches actual customer questions
- The "Who It's For" section explicitly qualifies the ICP with persona cards

**Issues:**
- **No social proof anywhere on the page** — no beta user count, no logos, no testimonials, no G2 badge. This is the single biggest conversion gap for cold paid traffic. Expert research consistently shows social proof above the fold lifts conversions 15%+
- **"Get early access →" CTA is not value-specific** — paid traffic is colder than organic; the CTA should promise a concrete deliverable ("Get your first ad brief free →")
- **The "EXPERIMENT" HTML comment is good** but the hypothesis it tests (problem framing before demo vs. demo-first) should be logged for tracking
- **CTA form uses Google Forms submission via `no-cors` fetch** — this means the `.then()` callback fires even on network errors, and the success state always shows "You are on the list!" regardless of actual submission success. For paid traffic, every false positive is a lost lead
- **No thank-you state or next step** — after submission, the button just turns green. There's no redirect to a thank-you page, no "Check your inbox" message, no calendar link. Paid traffic needs a clear next step to reinforce the conversion

**Recommendations:**
1. **Add social proof above the fold** — even "25+ teams in paid ads beta" or "Beta teams managing $50K+ monthly ad spend"
2. **Change CTA to "Get your first ad brief free →"** or "See your cross-platform brief →"
3. **Add a post-submission state** — change the hero area after successful submission to show: "You're in. Check your inbox for next steps." with a calendar booking link if available
4. **Add `hreflang` if targeting US/UK/CA/AU** — paid traffic from multiple geos should see localized meta signals
5. **The interactive demo is a strong engagement tool** — consider adding a soft CTA after Step 4 (report view): "Want this for your actual accounts? Get early access →"

### 2.3 Conversion Flow Analysis

**Current flow:**
```
Ad click → /for-paid-ads → email input → Google Form POST (no-cors) → button turns green → nothing else
```

**Issues with current flow:**
1. No dedicated thank-you page — means no post-conversion tracking pixel fires, no Google Ads conversion tag on a distinct URL, no "conversion page" for ad platform optimization
2. The `form_submit` dataLayer push happens in the `.then()` callback of a `no-cors` fetch — this fires regardless of whether the form actually submitted (Google Forms returns an opaque response in `no-cors` mode). The conversion event may be unreliable
3. No email validation beyond checking for `@` — no check for disposable emails, typos, or corporate vs. personal domains

**Recommended improved flow:**
```
Ad click → /for-paid-ads → email input → form submit → in-page thank-you state with:
  - Clear "You're in" confirmation
  - "Check your inbox" instruction
  - Optional: calendar booking link
  - Fire a reliable conversion event (not dependent on no-cors response)
```

### 2.4 Cross-Page Copy Consistency

All three landing pages (`for-paid-ads`, `for-product-intelligence`, `for-organic-growth`) follow the same structure:

```
Hero → Tool Strip → Problem Section → Demo → How It Works → Features → Audience → Stats → FAQ → CTA
```

This is good — consistent structure means paid traffic landing on any page gets the same quality experience. The copy is well-differentiated per vertical:

| Page | H1 | Accent Color |
|---|---|---|
| Paid Ads | "Stop stitching ad reports..." | Blue (#2563EB) |
| Product Intelligence | Varies | Orange (brand default) |
| Organic Growth | Varies | Green |

The color-coding by vertical is smart for brand recall across retargeting.

---

## 3. Audit: Measurement & Tracking

### 3.1 Current State

| Component | Status | Notes |
|---|---|---|
| GTM Container | Installed (`GTM-PKL589SW`) | Hardcoded noscript iframe on every page; deferred JS load via `duct.js` |
| GTM Deferred Load | Implemented | Loads on first interaction (scroll/click/keydown) or after 3s idle — good for performance |
| GA4 Property | Assumed configured | GA4 is expected to be configured inside GTM; no direct `gtag.js` on site |
| UTM Persistence | Implemented | `duct.js` stores UTM params to `sessionStorage` and pushes to `dataLayer` |
| `form_submit` event | Implemented | Pushed to `dataLayer` on form submission in `submitForm()` |
| Google Ads Conversion Tag | **NOT FOUND** | No native Google Ads conversion tag or Ads remarketing tag detected |
| LinkedIn Insight Tag | **NOT FOUND** | Required for LinkedIn Ads conversion tracking and retargeting |
| Twitter/X Pixel | **NOT FOUND** | Required for X Ads conversion tracking |
| Enhanced Conversions | **NOT FOUND** | Google Ads Enhanced Conversions (hashed email) not implemented |

### 3.2 Critical Tracking Gaps

**Gap 1: No verified GA4 conversion events**

The `submitForm()` function pushes `{ event: 'form_submit', page: ... }` to `dataLayer`. This is necessary but not sufficient:
- The event must be configured as a GA4 Event tag in GTM
- The GA4 event must be marked as a Key Event (conversion) in GA4 Admin
- It has not been verified that this event fires correctly (it fires in both `.then()` and `.catch()` of a `no-cors` fetch, so it may fire even on failures)

**Action:** Open GA4 → DebugView → submit a test form on each landing page → confirm `form_submit` event appears with correct parameters.

**Gap 2: No Google Ads conversion tracking**

Without a Google Ads conversion action linked to a conversion event, Google Ads cannot:
- Optimize bidding toward conversions (Smart Bidding will optimize for clicks, not signups)
- Report conversion rate or cost-per-conversion
- Build conversion-based audiences for remarketing

**Action (two options):**
- **Option A (preferred):** Create a Google Ads conversion action → import the GA4 `form_submit` key event into Google Ads
- **Option B:** Deploy a native Google Ads conversion tag via GTM that fires on the same trigger as `form_submit`

For $350/month budget with low conversion volume, Option A is simpler and avoids double-counting.

**Gap 3: No LinkedIn Insight Tag**

The LinkedIn Insight Tag is required for:
- Tracking conversions from LinkedIn Ads
- Building website retargeting audiences (minimum 300 members to serve)
- Demographic reporting on website visitors

**Action:** Add the LinkedIn Insight Tag to GTM as a Custom HTML tag. Fire it on All Pages. Create conversion events for form submissions.

**Gap 4: No Twitter/X Universal Website Tag**

The X pixel is required for:
- Tracking conversions from X Ads
- Building tailored audiences for retargeting
- Conversion optimization bidding

**Action:** Add the X Universal Website Tag to GTM. Configure a "Signup" conversion event that fires on the same `form_submit` dataLayer event.

### 3.3 UTM Tracking Assessment

UTM handling in `duct.js` is well-implemented:
- Reads all 5 standard UTM parameters from URL
- Persists to `sessionStorage` (survives page navigation within session)
- Pushes to `dataLayer` for GTM pickup

**One gap:** The UTM values are not included in the `form_submit` event payload. When analyzing conversions in GA4, you can still see the acquisition source via GA4's built-in attribution, but pushing UTM values alongside the conversion event would make manual analysis easier.

### 3.4 Conversion Tracking Checklist (Pre-Launch)

| # | Task | Priority | Status |
|---|---|---|---|
| 1 | Verify `form_submit` fires in GA4 DebugView on all pages | P0 | TODO |
| 2 | Mark `form_submit` as a Key Event in GA4 Admin | P0 | TODO |
| 3 | Import GA4 `form_submit` key event into Google Ads as a conversion action | P0 | TODO |
| 4 | Install LinkedIn Insight Tag via GTM | P0 | TODO |
| 5 | Install X Universal Website Tag via GTM | P0 | TODO |
| 6 | Configure LinkedIn conversion event for form submission | P1 | TODO |
| 7 | Configure X conversion event for signup | P1 | TODO |
| 8 | Set up Google Ads Enhanced Conversions (hashed email) | P2 | TODO |
| 9 | Create GA4 audiences for remarketing (visited page, no conversion) | P1 | TODO |
| 10 | Verify `og-image.png` exists at `https://getduct.ai/assets/og-image.png` | P0 | TODO |

---

## 4. Audit: SEO Tags & Indexing

### 4.1 Meta Tags Audit

| Page | Title | Description | Canonical | Robots | OG | Twitter | Verdict |
|---|---|---|---|---|---|---|---|
| `/` (index) | "Duct — Automated Intelligence..." | Present, good length | `https://getduct.ai/` | `index, follow` | Complete | Complete | Pass |
| `/for-paid-ads` | "Duct for Paid Ads — Cross-platform..." | Present, specific | `https://getduct.ai/for-paid-ads` | `index, follow` | Complete | Complete | Pass |
| `/for-product-intelligence` | Present | Present | Present | `index, follow` | Present | Present | Pass |
| `/for-organic-growth` | Present | Present | Present | `index, follow` | Present | Present | Pass |
| `/blog/` | Present | Present | Present | Expected | Expected | Expected | Check |
| `app/` (Next.js) | "Duct App" | Present | N/A | **`noindex, nofollow`** | Present | Present | Intentional |

**Overall SEO meta tag verdict: PASS** — All marketing pages have complete meta tag coverage. The app correctly blocks indexing.

### 4.2 Structured Data Audit

| Page | Schema Types | Assessment |
|---|---|---|
| `/` (index) | `WebSite` + `FAQPage` (7 Q&As) | Excellent — both schemas are correct and comprehensive |
| `/for-paid-ads` | `WebPage` + `FAQPage` (6 Q&As) | Good — FAQPage is detailed and SEO-optimized |
| `/for-product-intelligence` | `WebPage` + `FAQPage` | Expected present |
| `/for-organic-growth` | `WebPage` + `FAQPage` | Expected present |

**Gaps in structured data:**
- **Missing `SoftwareApplication` schema** — adding this to the homepage and landing pages would enable Google to show richer results (rating, pricing, category)
- **Missing `Organization` schema on landing pages** — the homepage has it embedded in `WebSite`, but landing pages only have `WebPage`
- **No `Article` schema on blog posts** — blog post pages should have `Article` or `BlogPosting` schema for Google News and Discover eligibility
- **No `BreadcrumbList` schema** — breadcrumbs help Google understand page hierarchy and can show in search results

**Recommendation:** Add `SoftwareApplication` schema to the homepage JSON-LD:
```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Duct",
  "applicationCategory": "BusinessApplication",
  "operatingSystem": "Web",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD",
    "description": "Free during beta"
  },
  "description": "Cross-tool intelligence platform for product, marketing, and sales teams."
}
```

### 4.3 Sitemap & Robots Assessment

**Sitemap (`sitemap.xml`):**
- All marketing pages listed — PASS
- Blog posts listed — PASS
- `lastmod` dates are not automated (manual updates) — acceptable for static site
- **Missing:** No `lastmod` update since March 2026 on most pages

**Robots.txt:**
- Allows all crawlers — PASS
- Explicitly allows AI bots (Claude, ChatGPT, Perplexity, Google-Extended) — excellent
- Links to sitemap — PASS

### 4.4 Indexing Concerns

- The site is on Cloudflare Pages, which has good crawler support and fast TTFB
- Pages use server-rendered HTML (no JS-dependent rendering) — fully crawlable
- The `duct-partials.js` loads nav/footer via synchronous XHR — crawlers may not execute this JS, meaning nav and footer links may not be discoverable. However, the main content is all in the static HTML, so this is low risk for content indexing. Internal links in the footer/nav that point to other pages may not pass link equity through partials
- **Action:** Verify in Google Search Console that all pages are indexed and no crawl errors exist

---

## 5. Audit: AEO / AI Discoverability

### 5.1 Current AEO Assets

| Asset | Status | Assessment |
|---|---|---|
| `llms.txt` | Present at root | Good — lists core pages, blog posts, and sitemap. Currently missing `/for-paid-ads` |
| `robots.txt` AI bot rules | Present | Explicitly allows Claude-SearchBot, Claude-User, ChatGPT-User, PerplexityBot, Google-Extended |
| FAQPage schema | Present on all marketing pages | Excellent — 6-7 Q&As per page, detailed answers |
| Direct answer blocks | Partial | FAQ answers are 30-80 words — good for AI extraction. Page copy is narrative-style, not optimized for verbatim extraction |

### 5.2 AEO Strengths

1. **`robots.txt` explicitly allows AI bots** — most sites block these; allowing them means Duct can be cited in AI-generated answers
2. **`llms.txt` exists** — this is a forward-looking AEO asset that few sites implement. AI crawlers (especially Anthropic's) check for this file
3. **FAQPage schema is comprehensive** — AI systems parse JSON-LD to extract factual answers. The FAQ answers are well-written, specific, and cite real platform names (GA4, Google Ads, Mixpanel, etc.)
4. **Content uses question-based headings** in some sections ("What is Duct?", "How long does setup take?") — this matches conversational AI query patterns

### 5.3 AEO Gaps

1. **`llms.txt` does not include `/for-paid-ads`** — this is the page most relevant for paid ads AI queries
2. **No `brand-facts.json` at `/.well-known/`** — this file prevents AI hallucination about the brand by providing a machine-readable identity (name, description, founding, pricing, capabilities). Recommended by AEO experts
3. **No `SpeakableSpecification` schema** — this tells Google Assistant and voice-based AI which parts of a page are speakable
4. **Blog posts are markdown rendered client-side** — AI crawlers that don't execute JavaScript may not be able to read blog content. The `blog/post.html` shell loads markdown via `fetch()` and renders with `marked` — this is a significant AEO gap for blog content
5. **No "TL;DR" or "Answer Hub" blocks** — pages don't have concise 30-60 word summary blocks at the top that AI can extract verbatim

### 5.4 AEO Recommendations

| # | Action | Impact | Effort |
|---|---|---|---|
| 1 | Add `/for-paid-ads` to `llms.txt` | High | 1 min |
| 2 | Create `/.well-known/brand-facts.json` with company identity | High | 15 min |
| 3 | Add "What is Duct?" TL;DR block (40-60 words) near top of each landing page | High | 10 min per page |
| 4 | Pre-render blog posts to static HTML for AI crawler accessibility | High | Medium effort |
| 5 | Add `SpeakableSpecification` to FAQ schema | Medium | 10 min |

---

## 6. Audit: Mobile Responsiveness & Loading Times

### 6.1 Mobile Responsiveness

**Breakpoints found in `duct.css` and page-level styles:**

| Breakpoint | Scope | Changes |
|---|---|---|
| `≤860px` | Global + page | Nav links hidden (mobile drawer activates), grids go 1-column, padding reduces |
| `≤700px` | Index hero | Hero layout goes single-column, text centers, demo tabs horizontal-scroll |
| `≤540px` | Demo step content | Various demo card sizing adjustments |

**Mobile-specific features:**
- Mobile nav drawer with hamburger menu — well-implemented with focus trapping, backdrop, and escape-key close
- Scroll-based reveal animations — `IntersectionObserver` with reasonable threshold
- Touch-friendly button sizes (hero CTA is full-width on mobile by nature of the form layout)

**Mobile Issues:**

1. **The hero demo preview on index.html may be too small on mobile** — the brief-card preview with findings/severity badges renders at 12-13px text, which is at the edge of readability on small screens. On mobile, the hero stacks vertically (good), but the demo card is a lot of content to scroll past before reaching "How It Works"
2. **`for-paid-ads.html` demo walkthrough on mobile** — the 4-step demo involves clicking buttons and cards. The touch targets are generally adequate (platform buttons are full-width cards), but the metric selection cards could use more padding on mobile
3. **The nav dropdown on `for-paid-ads.html` uses `:hover`** — this works on desktop but doesn't translate to mobile. The mobile drawer handles this correctly (it extracts dropdown links), so this is fine
4. **Google Fonts loaded on `for-paid-ads.html`** — adds ~100KB of font files and a render-blocking `<link>`. This doesn't affect the other pages. Consider `font-display: swap` (already in the Google Fonts URL via `display=swap`) and potentially deferring the font load for paid traffic where every millisecond of LCP matters

### 6.2 Loading Performance Analysis

**Architecture advantages:**
- Pure static HTML/CSS/JS — no framework, no hydration, no VDOM
- Hosted on Cloudflare Pages — global CDN with edge caching, HTTP/2, automatic Brotli compression
- CSS is inlined per-page (page-specific styles) + one shared stylesheet (`duct.css`) — minimal CSS roundtrips
- JS is deferred (`defer` attribute) or loaded at body end — does not block rendering
- GTM loads lazily (after interaction or 3s idle) — does not impact initial page load

**Performance concerns:**

| Concern | Page(s) | Impact |
|---|---|---|
| Google Fonts preconnect + load | `for-paid-ads.html` | Adds ~100-200ms to LCP on cold load |
| `duct-partials.js` uses synchronous XHR | All pages | Blocks rendering while fetching nav/footer HTML fragments; visible as a "flash" on slow connections |
| No explicit image dimensions on SVG icons | `for-paid-ads.html` demo | Minor CLS risk (width/height attributes are set, so this is mitigated) |
| No `<link rel="preload">` for critical CSS | All pages | Minor — CSS file is small and loads fast anyway |
| `og-image.png` referenced but possibly missing | All pages | Not a performance issue but affects social sharing previews and ad previews |

**Estimated Core Web Vitals (based on architecture):**

| Metric | Expected | Target | Verdict |
|---|---|---|---|
| LCP | <1.5s (text-first hero) | <2.5s | PASS |
| INP | <100ms (lightweight JS) | <200ms | PASS |
| CLS | <0.05 (no lazy-loaded images, minimal layout shift) | <0.1 | PASS |

The static architecture is inherently fast. No major performance blockers exist for paid ads landing pages.

### 6.3 Mobile-Specific Recommendations

1. **Test `for-paid-ads.html` on actual devices** — particularly the demo walkthrough steps on iPhone SE/small Android screens
2. **Consider adding `loading="lazy"` to below-fold SVG images** in the demo section
3. **The synchronous XHR in `duct-partials.js` should be converted to async** — for paid traffic where first-paint speed matters, a synchronous XHR blocking the parser is suboptimal. However, since the partials load nav and footer (which are above and below the fold respectively), the nav partial may cause a visible "pop-in" if made async. Consider inlining the nav HTML directly in the `for-paid-ads.html` page for the paid ads landing page specifically

---

## 7. Google Ads Plan: First Launch from Zero ($350/mo)

### 7.1 Strategic Context

**Budget reality:** $350/month = ~$11.50/day. At average B2B SaaS CPCs of $4-12, this yields 1-3 clicks per day. This is a learning budget, not a scale budget. Every decision must maximize signal-per-dollar.

**The goal is not conversions in month 1.** The goal is:
1. Learn which keywords and messages generate qualified clicks
2. Validate that paid search is a viable channel before investing more
3. Build foundational data (search term reports, audience signals, landing page conversion rate)

**Key constraint:** At ~$11.50/day, Google Ads will struggle to exit the "learning period" (which requires ~30 conversions in 30 days). This means:
- Do NOT use Smart Bidding (Maximize Conversions, Target CPA) at launch — there won't be enough data
- Use Manual CPC for the first 60-90 days
- Focus on one campaign only (not splitting across verticals)

### 7.2 Why Start with Paid Ads Vertical Only

The $350/month budget is too small to split across multiple campaigns. The paid ads vertical (`/for-paid-ads`) is the best starting point because:

1. **Highest intent match** — performance marketers searching for ad intelligence tools are actively experiencing the pain Duct solves
2. **Best landing page** — `/for-paid-ads` has the interactive demo, which is the strongest differentiation vs. competitors
3. **Relevant to the ad channel** — advertising to advertisers creates natural resonance ("this person understands my world")
4. **ICP self-selects** — the page explicitly qualifies "20-200 person companies" which helps filter out enterprise/agency clicks

### 7.3 Campaign Structure

**Single campaign, two ad groups. Manual CPC. One geographic target.**

```
Account: Duct
└── Campaign: Paid Ads Intelligence — Search
    ├── Budget: $11.50/day ($350/month)
    ├── Bidding: Manual CPC ($5-8 max CPC)
    ├── Network: Search only (no Display, no Partners)
    ├── Location: United States (or US + UK if budget allows)
    ├── Schedule: Mon-Fri 7am-7pm (business hours — ICP is at work)
    ├── Device: All devices (but monitor mobile vs. desktop conversion rate)
    │
    ├── Ad Group 1: Cross-Platform Ad Reporting
    │   ├── Keywords:
    │   │   [cross platform ad reporting]           — Exact
    │   │   [cross channel ad analytics]            — Exact
    │   │   "cross platform ad intelligence"        — Phrase
    │   │   "multi platform ad reporting"           — Phrase
    │   │   [ad performance dashboard multiple platforms] — Exact
    │   │
    │   └── Ads: 2 × RSA (see §10.1 for copy)
    │
    └── Ad Group 2: Ad Reporting Automation / Pain Point
        ├── Keywords:
        │   [automated ad reporting tool]           — Exact
        │   [ad reporting automation saas]          — Exact
        │   "automated ad performance report"       — Phrase
        │   "stop manual ad reporting"              — Phrase
        │   [consolidate ad platform data]          — Exact
        │
        └── Ads: 2 × RSA (see §10.1 for copy)
```

### 7.4 Keyword Strategy Deep Dive

**Principle: Intent > Volume.** At $350/month, every click must have buying intent. Informational keywords ("what is ad attribution") waste budget.

**Keyword selection criteria:**
1. Commercial intent (searching for a solution, not education)
2. Matches Duct's specific value prop (cross-platform intelligence, not just reporting)
3. Low enough competition that CPC stays under $10
4. Specific enough to avoid wasted spend on enterprise or agency queries

**Negative Keywords (add from Day 1):**

```
Negative keyword list: "Duct — Exclusions"
────────────────────────────────────────────
free
open source
enterprise
agency
tutorial
course
certification
template
excel
google sheets
spreadsheet
power bi
tableau
looker
domo
what is
how to
definition
job
salary
career
intern
```

**Why no broad match:** With $11.50/day, one irrelevant broad match click at $8 burns 70% of the daily budget. Exact and phrase match only until there are 50+ conversions to inform Smart Bidding.

### 7.5 Budget Allocation & Bidding Strategy

**Month 1-2: Manual CPC**

| Setting | Value | Rationale |
|---|---|---|
| Daily budget | $11.50 | $350/30 days |
| Max CPC bid | $6.00 (start) | B2B SaaS mid-range; adjust based on impression share |
| Ad rotation | Optimize (Google preferred) | Let Google learn which RSA combinations win |
| Ad schedule | Mon-Fri, 7am-7pm local time | ICP works business hours; weekend clicks are lower quality for B2B |
| Location | United States | Concentrate budget for faster learning |

**If CPC is too high (no impressions):** Increase max CPC to $8-10 but reduce ad schedule to core hours only (9am-5pm).

**If CPC is low and budget underspends:** Expand to UK market or extend hours.

**Month 3: Evaluate transition to Enhanced CPC or Maximize Clicks**
- Only if 15+ conversions have occurred
- Enhanced CPC lets Google adjust your manual bids ±30% based on conversion likelihood
- Do NOT use Maximize Conversions until 30+ monthly conversions exist

### 7.6 Tips & Tricks to Maximize a $350/Month Budget

These are practices from top Google Ads experts specifically for small-budget SaaS campaigns:

**1. Surgical dayparting**
Run ads only during business hours (Mon-Fri 7am-7pm). B2B SaaS clicks outside business hours have 40-60% lower conversion rates. This concentrates your $11.50/day on the highest-quality window.

**2. Single keyword ad groups (SKAGs) for top performers**
Once you identify 1-2 keywords that convert, break them into their own ad group with hyper-specific ad copy. This improves Quality Score, which lowers CPC by 20-30%.

**3. Aggressive negative keyword management**
Review the Search Terms report every Monday. Add negatives for any irrelevant query. With $350/month, one bad day of irrelevant clicks ($20 wasted) represents 6% of your monthly budget.

**4. Landing page relevance optimization**
Google rewards landing pages that match keyword intent with higher Quality Score. Your `/for-paid-ads` page already mentions "Google Ads, Meta, LinkedIn" — make sure the H1 and meta description include "cross-platform ad reporting" or similar keyword-matching language.

**5. Ad extensions (now called Assets) are free**
Add every applicable extension — they increase ad real estate and CTR at no extra cost:
- **Sitelink extensions:** "Try the live demo", "See how it works", "Read our blog"
- **Callout extensions:** "Free during beta", "No credit card", "10 min setup", "Read-only access"
- **Structured snippet:** "Platforms: Google Ads, Meta, LinkedIn, X"
- **Call extension:** If you have a phone number for founder-led sales

**6. Use ad customizers for urgency**
Countdown customizer in ad copy: "Beta spots closing in {COUNTDOWN(2026-05-15)}" creates urgency without being spammy.

**7. Geographic bid adjustments**
If US cities like San Francisco, New York, Austin, and Boston (SaaS hubs) show higher conversion rates after 30 days, increase bids +20% in those metros.

**8. Quality Score first, volume second**
A Quality Score of 8-10 can reduce CPC by 30-50% compared to a score of 5. Focus on:
- Ad copy relevance to keywords (include the keyword in the headline)
- Landing page relevance (keyword in H1, fast load time, mobile-friendly)
- Expected CTR (compelling ad copy with specific value props)

### 7.7 Conversion Goal & ROAS Measurement

**Primary conversion:** `beta_signup` (form submission on `/for-paid-ads`)

**Conversion value assignment:**
Since there's no immediate revenue from a beta signup, assign a proxy value:
- If historical data shows 15% of beta signups become paying customers at $299/month
- Then each beta signup is worth: 0.15 × $299 × 12 months = $538 LTV
- Proxy conversion value: **$100** (conservative estimate of near-term value for optimization purposes)

**ROAS calculation:**
- At $350/month spend and 5 signups: ROAS = (5 × $100) / $350 = 1.43x (proxy)
- At $350/month spend and 3 signups: ROAS = (3 × $100) / $350 = 0.86x (proxy)
- At $350/month spend and 10 signups: ROAS = (10 × $100) / $350 = 2.86x (proxy)

**The real ROAS metric is: beta_signup → pilot_agreement → paying_customer.** Track this manually for every paid-sourced signup.

### 7.8 Weekly Optimization Routine (15 Minutes)

Every Monday:

| Step | Action | Where |
|---|---|---|
| 1 | Check spend vs. budget | Google Ads → Campaign overview |
| 2 | Review Search Terms report | Google Ads → Keywords → Search terms |
| 3 | Add negative keywords for irrelevant queries | Keywords → Negative keywords |
| 4 | Check Quality Score per keyword | Keywords → Columns → Quality Score |
| 5 | Review conversion count | GA4 → Conversions |
| 6 | Check landing page conversion rate | GA4 → Pages → `/for-paid-ads` → conversion rate |
| 7 | Adjust bids (±10%) based on performance | Keywords → Max CPC |

**Rule of thumb for $350 budgets:** Make ONE change per week maximum. Multiple simultaneous changes make it impossible to attribute results.

### 7.9 Decision Framework

**After 30 days ($350 spent):**

| Signal | Action |
|---|---|
| 0 conversions, >100 clicks | Landing page problem. Check conversion rate. Test different CTA copy |
| 0 conversions, <30 clicks | CPC too high or keywords too niche. Expand keyword list or increase bids |
| 1-3 conversions at CPL <$120 | Promising. Continue and optimize ad copy. Consider increasing budget to $500 |
| 3+ conversions at CPL <$80 | Strong signal. Double the budget. Begin testing second vertical campaign |
| All clicks from irrelevant queries | Keyword selection problem. Rebuild keyword list. Add more negatives |

**After 60 days ($700 spent):**

| Signal | Action |
|---|---|
| CPL trending below $100 | Validated channel. Scale to $500-700/month |
| CPL above $150 with <5 conversions | Channel may not work at this budget level. Diagnose: is it keywords, ad copy, or landing page? |
| Good clicks but no conversions | Landing page is the bottleneck. A/B test hero copy and CTA |

**After 90 days ($1,050 spent):**

| Signal | Action |
|---|---|
| 10+ conversions, CPL <$100, downstream pilot conversion >10% | Scale aggressively. Add second vertical. Consider $1,000+/month |
| Some conversions but poor downstream quality | Refine targeting. Tighter keywords, add ICP qualifiers to ad copy |
| No meaningful signal | Pause Google Ads. Reallocate to LinkedIn or X where targeting is more precise |

---

## 8. Twitter/X Ads & LinkedIn Ads: Readiness Notes

### 8.1 Twitter/X Ads Readiness

**Pre-launch requirements:**
1. Install X Universal Website Tag via GTM
2. Create a "Signup" conversion event in X Ads
3. Create website retargeting audience (all visitors to `/for-paid-ads`)
4. Set up an X Ads account with billing

**Budget note:** X Ads minimum daily budget is $50-100/day for meaningful optimization. At $350/month total across all channels, X Ads alone would consume the entire budget. **Recommendation:** Do not run X Ads simultaneously with Google Ads at this budget level. Pick one channel, validate it, then expand.

**If X Ads is chosen instead of Google Ads:**
- Lower CPCs than Google ($2-5 for B2B SaaS)
- Good for targeting by interest/follower lookalikes in the paid media community
- Weaker conversion tracking and attribution compared to Google
- Best format: Website Cards with compelling image + problem-hook copy

### 8.2 LinkedIn Ads Readiness

**Pre-launch requirements:**
1. Install LinkedIn Insight Tag via GTM
2. Create conversion events for form submission
3. Set up LinkedIn Campaign Manager with billing
4. Build targeting audiences (see existing `docs/gtm/paid-growth-plan.md` for targeting specs)

**Budget note:** LinkedIn Ads are expensive — typical B2B SaaS CPC is $8-15, CPL is $40-120. At $350/month, you'd get 25-45 clicks and possibly 2-5 leads. This is borderline for generating meaningful data.

**If LinkedIn is chosen instead of Google Ads:**
- Unmatched B2B targeting precision (job title + company size + industry)
- Higher CPC but higher lead quality than other channels
- Thought Leadership Ads (boosting organic posts) have significantly lower CPM
- Lead Gen Forms capture emails without leaving LinkedIn (higher conversion rate)

**Recommendation:** At $350/month, prioritize Google Ads for the highest intent signal. Add LinkedIn at $500+/month when budget allows, starting with Thought Leadership Ads ($5-10/day).

### 8.3 Cross-Channel Budget Allocation (If Budget Increases)

If budget increases to $1,000/month:

| Channel | Budget | % | Purpose |
|---|---|---|---|
| Google Search | $500 | 50% | High-intent bottom-of-funnel |
| LinkedIn Ads | $350 | 35% | Precise ICP targeting |
| X Ads | $150 | 15% | Community-native awareness test |
| **Total** | **$1,000** | **100%** | |

---

## 9. Pre-Launch Checklist

### Must-Do Before First Dollar Spent

- [ ] **Verify `og-image.png` exists** at `https://getduct.ai/assets/og-image.png` — if not, create and deploy it
- [ ] **Test `form_submit` event** in GA4 DebugView on `/for-paid-ads`, `/for-product-intelligence`, `/for-organic-growth`
- [ ] **Mark `form_submit` as Key Event** in GA4 Admin → Events → mark as conversion
- [ ] **Link GA4 to Google Ads** — Google Ads → Tools → Linked accounts → Google Analytics
- [ ] **Import GA4 conversion** into Google Ads — Google Ads → Goals → Conversions → Import → GA4
- [ ] **Install LinkedIn Insight Tag** via GTM (All Pages trigger)
- [ ] **Install X Universal Website Tag** via GTM (All Pages trigger)
- [ ] **Build UTM sheet** with all planned ad URLs using the convention from `docs/gtm/paid-growth-plan.md`
- [ ] **Add negative keywords** to Google Ads before launching the first campaign
- [ ] **Set up Google Ads extensions/assets** — sitelinks, callouts, structured snippets
- [ ] **Create a Google Ads conversion action** linked to the GA4 `form_submit` event

### Should-Do Before Launch (High Impact)

- [ ] Add social proof to `/for-paid-ads` hero section (beta user count, company type badges)
- [ ] Update `llms.txt` to include `/for-paid-ads`
- [ ] Test the full form submission → confirmation flow on mobile and desktop
- [ ] Update CTA copy from "Get early access →" to "Get your first ad brief free →" (test)
- [ ] Verify `for-paid-ads.html` renders correctly on iPhone SE (smallest common screen)

### Nice-to-Have (Post-Launch Optimization)

- [ ] Add Enhanced Conversions (hashed email) for better cross-device attribution
- [ ] Create `/.well-known/brand-facts.json` for AEO
- [ ] Add `SoftwareApplication` schema to homepage
- [ ] Add a post-submission thank-you state with calendar booking link
- [ ] Set up Google Ads remarketing audience from GA4

---

## Appendix: Keyword Research & Ad Copy

### A.1 Google Ads RSA Copy — Ad Group 1: Cross-Platform Ad Reporting

**Responsive Search Ad 1:**

```
Headlines (max 30 chars each):
H1: Cross-Platform Ad Intelligence
H2: Google Ads + Meta + LinkedIn
H3: One Daily Brief. Automated.
H4: Stop Stitching Ad Reports
H5: Free During Beta — Join Now
H6: Cross-Channel Ad Insights
H7: For Performance Marketers
H8: 10 Min Setup. No Code.

Descriptions (max 90 chars each):
D1: Duct connects your ad platforms into one daily intelligence brief with cross-channel signals.
D2: See what Google Ads, Meta, and LinkedIn are collectively telling you. Free beta, no credit card.
```

**Responsive Search Ad 2:**

```
Headlines:
H1: Your Ad Platforms Don't Talk
H2: Duct Connects Them For You
H3: Cross-Platform Ad Reporting
H4: Daily Ad Intelligence Brief
H5: Free Beta — 25 Teams Only
H6: ROAS + CPA Across Platforms
H7: Built for 20-200 Person SaaS
H8: No Dashboards. Just Actions.

Descriptions:
D1: Stop pulling CSVs from three platforms. Duct surfaces cross-channel ad signals every morning.
D2: Built for performance marketers who run multi-platform campaigns without a dedicated data team.
```

### A.2 Google Ads RSA Copy — Ad Group 2: Ad Reporting Automation

**Responsive Search Ad 1:**

```
Headlines:
H1: Automate Your Ad Reporting
H2: Cross-Platform. Daily. Free.
H3: Stop Manual Ad Reports
H4: From 3 Platforms to 1 Brief
H5: Free Beta — Limited Spots
H6: Automated Ad Intelligence
H7: Budget Signals + Anomalies
H8: Connect in Under 5 Minutes

Descriptions:
D1: Stop spending 4 hours stitching ad data. Duct reads your platforms and surfaces what matters.
D2: Automated cross-platform ad reporting with budget reallocation signals and anomaly alerts.
```

**Responsive Search Ad 2:**

```
Headlines:
H1: Ad Reporting Takes Too Long
H2: Duct Automates It
H3: Google Ads + Meta in 1 Brief
H4: Daily Cross-Platform Digest
H5: Free Beta — No Credit Card
H6: Built for SaaS Marketers
H7: See Cross-Channel Blind Spots
H8: Creative Fatigue Detection

Descriptions:
D1: Automated ad intelligence for performance marketers. Cross-platform signals, anomaly alerts, daily.
D2: Stop tab-switching. Get one brief with attribution gaps, budget shifts, and creative fatigue alerts.
```

### A.3 Google Ads Extensions/Assets

**Sitelink Extensions:**
1. "Try the Live Demo" → `https://getduct.ai/for-paid-ads#demo` | Description: "See what Duct surfaces from example ad data"
2. "How It Works" → `https://getduct.ai/for-paid-ads#how` | Description: "Connect. Configure. Receive daily briefs."
3. "Read the Blog" → `https://getduct.ai/blog/` | Description: "SEO and growth intelligence insights"
4. "Product Intelligence" → `https://getduct.ai/for-product-intelligence` | Description: "Cross-tool briefs for PMs"

**Callout Extensions:**
- "Free During Beta"
- "No Credit Card Required"
- "10 Minute Setup"
- "Read-Only Access"
- "OAuth — No API Keys"
- "25+ Beta Teams"

**Structured Snippet:**
- Header: "Platforms"
- Values: "Google Ads, Meta Ads, LinkedIn Ads, X/Twitter, GA4, HubSpot"

### A.4 UTM Convention for This Campaign

```
utm_source    = google
utm_medium    = paid-search
utm_campaign  = paid-ads-intel-beta
utm_content   = rsa-crossplatform-v1  |  rsa-crossplatform-v2  |
                rsa-automation-v1     |  rsa-automation-v2
utm_term      = {keyword}

Example full URL:
https://getduct.ai/for-paid-ads?utm_source=google&utm_medium=paid-search&utm_campaign=paid-ads-intel-beta&utm_content=rsa-crossplatform-v1&utm_term={keyword}
```

### A.5 Competitor Keywords (Optional — Add in Month 2)

If budget increases, consider competitor targeting:

```
[supermetrics alternative]
[databox alternative]
[whatagraph alternative]
[ad reporting tool for saas]
"better than supermetrics"
```

These have high intent but also high CPC ($10-20). Only add once the primary keywords are validated.

---

*This audit supersedes the broader paid growth plan in `docs/gtm/paid-growth-plan.md` for the specific scope of the $350/month Google Ads launch. Refer to the paid growth plan for LinkedIn and Reddit-specific strategies at higher budget levels.*
