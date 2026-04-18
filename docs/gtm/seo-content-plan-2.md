# Duct — SEO & Content Plan
**Goal:** Rank for automated reporting, SaaS metrics, and growth intelligence keywords. Convert organic visitors to beta signups.
**ICP:** Growth PMs and Performance Marketers at 20–200 person SaaS companies without a dedicated data team.
**Execution stack:** Claude for content generation, Claude Code for free tools.

---

## EXECUTION ORDER

| Week | Priority | Output |
|------|----------|--------|
| 1–2 | Free Tools (2x) | SaaS Metrics Calculator + Weekly Brief Template Generator |
| 3–4 | Pillar Page | Automated Marketing Reporting Guide |
| 5–6 | Cluster 1 Posts (4x) | Automated reporting supporting content |
| 7–8 | Connector Pages (3x) | Mixpanel, GA4, HubSpot |
| 9–10 | Cluster 2 Posts (4x) | SaaS metrics supporting content |
| 11–12 | Comparison Pages (2x) | vs Databox, vs Supermetrics |
| 13+ | Cluster 3 + remaining connectors | Paid ads intelligence content |

---

## TIER 1 — FREE TOOLS
*Build first. Highest compounding value. Each tool page ends with a conversion hook to beta signup.*

---

### Tool 1: SaaS Metrics Benchmark Calculator

**URL:** `getduct.ai/tools/saas-metrics-calculator`

**Target keywords:**
- `saas metrics benchmarks` — 150 SV, Low KD, $6 CPC — direct ICP, low competition
- `saas metrics calculator` — 100 SV, Low KD — tool intent, high conversion
- `b2b saas metrics` — 100 SV — broad capture
- `key saas metrics` — 100 SV — informational → tool funnel

**Why this works:** Databox's growth rate calculator drives ~2K monthly visits from a single tool page. SaaS-specific metrics benchmarks have no dominant free tool. You own it by default.

**What the tool does:**
Input: MRR, churn rate, CAC, LTV, trial-to-paid rate, monthly actives
Output: Benchmark scores vs SaaS industry averages with colour-coded ratings (good / needs work / critical)
Show: "Your churn is 4.2% — median for your MRR band is 2.8%. Here's what that means for LTV."

**Conversion hook:**
> "Want these metrics tracked automatically every week and delivered to your inbox? That's Duct."
CTA: "Get your free weekly SaaS metrics brief →"

**Claude Code prompt to build:**
> Build a single-page React app: SaaS Metrics Benchmark Calculator. Inputs: MRR (€), monthly churn rate (%), CAC (€), LTV (€), trial-to-paid rate (%), WAU. Output: colour-coded benchmark scores vs industry averages sourced from standard SaaS benchmarks (OpenView, ChartMogul). Show a score for each metric: green = good, amber = needs work, red = critical. Clean minimal design, no dashboard, output reads like an intelligence brief not a report.

---

### Tool 2: Weekly Marketing Brief Template Generator

**URL:** `getduct.ai/tools/weekly-brief-template`

**Target keywords:**
- `weekly marketing report template` — 700 SV, Low KD, $2.50 CPC — highest volume in this list
- `weekly report template` — 700 SV — broad capture, funnel into tool
- `marketing weekly report` — 150 SV — direct ICP
- `weekly kpi report` — 50 SV, $6 CPC — commercial intent

**Why this works:** DashThis and Databox both rank for template keywords with static pages. You build an interactive generator that outputs a real customised template — more useful, more shareable, better conversion signal.

**What the tool does:**
Step 1: User selects their role (Growth PM / Performance Marketer / SEO Lead)
Step 2: Selects connected tools (GA4, Mixpanel, HubSpot, Google Ads, Ahrefs)
Step 3: Sets their north star metric
Output: A formatted markdown/HTML weekly brief template they can copy, with sections pre-populated for their stack

**Conversion hook:**
> "This template takes 2–3 hours to fill in manually every week. Duct fills it automatically."
CTA: "Get the automated version free during beta →"

