# Improve Duct Report Context — Implementation Plan

## Context

Duct's report generation currently uses a minimal `BusinessContext` (industry, budget, CPA, ROAS, notes) that is ephemeral and entered per-report. This means:
- Users re-enter the same info every time
- Reports lack rich business context (personas, competitors, brand, channels) that would make findings more actionable
- Future cross-tool reports (Google Ads + GA4 + Search Console) need richer context to correlate data meaningfully

**Goal:** Collect and persist rich business context via an onboarding wizard + settings page, stored in localStorage, and inject it into report generation prompts.

**Decisions:** Onboarding wizard + settings page. Client-side localStorage for persistence.

---

## 1. Expanded Industry Taxonomy

Replace the current 5-option dropdown with a comprehensive 30-industry taxonomy based on Google Ads verticals, HubSpot/Amplitude onboarding patterns, and digital ad spend prevalence:

### Industries (code-ready)
```js
const INDUSTRIES = [
  { value: "ecommerce_retail", label: "E-commerce & Retail", examples: "DTC brands, marketplaces, consumer goods" },
  { value: "saas_software", label: "SaaS & Software", examples: "B2B SaaS, dev tools, cloud services" },
  { value: "financial_services", label: "Financial Services", examples: "Banking, fintech, lending" },
  { value: "healthcare", label: "Healthcare & Life Sciences", examples: "Telehealth, pharma, medical devices" },
  { value: "education", label: "Education & E-learning", examples: "EdTech, online courses, universities" },
  { value: "real_estate", label: "Real Estate & Property", examples: "Residential, commercial, proptech" },
  { value: "professional_services", label: "Professional Services", examples: "Consulting, accounting, staffing" },
  { value: "marketing_advertising", label: "Marketing & Advertising", examples: "Agencies, PR, media buying" },
  { value: "travel_hospitality", label: "Travel & Hospitality", examples: "Hotels, airlines, OTAs, restaurants" },
  { value: "automotive", label: "Automotive", examples: "Dealerships, auto parts, rentals" },
  { value: "home_services", label: "Home Services & Improvement", examples: "HVAC, plumbing, roofing, landscaping" },
  { value: "legal", label: "Legal", examples: "Law firms, legal tech, compliance" },
  { value: "food_beverage", label: "Food & Beverage", examples: "CPG food, restaurants, meal delivery" },
  { value: "beauty_personal_care", label: "Beauty & Personal Care", examples: "Cosmetics, skincare, salons" },
  { value: "fitness_sports", label: "Fitness & Sports", examples: "Gyms, fitness apps, supplements" },
  { value: "technology_electronics", label: "Technology & Electronics", examples: "Consumer electronics, IT services" },
  { value: "media_entertainment", label: "Media & Entertainment", examples: "Streaming, gaming, publishing" },
  { value: "telecommunications", label: "Telecommunications", examples: "ISPs, mobile carriers, VoIP" },
  { value: "manufacturing", label: "Manufacturing & Industrial", examples: "Equipment, supply chain, logistics" },
  { value: "construction", label: "Construction & Engineering", examples: "Contractors, architecture, materials" },
  { value: "energy_utilities", label: "Energy & Utilities", examples: "Solar, renewables, oil & gas" },
  { value: "agriculture", label: "Agriculture & Farming", examples: "AgTech, farming equipment, crop science" },
  { value: "nonprofit_government", label: "Nonprofit & Government", examples: "NGOs, public sector, fundraising" },
  { value: "fashion_apparel", label: "Fashion & Apparel", examples: "Luxury, fast fashion, footwear, jewelry" },
  { value: "pets_animals", label: "Pets & Animals", examples: "Pet food, veterinary, pet tech" },
  { value: "b2b_marketplace", label: "B2B Marketplace & Wholesale", examples: "Distributors, wholesale, trade" },
  { value: "logistics_transportation", label: "Logistics & Transportation", examples: "Freight, last-mile, fleet" },
  { value: "recruitment_hr", label: "Recruitment & HR Tech", examples: "Job boards, ATS, staffing" },
  { value: "insurance", label: "Insurance", examples: "Health, auto, property, insurtech" },
  { value: "other", label: "Other", examples: "" },
];
```

