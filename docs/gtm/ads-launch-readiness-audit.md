# Duct Ads Launch Readiness Audit + Lean Google Ads Plan

_Date: 2026-04-08_

This document is a launch-readiness audit for Duct's paid acquisition push, with emphasis on:

- page copy, landing-page story, hero/first fold, and CTA quality
- conversion measurement and tracking
- SEO tags and indexing
- AEO / LLM discoverability
- mobile responsiveness and loading-time risk
- a practical Google Ads launch plan for a **$350/month** budget

It combines:

- repository review of the live marketing implementation
- existing Duct GTM docs
- external benchmarking from Google Ads guidance and adjacent SaaS landing pages

---

## 1. Bottom line

### Verdict

**Duct is not ready to launch Google Ads + LinkedIn Ads + X Ads together today.**

### Recommended launch posture

- **Conditional go:** one tightly scoped **Google Search** experiment only
- **Hold:** **LinkedIn Ads** until conversion tracking and proof are stronger
- **Hold:** **X / Twitter Ads** until there is a better offer, cleaner attribution, and more budget

### Why

1. **The budget is too small for three channels.**  
   $350/month is roughly **$11.50/day**. Split across three channels, none of them will gather enough signal to teach you much.

2. **Tracking is not ads-ready yet.**  
   The site currently pushes a generic `form_submit` event in `site/assets/duct.js`, but the existing GTM plan in `docs/gtm/paid-growth-plan.md` expects named conversion events like `beta_signup` and `pilot_agreement`.

3. **Cold-traffic conversion proof is still thin.**  
   The vertical landing pages have strong pain framing, but they still rely heavily on product promise and demo depth rather than immediate above-the-fold proof.

4. **The CTA is too generic for paid traffic.**  
   "Get early access" is easy to understand, but weaker than a value-specific CTA like "Get my first brief" or "See the paid ads brief."

### Overall readiness score

| Area | Status | Score | Summary |
|---|---|---:|---|
| Page copy / story / CTA | Yellow | 5.5/10 | Strong pain framing, but not enough proof or value-specific CTA for cold traffic |
| Measurement / conversion tracking | Red | 3.5/10 | GTM exists, but conversion design is too generic for ad optimization |
| SEO tags / indexing | Yellow | 7/10 | Core tags and robots are in place; blog URL/canonical setup is weaker than ideal |
| AEO discoverability | Yellow-Red | 4.5/10 | Good crawl allowance, but not enough answer-first public content or off-site authority |
| Mobile / loading-time risk | Yellow | 6.5/10 | Static site helps; some JS/font choices still create avoidable risk |
| **Overall** | **Yellow-Red** | **5.4/10** | Launch one search experiment only, not a three-channel rollout |

---

## 2. What was reviewed

### Repository inputs

- `site/index.html`
- `site/for-paid-ads.html`
- `site/for-product-intelligence.html`
- `site/for-organic-growth.html`
- `site/assets/duct.js`
- `site/assets/config.js`
- `site/blog/post.html`
- `site/robots.txt`
- `site/sitemap.xml`
- `app/src/app/layout.js`
- `app/src/components/ProductAnalytics.jsx`
- `app/src/lib/analytics-client.js`
- `docs/gtm/paid-growth-plan.md`
- `docs/gtm/seo-content-plan.md`
- `.github/scripts/check-pages.py`

### Validation run

- `.github/scripts/check-pages.py` passed with **0 errors**

### External references reviewed

- Google Ads Help: budgets, bidding, spend management
- Ahrefs: AEO and ChatGPT visibility guidance
- Unbounce: CTA and CRO best practices
- Public landing pages from **Triple Whale**, **HockeyStack**, **Supermetrics**, and **Dreamdata**

---

## 3. Deep audit

## 3.1 Page copy, landing-page story, hero, first fold, and CTA

### What is working

