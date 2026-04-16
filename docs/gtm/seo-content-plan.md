# Duct — Master SEO & Content Growth Plan
**Version:** 1.0 — April 2026
**ICP:** Growth PMs and Performance Marketers at 20–200 person SaaS companies without a dedicated data team.
**Execution stack:** Claude for content generation, Claude Code for free tools pages.

> This is not a content calendar. It is a compounding organic growth system. Every piece of content has a specific structural role: it either owns a SERP, feeds authority to a pillar, or converts a reader who is already in market. Nothing gets published without a defined role.

---

## Table of Contents

1. [Strategic Foundation](#1-strategic-foundation)
2. [Cluster Architecture](#2-cluster-architecture)
3. [Existing Content Audit](#3-existing-content-audit)
4. [Free Tools — Build First](#4-free-tools--build-first)
5. [Pillar Page Content Briefs](#5-pillar-page-content-briefs)
6. [Cluster Post Briefs](#6-cluster-post-briefs)
7. [Connector Pages](#7-connector-pages)
8. [Comparison Pages](#8-comparison-pages)
9. [Internal Linking Architecture](#9-internal-linking-architecture)
10. [90-Day Publishing Calendar](#10-90-day-publishing-calendar)
11. [Distribution & Promotion](#11-distribution--promotion)
12. [Measurement Framework](#12-measurement-framework)
13. [Technical SEO Baseline](#13-technical-seo-baseline)
14. [Appendix A: Full Keyword Reference Table](#appendix-a-full-keyword-reference-table)
15. [Appendix B: Post Brief Template](#appendix-b-post-brief-template)
16. [Appendix C: Claude Prompts for Content Generation](#appendix-c-claude-prompts-for-content-generation)

---

## 1. Strategic Foundation

### 1.1 What cluster blogging is and why it works

Cluster blogging (the pillar-cluster model) is a content architecture where one broad, authoritative page (the **pillar**) covers a topic at a high level, and a set of focused **cluster posts** each go deep on a specific subtopic. Every cluster post links back to the pillar; the pillar links out to all cluster posts.

**Why it works:**
- **Topical authority** — Search engines rank sites that demonstrate depth on a subject, not just sites with one good post. A complete cluster signals expertise.
- **Internal PageRank distribution** — The linking structure concentrates authority on the pillar page and ensures cluster posts benefit from it in return.
- **Compounding returns** — Each new cluster post adds to topical authority. Later posts rank faster than earlier ones.
- **Structured conversion path** — Every cluster post has a defined role: attract the reader, establish trust on their specific problem, direct them to the pillar or product page.

The alternative — publishing isolated posts on unrelated topics — produces no compounding effect. Posts stand alone, earn authority alone, and convert inconsistently. Cluster architecture turns a blog into a system.

### 1.2 Why Duct competes on depth, not volume

Duct's ICP — growth marketers and PMs — consume content professionally. They can tell immediately whether a post is written by someone who has actually run an analytics program or by someone summarising what one looks like. Generic content will not convert them.

**The rule:** Do not publish 5 posts per week. Publish 1–2 posts per week that are genuinely better than anything currently ranking for the target keyword. One post ranking position 3 for a high-intent term is worth more than 20 posts ranking nowhere.

The goal in the first 90 days is not traffic volume. It is topical authority in three narrow categories — one per cluster.

### 1.3 The three-cluster strategy

Three pillar pages. Three vertical clusters. Every post belongs to exactly one cluster. No orphan content.

```
Cluster 1: Automated Reporting
  → Pillar: /blog/automated-reporting-guide
  → Converts to: homepage + all vertical pages
  → ICP: broadest — any growth/marketing role drowning in manual reporting

Cluster 2: Product Intelligence
  → Pillar: /blog/product-intelligence-guide
  → Converts to: /for-product-intelligence
  → ICP: Growth PMs at 20–200 person SaaS

Cluster 3: Organic Growth & SEO Intelligence
  → Pillar: /blog/seo-intelligence-guide
  → Converts to: /for-organic-growth
  → ICP: Growth marketers and content/SEO leads
```

**Why three clusters and not two:**
The keyword data from competitor analysis shows Automated Reporting as a standalone category with higher search volume and lower competition than either product or SEO intelligence specifically. It also serves as a top-of-funnel entry point for both other clusters. Build it first.

### 1.4 The content-to-conversion thesis

The blog is a bottom-of-funnel conversion engine dressed as education.

Reader journey: ICP searches for a specific, felt problem → lands on a cluster post that describes their situation precisely → recognises Duct's cross-tool synthesis framing → follows a contextual inline CTA to the beta page.

This works only if the inline CTA is placed at the exact moment the reader's pain is fully articulated — mid-post, right after the problem is named — not at the end, not in a sidebar. Every post in this plan follows this convention.

### 1.5 Duct's content differentiation

Every competitor — Databox, DashThis, Supermetrics, Whatagraph — is forced to write content about dashboards and reporting interfaces. Duct gets to write content about *what to do with the data* — because that's what the product does.

This is a content category none of them can credibly own. Use it on every comparison, every cluster post, every tool page:

> "Dashboards show you what happened. Duct tells you what it means and what to do next."

---

## 2. Cluster Architecture

> All KD values are validated from Ahrefs data. CPC values from Google Keyword Planner. Validate before briefing each post as KDs shift.

### 2.1 Cluster 1 — Automated Reporting

**Pillar URL:** `/blog/automated-reporting-guide`
**Primary keyword:** `automated reporting tools` — 350 SV, KD 3, $10 CPC
**Converts to:** Homepage (`getduct.ai`) + all vertical pages via sitelinks

| Priority | Post Title | Primary Keyword | SV | KD | CPC |
|---|---|---|---|---|---|
| P1 | The Complete Guide to Automated Marketing Reporting (PILLAR) | `automated reporting tools` | 350 | 3 | $10 |
| P1 | How to Automate Your Weekly Marketing Report | `automated weekly report` | 100 | Low | $1.80 |
| P1 | Automated Reporting Tools — What to Look For (and What to Avoid) | `automated reporting software` | 300 | 9 | $0.60 |
| P1 | How to Connect GA4, HubSpot and Mixpanel Without a Data Team | `connect ga4 hubspot` | 200 | Low | — |
| P2 | Marketing Reporting Without a Dashboard | `marketing reporting tools` | 250 | Low | $3.50 |
| P2 | Automated Report Generation: A Practical Guide | `automated report generation` | 200 | 2 | $4 |
| P2 | What Is Automated Analytics? (And What It Isn't) | `automated analytics` | 200 | 1 | $2 |
| P3 | The Weekly Marketing Brief: What It Should Contain | `weekly marketing report` | 70 | Low | $3.50 |
| P3 | How to Build an Automated Reporting System Without Engineering | `automated reporting system` | 150 | 9 | $8 |

### 2.2 Cluster 2 — Product Intelligence

**Pillar URL:** `/blog/product-intelligence-guide`
**Primary keyword:** `product intelligence` — Low SV, KD 20–30, category-defining
**Converts to:** `/for-product-intelligence`

| Priority | Post Title | Primary Keyword | SV | KD | CPC |
|---|---|---|---|---|---|
| P1 | The Complete Guide to Product Intelligence for PMs (PILLAR) | `product intelligence` | Low | 20–30 | — |
| P1 | What Is Product Intelligence? (And Why It's Different From Product Analytics) | `product intelligence vs product analytics` | Low | 10–18 | — |
| P1 | Why Your Mixpanel Data Looks Fine But Retention Is Dropping | `mixpanel retention analysis` | Low | 25–35 | — |
| P1 | How to Correlate Ad Performance With Product Retention (Without a Data Team) | `google ads retention correlation` | Low | 12–20 | — |
| P2 | Product Analytics Without a Data Team | `product analytics without sql` | Low | Low | — |
| P2 | How to Build a Weekly SaaS Metrics Digest Without SQL | `saas reporting tools` | 150 | 3 | $10 |
| P2 | The PM's Weekly Data Review: What to Check and What to Skip | `weekly PM metrics review` | Low | 15–22 | — |
| P2 | How to Set Up Cross-Tool Anomaly Alerts for Your Product Stack | `product analytics anomaly detection` | Low | 18–28 | — |
| P2 | Mixpanel vs Amplitude: What Neither Tool Will Tell You | `mixpanel vs amplitude` | 1,200 | 40–55 | — |
| P3 | Linear + Mixpanel: How to Connect Engineering Velocity With Product Outcomes | `linear mixpanel integration` | Low | 8–15 | — |
| P3 | Feature Adoption Rate: How to Measure It Across Mixpanel, Intercom, and GA4 | `feature adoption rate measurement` | Low | 18–28 | — |
| P3 | The Hidden Cost of Manual Data Synthesis for PMs | `PM productivity analytics` | Low | 10–18 | — |

### 2.3 Cluster 3 — Organic Growth & SEO Intelligence

**Pillar URL:** `/blog/seo-intelligence-guide`
**Primary keyword:** `SEO intelligence` — Low SV, KD 25–35, category-defining
**Converts to:** `/for-organic-growth`

| Priority | Post Title | Primary Keyword | SV | KD | CPC |
|---|---|---|---|---|---|
| P1 | The Complete Guide to SEO Intelligence for Growth Teams (PILLAR) | `SEO intelligence` | Low | 25–35 | — |
| P1 | How to Connect Search Console, Ahrefs, and GA4 Without a Spreadsheet | `connect search console and ga4` | Low | 18–25 | — |
| P1 | Why Your Organic Traffic Is Up But Signups Are Flat | `organic traffic not converting` | Low | 22–30 | — |
| P1 | The Weekly SEO Brief: What It Should Contain and How to Automate It | `weekly SEO report template` | Low | 15–22 | — |
| P2 | Content Decay: How to Find It, Prioritise It, and Fix It | `content decay SEO` | Low | 28–38 | — |
| P2 | SEO Metrics That Actually Correlate With Revenue | `SEO metrics that matter` | Low | 25–35 | — |
| P2 | Keyword Gap Analysis Without a Spreadsheet *(existing — update)* | `keyword gap analysis process` | Low | 20–28 | — |
| P2 | Ahrefs vs Search Console vs GA4: Which to Trust When They Disagree | `ahrefs vs search console discrepancy` | Low | 18–28 | — |
| P3 | How to Set Up Automated SEO Alerts That Actually Mean Something | `automated SEO alerts` | Low | 15–20 | — |
| P3 | How to Build an SEO Content Calendar That Actually Gets Used | `SEO content calendar template` | Low | 20–30 | — |

---

## 3. Existing Content Audit

Two posts are live. Neither is linked into a cluster structure. Fix these before publishing anything new — they've been indexed longest and any authority they've accumulated should be directed into the cluster.

### Post 1: "Why Your SEO Metrics Aren't Telling You the Full Story"
**Current URL:** `/blog/posts/why-your-seo-metrics-arent-telling-you-the-full-story`
**Cluster role:** Cluster post — Organic Growth pillar

**Actions required:**
1. Add internal link to SEO pillar page (`/blog/seo-intelligence-guide`) — anchor text: "cross-tool SEO intelligence guide"
2. Add link to "How to Connect Search Console, Ahrefs, and GA4" post when live
3. Expand "What to actually look for" section — replace 4 bullet points with a decision matrix table: Signal → Likely Cause → Action
4. Update meta description: "Impressions up. Signups flat. Here's the cross-tool pattern that explains it — and how to fix it."
5. Add inline CTA immediately after the "What to actually look for" section (peak-pain moment). Keep end-of-post CTA as well.

### Post 2: "Keyword Gap Analysis Without a Spreadsheet"
**Current URL:** `/blog/posts/keyword-gap-analysis-without-a-spreadsheet`
**Cluster role:** Cluster post — Organic Growth pillar

**Actions required:**
1. Expand from ~650 to 1,200–1,500 words. Current post explains *why* gap analysis matters but not *how*. Add: "The 6-step keyword gap process (manual version)" — write for people who don't have Duct yet. This earns the featured snippet and the link.
2. Add prioritisation scoring matrix: Keyword → KD → Search trend → Business relevance → Existing content? → Score → Action
3. Add internal link to SEO pillar page
4. Update frontmatter: change `category` from "Content Strategy" to "SEO"
5. Add inline CTA after "The gap in the gap analysis" section

---

## 4. Free Tools — Build First

Build free tools before blog posts. One tool page with genuine utility outperforms five blog posts in the first 90 days. Tools earn backlinks passively, rank faster due to engagement signals, and convert directly because the visitor is already doing the job Duct automates.

Each tool page ends with a conversion hook. The pattern is always: show the painful manual version → let them use the free tool → "Duct does this automatically, every week, across your full stack."

---

### Tool 1: SaaS Metrics Benchmark Calculator
**URL:** `getduct.ai/tools/saas-metrics-calculator`

**Target keywords:**
- `saas metrics benchmarks` — 150 SV, Low KD, $6 CPC
- `saas metrics calculator` — 100 SV, Low KD
- `b2b saas metrics` — 100 SV, $2.50 CPC
- `key saas metrics` — 100 SV

**Why:** Databox's growth rate calculator drives ~2K monthly visits from a single tool page. SaaS-specific metrics benchmarks have no dominant free tool. You own this category by default.

**What the tool does:**
- Input: MRR, monthly churn rate (%), CAC, LTV, trial-to-paid rate (%), WAU
- Output: Colour-coded benchmark scores vs SaaS industry averages (green = good / amber = needs work / red = critical)
- Show context: "Your churn is 4.2% — median for your MRR band is 2.8%. Here's what that means for LTV."

**Conversion hook:**
> "Want these metrics tracked automatically every week and delivered to your inbox? That's Duct."
**CTA:** "Get your free weekly SaaS metrics brief →" → `getduct.ai`

**Claude Code prompt:**
> Build a single-page React app: SaaS Metrics Benchmark Calculator. Inputs: MRR (€/$), monthly churn rate (%), CAC (€/$), LTV (€/$), trial-to-paid rate (%), WAU. Output: colour-coded benchmark scores vs industry averages from standard SaaS benchmarks (OpenView, ChartMogul). Show a score per metric: green = good, amber = needs work, red = critical. Include a brief explanation of why each metric matters. Clean minimal design. Output reads like an intelligence brief not a dashboard. End with a CTA card: "Want these tracked automatically each week? That's Duct." Button links to https://getduct.ai

---

### Tool 2: Weekly Marketing Brief Template Generator
**URL:** `getduct.ai/tools/weekly-brief-template`

**Target keywords:**
- `weekly marketing report template` — 700 SV, Low KD, $2.50 CPC — highest volume in dataset
- `weekly report template` — 700 SV
- `marketing weekly report` — 150 SV
- `weekly kpi report` — 50 SV, $6 CPC

**Why:** DashThis and Databox both rank for template keywords with static pages. An interactive generator that outputs a real customised template is more useful, more shareable, and better as a conversion signal. You outrank static pages with dynamic tools.

**What the tool does:**
- Step 1: User selects role (Growth PM / Performance Marketer / SEO Lead)
- Step 2: Selects tool stack (checkboxes: GA4, Mixpanel, HubSpot, Google Ads, Ahrefs, GSC, Meta Ads, LinkedIn Ads)
- Step 3: Sets north star metric (free text or dropdown)
- Output: Formatted weekly brief template with pre-populated section headers, metric slots, and placeholder insights specific to their tool stack. Copy-to-clipboard button.

**Conversion hook:**
> "This template takes 2–3 hours to fill in manually every week. Duct fills it automatically."
**CTA:** "Get the automated version free during beta →" → `getduct.ai`

**Claude Code prompt:**
> Build a multi-step weekly brief template generator in React. Step 1: role selector (3 options with icons). Step 2: tool stack selector (checkboxes, 8 tools). Step 3: north star metric input (free text). Output: formatted weekly brief template with section headers and metric slots specific to their stack. Add copy-to-clipboard. Add a CTA card at the bottom: "This takes 3 hours manually. Duct does it automatically every week." Button: "Get early access →" linking to https://getduct.ai. Clean, minimal design.

---

### Tool 3: CAC / LTV Calculator
**URL:** `getduct.ai/tools/cac-ltv-calculator`

**Target keywords:**
- `cac ltv ratio` — 400 SV
- `how to calculate ltv` — 300 SV
- `customer acquisition cost calculator` — 200 SV
- `ltv cac ratio saas` — 150 SV, $4 CPC

**Why:** Every growth PM runs this calculation. No dominant free tool owns it for SaaS specifically. Quick build, permanent traffic.

**What the tool does:**
- Input: monthly new customers, total sales + marketing spend, avg revenue per customer, avg customer lifespan (months)
- Output: CAC, LTV, LTV:CAC ratio, payback period, colour-coded health score
- Benchmark: "For SaaS, healthy LTV:CAC is >3:1. Yours is X:1."

**Conversion hook:**
> "Duct tracks your LTV:CAC trend automatically each week and alerts you when it shifts."
**CTA:** "See it in action →" → `getduct.ai`

**Claude Code prompt:**
> Build a React SaaS CAC/LTV calculator. Inputs: monthly new customers, total monthly sales + marketing spend (€/$), average monthly revenue per customer (€/$), average customer lifespan in months. Calculated outputs: CAC, LTV, LTV:CAC ratio, payback period in months. Show each output with a colour-coded health indicator benchmarked against SaaS standards (LTV:CAC: green >3:1, amber 2–3:1, red <2:1 etc.). Include brief explanations. Clean design. End with CTA: "Duct tracks this automatically week over week and alerts you when it shifts." Button links to https://getduct.ai

---

## 5. Pillar Page Content Briefs

Pillar pages are the most important content in the plan. Write these first or simultaneously with the first cluster posts. They serve as the internal link hub for each cluster and rank for category-level keywords.

---

### Pillar 1: The Complete Guide to Automated Marketing Reporting

**URL:** `/blog/automated-reporting-guide`
**Word count:** 2,500–3,500 words
**Primary keywords:** `automated reporting tools` (350 SV, $10 CPC), `automated reporting software` (300 SV), `automated report generation` (200 SV)
**Search intent:** Comprehensive guide — someone who wants to understand and implement automated reporting

**Required sections:**
1. What automated marketing reporting actually means (vs. scheduling a PDF export)
2. Why manual reporting is broken — the 3–4 hour Monday morning problem
3. What belongs in an automated marketing report
4. How to automate each channel: GA4, HubSpot, Google Ads, Mixpanel
5. What to look for in automated reporting tools (evaluation criteria)
6. The difference between automated reporting and automated intelligence (Duct's differentiator)
7. How to set up automated reporting in under 10 minutes
8. What a good automated brief looks like — include a real example brief format (table)

**Inline CTA placement:** After section 6 ("The difference between automated reporting and automated intelligence")
**CTA:** "Most automated reporting tools give you a dashboard. Duct gives you a brief — what changed, why it matters, what to do next. [Get your first automated brief free →](/)"

**Internal links out:** Link to all Cluster 1 supporting posts as they publish. Update this page each time a new cluster post goes live.

---

### Pillar 2: The Complete Guide to Product Intelligence for PMs

**URL:** `/blog/product-intelligence-guide`
**Word count:** 2,500–3,500 words
**Primary keywords:** `product intelligence`, `saas reporting tools` (150 SV, $10 CPC), `saas metrics software` (150 SV, $8 CPC)
**Search intent:** Definitional + comprehensive guide

**Required sections:**
1. What product intelligence means in 2026 — define the category. Product analytics = dashboards showing what users did. Product intelligence = synthesised cross-tool patterns that drive decisions.
2. Why product analytics alone isn't enough — the fragmentation problem. Average PM uses 5–7 tools. Each excellent in isolation. None produces the cross-tool signal.
3. The PM's tool stack and each tool's blind spot — Mixpanel (what users did, not why), GA4 (acquisition, not behaviour depth), Google Ads (spend efficiency, not downstream product impact), Intercom (surface complaints, not retention correlation), Linear (engineering output, not product outcome)
4. The 5 cross-tool product patterns that matter most — (1) Ad spend + feature adoption rate, (2) Retention cohort + NPS by acquisition channel, (3) Engineering velocity + activation rate, (4) Support ticket volume + churn signal, (5) Engagement score + expansion revenue
5. How to build a weekly PM intelligence workflow — the manual version. What to check, in what order, how long it takes.
6. What a good PM brief looks like — include a real example brief format (featured snippet candidate)
7. How to automate cross-tool product synthesis — one section. Manual takes ~3 hours/week; automated delivers the same signal in a Monday brief.
8. The future of product intelligence — dashboards are being replaced by synthesis layers.

**Inline CTA placement:** After section 7
**CTA:** "Get your cross-tool product brief automatically — [join the beta →](/for-product-intelligence)"

---

### Pillar 3: The Complete Guide to SEO Intelligence for Growth Teams

**URL:** `/blog/seo-intelligence-guide`
**Word count:** 2,500–3,500 words
**Primary keywords:** `SEO intelligence`, `cross-tool SEO analytics`, `automated SEO reporting`
**Search intent:** Definitional + comprehensive guide

**Required sections:**
1. What SEO intelligence actually means (vs. basic SEO reporting) — most SEO reporting is lagging indicator tracking. SEO intelligence is pattern detection across tools in real time.
2. The three-layer SEO stack — Visibility (Search Console), Authority (Ahrefs), Conversion (GA4). Specific metrics at each layer.
3. Why cross-tool synthesis is the missing layer — teams optimise each layer independently. Use a concrete example: ranking rising + conversions flat = audience mismatch, not a keyword problem.
4. The 5 most important cross-tool SEO correlations — (1) GSC impressions vs GA4 conversion rate by landing page, (2) Ahrefs position change vs GSC CTR delta, (3) Content publish date vs ranking velocity by cluster, (4) Keyword gap + editorial calendar gap, (5) Backlink velocity vs ranking velocity
5. How to build a weekly SEO intelligence workflow — the manual version. Four steps: pull ranking delta, pull conversion delta, identify divergences, prioritise one action.
6. What a good SEO brief looks like — include a real example brief format (table)
7. The tool stack required — Search Console + Ahrefs + GA4 + content calendar. Note the integration problem: each best-in-class, none talk to each other.
8. How to automate the synthesis — this is where Duct enters. Keep it one section.

**Inline CTA placement:** After section 8
**CTA:** "See how Duct synthesises your SEO stack automatically — [join the beta →](/for-organic-growth)"

---

## 6. Cluster Post Briefs

Key posts expanded with full briefs. Use Appendix B template for remaining posts.

---

### "Why Your Organic Traffic Is Up But Signups Are Flat"
**URL:** `/blog/organic-traffic-not-converting`
**Cluster:** Organic Growth | **Priority:** P1
**Primary keyword:** `organic traffic not converting` — KD 22–30
**Word count:** 1,500 words

**Why this post:** Anyone searching this is experiencing the exact pain Duct solves. Conversion rate from this post to beta sign-up should be among the highest in the cluster.

**Required sections:**
1. The scenario: organic up, signups flat — why this is more common than people admit
2. The four most common causes (audience mismatch, keyword intent mismatch, CTA friction, attribution gap)
3. How to diagnose which one you have (step by step, using GSC + GA4)
4. The cross-tool pattern that reveals it — this is where you need to read all three tools simultaneously

**Inline CTA:** After section 4, before the fix section
**CTA:** "This is the exact pattern Duct is built to surface automatically. [See it in action →](/for-organic-growth)"

---

### "Mixpanel vs Amplitude: What Neither Tool Will Tell You"
**URL:** `/blog/mixpanel-vs-amplitude`
**Cluster:** Product Intelligence | **Priority:** P2
**Primary keyword:** `mixpanel vs amplitude` — 1,200 SV, KD 40–55
**Word count:** 2,000 words

**Why this post:** High volume comparison. Angle "what neither tool will tell you" (cross-tool synthesis) is genuinely differentiated from every other comparison post on this keyword. Higher KD but significant traffic potential.

**Required sections:**
1. What Mixpanel does well — be honest and specific
2. What Amplitude does well — be honest and specific
3. Where both fall short (the synthesis gap — neither tells you what the data means across your stack)
4. A real scenario: ROAS rising + retention falling — only visible if you read Google Ads and Mixpanel simultaneously
5. When to use Mixpanel vs Amplitude (genuine recommendation)
6. What to use when you need the layer above both

**Inline CTA:** After section 4
**CTA:** "Duct works with both. Connect whichever you use and get a weekly synthesis across your full stack. [Connect free →](/for-product-intelligence)"

---

### "How to Correlate Ad Performance With Product Retention"
**URL:** `/blog/correlate-ads-with-retention`
**Cluster:** Product Intelligence | **Priority:** P1
**Primary keyword:** `google ads retention correlation` — KD 12–20
**Word count:** 1,500 words

**Why this post:** Near-zero competition. Very high ICP relevance. The query perfectly surfaces Duct's cross-tool value — the only way to see this correlation is to read Google Ads and Mixpanel simultaneously.

**Required sections:**
1. Why ROAS is an incomplete metric (retention is missing)
2. What ad-to-retention correlation looks like in the data
3. How to build the analysis manually (step by step)
4. The common patterns: high-ROAS + low-retention campaigns (you're paying to acquire churners)
5. What to do when you find it

**Inline CTA:** After section 3 ("here's how to build this manually — or let Duct do it automatically")
**CTA:** "Duct connects Google Ads and Mixpanel and surfaces this correlation automatically in your weekly brief. [Get early access →](/for-product-intelligence)"

---

## 7. Connector Pages

One page per integration. Template is identical for each. Build after Tier 1 tools and first cluster pillar pages.

**Page structure for each:**
1. What data [Tool] gives you
2. What's missing when you use it in isolation
3. What Duct adds: cross-tool synthesis, weekly brief
4. How to connect [Tool] to Duct (OAuth, 2 minutes)
5. What your first brief includes from [Tool]

**Conversion hook pattern:** "Connect [Tool] in 2 minutes. First brief in your inbox this Monday."

---

| Page | URL | Primary Keywords | SV | Notes |
|---|---|---|---|---|
| Duct + Mixpanel | `/integrations/mixpanel` | `mixpanel reporting`, `mixpanel automated report` | 400 | Build first — core ICP tool |
| Duct + GA4 | `/integrations/ga4` | `ga4 reporting tools`, `google analytics automated reports` | 300 | Second — universal tool |
| Duct + HubSpot | `/integrations/hubspot` | `hubspot reporting`, `hubspot analytics reporting` | 600 | Third — high CPC ($4) |
| Duct + Google Ads | `/integrations/google-ads` | `google ads reporting tool`, `automated google ads report` | 200 | Fourth |
| Duct + Ahrefs | `/integrations/ahrefs` | `ahrefs reporting` | 4,900 | Supermetrics ranks here and drives 421 visits — steal it |
| Duct + Search Console | `/integrations/google-search-console` | `google search console reporting` | 300 | Pairs with Ahrefs page |
| Duct + Meta Ads | `/integrations/meta-ads` | `meta ads reporting tool`, `facebook ads automated report` | 250 | |
| Duct + Linear | `/integrations/linear` | `linear analytics`, `linear reporting` | 100 | Low volume, high intent for PM ICP |

---

## 8. Comparison Pages

Highest converting page type in this space. The visitor is already in buying mode. Build after the first two clusters are published.

**Core principle for all comparison pages:** Be genuinely honest about the competitor's strengths. Credibility through honesty converts better than trash talk. Hard on the specific weakness only.

---

### Duct vs Databox
**URL:** `/vs/databox`
**Primary keywords:** `databox alternative` (500 SV, $8 CPC), `databox vs` (200 SV), `alternatives to databox` (150 SV)

**Core argument:** Databox is a dashboard tool. Duct is a brief tool. If you want to look at data, use Databox. If you want to know what to do next, use Duct. Not competitors — different jobs to be done.

**Structure:**
1. What Databox does well (honest — builds credibility)
2. Where Databox falls short for your ICP (manual interpretation, no cross-tool synthesis, you still have to figure out what it means)
3. What Duct does differently (brief not dashboard, synthesis not display)
4. Side-by-side comparison table
5. Who should use which

**CTA:** "Try Duct free during beta. If you want a dashboard back, Databox will still be there."

---

### Duct vs Supermetrics
**URL:** `/vs/supermetrics`
**Primary keywords:** `supermetrics alternative` (1,500 SV), `supermetrics competitors` (1,070 SV), `supermetrics vs` (400 SV)

**Core argument:** Supermetrics moves data from A to B. You still have to interpret it. Duct interprets it for you.

**What Supermetrics does well:** Connector breadth, agency use cases, mature platform
**The specific weakness:** It's a data pipe, not intelligence. After Supermetrics, you still have a spreadsheet or dashboard full of numbers and no synthesis.

---

### Duct vs DashThis
**URL:** `/vs/dashthis`
**Primary keywords:** `dashthis alternative` (800 SV), `dashthis competitors` (300 SV)

**Core argument:** DashThis is built for agencies reporting to clients. Duct is built for internal growth teams reporting to themselves. Different audience, different job.

---

### Duct vs Whatagraph
**URL:** `/vs/whatagraph`
**Primary keywords:** `whatagraph alternative` (400 SV), `whatagraph competitors` (200 SV)

**Core argument:** Whatagraph automates the creation of client-facing reports. Duct automates the synthesis for internal decision-making. Again: agency tool vs internal growth tool.

---

## 9. Internal Linking Architecture

Internal linking is the primary PageRank distribution tool on a new domain. Do not treat it as optional.

### The rules

- Every cluster post links **up** to its pillar page (mandatory, placed naturally within content)
- The pillar page links **out** to every cluster post (update the pillar each time a new cluster post publishes)
- Cluster posts within the same vertical cross-link to each other when topically adjacent (not forced)
- Every blog post links to the relevant product page via an inline CTA mid-post AND an end-of-post CTA
- Free tool pages link to the relevant pillar page and product page
- Connector pages link to the relevant cluster pillar and product page
- Comparison pages link to the homepage and relevant product pages

### The link map

```
CLUSTER 1: AUTOMATED REPORTING
/blog/automated-reporting-guide  [Pillar]
  ├── /blog/automate-weekly-marketing-report
  ├── /blog/automated-reporting-tools
  ├── /blog/connect-ga4-hubspot-mixpanel
  ├── /blog/marketing-reporting-without-dashboard
  ├── /blog/automated-report-generation
  ├── /blog/what-is-automated-analytics
  ├── /blog/weekly-marketing-brief
  └── /blog/automated-reporting-system
        ↓ all link back to pillar + to getduct.ai

CLUSTER 2: PRODUCT INTELLIGENCE
/blog/product-intelligence-guide  [Pillar]
  ├── /blog/what-is-product-intelligence
  ├── /blog/mixpanel-retention-dropping
  ├── /blog/correlate-ads-with-retention
  ├── /blog/product-analytics-without-data-team
  ├── /blog/weekly-saas-metrics-digest
  ├── /blog/pm-weekly-data-review
  ├── /blog/cross-tool-anomaly-alerts
  ├── /blog/mixpanel-vs-amplitude
  ├── /blog/linear-mixpanel-integration
  └── /blog/feature-adoption-rate-measurement
        ↓ all link back to pillar + to /for-product-intelligence

CLUSTER 3: SEO INTELLIGENCE
/blog/seo-intelligence-guide  [Pillar]
  ├── /blog/connect-search-console-ahrefs-ga4
  ├── /blog/organic-traffic-not-converting
  ├── /blog/weekly-seo-brief-template
  ├── /blog/content-decay-guide
  ├── /blog/seo-metrics-that-matter
  ├── /blog/keyword-gap-analysis  [existing]
  ├── /blog/ahrefs-vs-search-console-vs-ga4
  ├── /blog/automated-seo-alerts
  └── /blog/seo-content-calendar
        ↓ all link back to pillar + to /for-organic-growth

FREE TOOLS
/tools/saas-metrics-calculator → product-intelligence-guide + /for-product-intelligence
/tools/weekly-brief-template → automated-reporting-guide + getduct.ai
/tools/cac-ltv-calculator → product-intelligence-guide + /for-product-intelligence

CONNECTOR PAGES
/integrations/[tool] → relevant cluster pillar + relevant product page

COMPARISON PAGES
/vs/[competitor] → getduct.ai + relevant product pages
```

### Anchor text conventions

| Link type | Style | Example |
|---|---|---|
| Cluster post → pillar | Descriptive, keyword-rich | "automated marketing reporting guide" |
| Pillar → cluster post | Topic-specific | "how to automate your weekly marketing brief" |
| Any post → product page | Benefit-oriented | "see how Duct automates this" |
| Cross-cluster link | Natural language | "the same pattern appears in product retention data" |

**Never use:** "click here," "learn more," "this post," "here"

---

## 10. 90-Day Publishing Calendar

**Sequencing logic:**
- Fix existing posts (Week 1) before publishing anything new
- Free tools ship in parallel with Week 1–2 blog work (Claude Code)
- Pillar pages publish before or simultaneously with first cluster posts
- Cluster 1 (Automated Reporting) publishes first — broadest ICP, fastest to rank
- Cluster 2 (Product Intelligence) starts Week 3
- Cluster 3 (SEO Intelligence) starts Week 5

**Publishing rate:** 1–2 posts per week. One high-quality post beats two mediocre ones every time with this ICP.

### Week 1–2 — Foundation

| Week | Action | Type | Notes |
|---|---|---|---|
| 1 | Fix: Keyword Gap Analysis post | Existing content | Expand + add pillar link |
| 1 | Fix: SEO Metrics post | Existing content | Add cluster structure + inline CTA |
| 1 | Build: SaaS Metrics Calculator | Free tool (Claude Code) | Ship in parallel |
| 2 | Publish: Automated Reporting Guide | Cluster 1 Pillar | Publish first — this is the hub |
| 2 | Build: Weekly Brief Template Generator | Free tool (Claude Code) | Ship in parallel |

### Week 3–4 — First Cluster Posts

| Week | Publish | Cluster | Priority |
|---|---|---|---|
| 3 | How to Automate Your Weekly Marketing Report | Automated Reporting | P1 |
| 3 | Publish: Product Intelligence Guide | Product Intelligence Pillar | Pillar |
| 4 | What Is Product Intelligence? | Product Intelligence | P1 |
| 4 | Automated Reporting Tools — What to Look For | Automated Reporting | P1 |

### Week 5–6 — Depth

| Week | Publish | Cluster | Priority |
|---|---|---|---|
| 5 | Publish: SEO Intelligence Guide | SEO Intelligence Pillar | Pillar |
| 5 | Why Your Mixpanel Data Looks Fine But Retention Is Dropping | Product Intelligence | P1 |
| 6 | How to Connect Search Console, Ahrefs, and GA4 | SEO Intelligence | P1 |
| 6 | How to Connect GA4, HubSpot and Mixpanel Without a Data Team | Automated Reporting | P1 |

### Week 7–8 — High-Intent Posts

| Week | Publish | Cluster | Priority |
|---|---|---|---|
| 7 | Why Your Organic Traffic Is Up But Signups Are Flat | SEO Intelligence | P1 |
| 7 | How to Correlate Ad Performance With Product Retention | Product Intelligence | P1 |
| 8 | Marketing Reporting Without a Dashboard | Automated Reporting | P2 |
| 8 | The PM's Weekly Data Review | Product Intelligence | P2 |

### Week 9–10 — Connector Pages + Cluster Depth

| Week | Action | Type |
|---|---|---|
| 9 | Publish: Duct + Mixpanel connector page | Connector |
| 9 | Publish: Duct + GA4 connector page | Connector |
| 9 | The Weekly SEO Brief Template | SEO Intelligence P1 |
| 10 | Publish: Duct + HubSpot connector page | Connector |
| 10 | Content Decay Guide | SEO Intelligence P2 |
| 10 | Build: CAC/LTV Calculator | Free tool |

### Week 11–12 — Differentiation + Comparison

| Week | Action | Type |
|---|---|---|
| 11 | Ahrefs vs Search Console vs GA4: Which to Trust | SEO Intelligence P2 |
| 11 | Mixpanel vs Amplitude: What Neither Will Tell You | Product Intelligence P2 |
| 12 | Duct vs Databox comparison page | Comparison |
| 12 | Duct vs Supermetrics comparison page | Comparison |

### Weeks 13+ — Backlog (priority order)

1. SEO Metrics That Actually Correlate With Revenue
2. How to Set Up Cross-Tool Anomaly Alerts for Your Product Stack
3. Linear + Mixpanel: Engineering Velocity With Product Outcomes
4. Feature Adoption Rate Measurement
5. Automated Report Generation: A Practical Guide
6. Duct vs DashThis + Duct vs Whatagraph comparison pages
7. Remaining connector pages (Google Ads, Ahrefs, GSC, Meta, Linear)
8. How to Set Up Automated SEO Alerts That Actually Mean Something
9. The Hidden Cost of Manual Data Synthesis for PMs

---

## 11. Distribution & Promotion

Publishing is 20% of the work. The ICP discovers content through community shares first, then Google reinforces it. Publish without distributing and traffic accumulates slowly.

### 11.1 Community distribution

**For Automated Reporting + SEO cluster:**

| Community | Size | What to post | How |
|---|---|---|---|
| r/SEO | 580K | Ahrefs vs GSC vs GA4, content decay posts | Discussion frame, not link post. "We noticed these three disagreed — here's what we found." |
| r/juststart | 125K | Content decay, keyword gap posts | Practical framework posts. Post the process, not the product. |
| Demand Curve Slack | ~5K growth marketers | Weekly brief template | Share as a free resource in #content or #seo |
| Superpath | Professional content community | SEO brief and content calendar posts | Lead with craft. No product pitch. |

**For Product Intelligence cluster:**

| Community | Size | What to post | How |
|---|---|---|---|
| Lenny's Slack | ~30K PMs | "What Is Product Intelligence?" post | Post in #tools-and-resources. Educational, no pitch. |
| r/ProductManagement | 200K | "Mixpanel data looks fine but retention dropping" | Frame as a diagnostic question. Ask for community input. |
| Mind the Product Slack | Senior PM community | PM weekly data review framework | Professional community. Lead with the framework. |
| Product-Led Alliance | PLG-focused | "Correlate ad performance with product retention" | PLG-specific problem. Directly relevant to this community. |

### 11.2 LinkedIn (second highest leverage)

Turn each blog post into 3 LinkedIn posts in different formats. Not reposts — different framings of the same content.

**Format 1 — The Hook Post:** Start with the most provocative claim in the post. 200–300 words. Link in first comment, not body.
> *"Your organic traffic is up 40%. Your signups are flat. Here's what that usually means — and it's not a conversion problem."*

**Format 2 — The Framework Post:** Extract the central framework as a numbered list or table. Tag relevant tools (Ahrefs, GA4, Mixpanel) to extend reach.

**Format 3 — The Story Post:** Tell a real example from the post as a narrative. Feels personal, performs well.

**Founder posts > brand posts.** Founder LinkedIn posts outperform brand account posts 5–10x at early-stage B2B SaaS. Every post should have a founder version from a personal account. The Duct brand page reshares it.

### 11.3 Newsletter seeding targets

| Newsletter | Audience | Pitch angle |
|---|---|---|
| Lenny's Newsletter | 500K+ PMs/growth | Guest post: "The PM data workflow that wastes the most time" |
| Growth Newsletter | Growth marketers | Guest piece: "Why organic traffic not converting is almost always the same problem" |
| The Slice | Content marketers | SEO brief template or content decay framework |
| Indie Hackers Weekly | Solo operators | Keyword gap analysis post |

### 11.4 Backlink tactics

**Tool mention outreach:** Every cluster post mentions 3–5 tools by name with meaningful depth. Email the tool's content or community team with a direct link to the mention — ask if they'd share in their newsletter or link from their integration pages. Conversion rate ~5–10%. The links are highly relevant to the cluster topic.

**Roundup inclusion:** For pillar pages, identify top 5 ranking roundups for "best SEO tools" and "product analytics tools." Check if they accept submissions. Reach out with the Duct framing.

### 11.5 Repurposing pipeline

Each long-form post produces:
- 1 Twitter/X thread (most tactical section, fully expanded — not a summary)
- 1 LinkedIn post (rotate formats: hook → framework → story → hook…)
- 1 short email to beta waitlist (3 sentences + link)

Write once, distribute in five places.

---

## 12. Measurement Framework

### 12.1 What to track and where

**Google Search Console — weekly:**
- Impressions trend by page — is Google beginning to surface the content?
- CTR by page — below 3% on a non-branded informational query = title/meta problem, not content problem
- Average position by page — anything ranked 8–20 is a "push" candidate (add internal links, minor content update)
- Query-level data — what are people actually searching when they find your pages? Unintended queries often reveal the next post to write

**GA4 — weekly:**
- Organic sessions by page
- Engagement rate by page — target >55% for blog content
- Blog → beta sign-up conversion rate — **single most important metric in the framework**. Set up as a GA4 conversion event on form submissions on all product pages.
- Time on page for pillar pages — target >3 minutes

**Ahrefs — bi-weekly:**
- Domain Rating trend
- Keyword ranking positions for all target keywords
- New backlinks earned — which content earns links tells you which topics the audience values most
- Organic traffic estimate trend

### 12.2 Success benchmarks by stage

**30 days — Foundation**
Target at 30 days is instrumentation, not traffic. SEO indexing takes 4–8 weeks from publishing.
- Both pillar pages indexed (verify in GSC Coverage report)
- All published cluster posts indexed
- GA4 conversion events firing correctly for beta sign-up
- Free tools live and indexed
- Zero organic traffic target — do not optimise for this yet

**60 days — Early traction**
- 500–1,500 total organic sessions/month
- At least 2 posts appearing in positions 10–30 for primary keywords
- 1–3 beta sign-ups attributable to blog content
- Tool pages receiving traffic

**90 days — Cluster authority forming**
- 2,000–5,000 organic sessions/month
- At least 1 post ranking top 10 for a primary keyword
- 5–10 beta sign-ups from blog (cumulative)
- 3–5 referring domains
- Google ranking Duct for keyword variations never directly targeted (cluster structure working)

### 12.3 Intervention signals

| Signal | What it usually means | Action |
|---|---|---|
| Post indexed 6+ weeks, zero impressions | Query too narrow or page being filtered | Check GSC Coverage. Reassess keyword targeting. |
| Post ranked 15–30 for 8+ weeks, no movement | Needs authority push | Add 2–3 internal links from higher-authority pages. Expand post with a related section. |
| Post ranking well (top 10) but low CTR | Title/meta mismatch | Rewrite title and meta. Use GSC query data to see what searchers expected. |
| Blog traffic growing but zero conversions | CTA placement or tracking broken | Check GA4 conversion event firing. Test inline CTA vs end-of-post CTA placement. |

### 12.4 Monthly 15-minute retrospective

1. Which 3 posts had the most organic sessions? Why? (keyword win, distribution spike, or backlink?)
2. Which cluster posts are in positions 8–20? These are "push" candidates — add internal links.
3. What are the top 5 queries GSC is ranking for with no dedicated content? These are your next posts.
4. What is the blog → beta conversion rate? Below 0.5% = CTA work needed. Above 2% = double publishing rate.

---

## 13. Technical SEO Baseline

Do all of these before publishing any content. They are not optional.

**Sitemap:** Every new URL must be added to `/sitemap.xml` at publishing time. Add to publishing checklist. Use `changefreq: monthly` and `priority: 0.7` for blog posts, `priority: 0.8` for tool pages and pillar pages.

**Submit to GSC:** Go to Google Search Console → Sitemaps → Submit `https://getduct.ai/sitemap.xml`. Do this today if not already done.

**Canonical tags:** Verify `/blog/post.html` renders the correct canonical URL for each post (should be the post's permalink). If rendering `post.html?slug=...` as the canonical, fix before publishing.

**Article schema:** Blog posts need `Article` schema (or `BlogPosting` subtype). Add to the blog post template so it applies automatically. Minimum fields: `headline`, `author`, `datePublished`, `dateModified`.

**Tool pages schema:** Use `SoftwareApplication` schema for free tool pages.

**Internal link minimum per post:**
1. The cluster pillar page
2. One other cluster post (when available)
3. The product conversion page (via inline CTA)

**Robots.txt:** Verify `/blog/` is not accidentally blocked. Confirm crawling is unrestricted for `/tools/`, `/integrations/`, `/vs/`.

**Core Web Vitals:** Check GSC → Core Web Vitals report. Fonts loading from Google Fonts can delay rendering on slow connections — monitor but not a ranking emergency.

---

## Appendix A: Full Keyword Reference Table

| Content | Primary Keyword | SV | KD | CPC | Intent | URL | Cluster | Priority |
|---|---|---|---|---|---|---|---|---|
| Automated Reporting Guide (Pillar) | `automated reporting tools` | 350 | 3 | $10 | Commercial | `/blog/automated-reporting-guide` | 1 | Pillar |
| Product Intelligence Guide (Pillar) | `product intelligence` | Low | 20–30 | — | Definitional | `/blog/product-intelligence-guide` | 2 | Pillar |
| SEO Intelligence Guide (Pillar) | `SEO intelligence` | Low | 25–35 | — | Definitional | `/blog/seo-intelligence-guide` | 3 | Pillar |
| SaaS Metrics Calculator (Tool) | `saas metrics benchmarks` | 150 | Low | $6 | Tool | `/tools/saas-metrics-calculator` | — | T1 |
| Weekly Brief Generator (Tool) | `weekly marketing report template` | 700 | Low | $2.50 | Tool | `/tools/weekly-brief-template` | — | T1 |
| CAC/LTV Calculator (Tool) | `cac ltv ratio` | 400 | Low | — | Tool | `/tools/cac-ltv-calculator` | — | T1 |
| Automate Weekly Marketing Report | `automated weekly report` | 100 | Low | $1.80 | Procedural | `/blog/automate-weekly-marketing-report` | 1 | P1 |
| Automated Reporting Tools Review | `automated reporting software` | 300 | 9 | $0.60 | Commercial | `/blog/automated-reporting-tools` | 1 | P1 |
| Connect GA4 HubSpot Mixpanel | `connect ga4 hubspot` | 200 | Low | — | Procedural | `/blog/connect-ga4-hubspot-mixpanel` | 1 | P1 |
| Marketing Reporting Without Dashboard | `marketing reporting tools` | 250 | Low | $3.50 | Commercial | `/blog/marketing-reporting-without-dashboard` | 1 | P2 |
| What Is Product Intelligence? | `product intelligence vs analytics` | Low | 10–18 | — | Definitional | `/blog/what-is-product-intelligence` | 2 | P1 |
| Mixpanel Retention Dropping | `mixpanel retention analysis` | Low | 25–35 | — | Diagnostic | `/blog/mixpanel-retention-dropping` | 2 | P1 |
| Correlate Ads With Retention | `google ads retention correlation` | Low | 12–20 | — | Procedural | `/blog/correlate-ads-with-retention` | 2 | P1 |
| Product Analytics Without Data Team | `product analytics without sql` | Low | Low | — | Procedural | `/blog/product-analytics-without-data-team` | 2 | P2 |
| Weekly SaaS Metrics Digest | `saas reporting tools` | 150 | 3 | $10 | Commercial | `/blog/weekly-saas-metrics-digest` | 2 | P2 |
| Mixpanel vs Amplitude | `mixpanel vs amplitude` | 1,200 | 40–55 | — | Comparison | `/blog/mixpanel-vs-amplitude` | 2 | P2 |
| Connect GSC Ahrefs GA4 | `connect search console and ga4` | Low | 18–25 | — | Procedural | `/blog/connect-search-console-ahrefs-ga4` | 3 | P1 |
| Organic Traffic Not Converting | `organic traffic not converting` | Low | 22–30 | — | Diagnostic | `/blog/organic-traffic-not-converting` | 3 | P1 |
| Weekly SEO Brief Template | `weekly SEO report template` | Low | 15–22 | — | Resource | `/blog/weekly-seo-brief-template` | 3 | P1 |
| Content Decay Guide | `content decay SEO` | Low | 28–38 | — | Procedural | `/blog/content-decay-guide` | 3 | P2 |
| Ahrefs vs GSC vs GA4 | `ahrefs vs search console discrepancy` | Low | 18–28 | — | Comparison | `/blog/ahrefs-vs-search-console-vs-ga4` | 3 | P2 |
| Duct vs Databox | `databox alternative` | 500 | Low | $8 | Commercial | `/vs/databox` | — | C1 |
| Duct vs Supermetrics | `supermetrics alternative` | 1,500 | Low | — | Commercial | `/vs/supermetrics` | — | C1 |
| Duct vs DashThis | `dashthis alternative` | 800 | Low | — | Commercial | `/vs/dashthis` | — | C2 |
| Duct + Mixpanel | `mixpanel reporting` | 400 | Low | $3 | Commercial | `/integrations/mixpanel` | — | I1 |
| Duct + GA4 | `ga4 reporting tools` | 300 | Low | $5 | Commercial | `/integrations/ga4` | — | I1 |
| Duct + HubSpot | `hubspot reporting` | 600 | Low | $4 | Commercial | `/integrations/hubspot` | — | I1 |
| Duct + Ahrefs | `ahrefs reporting` | 4,900 | Low | — | Commercial | `/integrations/ahrefs` | — | I2 |

---

## Appendix B: Post Brief Template

Use this for every post. No post gets written without a completed brief.

```
---
BRIEF: [Post title]
---

Target primary keyword:
Target secondary keywords (2–3):
Validated KD (from Ahrefs):
Validated SV (from Ahrefs):
Search intent: [informational / procedural / comparison / commercial / tool]
Target word count:
Target URL:
Cluster: [Automated Reporting / Product Intelligence / SEO Intelligence / Tool / Connector / Comparison]
Priority: [P1 / P2 / P3]

---

READER
Who is this person specifically? (job title, company stage, what they're trying to do today)

What is the one thing this reader should be able to do after reading this that they couldn't before?

What are they searching for right before they land on this post?

---

REQUIRED SECTIONS (headings)
1.
2.
3.
4.
5.

---

MANDATORY INTERNAL LINKS
- Pillar link: [URL] — anchor text: [exact text]
- Cluster post link: [URL] — anchor text: [exact text]
- Product page CTA: [URL] — anchor text: [exact text]

---

INLINE CTA
Placement: [which section — "immediately after [section name]"]
CTA text: [exact wording]
URL: [product page URL]

END-OF-POST CTA
CTA text: [exact wording]
URL: [product page URL]

---

COMPETITORS TO BEAT
[List top 3 ranking pages for primary keyword — what do they cover, what do they miss?]

---

NOTES FOR CLAUDE
[Specific examples to include, tools to mention, data points to feature, angle to take]
```

---

## Appendix C: Claude Prompts for Content Generation

### For pillar pages:
```
Write a comprehensive guide titled "[title]" targeting the primary keyword "[keyword]".

ICP: [Growth PMs / Performance Marketers / SEO leads] at 20–200 person SaaS companies without a dedicated data team.

Tone: Direct, opinionated, practitioner-level. Written by someone who has actually done this job. No filler, no padding, no generic advice.

Required sections: [paste structure from Section 5]

Word count: [2,500–3,500]

Internal links to include:
- Link to "[related post title]" at [URL] using anchor text "[anchor text]"

Inline CTA: Place immediately after [section name]. Text: "[CTA text]". URL: [product page URL]

End-of-post CTA: "[CTA text]". URL: [product page URL]

Do not mention Duct until the CTA sections — earn the pitch by being genuinely useful first.
```

### For cluster posts:
```
Write a [word count] word blog post titled "[title]" targeting primary keyword "[keyword]".

ICP: [specific role] at a 20–200 person SaaS company. They don't have a dedicated data team. They are searching for this because [specific situation].

Tone: Direct, no padding. Written by a practitioner, not a summariser.

Angle: [paste angle from Section 6]

Required sections: [paste sections]

Internal links:
- Link to "[pillar page title]" at [URL] using anchor text "[anchor text]"
- Link to "[related cluster post]" at [URL] using anchor text "[anchor text]"

Inline CTA: Place immediately after [section name]. Text: "[exact CTA text]". URL: [URL]
End-of-post CTA: "[exact CTA text]". URL: [URL]
```

### For comparison pages:
```
Write a comparison page: "Duct vs [Competitor]".

Be honest about [Competitor]'s strengths — list them specifically. Credibility through honesty.

The specific weakness to address: [weakness — e.g., "Supermetrics moves data but doesn't interpret it"].

Core argument: [argument from Section 8]

Structure: (1) What [competitor] does well, (2) Where it falls short for internal growth teams, (3) What Duct does differently, (4) Side-by-side comparison table with rows: Setup time / Requires data team / Output format / Cross-tool synthesis / Pricing / Best for, (5) Who should use which.

No trash talk. No marketing language. Honest and specific throughout.

End CTA: "[CTA text from Section 8]"
```

### For connector pages:
```
Write a product integration page for "Duct + [Tool]".

Structure: (1) What [Tool] gives you, (2) What's missing when you use it in isolation (be specific — not vague), (3) What Duct adds: cross-tool synthesis, weekly brief, (4) How to connect (OAuth, 2 min — keep this very short), (5) What the first brief includes from [Tool] — give a real example.

Tone: Concise, specific, no marketing fluff. This is a technical-ish page for someone who already uses [Tool] and wants to know what Duct adds.

Target keyword: "[keyword]"

Internal links:
- Link to "[relevant pillar]" at [URL] using anchor text "[anchor]"

End CTA: "Connect [Tool] in 2 minutes. First brief in your inbox this Monday." → [product page URL]
```

### For free tool pages (the page wrapping each tool):
```
Write a landing page for the "[tool name]" free tool at getduct.ai/tools/[slug].

Structure: (1) What this tool does and who it's for (2 sentences max), (2) [TOOL EMBED GOES HERE placeholder], (3) How to use it (3 bullet points), (4) Why this matters — explain the metric/problem the tool addresses (200 words, practitioner-level), (5) The manual version vs the automated version — this is the conversion section.

Conversion section: "This tool gives you a snapshot. Duct gives you a trend — the same calculation run automatically every week across your full stack, delivered to your inbox on Monday morning."

CTA: "Get your free weekly brief →" → getduct.ai

Target keyword: "[primary keyword]"
Internal links: Link to "[relevant pillar]" at [URL]
```

---

*Last updated: April 2026 | Next review: when first 10 posts are published or at 60-day mark, whichever comes first.*
*KD estimates marked as ranges are directional — validate against live Ahrefs data before briefing each post.*