**Design decisions:**
- Ordered by digital ad spend prevalence (e-commerce & SaaS first)
- Insurance split from Financial Services — distinct ad benchmarks (highest CPC verticals)
- Home Services is its own category — one of the largest local search verticals
- Business model is separate from industry (same industry can be DTC or lead-gen)

### Business Models
```js
const BUSINESS_MODELS = [
  { value: "ecommerce_dtc", label: "E-commerce / DTC" },
  { value: "saas_subscription", label: "SaaS / Subscription" },
  { value: "marketplace", label: "Marketplace" },
  { value: "lead_generation", label: "Lead Generation" },
  { value: "agency_consultancy", label: "Agency / Consultancy" },
  { value: "content_media", label: "Content / Media" },
  { value: "local_brick_mortar", label: "Brick & Mortar / Local" },
  { value: "hybrid", label: "Hybrid (Online + Offline)" },
  { value: "app_mobile", label: "App / Mobile-first" },
  { value: "wholesale_b2b", label: "Wholesale / B2B Commerce" },
];
```

### Company Stages
```js
const COMPANY_STAGES = [
  { value: "pre_revenue", label: "Pre-revenue / Startup" },
  { value: "early_stage", label: "Early-stage (Seed / Series A)" },
  { value: "growth_stage", label: "Growth-stage (Series B+)" },
  { value: "established", label: "Established / Mature" },
  { value: "enterprise", label: "Enterprise" },
];
```

### Company Sizes
```js
const COMPANY_SIZES = [
  { value: "solo", label: "Solo / Freelancer", range: "1" },
  { value: "small", label: "Small", range: "2-10" },
  { value: "mid_small", label: "Mid-small", range: "11-50" },
  { value: "mid_market", label: "Mid-market", range: "51-200" },
  { value: "upper_mid", label: "Upper mid-market", range: "201-1,000" },
  { value: "enterprise", label: "Enterprise", range: "1,001-10,000" },
  { value: "large_enterprise", label: "Large Enterprise", range: "10,000+" },
];
```

---

## 2. Business Profile Data Model

### Full schema — `BusinessProfile`

**A. Company Basics** (existing fields expanded)
- `company_name: str` — personalization + report headers
- `industry: str` — expanded to 30-industry taxonomy above
- `business_model: str` — from BUSINESS_MODELS list
- `company_stage: str` — from COMPANY_STAGES list
- `company_size: str` — from COMPANY_SIZES list
- `monthly_budget: float` — keep existing
- `website_url: str` — for future domain-based enrichment

**B. Targets & KPIs** (existing + new)
- `target_cpa: float` — keep existing
- `target_roas: float` — keep existing
- `primary_kpi: str` — revenue, signups, leads, app_installs, purchases, bookings, calls
- `secondary_kpis: list[str]` — up to 3 additional tracked metrics
- `monthly_revenue_target: float` — for revenue-oriented analysis
- `average_order_value: float` — critical for ROAS/CPA interpretation

**C. Target Audience** (new)
- `personas: list[Persona]` — up to 3, each:
  - `name: str` — e.g. "Marketing Managers at Series B startups"
  - `description: str` — pain points, motivations (1-2 sentences)
  - `priority: str` — primary / secondary / future
- Why: LLM can judge whether a $200 CPA is reasonable for enterprise SaaS vs consumer app

**D. Competitive Landscape** (new)
- `competitors: list[Competitor]` — up to 5, each:
  - `name: str`
  - `differentiator: str` — what makes YOU different from them
- `positioning_statement: str` — one-liner on unique value prop
- Why: identifies competitive keyword opportunities, helps LLM flag cannibalization

**E. Brand & Messaging** (new)
- `brand_voice: str` — professional, friendly, bold, technical, playful
- `banned_phrases: list[str]` — terms to avoid in reports
- `preferred_terms: dict[str, str]` — replacements map
- Why: report language matches brand; post-processing sanitizes output