1. **The vertical pages are much better than the homepage for paid traffic.**  
   `site/for-paid-ads.html`, `site/for-product-intelligence.html`, and `site/for-organic-growth.html` are all more specific than `site/index.html`, which is what paid traffic usually needs.

2. **The problem framing is strong.**  
   The vertical pages do a good job of naming felt pain:
   - cross-platform reporting friction on `/for-paid-ads`
   - adoption / retention blind spots on `/for-product-intelligence`
   - ranking / traffic / conversion disconnects on `/for-organic-growth`

3. **The interactive demos create substance.**  
   For visitors who stay on the page, the demos are a real differentiator. They move the page beyond generic SaaS copy and show the kind of output Duct is promising.

4. **There is one dominant CTA path.**  
   The pages do not overload visitors with many conflicting asks.

### What is not strong enough yet

1. **The homepage hero is too broad for paid clicks.**  
   `site/index.html` says "Automated Intelligence Across Your Entire Tool Stack." That is accurate, but it is too wide for a paid click where the visitor expects a page that matches one problem and one outcome.

2. **The hero CTA is generic rather than value-specific.**  
   Across pages, the main CTA is still essentially:
   - "Get early access"

   That is fine for warm traffic, but cold paid traffic usually responds better to:
   - "See the paid ads brief"
   - "Get my first brief"
   - "Get the weekly SEO brief"
   - "See what Duct found"

3. **Above-the-fold proof is still light.**  
   Compared with pages like Triple Whale, Supermetrics, and Dreamdata, Duct does not yet show enough immediate proof in the first screen:
   - no customer logos
   - no testimonial quote
   - no named customer outcome
   - no hard benchmark like "used by X teams" or "saves Y hours"

4. **The story sequence is good, but the payoff is delayed.**  
   The vertical pages explain the problem well, but the first fold still depends heavily on belief in the product promise. Cold traffic tends to convert better when the first fold answers:
   - who this is for
   - what they get
   - what changes
   - why they should trust it

5. **The CTA intent is still beta/waitlist intent, not commercial intent.**  
   The current ask is structurally closer to "join the list" than "start solving this now." That weakens paid-search economics because the visitor is not being asked to take the most value-linked next step.

### Page-specific implications

#### `site/index.html`

- **Do not send paid traffic here.**
- It is a good brand homepage, not a paid acquisition page.

#### `site/for-paid-ads.html`

- This is the **best candidate** for a first Google Ads launch page.
- It has the strongest alignment with search-intent phrases around reporting, attribution, and paid-media clarity.
- The interactive demo is useful, but the hero would perform better with:
  - one proof line
  - one stronger value CTA
  - one trust statement tied to real outcomes

#### `site/for-product-intelligence.html`

- Good page, but likely too category-creation heavy for a tiny search budget.
- Better for content, founder-led traffic, and later expansion.

#### `site/for-organic-growth.html`

- Strong page for SEO/growth operators.
- Also a viable future paid-search page, but still lower priority than `/for-paid-ads` for immediate search learning.

### Recommendation

For the first paid experiment:

- use **one page only**
- use **`/for-paid-ads`**
- tighten the hero message around:
  - who it is for
  - what the brief does
  - what decision it helps them make

---

## 3.2 Measurement and tracking readiness

### What is working

1. **GTM is installed cleanly.**  
   `site/assets/config.js` sets the GTM container, and `site/assets/duct.js` loads GTM in a deferred way.

2. **UTM parameters are captured into session storage.**  
   That is a good foundation for channel attribution.

3. **There is already some event thinking in place.**  
   `site/assets/demo.js` and `site/assets/duct.js` push useful behavior into `dataLayer` such as:
   - `utm_data`
   - `form_submit`
   - demo-related events

4. **The app and the marketing site both follow the GTM pattern.**

### The critical gaps

1. **There is no named primary conversion event implemented in code.**  
   The repo's GTM strategy expects:
   - `beta_signup`
   - `pilot_agreement`

   But the shared site JS currently pushes only:

   - `form_submit`