**Claude Code prompt to build:**
> Build a multi-step weekly brief template generator. Step 1: role selector (3 options). Step 2: tool stack selector (checkboxes, 8 tools). Step 3: north star metric input. Output: a formatted weekly brief template with pre-filled section headers, metric slots, and placeholder insights specific to their tool stack. Add a copy-to-clipboard button. End with a CTA card: "This takes 3 hours manually. Duct does it automatically." Button: "Get early access →" linking to https://getduct.ai

---

### Tool 3: CAC / LTV Calculator

**URL:** `getduct.ai/tools/cac-ltv-calculator`

**Target keywords:**
- `cac ltv ratio` — 400 SV — high intent SaaS ICP
- `how to calculate ltv` — 300 SV — informational → tool
- `customer acquisition cost calculator` — 200 SV
- `ltv cac ratio saas` — 150 SV, $4 CPC

**Why this works:** Every growth PM runs this calculation. No dominant free tool owns it for SaaS specifically. Quick build, permanent traffic.

**What the tool does:**
Input: monthly new customers, total sales + marketing spend, avg revenue per customer, avg customer lifespan (months)
Output: CAC, LTV, LTV:CAC ratio, payback period, colour-coded health score
Benchmark: "For SaaS, healthy LTV:CAC is >3:1. Yours is X."

**Conversion hook:**
> "Duct tracks your LTV:CAC trend automatically each week and alerts you when it shifts."
CTA: "See it in action →"

---

## TIER 2 — CLUSTER CONTENT

### CLUSTER 1: Automated Reporting
*Widest ICP. Targets anyone frustrated with manual reporting regardless of vertical.*

---

#### Pillar Page: The Complete Guide to Automated Marketing Reporting

**URL:** `getduct.ai/blog/automated-marketing-reporting`

**Target keywords:**
- `automated reporting tools` — 350 SV, $10 CPC — highest commercial value in dataset
- `automated reporting software` — 300 SV, $0.60 CPC
- `automated report generation` — 200 SV, $4 CPC
- `automated reporting system` — 150 SV, $8 CPC
- `marketing report automation` — 150 SV

**Why this is the pillar:** Highest CPC keywords in your dataset = highest commercial intent. This page anchors the entire cluster and should be the longest, most comprehensive piece you publish.

**Structure:**
1. What is automated marketing reporting (definition section for long-tail)
2. Why manual reporting is broken (pain amplification)
3. What to look for in automated reporting tools
4. How to automate each channel: GA4, HubSpot, Google Ads, Mixpanel
5. The difference between a report and an intelligence brief (Duct differentiation)
6. How to set up automated reporting in under 10 minutes

**Conversion hook:**
> "Most automated reporting tools give you a dashboard. Duct gives you a brief — what changed, why it matters, what to do next."
CTA: "Get your first automated brief free →"

**Word count target:** 2,500–3,000 words
**Internal links:** Link to all four supporting posts + tool pages

---

#### Supporting Post 1: How to Automate Your Weekly Marketing Report

**URL:** `getduct.ai/blog/automate-weekly-marketing-report`

**Target keywords:**
- `how to automate marketing reports` — 150 SV
- `automated weekly report` — 100 SV, $1.80 CPC
- `weekly marketing report` — 70 SV, $3.50 CPC

**Angle:** Step-by-step practical guide. Tool agnostic in body, Duct as the conclusion.

**Structure:**
1. What should be in a weekly marketing report
2. How to connect GA4 + HubSpot + ads data
3. The manual approach (show the pain: 3–4 hours)
4. The automated approach: what to look for
5. How Duct does it in 10 minutes

**Conversion hook:**
> "Follow this guide and you'll save 3 hours. Connect Duct and you'll never do it again."
CTA: "Try Duct free during beta →"

**Word count:** 1,500 words

---

#### Supporting Post 2: Automated Reporting Tools — What to Look For (and What to Avoid)

**URL:** `getduct.ai/blog/automated-reporting-tools`