**F. Channels & Strategy** (new)
- `active_channels: list[str]` — paid_search, paid_social, seo, email, content, affiliates, display, video, referral, events
- `primary_channel: str` — where most budget/effort goes
- `seed_keywords: list[str]` — up to 10 core keyword themes
- `seasonality_notes: str` — e.g. "Q4 is peak; summer is slow"
- Why: cross-tool reports correlate paid + organic + analytics

---

## 3. Onboarding Wizard — UX Design

### Behavioral Science Principles Applied

| Principle | Application |
|---|---|
| **Endowed Progress Effect** (Nunes & Dreze) | Progress bar starts at ~15% — "We already know a few things from your signup." Show step 2/7 not 1/6. |
| **Commitment & Consistency** (Cialdini) | Start with easiest question (company name). Each answer creates micro-commitment. Show profile "coming to life." |
| **Goal Gradient Effect** | Easiest questions first AND last (sandwich structure). Near end: "Just one more thing..." |
| **Zeigarnik Effect** | Incomplete profile persists as a gentle indicator in nav. Empty states in reports prompt completion. |
| **Progressive Disclosure** | One category per screen. Optional "Add more detail" expansions within each step. |
| **Cognitive Load Theory** (Sweller) | Max 3-4 visible inputs per screen. Card selectors over free-text where possible. Recognition over recall. |
| **Default Effect** | Pre-select common channels for their industry. Suggest brand voice based on business model. |
| **Social Proof** | "Most B2B SaaS companies track 3-5 competitors." "Teams like yours typically set up 2-4 personas." |

### Copy Pattern: Value-Before-Ask

Every screen explains WHY before asking WHAT:

| Screen | Value framing |
|---|---|
| Company | *"Tell us about your business so we can benchmark against your industry"* |
| Targets | *"Share your goals so every report tracks what actually matters to you"* |
| Audience | *"Describe your audience so we can tell you who's engaging — and who's not"* |
| Competitors | *"Name your competitors so we can flag keyword overlap and positioning gaps"* |
| Brand | *"Define your voice so report language matches how you talk"* |
| Channels | *"Select your channels so we can break down performance where it counts"* |

### Screen-by-Screen Flow

**Screen 0 — Welcome (no input)**
Heading: *"Let's set up Duct for you"*
Subtext: *"This takes about 3 minutes and makes every report more relevant to your business."*
3 bullet points showing what they'll configure. [Get started] primary CTA.

**Screen 1 — Your Company (3 fields)**
Heading: *"What's your company called?"*
- Company name (text input, auto-focused)
- Industry (searchable dropdown — 30 options with examples as helper text)
- Business model (card selector — 5 most common, "More options" expands to full list)
Microcopy after: *"Nice — we're already learning about you."*

**Screen 2 — Your Targets (3-4 fields)**
Heading: *"What are you chasing?"*
- Primary KPI (card selector: Revenue, Signups, Leads, Purchases, Bookings, Calls)
- Target CPA and Target ROAS (side-by-side number inputs)
- Monthly budget (number input with currency symbol)
- Average order value (optional, shown if business model is e-commerce)
Helper: *"These shape how we evaluate every campaign in your reports."*

**Screen 3 — Your Audience (dynamic 1-3 cards)**
Heading: *"Who are you trying to reach?"*
- Start with 1 persona card: Name + Description textarea + Priority toggle (primary/secondary/future)
- [+ Add another] button, up to 3
Helper: *"Even a rough sketch helps. You can refine later."*
Social proof: *"Most teams describe 2-3 personas."*

**Screen 4 — Your Competition (search + add)**
Heading: *"Who do you keep tabs on?"*
- Text input to add competitor name + one-line differentiator
- [+ Add another] up to 5
- Positioning statement textarea: *"In one sentence, what makes you different?"*
Helper: *"Start with your top 1-2. You can add more anytime."*

**Screen 5 — Your Brand Voice (card selector + optional)**
Heading: *"How does your brand sound?"*
- 5 archetype cards: Professional, Friendly, Bold, Technical, Playful
  - Each card has a 1-line example: e.g. Professional = *"Data-driven insights for strategic decisions"*