2. **The current success logic can overcount conversions.**  
   In `site/assets/duct.js`, the form submit flow treats both:
   - `then(...)`
   - `catch(...)`

   as a success state in the UI and in `dataLayer`.

   That means:
   - a network error
   - an upstream Google Forms issue
   - a blocked request

   can still look like a successful conversion in analytics.

3. **There is no conversion qualification layer.**  
   For paid traffic, raw email capture is not enough. You need to distinguish:
   - all signups
   - qualified signups
   - pipeline / pilot-qualified leads

4. **UTMs are not clearly being written into the lead record itself.**  
   They are stored in the browser and pushed to `dataLayer`, but this audit did not find evidence that they are being attached to the submitted lead in a durable CRM-friendly way.

5. **CTA position and page context are not being passed as conversion metadata.**  
   Paid learning gets much faster if every conversion tells you:
   - page
   - vertical
   - CTA location
   - experiment
   - source / medium / campaign / term / content

6. **Google Ads / LinkedIn / X platform conversion wiring is not verifiable from the repo.**  
   It may exist inside GTM, but this code review alone cannot confirm:
   - Google Ads conversion tag
   - conversion linker
   - LinkedIn Insight Tag
   - X pixel
   - offline conversion import

### Launch recommendation

Before any paid spend:

1. Add a proper `beta_signup` event in `dataLayer`
2. Add `vertical`, `cta_position`, and UTM parameters to that event
3. Add a downstream event:
   - `qualified_lead`
   - or `pilot_agreement`
4. Import downstream quality back into Google Ads manually if needed

### Suggested event model

#### Primary interim conversion

- `beta_signup`

Parameters:

- `vertical`
- `page_type`
- `cta_position`
- `offer`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `utm_term`

#### Downstream quality conversion

- `qualified_lead`
- `pilot_agreement`

Parameters:

- `vertical`
- `source_platform`
- `estimated_pipeline_value`

### Bottom line

**Tracking is the single biggest blocker to a wider paid launch.**  
With the current implementation, you can measure top-of-funnel behavior, but not confidently optimize ad spend toward revenue or even reliably toward qualified leads.

---

## 3.3 SEO tags and indexing

### What is working

1. **Core technical SEO is present on marketing pages.**
   - canonical tags
   - robots tags
   - OG tags
   - Twitter tags

2. **`robots.txt` is permissive and healthy.**
   - crawling is allowed
   - sitemap is declared

3. **`sitemap.xml` exists and includes the main landing pages.**

4. **CI validation is already in place.**  
   `.github/scripts/check-pages.py` enforces the head-tag baseline well.

### What is weaker than ideal

1. **Blog URLs are query-string based.**  
   `site/blog/post.html` sets canonical URLs like:

   - `/blog/post?slug=...`

   and `site/sitemap.xml` uses the same pattern.

   This is workable, but weaker than:

   - `/blog/keyword-gap-analysis-without-a-spreadsheet`

   Clean URLs are generally better for:
   - shareability
   - citation quality
   - perceived authority
   - AI answer extraction

2. **Blog rendering is client-side.**  
   `site/blog/post.html` fetches markdown and renders it in the browser with `marked.min.js`.

   That introduces two issues:
   - some crawlers and answer systems will process it less reliably
   - the content is not present in the initial HTML response

3. **Structured data is solid but still basic.**
   - landing pages use `WebPage` and `FAQPage`
   - blog uses `Article`

   Missing opportunities:
   - richer `SoftwareApplication` / `Product` style schema where appropriate
   - stronger question-answer and comparison content that maps to search intent

4. **The public site does not yet own many category-defining queries.**  
   The best strategic keyword ideas already exist in `docs/gtm/seo-content-plan.md`, but the public site still needs more indexed, answer-friendly content to capitalize on them.

### Bottom line

