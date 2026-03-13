# Duct — Paid Growth Plan

> Paid ads at this stage are a validation tool, not a scale engine. The goal is to find 1–2 channels where cost per acquisition is sustainable before committing meaningful budget. Every dollar spent should be measurable. No brand awareness. No spray and pray.

---

## Table of Contents

0. [What Paid Growth Is (and Isn't) at This Stage](#0-what-paid-growth-is-and-isnt-at-this-stage)
1. [The Foundation: Before Spending Anything](#1-the-foundation-before-spending-anything)
2. [Channel Strategy](#2-channel-strategy)
3. [Creative and Copy Framework](#3-creative-and-copy-framework)
4. [Retargeting Setup](#4-retargeting-setup)
5. [The $1,500/Month Starter Stack](#5-the-1500month-starter-stack)
6. [Measurement and Decision Framework](#6-measurement-and-decision-framework)
7. [The Founder-Led Ads Playbook](#7-the-founder-led-ads-playbook)
8. [What Not to Do](#8-what-not-to-do)
9. [90-Day Paid Growth Roadmap](#9-90-day-paid-growth-roadmap)
- [Appendix: Ad Copy Templates and UTM Convention](#appendix-ad-copy-templates-and-utm-convention)

---

## 0. What Paid Growth Is (and Isn't) at This Stage

Most early-stage SaaS teams approach paid ads the wrong way. They see a budget line, pick a channel, and start spending — then wonder why the results don't justify the cost.

Here's the right mental model for Duct's current stage:

**Paid ads are a signal amplifier, not a demand generator.** They work best when you already know your message resonates (because organic and community distribution have validated it) and you want to reach more of the same people, faster, at a known cost.

Duct has two live verticals with validated landing pages and validated messaging. The organic channels (community, LinkedIn, blog) are in motion. Paid is the next lever — but the goal is not to scale yet. The goal is to:

1. Validate that paid acquisition is viable (i.e., that CAC < LTV at a meaningful margin)
2. Identify which 1–2 channels produce the best-quality sign-ups at the lowest cost
3. Build the infrastructure (tracking, creative testing, audience data) to scale when ready

**The CAC target:** At $299/month (Growth tier), a 6-month payback period means a maximum sustainable CAC of ~$200–300. At $499/month (Pro tier), the ceiling is ~$400–500. Start with the Growth tier CAC as the benchmark — if a channel can't hit sub-$300 CAC with good-quality sign-ups, it's not worth scaling.

**The starting budget:** $1,500/month across 3 channels. This is enough to get statistically meaningful data from LinkedIn and Google Search within 30 days. It is not enough to "see results" in the traditional sense — set expectations accordingly. The output of month 1 is learning, not pipeline.

---

## 1. The Foundation: Before Spending Anything

Do not spend a dollar on paid traffic until this infrastructure is in place. Paid traffic without conversion tracking is burning money.

### 1.1 Conversion tracking

Two conversion events need to be firing correctly in GA4 before any paid campaign launches:

**Event 1: `beta_signup`**
- Triggers: when a user submits the early access form on `/for-organic-growth` or `/for-product-intelligence`
- Implementation: GA4 event via GTM (container `GTM-PKL589SW` is already installed)
- In GTM: create a Form Submission trigger on the Google Form embed, fire a GA4 Event tag with event name `beta_signup` and parameter `vertical` = `organic_growth` or `product_intelligence`
- Mark this as a GA4 Conversion in the GA4 admin panel

**Event 2: `pilot_agreement`**
- Triggers: when a user reaches the pilot confirmation state (email, calendar booking, or explicit form)
- This is the downstream conversion — beta sign-up is the top of the paid funnel, pilot agreement is the bottom
- Even if this is manually tracked in a spreadsheet initially, log it with the source/medium so you can tie it back to which paid channel produced it

**Verify before launch:** Use GA4 DebugView to confirm both events fire correctly. Then confirm they appear as conversions in the Google Ads and LinkedIn conversion dashboards (requires linking GA4 to both ad platforms).

### 1.2 UTM tagging convention

Every paid link must be tagged from day one. Attribution gets messy fast — a consistent convention prevents it.

```
utm_source    = linkedin | google | reddit
utm_medium    = paid-social | paid-search | paid-social
utm_campaign  = [vertical]-[objective]
               e.g. organic-growth-beta | product-intel-beta
utm_content   = [ad-format]-[creative-variant]
               e.g. single-image-hook1 | lead-gen-outcome2
utm_term      = [keyword] (Google Search only)
```

**Build all UTM links in a shared sheet** before campaign launch. Never let a campaign go live without tagged URLs — GA4 will attribute the traffic as direct/none and you'll lose all channel-level data.

### 1.3 Landing page requirements

The existing vertical pages (`/for-organic-growth` and `/for-product-intelligence`) are solid starting points for paid traffic. They have:
- Clear, pain-led headlines ("Stop publishing blind. Start compounding.")
- Specific use cases that match ICP search intent
- A single CTA with scarcity framing ("14 spots remaining")

**Do not send paid traffic to the homepage.** Always send to the vertical-specific page. The homepage is broad by design; paid traffic converts best on specificity.

**One thing to test:** Add a short "How it works" section or a 60-second demo video above the fold on each landing page. Paid traffic is colder than organic — they need more immediate context than someone who found you via a blog post or community share.

### 1.4 Define your CAC ceiling before launch

Write these numbers down and share them with anyone involved in running the ads:

| Tier | MRR | 6-month LTV | Max CAC (6-mo payback) |
|---|---|---|---|
| Growth | $299/mo | $1,794 | $300 |
| Pro | $499/mo | $2,994 | $500 |

If a channel is producing sign-ups at CPL > $150 after 30 days, and those sign-ups are not converting to pilots at >15%, the channel economics do not work. Stop spending and diagnose before continuing.

---

## 2. Channel Strategy

### Priority 1 — LinkedIn Ads

**Why LinkedIn first:** The ICP — Growth PMs and Growth Marketers at 20–200 person SaaS — is reachable on LinkedIn with surgical precision. You can target by job title, company size, industry, and seniority simultaneously. No other platform gives you this level of B2B targeting without wasted impressions.

**The targeting setup:**

```
Campaign 1: Organic Growth Vertical
  Job Titles: Growth Marketer, Head of Growth, SEO Manager,
              Content Strategist, Content Marketing Manager,
              Growth Lead, Marketing Manager
  Company Size: 11–200 employees
  Industry: Software/Technology, Internet
  Location: US, UK, Canada, Australia
  Exclude: Students, Interns

Campaign 2: Product Intelligence Vertical
  Job Titles: Product Manager, Growth PM, Senior PM,
              Head of Product, VP Product, Product Lead,
              Product Marketer
  Company Size: 11–200 employees
  Industry: Software/Technology, Internet
  Location: US, UK, Canada, Australia
  Exclude: Students, Interns
```

**Recommended formats:**

- **Single Image Ad** — for driving traffic to the landing page. Lower friction than video for a cold audience. Use the problem-hook headlines from the landing pages.
- **Lead Gen Form** — for capturing beta sign-up email directly in LinkedIn without leaving the platform. Higher conversion rate than click-through for cold audiences. Connect the form to your email system via Zapier.

Start with Single Image Ads in week 1–2 (easier to test creative quickly). Add Lead Gen Forms in week 3 once you have a baseline CTR.

**Budget:** $800/month ($400 per vertical campaign). Set bids to Maximum Delivery initially — let LinkedIn optimise. Switch to Manual CPC if you're burning through budget too fast without conversions.

**Expected benchmarks:**
- CTR: 0.4–0.8% (B2B average; above 0.8% is strong)
- CPL via Lead Gen Form: $40–90
- CPL via click-through: $60–120 (depends on landing page conversion rate)

**The LinkedIn learning period:** LinkedIn needs 50 conversion events per ad set to exit the learning phase and optimise properly. At CPL of $60, that's $3,000 of spend. You won't exit the learning phase in month 1 — that's normal. Focus on CPL trend direction, not absolute numbers.

---

### Priority 2 — Google Search Ads

**Why Google Search:** LinkedIn shows ads to people who may or may not be thinking about your problem right now. Google Search captures people who are actively searching for a solution — the highest commercial intent available. The trade-off: the specific keywords for Duct's category have low search volume. You won't get scale here, but the clicks you do get are highly qualified.

**Keyword groups by vertical:**

**Organic Growth Campaign:**

| Match Type | Keyword | Intent |
|---|---|---|
| Exact | [automated seo reporting] | High — looking for the product |
| Exact | [seo tool integration] | High — integration pain point |
| Exact | [connect search console ahrefs] | High — specific workflow problem |
| Phrase | "seo reporting automation" | High |
| Phrase | "cross-tool seo analytics" | High |
| Exact | [weekly seo brief template] | Med-High — template intent |
| Exact | [seo brief automation] | High |

**Product Intelligence Campaign:**

| Match Type | Keyword | Intent |
|---|---|---|
| Exact | [product analytics automation] | High |
| Exact | [automated pm reporting] | High |
| Exact | [mixpanel reporting tool] | High |
| Phrase | "product intelligence tool" | High |
| Phrase | "cross-tool product analytics" | High |
| Exact | [pm weekly brief] | Med-High |
| Exact | [connect mixpanel intercom] | High |

**Match types:** Exact and Phrase only. Do not use Broad Match — it will drain budget on irrelevant queries. Add negative keywords from day one: "free," "enterprise," "tutorial," "what is," "definition" (unless you have content targeting informational intent).

**Ad structure:**

Each campaign gets 1 ad group per keyword theme. Each ad group gets 3 responsive search ads with different headline combinations. Google will rotate and learn which combinations perform.

**Headlines to write (15 available slots — use 8–10):**
- "Stop Tab-Switching. Start Knowing." (mirrors landing page)
- "Your SEO Tools Don't Talk to Each Other"
- "Automated Cross-Tool SEO Reports"
- "Weekly SEO Brief. Automated."
- "Connect Search Console, Ahrefs + GA4"
- "Product Analytics. Synthesised Automatically."
- "Mixpanel + Intercom + Linear. One Brief."
- "Free Beta — 14 Spots Remaining"
- "Get Your First Duct Brief Free"
- "SEO Intelligence for Growth Teams"

**Budget:** $500/month ($250 per vertical campaign). Set bids to Maximize Conversions once the `beta_signup` GA4 conversion is linked. In the first 2 weeks, use Manual CPC with bids of $5–8 to control spend while you gather data.

**Expected benchmarks:**
- CPC: $4–12 (B2B SaaS, low-competition category keywords)
- CTR: 3–8% (Search ads have naturally higher CTR than display)
- Conversion rate (landing page): 10–25% (depends on how well keyword → ad → landing page alignment holds)

---

### Priority 3 — Reddit Ads (test only)

**Why Reddit:** The ICP is highly active on r/SEO (580K members) and r/ProductManagement (200K members). Reddit Ads allow subreddit-level targeting, which means you can put Duct ads directly in front of people already having conversations about your exact problem.

**The caveat:** Reddit users are skeptical of ads. The format that works best is Promoted Posts that look and feel like organic community content — not polished brand ads. The conversion rate is typically lower than LinkedIn or Google Search, and the attribution is harder to measure.

**Targeting setup:**
```
Ad Set 1: Subreddits = r/SEO, r/juststart, r/bigseo
Ad Set 2: Subreddits = r/ProductManagement, r/productdesign, r/startups

Format: Promoted Post (looks like an organic Reddit post)
Headline style: Community-native, problem-first, no corporate language
```

**Budget:** $200/month. This is a test — keep it small. The primary value at this stage is awareness within communities you're already working organically. It reinforces the community presence rather than replacing it.

---

### Channels to skip (for now)

| Channel | Why not yet |
|---|---|
| Meta/Facebook | Wrong context — personal browsing mode. B2B conversion rates are poor without retargeting existing audiences. |
| Twitter/X Ads | Conversion tracking is unreliable. Platform volatility makes it hard to build on. |
| Display/Programmatic | Too broad. No job title or intent targeting. Brand awareness play — not appropriate before product-market fit. |
| YouTube | High production cost for creative. Brand awareness, not direct response. Post-Series A. |

---

## 3. Creative and Copy Framework

### The 3 ad formats that work for B2B SaaS beta

**Format 1 — Problem Hook**
Lead with the specific pain. Make the ICP nod their head in the first sentence. Do not mention the product in the hook — earn the reader's attention first.

> *"You pull Search Console on Monday. Ahrefs in a separate tab. GA4 in another. By the time you've reconciled them, it's Tuesday."*

**Format 2 — Concrete Outcome**
Lead with the specific result. Especially effective for retargeting (someone already knows the problem — show them what life looks like with it solved).

> *"Every Monday: a cross-tool SEO brief covering your rankings, traffic, and conversion gaps. Automated. In your inbox before standup."*

**Format 3 — Social Proof / Authority**
Lead with credibility. Works best once you have pilot customers or specific data points. Hold this format until you have 1–2 customer quotes or usage stats.

> *"Growth teams at [Company] cut their Monday data pull from 4 hours to 10 minutes."*

### The creative testing sequence

Do not launch 10 ad variations at once. You won't have the budget to generate statistically meaningful data across all of them.

**Week 1–2:** Launch 3 variations of Format 1 (Problem Hook) with the same CTA. Identical targeting. Let them run.

**Week 3:** Kill the lowest-CTR variation. Launch 2 variations of Format 2 (Concrete Outcome). Now you're testing problem hook vs. outcome hook.

**Week 4:** Identify the winning format. Test 2 CTA variations on the winner.

**The CTA options to test:**
- "Join the beta →" (lowest friction, vague on value)
- "Get your first brief free →" (higher friction, clearer value)
- "See how it works →" (lowest commitment, educational)

Start with "Get your first brief free →" — it mirrors the product's core value delivery (the Monday brief) and sets expectation before sign-up.

### Ad copy for each vertical

**Organic Growth — Problem Hook:**

> **Headline:** Your SEO tools don't talk to each other.
>
> **Body:** Search Console, Ahrefs, and GA4 each tell a different story. No one reads them together. Duct connects them and delivers the cross-tool brief your Monday needs.
>
> **CTA:** Get your first brief free →

**Organic Growth — Concrete Outcome:**

> **Headline:** Weekly SEO brief. Automated.
>
> **Body:** Know exactly which actions will move organic growth this week — before your standup. Duct reads across your Search Console, Ahrefs, and GA4 and surfaces the signals that matter.
>
> **CTA:** Join the beta →

**Product Intelligence — Problem Hook:**

> **Headline:** Analytics says adoption is up. Intercom says users are confused.
>
> **Body:** When your tools disagree, you don't know which to trust. Duct reads across Mixpanel, Intercom, Linear, and Salesforce — and surfaces what they're collectively trying to tell you.
>
> **CTA:** Get your first brief free →

**Product Intelligence — Concrete Outcome:**

> **Headline:** Stop tab-switching. Start knowing.
>
> **Body:** Every Monday: a synthesised brief across your entire product stack. What changed, what it means, and what to do about it. Automated.
>
> **CTA:** Join the beta →

---

## 4. Retargeting Setup

Every visitor who lands on `/for-organic-growth` or `/for-product-intelligence` and does not complete the sign-up form is a warm lead. Retargeting these visitors costs 3–5x less per conversion than cold acquisition.

### Building the retargeting audiences

**LinkedIn Matched Audiences:**
- Install the LinkedIn Insight Tag on the site (add the script tag to the `<head>` of both vertical pages via GTM)
- Create a Website Audience: Visited `/for-organic-growth` in the last 30 days
- Create a Website Audience: Visited `/for-product-intelligence` in the last 30 days
- Exclude: Anyone who completed the `beta_signup` conversion event

**Google Remarketing:**
- GA4 → Audiences → Create audience: "Visited organic growth page, no conversion"
- Import this audience into Google Ads for remarketing

**Important threshold:** LinkedIn requires a minimum of 300 matched members before a retargeting audience can serve. At low traffic volumes, it may take 4–6 weeks to reach this threshold. Track the audience size in LinkedIn Campaign Manager weekly. Until you hit 300, do not allocate budget to LinkedIn retargeting.

### Retargeting creative

Retargeting creative should be different from cold acquisition creative. The visitor already knows the problem — don't restate it. Lead with the outcome or a specific differentiator.

**Retargeting ad angles:**
- "Still reconciling Search Console and Ahrefs manually?" (callback to the problem they came in for)
- "14 spots remaining in the beta — grab yours." (scarcity/urgency)
- "See what a Duct brief looks like." (reduce uncertainty with a concrete preview)

**Retargeting budget:** 20–25% of total paid budget. At $1,500/month total, that's $300–375/month on retargeting. Split evenly between LinkedIn and Google once both audiences are above threshold.

---

## 5. The $1,500/Month Starter Stack

This is the prescriptive month 1 allocation. Run exactly this before adjusting anything.

### Budget allocation

| Channel | Budget | % | Purpose |
|---|---|---|---|
| LinkedIn Ads | $800 | 53% | Primary cold acquisition |
| Google Search | $500 | 33% | High-intent bottom-of-funnel |
| Reddit Ads | $200 | 13% | Community awareness test |
| **Total** | **$1,500** | **100%** | |

### LinkedIn campaign structure

```
Account
└── Campaign Group: Duct Beta Acquisition
    ├── Campaign: Organic Growth Vertical
    │   ├── Budget: $400/month ($13/day)
    │   ├── Objective: Website Visits or Lead Generation
    │   ├── Ad Set: Growth Marketers (targeting as defined in §2)
    │   └── Ads: 3 × Single Image (Problem Hook variants)
    │
    └── Campaign: Product Intelligence Vertical
        ├── Budget: $400/month ($13/day)
        ├── Objective: Website Visits or Lead Generation
        ├── Ad Set: Product Managers (targeting as defined in §2)
        └── Ads: 3 × Single Image (Problem Hook variants)
```

### Google Search campaign structure

```
Account
└── Campaign: Organic Growth — Search
│   ├── Budget: $250/month ($8/day)
│   ├── Bidding: Maximize Conversions (linked to beta_signup event)
│   ├── Ad Group: SEO Reporting Automation
│   │   ├── Keywords: [automated seo reporting], [seo tool integration], "seo reporting automation"
│   │   └── Ads: 3 × RSA with problem-hook headlines
│   └── Ad Group: Cross-Tool SEO
│       ├── Keywords: [connect search console ahrefs], "cross-tool seo analytics"
│       └── Ads: 3 × RSA with integration-focused headlines
│
└── Campaign: Product Intelligence — Search
    ├── Budget: $250/month ($8/day)
    ├── Bidding: Maximize Conversions
    ├── Ad Group: Product Analytics Automation
    │   ├── Keywords: [product analytics automation], [automated pm reporting], "product intelligence tool"
    │   └── Ads: 3 × RSA with problem-hook headlines
    └── Ad Group: Tool Integration
        ├── Keywords: [connect mixpanel intercom], [mixpanel reporting tool]
        └── Ads: 3 × RSA with integration-focused headlines
```

### The weekly 15-minute check-in

Every Monday, run through this in order:

1. **GA4 → Acquisition → Traffic acquisition:** How many sessions from each paid channel? How many `beta_signup` conversions?
2. **LinkedIn Campaign Manager:** CTR per ad, CPL per campaign. Any ad with CTR < 0.3% after 500 impressions → pause it.
3. **Google Ads:** Average CPC, conversion rate per ad group. Any keyword with 0 conversions after $30 spend → add to negative list or pause.
4. **Action:** One change per channel maximum per week. Do not make multiple simultaneous changes — you won't be able to attribute results.

---

## 6. Measurement and Decision Framework

### The 4 metrics that matter

| Metric | Where to find it | Good | Concerning |
|---|---|---|---|
| CTR | LinkedIn/Google Ads | >0.5% (LinkedIn), >3% (Search) | <0.3% (LinkedIn), <1.5% (Search) |
| CPL | GA4 + spend data | <$80 | >$120 |
| Trial→Pilot conversion | Manual tracking | >15% | <8% |
| Blended CAC | Total spend ÷ paid pilots | <$300 | >$500 |

**Note on attribution:** LinkedIn and Google Ads both report conversions using their own attribution windows (often 30-day click, 1-day view). These numbers will be higher than what GA4 reports. Use GA4 + UTMs as the source of truth for all decisions. The ad platform dashboards are useful for creative and targeting optimisation, not for CAC calculations.

### The 30/60/90 decision framework

**30-day checkpoint:**
- Kill any LinkedIn ad set with CPL > $120 and CTR < 0.4% after 500+ impressions
- Kill any Google keyword with 0 conversions after $30 spend
- Assess: is retargeting audience > 300 on LinkedIn? If yes, launch retargeting campaigns.
- Decision question: is at least 1 channel producing sign-ups at CPL < $100?

**60-day checkpoint:**
- If 1+ channel shows CPL < $80 with 3+ conversions → double its budget
- If both channels are CPL > $120 → do not increase budget; iterate creative first
- Begin tracking Trial→Pilot conversion rate per channel. If LinkedIn sign-ups convert to pilots at 2× the rate of Google, LinkedIn has better lead quality even at higher CPL.
- Decision question: do the economics work at 2× current spend?

**90-day checkpoint:**
- If blended CAC < $250 with 5+ pilots → begin scaling. Move LinkedIn to $2,000/month, Google to $1,000/month.
- If blended CAC > $400 → pause paid, diagnose. The issue is usually: landing page conversion rate, lead quality (targeting), or pilot conversion rate (product/sales).
- Decision question: ready to add Sales/RevOps vertical creative to the mix?

### The LTV maths

At current pricing:

| Tier | MRR | 12-mo LTV | LTV:CAC at $250 CAC |
|---|---|---|---|
| Growth ($299/mo) | $299 | $3,588 | 14:1 |
| Pro ($499/mo) | $499 | $5,988 | 24:1 |

Even at a $250 CAC and 12-month retention, the economics are strong. The risk at this stage is not LTV — it's whether the trial→paid conversion rate is high enough to make the CAC calculation real rather than theoretical. Track it from the first paid pilot.

---

## 7. The Founder-Led Ads Playbook

This is the lowest-friction, highest-ROI paid channel available to Duct right now — and most early-stage founders skip it entirely.

**The insight:** LinkedIn's Thought Leadership Ads format lets you boost an existing organic post from a personal profile using the company's ad budget. These posts perform dramatically better than traditional brand ads because:
- They appear as a personal post in the feed (less ad fatigue)
- The social proof (likes, comments) from the organic run carries over
- The ICP trusts a founder's perspective more than a brand's

**How to identify posts worth boosting:**
1. Any organic LinkedIn post from the founder with engagement rate > 3% (likes + comments ÷ impressions)
2. Posts where commenters have ICP job titles (PM, Growth Marketer, SEO Manager)
3. Posts that describe the core problem Duct solves — not product posts

**How to boost:**
- LinkedIn Campaign Manager → Create Campaign → Thought Leadership Ad
- Select the organic post → Set targeting (same as campaign 1 or 2 above) → Set budget $5–10/day
- Run for 2 weeks, then assess CPL vs. cold creative

**Budget allocation:** Take $100–150/month from the Reddit test budget and allocate to Thought Leadership Ads once you have 2–3 qualifying organic posts. This is likely to outperform Reddit for lead quality.

**The content → ads flywheel:** The best posts to boost are the ones that already have organic engagement. This means the founder posting consistently on LinkedIn is a direct input to paid performance. The two are not separate strategies — organic LinkedIn performance informs which paid creative to produce.

---

## 8. What Not to Do

These are the mistakes that drain early-stage paid budgets fastest.

**Don't run brand awareness campaigns.** Duct has not yet achieved product-market fit across its verticals. Brand awareness spend (CPM campaigns, display, YouTube) is designed to create demand, not capture it. Every dollar should have a measurable path to conversion.

**Don't use Broad Match keywords in Google.** Broad Match will serve your ads for "SEO tools," "analytics software," "product management" — terms that look relevant but have no commercial intent toward Duct's specific value prop. Use Exact and Phrase only until you have enough conversion data to consider Broad Match Modifier.

**Don't drive paid traffic to the homepage.** The homepage (`/index.html`) is designed to introduce Duct broadly. Paid traffic converts best on specificity. Always link to the vertical-specific landing page that matches the ad's ICP.

**Don't run paid without conversion tracking.** If `beta_signup` and `pilot_agreement` events are not firing correctly in GA4 and imported into the ad platforms, you have no signal to optimise against. The campaign will optimise for clicks, not conversions. Verify tracking before launch, not after.

**Don't optimise for CPM or CTR alone.** These are vanity metrics at this stage. A 2% CTR that produces no sign-ups is worth less than a 0.4% CTR that converts to pilots. CPL and CAC are the only metrics that matter for budget decisions.

**Don't scale before validating CAC across 20+ conversions per channel.** 5 conversions on a channel tells you nothing statistically meaningful. 20+ conversions gives you a reliable CPL. Scale only when you have a channel producing 20+ sign-ups at sub-$100 CPL and the downstream pilot conversion rate is above 10%.

---

## 9. 90-Day Paid Growth Roadmap

### Month 1 — Setup and First Signal

**Goal:** Get every dollar tagged, tracked, and generating data. The output is learning, not pipeline.

| Week | Action |
|---|---|
| 1 | Set up GA4 conversion events (`beta_signup`, `pilot_agreement`). Verify in DebugView. Link GA4 to Google Ads and LinkedIn. |
| 1 | Build UTM sheet. Create all UTM links for all planned ads. |
| 1 | Launch LinkedIn campaigns (both verticals, $400 each, 3 Problem Hook ad variants). |
| 2 | Launch Google Search campaigns (both verticals, $250 each, Exact/Phrase match). |
| 2 | Launch Reddit Promoted Posts ($200, subreddit-targeted). |
| 3 | First weekly check-in. Pause underperforming LinkedIn ads (CTR < 0.3% after 500 impressions). |
| 4 | 30-day checkpoint. Assess CPL by channel. Kill underperformers. Identify retargeting threshold status. |

**Month 1 success signal:** At least 1 channel producing sign-ups at CPL < $120. Even 3–5 sign-ups total is acceptable — the goal is baseline data.

### Month 2 — Optimise and Retarget

**Goal:** Improve CPL on the winning channel. Introduce retargeting.

| Week | Action |
|---|---|
| 5 | Launch retargeting if LinkedIn audience > 300. Creative: scarcity/outcome angle. |
| 5 | Test Concrete Outcome creative format alongside Problem Hook on best-performing channel. |
| 6 | Kill Reddit if CPL > $150 with < 3 conversions. Reallocate to LinkedIn Thought Leadership Ads. |
| 7 | 60-day checkpoint. Double budget on best-performing channel. |
| 8 | Begin tracking Trial→Pilot conversion by channel. Identify lead quality differences. |

**Month 2 success signal:** CPL trending below $100 on at least 1 channel. Retargeting audience active.

### Month 3 — Scale and Extend

**Goal:** Validate scalability of the winning channel. Begin creative for next vertical.

| Week | Action |
|---|---|
| 9 | If CAC < $250 validated → scale winning channel to 2× budget. |
| 10 | Begin producing creative for Sales/RevOps vertical (to be ready for when that landing page launches). |
| 11 | 90-day checkpoint. Go/no-go on scaling. |
| 12 | Retrospective: which channel produced the highest-quality pilots? What was the blended CAC? What creative format won? Document for month 4 brief. |

**Month 3 success signal:** 5+ paid pilots attributable to paid channels. Blended CAC documented and below $300.

---

## Appendix: Ad Copy Templates and UTM Convention

### LinkedIn Ad Templates — Organic Growth Vertical

**Template A — Problem Hook:**
```
Headline (max 70 chars):
Your SEO tools don't talk to each other.

Introductory text (max 150 chars):
Search Console, Ahrefs, GA4 — three tabs, three different stories.
Duct connects them and surfaces what they're collectively trying to tell you.

CTA: Get your first brief free →
Destination: /for-organic-growth?utm_source=linkedin&utm_medium=paid-social&utm_campaign=organic-growth-beta&utm_content=single-image-hook-a
```

**Template B — Concrete Outcome:**
```
Headline:
Weekly SEO brief. Automated. In your inbox Monday.

Introductory text:
Know exactly which actions will move organic growth this week —
before your standup. No spreadsheets. No tab-switching.

CTA: Join the beta →
Destination: /for-organic-growth?utm_source=linkedin&utm_medium=paid-social&utm_campaign=organic-growth-beta&utm_content=single-image-outcome-b
```

**Template C — Specificity Hook:**
```
Headline:
Why is organic traffic up but signups flat?

Introductory text:
If your Search Console and GA4 are telling different stories,
you're optimising in the dark. Duct reads both — and tells you what's actually going on.

CTA: Get your first brief free →
Destination: /for-organic-growth?utm_source=linkedin&utm_medium=paid-social&utm_campaign=organic-growth-beta&utm_content=single-image-hook-c
```

---

### LinkedIn Ad Templates — Product Intelligence Vertical

**Template A — Problem Hook:**
```
Headline:
Analytics says adoption is up. Intercom says users are confused.

Introductory text:
When your tools disagree, you don't know which to trust.
Duct reads across Mixpanel, Intercom, Linear, and Salesforce — and tells you what they collectively mean.

CTA: Get your first brief free →
Destination: /for-product-intelligence?utm_source=linkedin&utm_medium=paid-social&utm_campaign=product-intel-beta&utm_content=single-image-hook-a
```

**Template B — Concrete Outcome:**
```
Headline:
Stop tab-switching. Start knowing.

Introductory text:
Every Monday: a synthesised brief across your entire product stack.
What changed, what it means, and what to do about it. Automated.

CTA: Join the beta →
Destination: /for-product-intelligence?utm_source=linkedin&utm_medium=paid-social&utm_campaign=product-intel-beta&utm_content=single-image-outcome-b
```

**Template C — Specificity Hook:**
```
Headline:
3 hours a week on data that should take 10 minutes.

Introductory text:
The average PM spends Monday morning pulling numbers from Mixpanel,
Intercom, and Linear just to decide what to work on.
Duct delivers those answers automatically — before standup.

CTA: Get your first brief free →
Destination: /for-product-intelligence?utm_source=linkedin&utm_medium=paid-social&utm_campaign=product-intel-beta&utm_content=single-image-hook-c
```

---

### Google Search Headline Sets

**Organic Growth Campaign — Ad Group: SEO Reporting Automation**
```
Headlines (pick 8–10):
1. Automated Cross-Tool SEO Reports
2. Stop Pulling SEO Data Manually
3. Search Console + Ahrefs + GA4. One Brief.
4. Weekly SEO Brief. Automated.
5. Free Beta — 14 Spots Remaining
6. Get Your First Duct Brief Free
7. SEO Intelligence for Growth Teams
8. Your SEO Tools. Synthesised.
9. Know What to Work On. Every Monday.
10. Connect Your SEO Stack in 10 Minutes

Descriptions:
1. Duct reads across your Search Console, Ahrefs, and GA4 — and delivers a cross-tool brief before your Monday standup. Free beta.
2. Stop spending 4 hours a week reconciling SEO data. Duct synthesises it automatically and surfaces what actually needs your attention.
```

**Product Intelligence Campaign — Ad Group: Product Analytics Automation**
```
Headlines:
1. Automated PM Intelligence Briefs
2. Mixpanel + Intercom + Linear. One Brief.
3. Stop Tab-Switching. Start Knowing.
4. Cross-Tool Product Analytics
5. Weekly PM Brief. Automated.
6. Free Beta — 14 Spots Remaining
7. Product Intelligence for PMs
8. Know What's Happening Across Your Stack
9. Get Your First Duct Brief Free
10. Connect Your Product Tools in 10 Min

Descriptions:
1. Duct reads across Mixpanel, Intercom, Linear, and Salesforce — and delivers the cross-tool story they're collectively trying to tell you. Free beta.
2. Stop spending 3 hours a week pulling product data manually. Duct synthesises your entire stack and surfaces what needs your attention — every Monday.
```

---

### UTM Naming Convention Reference

```
utm_source values:
  linkedin
  google
  reddit

utm_medium values:
  paid-social     (LinkedIn, Reddit)
  paid-search     (Google Search)

utm_campaign values:
  organic-growth-beta
  product-intel-beta
  sales-revops-beta     (future)

utm_content values:
  single-image-hook-a
  single-image-hook-b
  single-image-hook-c
  single-image-outcome-a
  single-image-outcome-b
  lead-gen-hook-a
  lead-gen-outcome-a
  thought-leadership-[post-date]
  retargeting-scarcity
  retargeting-outcome

utm_term values (Google Search only):
  Use the exact keyword that triggered the ad
  (Google auto-populates this with ValueTrack parameter {keyword})
  Add {keyword} to the URL: utm_term={keyword}
```

---

*CAC targets throughout this document are based on the $299/month Growth tier pricing. Adjust targets upward proportionally if the majority of paid sign-ups convert to the $499 Pro tier.*
