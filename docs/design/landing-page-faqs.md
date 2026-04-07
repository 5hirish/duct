# Landing Page FAQ Sections — Content & Implementation Spec

> **Purpose**: Add FAQ sections to all three landing pages for SEO, AIO/AEO optimization, and user value.
> **Status**: Ready for implementation
> **Date**: 2026-04-07

## Context

The three landing pages (`for-paid-ads.html`, `for-product-intelligence.html`, `for-organic-growth.html`) have no FAQ sections. Adding FAQs serves three goals:

1. **SEO** — FAQ schema (FAQPage JSON-LD) improves topical relevance and can earn rich results
2. **AIO/AEO** — Well-structured Q&A pairs (40-60 word answers, self-contained, direct lead sentence) increase citation likelihood by AI answer engines (ChatGPT, Perplexity, Google AI Overviews) by 40-60%
3. **User value** — Clears buying objections (security, pricing, setup) right before the final CTA

### Research-Backed Formatting Rules Applied

- 6 questions per page (sweet spot of 5-7)
- Answers lead with a direct 40-60 word paragraph (featured snippet format)
- Each answer is self-contained (no "as mentioned above" — AI engines extract individual pairs)
- Questions use natural search phrasing ("What is...", "How does...", "Does Duct...")
- Mix of question types: definitional, integration, security, differentiation, pricing, outcome
- FAQPage JSON-LD schema added separately from existing WebPage schema