**Target keywords:**
- `best automated reporting tools` — 200 SV
- `automated reporting tools comparison` — 100 SV
- `marketing automation reporting` — 150 SV

**Angle:** Honest evaluation framework. Not a listicle. Teaches the reader how to evaluate tools — then positions Duct's brief-first approach as the differentiated choice.

**Key differentiation point to make:** Most tools automate the creation of a dashboard or PDF report. Duct automates the *synthesis* — it tells you what the data means, not just what the data is.

**Conversion hook:**
> "If you want another dashboard, there are plenty of options. If you want to know what to do next, that's what Duct is for."
CTA: "See a live brief →" (link to demo)

**Word count:** 1,800 words

---

#### Supporting Post 3: How to Connect GA4, HubSpot and Mixpanel Without a Data Team

**URL:** `getduct.ai/blog/connect-ga4-hubspot-mixpanel`

**Target keywords:**
- `connect ga4 hubspot` — 200 SV
- `mixpanel ga4 integration` — 150 SV
- `hubspot analytics integration` — 300 SV
- `marketing stack integration no code` — 100 SV

**Angle:** Practical how-to. Covers OAuth connections, what data each tool provides, and how to synthesise signals across all three. Duct as the zero-engineering solution.

**Conversion hook:**
> "Or connect all three to Duct in 10 minutes and get a synthesised brief every week automatically."
CTA: "Connect your stack →"

**Word count:** 1,500 words

---

#### Supporting Post 4: Marketing Reporting Without a Dashboard

**URL:** `getduct.ai/blog/marketing-reporting-without-dashboard`

**Target keywords:**
- `marketing reporting tools` — 250 SV, $3.50 CPC
- `marketing reporting without dashboard` — low SV, zero competition — own it
- `marketing intelligence brief` — 100 SV

**Angle:** Contrarian. "Dashboards are built for looking at data. Your job is making decisions." Make the case that briefs > dashboards for busy growth teams. This is Duct's core positioning article.

**Conversion hook:** This IS the product pitch. End with the brief demo.
CTA: "See what a brief looks like →" (link to interactive demo)

**Word count:** 1,200 words

---

### CLUSTER 2: SaaS Metrics
*Targets Growth PMs specifically. More technical, higher intent.*

---

#### Pillar Page: The SaaS Metrics Guide — What to Track, When and Why

**URL:** `getduct.ai/blog/saas-metrics-guide`

**Target keywords:**
- `saas metrics` — 1,000 SV, $1.30 CPC — highest volume in your dataset
- `key saas metrics` — 100 SV
- `saas metrics guide` — 100 SV, $5 CPC
- `b2b saas metrics` — 100 SV, $2.50 CPC
- `saas metrics that matter` — 90 SV, $7 CPC

**Why this is the pillar:** 1,000 monthly searches, $1.30 CPC. This is the broadest entry point for your Growth PM ICP. Own it.

**Structure:**
1. The 10 SaaS metrics every growth team should track
2. Activation metrics: what they are and how to read them
3. Retention metrics: cohort analysis without SQL
4. Expansion metrics: NRR, upsell signals
5. Acquisition metrics: CAC, payback period, channel efficiency
6. How to track all of these weekly without a data team

**Conversion hook:**
> "Duct tracks all of these automatically and delivers a weekly brief ranked by what needs your attention most."
CTA: "Get your free SaaS metrics brief →"

**Word count:** 3,000 words
**Link to:** SaaS Metrics Calculator tool, all supporting posts

---

#### Supporting Post 1: The 10 SaaS Metrics Every Growth PM Should Track Weekly

**URL:** `getduct.ai/blog/saas-metrics-growth-pm`

**Target keywords:**
- `saas metrics for growth` — 150 SV
- `growth pm metrics` — 100 SV
- `product growth metrics` — 150 SV
- `saas growth kpis` — 100 SV

**Angle:** Opinionated. Not a generic list. Ranked by decision-making importance, not industry convention. Written for a PM who has 20 minutes on Monday morning.