- Optional: banned phrases (tag input — type and press Enter)
- Optional: preferred terms (key-value pairs, "Replace X with Y")
Helper: *"Pick the closest match. We'll fine-tune the rest."*

**Screen 6 — Your Channels (multi-select cards)**
Heading: *"Where do you show up?"*
- Visual card grid with icons: Paid Search, Paid Social, SEO, Email, Content/Blog, Display, Video/YouTube, Affiliates, Referral, Events
- Pre-selected defaults based on industry chosen in step 1
- Seed keywords: tag input, up to 10
- Seasonality: textarea, 1-2 sentences
Helper: *"We'll focus your reports on these channels."*

**Screen 7 — Summary (no new input)**
Heading: *"Here's your Duct profile"*
Visual summary of all sections with edit links per section.
Completion indicator: "6/6 sections complete" (or partial if skipped).
Primary CTA: [Start generating reports] → redirects to `/generate`
Secondary: [Go to Settings] → `/settings`

### UX Implementation Details

- **Progress bar:** Segmented, 6 segments (one per input screen). Label shows "Step N of 6: Category Name"
- **Skip behavior:** Every step after Screen 1 has *"I'll do this later"* in subtle text below primary CTA
- **Incremental save:** Each step saves to localStorage on transition (not just at end)
- **Keyboard nav:** Enter advances to next step, Tab between fields, Escape = skip
- **Transitions:** Subtle slide-left animation (200-300ms, ease-out)
- **Mobile:** Single column, larger touch targets (44px min), auto-advance on single-select
- **Required vs optional:** Only company name is truly required. Everything else skippable.

### Progressive Profiling (Post-Onboarding)

Collect remaining context over time via:

1. **Empty states in reports:** When report shows audience data but no personas configured → *"Add your target personas to see audience breakdown → [Add persona]"*
2. **Feature-gated prompts:** When user clicks competitive analysis but no competitors → *"To show competitive insights, tell us who you're up against. [Add competitors — takes 30 seconds]"*
3. **Post-report nudges:** After first report viewed → *"Want more relevant insights? Tell us about your brand voice."*
4. **Completion indicator in nav:** Persistent but non-intrusive dot/badge on avatar showing profile completion

---

## 4. Files to Modify/Create

### Frontend (New Files)

| File | Purpose |
|---|---|
| `app/src/lib/businessProfile.js` | localStorage CRUD: `getProfile()`, `saveProfile(data)`, `saveProfileSection(section, data)`, `clearProfile()`, `getProfileCompletion()`. Key: `duct_business_profile` |
| `app/src/lib/profileConstants.js` | INDUSTRIES, BUSINESS_MODELS, COMPANY_STAGES, COMPANY_SIZES, CHANNELS, KPI_OPTIONS, BRAND_VOICES constants |
| `app/src/app/(app)/onboarding/page.jsx` | Multi-step wizard (screens 0-7 above) |
| `app/src/app/(app)/settings/page.jsx` | Tabbed settings page — Company / Targets / Audience / Competition / Brand / Channels |

### Frontend (Modified Files)

| File | Change |
|---|---|
| `app/src/components/AppNav.jsx` | Avatar click → dropdown menu with "Settings" + "Sign out". Profile completion badge. |
| `app/src/app/(app)/generate/page.jsx` | Auto-populate from profile. Show profile summary card. Pass `business_profile` in API call. |
| `app/src/app/(app)/layout.js` | First-load check: if no profile, show dismissible banner linking to `/onboarding` |
| `app/src/lib/api.js` | Add `business_profile` field to `generateReport()` params |

### Backend (Modified Files)

| File | Change |
|---|---|
| `backend/routes/schemas.py` | Add `Persona`, `Competitor`, `BusinessProfile` Pydantic models. Add `business_profile: BusinessProfile` to `GenerateRequest`. Keep `business_context` for backward compat. |
| `backend/agents/reporter/prompts.py` | Expand `_format_business_context()` → `_format_business_profile()`. Add relevance filtering by connector type. Brand guardrail post-processing pass. |
| `backend/routes/generate.py` | Read `business_profile` from request, merge with legacy `business_context`, pass to agent |