**The marketing site passes the SEO hygiene baseline, but the blog architecture is still weaker than it should be for long-term discoverability.**

---

## 3.4 AEO discoverability (ChatGPT / Perplexity / AI Overviews / Claude-style retrieval)

### What is working

1. **AI-related user agents are explicitly allowed in `site/robots.txt`.**
2. **Landing pages are mostly static HTML and easy to crawl.**
3. **FAQ schema is already present on core pages.**
4. **The site has a strong product thesis that can become answer-engine-friendly with better public content.**

### What is missing

1. **Too little answer-first public content.**  
   The best AEO pages are not just landing pages. They are pages that answer:
   - what is X
   - how to do Y
   - why Z happens
   - best tools for A
   - X vs Y

2. **Not enough entity-rich, comparison-style content.**  
   Duct should be publishing pages that naturally mention:
   - Google Ads
   - LinkedIn Ads
   - X Ads
   - GA4
   - Mixpanel
   - HubSpot
   - Ahrefs
   - Search Console

   because LLMs tend to reuse pages that are explicit, comparative, and rich in named entities.

3. **The blog delivery method is less AI-friendly than static article pages.**

4. **Off-site mention footprint is still likely too small.**  
   The Ahrefs guidance is directionally right here: LLM visibility is heavily shaped by:
   - third-party mentions
   - YouTube mentions
   - Reddit / community visibility
   - review / comparison sites

   Duct's docs are strong internally, but internal docs do not build external AI visibility.

### Practical AEO priorities

1. Publish answer-first articles tied to real product use cases
2. Use clear question headings and direct answer blocks
3. Add more comparison and "how to" content
4. Build third-party mentions in communities, podcasts, creator videos, and comparison pages

### Bottom line

**Duct is crawlable by answer engines, but not yet discoverable enough by them.**

---

## 3.5 Mobile responsiveness and loading-time risk

### What is working

1. **The site is static HTML/CSS/JS.**  
   That is a major advantage compared with heavier marketing stacks.

2. **GTM is deferred.**  
   `site/assets/duct.js` avoids loading GTM immediately on first paint.

3. **The shared CSS is system-font based.**  
   `site/assets/duct.css` uses system stacks by default, which is good for performance.

4. **The site has a responsive mobile nav and flexible hero/form layouts.**

### Risks and friction points

1. **`/for-paid-ads` loads Google Fonts in the head.**  
   That introduces avoidable render dependency for one of the most likely paid landing pages.

2. **The blog loads a blocking CDN script for markdown rendering.**  
   `site/blog/post.html` includes:
   - `https://cdn.jsdelivr.net/npm/marked/marked.min.js`

   That is not ideal for either performance or crawl consistency.

3. **The demo pages are JS-heavy relative to the simplicity of the funnel goal.**  
   The demos are strong product proof, but they also increase:
   - DOM size
   - JS parsing
   - interaction complexity

4. **The hero sections are elegant, but still quite tall.**  
   On smaller mobile screens, the combination of:
   - large headline
   - subhead
   - form
   - footnote

   can push proof and clarity lower than ideal for a paid click.

### Bottom line

**Mobile responsiveness is broadly fine, but the paid landing pages should be treated as conversion pages first and product-showcase pages second.**

---

## 4. What similar SaaS landing pages do better

## 4.1 Triple Whale

What stands out:

- hard proof near the top
- very clear category framing
- repeated quantified trust signals
- dual CTA (`free` + `demo`)

Takeaway for Duct:

- Duct should add one harder proof element above the fold
- Duct should separate:
  - low-friction demo CTA
  - higher-intent primary CTA

## 4.2 Supermetrics

What stands out:

- one-line value proposition that is immediately clear
- strong AI positioning tied to a known platform (`Claude`)
- multiple ways to engage (`try`, `tour`, `demo`)

Takeaway for Duct:

- sharpen the hero into one specific promise
- make the CTA describe the value, not just the action