Sources:
- [Seize Marketing Agency — FAQs in SEO 2026](https://seizemarketingagency.com/faqs-in-seo/)
- [Frase.io — AEO Complete Guide 2026](https://www.frase.io/blog/what-is-answer-engine-optimization-the-complete-guide-to-getting-cited-by-ai)
- [AirOps — Answer Engine Optimization 2026](https://www.airops.com/blog/aeo-answer-engine-optimization)
- [SemAI — Why Structure and FAQs Matter for AEO](https://semai.ai/blogs/why-structure-and-faqs-matter-for-answer-engine-optimization/)
- [Google Developers — FAQPage Structured Data](https://developers.google.com/search/docs/appearance/structured-data/faqpage)

---

## FAQ Content

### Page 1: `site/for-paid-ads.html`

**Q1: What is Duct for paid ads?**
Duct is a cross-platform ad intelligence tool that connects Google Ads, Meta, LinkedIn, and Twitter into one daily brief. Instead of pulling CSVs from each platform, you get cross-platform correlations, creative fatigue alerts, and budget reallocation signals delivered every morning. Built for performance marketers at 20–200 person SaaS companies who run multi-platform campaigns without a data team.

**Q2: How long does it take to connect my ad platforms to Duct?**
Under five minutes. Duct uses one-click OAuth to connect Google Ads, Meta, LinkedIn, Twitter, GA4, HubSpot, Klaviyo, and TikTok Ads. No API keys to configure and no developer time required. You select your platforms, authorize read-only access, and your first daily ad intelligence brief arrives the next morning.

**Q3: Does Duct modify anything in my ad accounts?**
No. Duct operates in strict read-only mode. It connects through official platform APIs to read your performance data but never creates, modifies, or deletes campaigns, budgets, or creatives. OAuth tokens are stored server-side, all data in transit is encrypted via TLS, and no data is stored without your explicit approval.

**Q4: How is Duct different from building cross-platform ad reports in spreadsheets or dashboards?**
Spreadsheets and dashboards show you what happened — Duct tells you what to do about it. Instead of manually pulling CSVs from three platforms and merging them weekly, Duct automatically correlates data across Google Ads, Meta, and LinkedIn to surface creative fatigue, budget reallocation opportunities, and cross-channel attribution gaps that static reports miss entirely.

**Q5: How much does Duct for paid ads cost?**
Duct is free during the beta period with no credit card required. We are onboarding the first 25 teams personally, and every team gets a setup call and direct access to the founders. Paid plans will be announced after beta, and beta users will be grandfathered into early pricing.

**Q6: What kind of insights does the daily ad intelligence brief surface?**
Each morning, Duct delivers cross-platform attribution analysis, creative fatigue alerts flagging ads losing effectiveness, budget reallocation signals showing where to shift spend, and anomaly detection for unexpected metric changes. It can spot when Google ROAS rises while Meta CPA spikes simultaneously — a cross-channel pattern no single-platform dashboard reveals.

---

### Page 2: `site/for-product-intelligence.html`

**Q1: What is Duct for product intelligence?**
Duct is a cross-tool product intelligence platform that connects Mixpanel, Intercom, Linear, FullStory, and the rest of your stack into one daily PM briefing. It surfaces cross-tool correlations, detects anomalies, and lets you ask plain-English questions like "Why did DAU drop Thursday?" without writing SQL or building dashboards. Designed for growth PMs at 20–200 person SaaS companies.

**Q2: What tools does Duct connect to, and how hard is setup?**
Duct connects to Mixpanel, Amplitude, Intercom, Linear, FullStory, Jira, HubSpot, Segment, and Slack through one-click OAuth. Setup takes under five minutes with no API keys or engineering support needed. Duct reads your data in strict read-only mode, and your first cross-tool PM briefing arrives the next morning, already correlated around your north star metric.

**Q3: Is my product data safe with Duct?**
Yes. Duct uses read-only API access through official OAuth integrations — it never writes to, modifies, or deletes anything in Mixpanel, Intercom, Linear, or any connected tool. All data in transit is encrypted via TLS, OAuth tokens are stored server-side and never exposed to the browser, and no data is stored without your explicit approval.

**Q4: How is Duct different from using Mixpanel or Amplitude dashboards directly?**
Single-tool dashboards show you metrics in isolation. Duct connects your analytics, support, engineering, and revenue tools to surface correlations between them. When a feature launch in Linear coincides with a spike in Intercom tickets and a drop in Mixpanel retention, Duct connects those signals automatically — no dashboard switching, no manual correlation, no SQL.

**Q5: Does Duct for product intelligence cost anything?**
Duct is completely free during the beta period. No credit card, no usage limits. We are onboarding the first 25 product teams personally — each team gets a hands-on setup call where we tune your daily brief around your north star metric. Paid pricing will be published after beta, with early adopters receiving grandfathered rates.

**Q6: What does the daily PM briefing actually contain?**
The daily briefing surfaces what changed across your product stack overnight: anomalies in activation or retention from Mixpanel, spikes in support volume from Intercom, blocked tickets in Linear, and session replay patterns from FullStory. Duct cross-correlates these signals and delivers plain-English explanations of what is blocking adoption and what to ship next.

---

### Page 3: `site/for-organic-growth.html`

**Q1: What is Duct for organic growth?**
Duct is a cross-tool organic growth platform that connects Google Search Console, Ahrefs, Semrush, GA4, and your content tools into one weekly action brief. Instead of checking five dashboards for ranking changes, it tells you exactly which pages to update, which keywords to target, and which content to publish next. Built for growth marketers at 20–200 person SaaS companies.

**Q2: How does Duct connect to my SEO and content tools?**
Duct connects to Google Search Console, Ahrefs, GA4, Semrush, Notion, LinkedIn Analytics, HubSpot, Slack, and Mixpanel through one-click OAuth. No API keys, no developer time, and setup takes under five minutes. Duct reads your data in strict read-only mode and delivers your first prioritized organic action brief within a day of connecting.

**Q3: Does Duct store my SEO data or share it with third parties?**
No. Duct accesses your data through official APIs in read-only mode and never stores data without your explicit approval. It does not share your keyword rankings, traffic data, or content performance with any third party. All data in transit is encrypted via TLS, and OAuth tokens are stored server-side, never exposed to the browser.

**Q4: How is Duct different from using Ahrefs or Search Console directly?**
Individual SEO tools show you data in isolation — rank changes in one tab, traffic in another, content gaps in a third. Duct correlates signals across all of them to surface prioritized actions. When a keyword cluster gains impressions in Search Console while Ahrefs shows a competitor's page weakening and GA4 shows rising conversions, Duct connects those dots and tells you what to publish.

**Q5: What does Duct for organic growth cost?**
Duct is free during the beta period with no credit card required. We are onboarding the first 25 growth teams with hands-on setup — connecting your stack, tuning the weekly brief around your funnel, and helping your team act on the first set of recommendations. Paid plans will be announced after beta with early adopter pricing locked in.

**Q6: What kind of actions does the weekly organic brief recommend?**
Each week, Duct delivers prioritized actions like pages losing rankings that need updating, keyword gaps where competitors are weakening, content briefs for high-opportunity topics, and traffic anomaly alerts. It cross-references Search Console impression trends with Ahrefs backlink changes and GA4 conversion data to rank actions by projected impact on organic growth.

---

## Implementation Steps

### Step 1: Add FAQ HTML section to each page

Insert a `<!-- FAQ -->` section between the `<!-- STATS -->` and `<!-- CTA -->` comment markers on each page.

- `site/for-paid-ads.html` — insert before `<!-- CTA -->` (line 522)
- `site/for-product-intelligence.html` — insert before `<!-- CTA -->` (line 508)
- `site/for-organic-growth.html` — insert before `<!-- CTA -->` (line 295)

HTML structure uses `<details>`/`<summary>` for native accordion (zero JS, progressive enhancement):

```html
<!-- FAQ -->
<section class="faq" id="faq">
<div class="faq-inner">
  <div class="reveal">
    <p class="tag">FAQ</p>
    <h2>Frequently asked <em>questions</em></h2>
  </div>
  <div class="faq-list reveal">
    <details class="faq-item">
      <summary class="faq-q">Question text here?</summary>
      <p class="faq-a">Answer text here.</p>
    </details>
    <!-- ... 5 more items -->
  </div>
</div>
</section>
```

### Step 2: Add FAQ styles to `site/assets/duct.css`

Since all three pages share the same FAQ styles, add them to the shared stylesheet (same pattern as `.problem`, `.stats`, `.cta` which are already in `duct.css` despite appearing on multiple pages). Styles needed:

- `.faq` section container (padding, background matching page theme)
- `.faq-inner` centered layout (max-width matching other sections)
- `.faq-list` vertical layout with gap
- `.faq-item` with bottom border separator
- `.faq-q` (summary) — font weight, padding, cursor pointer, chevron indicator
- `.faq-a` — body text styling matching existing answer/paragraph patterns
- `details[open]` chevron rotation animation

### Step 3: Add FAQPage JSON-LD schema to each page's `<head>`

Add a second `<script type="application/ld+json">` block (separate from the existing `WebPage` schema) with `@type: FAQPage` containing all 6 Q&A pairs.

### Step 4: Add nav anchor

Add `<a href="#faq">FAQ</a>` to each page's navigation links.

### Critical files to modify

- `site/for-paid-ads.html`
- `site/for-product-intelligence.html`
- `site/for-organic-growth.html`
- `site/assets/duct.css`

### No sitemap changes needed

FAQs are added to existing pages, not new URLs.

## Verification

1. Open each page locally and confirm FAQ section renders between stats and CTA
2. Expand/collapse each `<details>` item — verify native accordion behavior
3. Validate FAQPage JSON-LD with [Google Rich Results Test](https://search.google.com/test/rich-results)
4. Check that FAQ styles are consistent across all three pages
5. Verify `#faq` anchor scroll works from the nav link