**Conversion hook:**
> "These 10 metrics take 3 hours to pull manually each week. Duct delivers them automatically every Monday."
CTA: "Start your free brief →"

**Word count:** 1,500 words

---

#### Supporting Post 2: Product Analytics Without a Data Team

**URL:** `getduct.ai/blog/product-analytics-without-data-team`

**Target keywords:**
- `product analytics without sql` — low SV, zero competition — own it
- `mixpanel without analyst` — low SV, zero competition
- `product analytics small team` — 100 SV
- `amplitude vs mixpanel for growth` — 200 SV

**Angle:** Directly addresses your ICP's constraint. No data team, no SQL, no BI tool. Here's how to get the same insight quality using tools you already have.

**Conversion hook:**
> "This is exactly the problem Duct is built to solve. Connect your product analytics stack and get a weekly brief without touching SQL."
CTA: "Connect Mixpanel free →"

**Word count:** 1,500 words

---

#### Supporting Post 3: How to Build a Weekly SaaS Metrics Digest Without SQL

**URL:** `getduct.ai/blog/weekly-saas-metrics-digest`

**Target keywords:**
- `weekly saas report` — 50 SV
- `saas metrics reporting` — 150 SV, $8 CPC — high CPC = high intent
- `saas reporting tools` — 150 SV, $10 CPC — highest CPC in your keyword set
- `automated saas analytics` — 100 SV

**Angle:** Step-by-step guide to assembling a weekly SaaS metrics brief manually — then showing the automated version. Tutorial format that makes the manual process feel painful enough to justify the tool.

**Conversion hook:**
> "Or let Duct assemble this automatically. First brief in your inbox in 10 minutes."
CTA: "Try it free during beta →"

**Word count:** 1,800 words

---

#### Supporting Post 4: Mixpanel vs Amplitude — Which Metrics Actually Matter for Growth

**URL:** `getduct.ai/blog/mixpanel-vs-amplitude-growth`

**Target keywords:**
- `mixpanel vs amplitude` — 1,200 SV — high volume comparison
- `mixpanel or amplitude for saas` — 200 SV
- `amplitude vs mixpanel growth` — 150 SV

**Angle:** Genuinely useful comparison focused on growth use cases, not feature lists. Conclude with: "Both tools surface the data. Neither tells you what it means week to week. That's what Duct adds."

**Conversion hook:**
> "Duct works with both. Connect whichever you use and get a weekly synthesis across your full stack."
CTA: "Connect Mixpanel or Amplitude →"

**Word count:** 2,000 words

---

### CLUSTER 3: Paid Ads Intelligence
*Targets Performance Marketers. Third priority — after Clusters 1 and 2.*

---

#### Pillar Page: Cross-Channel Paid Ads Reporting — The Complete Guide

**URL:** `getduct.ai/blog/cross-channel-paid-ads-reporting`

**Target keywords:**
- `cross channel reporting` — 300 SV, $5 CPC
- `paid ads reporting` — 200 SV
- `multi channel attribution` — 400 SV
- `google ads meta ads reporting` — 150 SV

**Structure:**
1. Why single-channel reporting lies to you
2. The cross-channel signals that matter (ROAS vs retention, audience overlap, creative fatigue)
3. How to build a cross-channel reporting system
4. What a daily paid ads brief looks like

**Conversion hook:**
> "Duct correlates signals across Google, Meta, LinkedIn and your CRM automatically. Daily brief in your inbox."
CTA: "Try Paid Ads Intelligence free →" (link to /for-paid-ads)

**Word count:** 2,500 words

---

#### Supporting Post 1: Creative Fatigue Detection — How to Catch It Before It Kills Your ROAS

**URL:** `getduct.ai/blog/creative-fatigue-detection`

**Target keywords:**
- `creative fatigue facebook ads` — 400 SV
- `ad creative fatigue` — 300 SV
- `how to detect creative fatigue` — 150 SV

**Angle:** Specific, technical, useful. Shows what creative fatigue looks like in the data (CTR drop + frequency rise), how to catch it early, and how Duct alerts you automatically.