## 4.3 Dreamdata

What stands out:

- clear B2B marketer framing
- explicit mention of syncing conversions back to ad platforms
- strong full-funnel positioning

Takeaway for Duct:

- talk more explicitly about:
  - revenue quality
  - qualified pipeline
  - conversion signal quality

## 4.4 HockeyStack

What stands out:

- heavy use-case segmentation
- immediate "what this does" framing
- strong action-oriented narrative

Takeaway for Duct:

- keep the role-specific pages
- make the first fold even more role- and outcome-specific

---

## 5. Same-day blockers before spending

If you want to spend money today, these are the minimum blockers to address operationally:

1. **Do not split the budget across Google + LinkedIn + X**
2. **Use one landing page only**: `/for-paid-ads`
3. **Make `beta_signup` a real event**
4. **Create one downstream qualified-lead event**
5. **Import or manually reconcile lead quality weekly**
6. **Add CTA metadata to conversion events**
7. **Ensure Google Ads conversion linker is live in GTM**
8. **Confirm UTMs are captured in the lead workflow, not just analytics**

If those are not true, the launch should be considered **measurement-first**, not **scale-first**.

---

## 6. Recommended channel posture for this budget

| Channel | Recommendation | Why |
|---|---|---|
| Google Search | **Launch** | Highest intent, best fit for tiny budget, easiest to learn from |
| LinkedIn Ads | **Hold** | Good channel in principle, but too expensive for $350/month learning |
| X / Twitter Ads | **Hold** | Lower commercial intent, weaker tracking confidence, higher noise |

### Why not LinkedIn and X right now

For this budget, the main job is not reach. It is **signal quality**.

Google Search can still teach you:

- which problems people search for
- which terms convert
- which page-message pair resonates

LinkedIn and X at this spend level are much more likely to teach you:

- how fast budget disappears

That is not the same thing.

---

## 7. Lean Google Ads plan ($350/month, starting from zero)

## 7.1 Objective

### Primary goal

Learn which **commercial-intent search terms** produce the highest rate of:

- beta signups
- qualified leads
- early pipeline conversations

### Realistic optimization goal on day 1

Not true ROAS yet.

Because Duct is not yet sending real revenue back into Google Ads, the honest day-1 optimization target is:

- **qualified lead rate per dollar**

Use:

- `beta_signup` as the interim primary conversion
- `qualified_lead` / `pilot_agreement` as the real decision-making metric

Once revenue-linked or pipeline-weighted values are flowing back, move toward:

- **Maximize Conversion Value**
- later **tROAS**

---

## 7.2 Offer and landing-page choice

### Use this page

- **`https://getduct.ai/for-paid-ads`**

### Why

- strongest alignment with paid-search commercial intent
- strongest fit to the actual acquisition context
- easiest place to test a direct reporting / attribution / optimization message

### Do not use

- homepage
- multiple landing pages in the first test

---

## 7.3 Campaign structure

Keep this very small.

### Campaign 1 — Core commercial intent

- **Budget:** ~$8/day (~$243/month)
- **Goal:** capture the clearest "I need software for this" intent

#### Ad group A: paid media reporting

Suggested keywords:

- `[paid media reporting tool]`
- `[ppc reporting tool]`
- `[ad reporting software]`
- `"cross channel ad reporting"`
- `"ad performance reporting software"`

#### Ad group B: attribution / cross-channel clarity

Suggested keywords:

- `[marketing attribution software]`
- `"cross channel attribution tool"`
- `[paid media attribution tool]`
- `"google ads linkedin attribution"`
- `"ad spend attribution software"`

#### Ad group C: paid ads intelligence

Suggested keywords:

- `[paid ads intelligence]`
- `[ad intelligence platform]`
- `"creative fatigue tool"`
- `"campaign anomaly detection"`
- `"budget pacing tool"`