---

## 5. Prompt Integration Strategy

### Relevance Filtering by Report Type

| Report type | Sections injected |
|---|---|
| **Paid Ads** | company, targets, personas (CPA interpretation), competitors (keyword context), channels, seasonality |
| **Analytics (future)** | company, personas, channels, KPIs, product context |
| **SEO/Search Console (future)** | company, competitors, seed keywords, channels |
| **Cross-tool (future)** | ALL sections with cross-reference instructions |

### XML Format for Prompt Injection

```xml
<business_profile>
  <company>
    - Name: Acme Corp
    - Industry: SaaS & Software
    - Model: SaaS / Subscription
    - Stage: Growth-stage (Series B+)
    - Monthly budget: $85,000
  </company>
  <targets>
    - Primary KPI: Signups
    - Target CPA: $45.00
    - Target ROAS: 4.0x
    - Monthly revenue target: $200,000
    - Average order value: $99/mo
  </targets>
  <audience>
    - Primary: "Marketing Managers at Series B startups" — frustrated with fragmented analytics, want one view
    - Secondary: "Solo founders" — no time for manual reporting, need automated insights
  </audience>
  <competitive_landscape>
    - Competitors: Databox (lacks narrative output), Supermetrics (no cross-tool correlation), Whatagraph (agency-focused)
    - Positioning: Only tool that combines cross-tool correlation with narrative insights
  </competitive_landscape>
  <channels>
    - Active: Paid Search, SEO, Content, Email
    - Primary: Paid Search
    - Seed keywords: product analytics, marketing dashboard, cross-tool reporting
    - Seasonality: Q4 budget increase; January slowdown
  </channels>
</business_profile>
```

### Token Budget
- Cap full profile injection at ~800 tokens
- Truncate description fields if needed
- Omit empty sections entirely

### Brand Guardrail Post-Processing
After synthesis completes, run a find-replace pass on narrative/findings text:
- Apply `preferred_terms` map (e.g., "dashboard" → "cross-tool correlation")
- Filter out `banned_phrases`
- This happens in `backend/routes/generate.py` before returning the response

---

## 6. Settings Page Design

- **Route:** `/settings`
- **Access:** Avatar dropdown in AppNav (replaces bare "Sign out")
- **Layout:** Tabbed — Company | Targets | Audience | Competition | Brand | Channels
- **Each tab:** Shows current values with inline edit. Same field components as onboarding.
- **Top bar:** Completion indicator ("4/6 sections complete") + "Re-run onboarding" link
- **Save:** Auto-saves on blur/change to localStorage (no explicit save button)

---

## 7. Implementation Order

| Step | What | Files |
|---|---|---|
| 1 | Constants & localStorage lib | `profileConstants.js`, `businessProfile.js` |
| 2 | Backend `BusinessProfile` model | `schemas.py` |
| 3 | Onboarding wizard | `onboarding/page.jsx` |
| 4 | Settings page | `settings/page.jsx` |
| 5 | AppNav dropdown with Settings link | `AppNav.jsx` |
| 6 | Layout first-load banner | `layout.js` |
| 7 | Prompt integration + relevance filtering | `prompts.py`, `generate.py` |
| 8 | Generate page auto-populate | `generate/page.jsx`, `api.js` |
| 9 | Brand guardrail post-processing | `generate.py` |

---

## 8. Verification

1. Walk through onboarding wizard end-to-end — verify each step saves to `duct_business_profile` in localStorage
2. Skip steps and verify partial profiles work
3. Open Settings page — verify it reads the saved profile and allows editing
4. Navigate to Generate — verify profile auto-populates business context fields
5. Generate a report with a saved profile — add debug logging to confirm enriched XML context in prompt
6. Generate a report WITHOUT a profile — confirm backward compatibility (no errors)
7. Add a banned phrase + preferred term, generate report, verify post-processing applied
8. Clear localStorage — verify onboarding banner appears
9. Test mobile layout for onboarding wizard (single column, touch targets)
10. Test keyboard navigation through wizard (Enter, Tab, Escape)