**Conversion hook:**
> "Duct detects creative fatigue automatically and sends a Slack alert before it tanks your ROAS."
CTA: "Get early access to Paid Ads Intelligence →"

**Word count:** 1,500 words

---

#### Supporting Post 2: How to Read Cross-Channel Signals: Google Ads + Meta + LinkedIn

**URL:** `getduct.ai/blog/cross-channel-signals-google-meta-linkedin`

**Target keywords:**
- `google ads meta combined reporting` — 150 SV
- `cross channel marketing signals` — 100 SV
- `google ads and meta attribution` — 200 SV

**Angle:** Shows a real example: Google search intent feeding Meta retargeting. How to identify audience overlap. How to spot which channel is cannibalising vs compounding.

**Conversion hook:**
> "This analysis takes 4 hours manually. Duct runs it every day and delivers the finding in one line."

**Word count:** 1,500 words

---

## TIER 3 — CONNECTOR PAGES

*One page per integration. Target: "[tool] reporting" and "[tool] weekly digest" keywords. Build after Tier 1 tools and first cluster.*

### Page structure for each (identical template):
1. What data [Tool] gives you
2. What's missing when you use it in isolation
3. What Duct adds: cross-tool synthesis, weekly brief
4. How to connect [Tool] to Duct (OAuth, 2 min)
5. What your first brief looks like

---

### Connector Page 1: Duct + Mixpanel

**URL:** `getduct.ai/integrations/mixpanel`

**Target keywords:**
- `mixpanel reporting` — 400 SV, $3 CPC
- `mixpanel weekly report` — 100 SV
- `mixpanel automated report` — 100 SV
- `ahrefs integrations` — 2,400 SV (Supermetrics ranks for this — opportunity)

**Conversion hook:** "Connect Mixpanel in 2 minutes. First brief in your inbox this Monday."

---

### Connector Page 2: Duct + GA4

**URL:** `getduct.ai/integrations/ga4`

**Target keywords:**
- `ga4 reporting tools` — 300 SV, $5 CPC
- `google analytics automated reports` — 150 SV, $5 CPC
- `ga4 weekly report` — 100 SV

**Conversion hook:** "GA4 shows you the numbers. Duct tells you what they mean."

---

### Connector Page 3: Duct + HubSpot

**URL:** `getduct.ai/integrations/hubspot`

**Target keywords:**
- `hubspot reporting` — 600 SV, $4 CPC
- `hubspot analytics reporting` — 200 SV
- `hubspot weekly report` — 100 SV

**Conversion hook:** "Connect HubSpot and see how your pipeline signals correlate with your product and ad data."

---

### Connector Page 4: Duct + Google Ads

**URL:** `getduct.ai/integrations/google-ads`

**Target keywords:**
- `google ads reporting tool` — 200 SV, $4 CPC
- `automated google ads report` — 150 SV, $5 CPC
- `google ads weekly brief` — 50 SV

---

### Connector Page 5: Duct + Ahrefs

**URL:** `getduct.ai/integrations/ahrefs`

**Target keywords:**
- `ahrefs reporting` — 4,900 SV — Supermetrics ranks here and drives 421 visits. Steal it.
- `ahrefs automated report` — 150 SV
- `ahrefs weekly digest` — low SV, zero competition

---

### Connector Page 6: Duct + Search Console

**URL:** `getduct.ai/integrations/google-search-console`

**Target keywords:**
- `google search console reporting` — 300 SV
- `search console weekly report` — 100 SV
- `gsc automated report` — 100 SV

---

## TIER 4 — COMPARISON PAGES
*Highest converting page type in this space. Visitor is already in buying mode. Build after first two clusters.*

---

### Comparison Page 1: Duct vs Databox

**URL:** `getduct.ai/vs/databox`

**Target keywords:**
- `databox alternative` — 500 SV, $8 CPC — high commercial intent
- `databox vs` — 200 SV
- `alternatives to databox` — 150 SV