### Campaign 2 — Learning long-tail / problem-aware search

- **Budget:** ~$2.50/day (~$76/month)
- **Goal:** test narrower pain-led searches without polluting the main campaign

Suggested keywords:

- `"google ads linkedin reporting"`
- `"google ads twitter reporting"`
- `"cross platform ad reporting"`
- `"why roas up but retention down"`
- `"measure paid media quality"`

### Campaign 3 — Brand / reserve

- **Budget:** ~$1/day (~$30/month)
- Run only if branded demand exists
- If branded demand is negligible, roll this budget into Campaign 1

---

## 7.4 Match types

Use only:

- **Exact**
- **Phrase**

Do **not** use:

- Broad match
- Display expansion
- Performance Max
- Search Partners on day 1

For this budget, control matters more than volume.

---

## 7.5 Bidding approach

### Week 1-2

Use:

- **Manual CPC**
  or
- **Maximize Clicks with a bid cap**

Why:

- zero conversion history
- tiny budget
- need clean search-term learning before giving the system too much freedom

### Once you have signal

Switch to:

- **Maximize Conversions**

when you have enough trustworthy conversion volume to support it.

### Do not use yet

- Target CPA
- Target ROAS
- Maximize Conversion Value

until you have:

- real conversion data
- downstream qualification
- ideally revenue or pipeline weighting

---

## 7.6 Suggested ad-copy angles

Create **2-3 responsive search ads per ad group**, not more.

### Angle 1 — reporting pain

Headlines:

- Stop stitching ad reports
- Google + LinkedIn reporting, one brief
- Cross-channel paid media clarity
- Daily paid ads brief
- Find budget shifts faster

Descriptions:

- Duct connects your ad stack and surfaces the signals no single dashboard shows on its own.
- Spot creative fatigue, attribution gaps, and budget reallocation opportunities before they waste spend.

### Angle 2 — action and decision support

Headlines:

- Stop checking dashboards. Start deciding.
- Find what changed across paid faster
- See the paid ads brief
- Know where to shift budget
- Catch creative fatigue early

Descriptions:

- Get one decision-ready paid ads brief with what changed, why it matters, and what to do next.
- Built for performance marketers who need cross-channel clarity without another spreadsheet.

### Angle 3 — category framing

Headlines:

- Paid ads intelligence for lean teams
- Cross-tool ad intelligence
- Attribution and reporting, together
- One brief for your paid stack
- Better budget decisions, faster

Descriptions:

- Duct connects Google Ads, LinkedIn, and the rest of your paid stack into one operator-ready brief.
- Learn faster, cut noise, and focus on the signals that actually move ROAS and pipeline quality.

---

## 7.7 Negative keywords

Start with:

- free
- template
- templates
- excel
- spreadsheet
- course
- training
- certification
- jobs
- job
- salary
- definition
- meaning
- pdf
- tutorial
- agency
- consultant
- freelancer
- internship
- login

Review search terms every **48-72 hours** in the first two weeks.

---

## 7.8 Geo and schedule

For this budget:

- start with **one to three geographies only**
- pick the markets where you can actually follow up and sell

Suggested initial schedule:

- weekdays only
- business hours first

This is not because the product cannot convert outside those hours. It is because tiny budgets benefit from tighter initial control.

---

## 7.9 Conversion setup for Google Ads

### Interim primary conversion

- `beta_signup`

### Secondary diagnostic events

- `demo_fragment_view`
- `view_full_report`
- `cta_click`

### Real business conversion

- `qualified_lead`
- `pilot_agreement`

### Decision rule

Use Google Ads for:

- keyword-level learning
- ad-level CTR and CPC optimization

Use your own reporting as source of truth for:

- CAC
- lead quality
- pilot rate
- revenue signal

---

## 7.10 Fail-fast rules

This budget is only useful if you kill waste quickly.

### Pause a keyword if:

- it spends **$20-25** with no conversion
- or CTR stays below **2.5%** after enough impressions to judge relevance

### Pause an ad if:

- CTR is weak versus its peer after ~300-500 impressions
- message clearly underperforms the other RSA

### Rework the landing page if:

- search CTR is acceptable but page conversion rate stays weak
- visitors engage with the demo but do not submit
- there is traffic but no qualified leads after meaningful click volume

### Do not add budget unless:

- at least one keyword cluster is converting
- and the downstream lead quality is acceptable

---

## 7.11 Success criteria for the first 30 days

The goal is not scale. The goal is to learn fast.

### Good outcome

- at least one keyword theme produces signups at a tolerable CPL
- at least some of those signups become qualified leads
- you know which message / keyword cluster to double down on

### Bad outcome

- traffic with no conversions
- conversions with no quality
- budget spread too thin to produce decisions

### Questions to answer after month 1

1. Which keyword group had the best CTR?
2. Which keyword group had the best signup rate?
3. Which keyword group had the best qualified-lead rate?
4. Did `/for-paid-ads` convert cold search traffic well enough to keep?
5. Is there evidence to justify improving this page further or pivoting to a different offer/page?

---

## 8. Small-budget tips that matter disproportionately

1. **One page, one promise, one persona**
2. **Exact + phrase only**
3. **No three-channel launch**
4. **Mine search terms constantly**
5. **Use negative keywords aggressively**
6. **Do not optimize to vanity CTR alone**
7. **Treat raw email capture as provisional, not final truth**
8. **Use downstream qualification to decide whether to keep spending**

---

## 9. Recommended next actions

## Today

1. Launch **Google Search only**
2. Use **`/for-paid-ads`** only
3. Create a real `beta_signup` event
4. Add downstream qualification tracking
5. Confirm GTM conversion linker and Google Ads conversion import
6. Set up a simple weekly lead-quality review

## Within 72 hours

1. Strengthen the hero CTA on `/for-paid-ads`
2. Add at least one proof element above the fold
3. Make conversion metadata richer
4. Confirm UTMs land in the lead record

## Within 2 weeks

1. Publish one answer-first supporting article relevant to paid media intelligence
2. Review search-term data and prune aggressively
3. Decide whether the first page/message pair is good enough to keep

---

## 10. Final recommendation

If the question is:

> "Are we ads-ready to launch Google Ads, LinkedIn Ads, and X Ads today?"

The answer is:

**No.**

If the question is:

> "Are we ready to run one disciplined Google Search test to learn fast?"

The answer is:

**Yes, conditionally — but only if tracking is tightened first and only if the launch is kept to one page, one offer, and one channel.**

---

## Appendix: research notes used in this audit

### External

- Google Ads budget and spend guidance:
  - <https://support.google.com/google-ads/answer/2375454?hl=en>
  - <https://support.google.com/google-ads/answer/1704424?hl=en>
- Ahrefs on AEO and ChatGPT visibility:
  - <https://ahrefs.com/blog/answer-engine-optimization>
  - <https://ahrefs.com/blog/how-to-rank-on-chatgpt/>
- Unbounce on CTA and CRO:
  - <https://unbounce.com/landing-page-articles/how-to-write-the-perfect-call-to-action/>
  - <https://unbounce.com/conversion-rate-optimization/cro-best-practices/>
- Comparable SaaS pages reviewed:
  - <https://www.triplewhale.com/>
  - <https://www.hockeystack.com/>
  - <https://www.supermetrics.com/>
  - <https://www.dreamdata.io/>

### Duct internal references

- `docs/gtm/paid-growth-plan.md`
- `docs/gtm/seo-content-plan.md`
- `site/assets/duct.js`
- `site/for-paid-ads.html`
- `site/for-product-intelligence.html`
- `site/for-organic-growth.html`
- `site/index.html`
- `site/blog/post.html`
- `site/robots.txt`
- `site/sitemap.xml`