**Core argument:** Databox is a dashboard tool. Duct is a brief tool. If you want to look at data, use Databox. If you want to know what to do next, use Duct. Not competitors — different jobs to be done.

**Structure:**
1. What Databox does well (be honest — credibility)
2. Where Databox falls short for your ICP (manual interpretation, no cross-tool synthesis)
3. What Duct does differently (brief not dashboard, synthesis not display)
4. Side-by-side comparison table
5. Who should use which

**Conversion hook:** "Try Duct free. If you want a dashboard back, Databox will still be there."

---

### Comparison Page 2: Duct vs Supermetrics

**URL:** `getduct.ai/vs/supermetrics`

**Target keywords:**
- `supermetrics alternative` — 1,500 SV — Supermetrics own blog ranks for this
- `supermetrics competitors` — 1,070 SV (Supermetrics own page drives this)
- `supermetrics vs` — 400 SV

**Core argument:** Supermetrics moves data from A to B. You still have to interpret it. Duct interprets it for you.

**Structure:** Same as Databox comparison. Be honest about Supermetrics strengths (connector breadth, agency use cases). Hard on the weakness: it's a data pipe, not intelligence.

---

### Comparison Page 3: Duct vs DashThis

**URL:** `getduct.ai/vs/dashthis`

**Target keywords:**
- `dashthis alternative` — 800 SV (DashThis drives most of their own traffic from this)
- `dashthis competitors` — 300 SV

**Core argument:** DashThis is built for agencies reporting to clients. Duct is built for internal growth teams reporting to themselves. Different audience, different job.

---

## CONTENT PRODUCTION NOTES

### Claude prompts for each content type

**For pillar pages:**
> Write a comprehensive guide titled "[title]" targeting the keyword "[primary keyword]". ICP: Growth PMs and Performance Marketers at 20–200 person SaaS companies without a dedicated data team. Tone: direct, opinionated, practitioner-level. No fluff. Structure: [paste structure above]. Word count: [X]. End with a conversion section positioning Duct as the automated solution. CTA: "[hook text]". Do not mention Duct until the final section — earn the pitch.

**For supporting posts:**
> Write a [word count] word blog post titled "[title]" targeting keyword "[primary keyword]". Tone: practitioner, direct, no padding. ICP: [role] at 20–200 person SaaS without a data team. Angle: [paste angle]. End with this conversion hook: "[hook text]" and this CTA: "[CTA text]" linking to [URL].

**For connector pages:**
> Write a product integration page for "Duct + [Tool]". Structure: what [Tool] gives you, what's missing in isolation, what Duct adds, how to connect (OAuth, 2 min), what the first brief looks like. Tone: concise, specific, no marketing fluff. Target keyword: "[keyword]". End with CTA: "[hook text]".

**For comparison pages:**
> Write a comparison page: "Duct vs [Competitor]". Be honest about [Competitor]'s strengths. Hard on the specific weakness: [weakness]. Core argument: [argument]. Structure: what [competitor] does well, where it falls short for growth teams, what Duct does differently, side-by-side table, who should use which. No trash talk. Credibility through honesty.

---

## TRACKING & SUCCESS METRICS

| Metric | 30 days | 60 days | 90 days |
|--------|---------|---------|---------|
| Organic clicks | >50 | >200 | >500 |
| Tool page visits | >100 | >400 | >1,000 |
| Blog → beta signups | >5 | >20 | >50 |
| Keywords ranking (any position) | >20 | >75 | >150 |
| Pages indexed | >10 | >20 | >35 |

**Nothing ranks before 60 days. Do not measure organic traffic before then.**

---

## QUICK WINS TO DO FIRST

Before writing a single word of content, do these three things this week:

1. **Submit sitemap to Google Search Console** — `getduct.ai/sitemap.xml` — if not already done
2. **Add blog schema markup** — Article schema on every post so Google understands content type
3. **Internal linking plan** — Every existing landing page (/for-paid-ads, /for-product-intelligence, /for-organic-growth) should link to the relevant cluster pillar page once published

---

*Last updated: April 2026 | Next review: when first 10 posts are published*