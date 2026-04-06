# Plan: Add Interactive Demo to `for-product-intelligence.html` and `for-organic-growth.html`

> **Archived (April 2026).** Work completed; retained as a record. See [`README.md`](README.md) in this folder.

---

## Progress Tracker

**Last updated:** 2026-03-31 (all items complete)  
**Branch:** `claude/add-demo-component-EIi65`

### `for-product-intelligence.html`

| Item | Status |
|---|---|
| Demo CSS block (~200 lines inline `<style>`) | ✅ Done — committed |
| Nav: "Try the demo" link + subtitle suffix `· demo` | ✅ Done — committed |
| 4-step wizard HTML (tool selection, goal, analysis, report preview) | ✅ Done — committed |
| Report modal HTML | ✅ Done — committed |
| JS script block (PLATFORM_DATA + wizard logic + report rendering) | ✅ Done — committed |

### `for-organic-growth.html`

| Item | Status |
|---|---|
| Demo CSS block + green accent overrides | ✅ Done — committed |
| Nav: "Try the demo" link + subtitle suffix `· demo` | ✅ Done — committed |
| 4-step wizard HTML (SEO tool selection, goal, analysis, report preview) | ✅ Done — committed |
| Report modal HTML | ✅ Done — committed |
| JS script block (PLATFORM_DATA + wizard logic + report rendering) | ✅ Done — committed |

---

## Context
`for-paid-ads.html` has a 4-step interactive walkthrough demo that lets visitors pick their tool stack, set a goal, watch a mock analysis animation, and see a realistic report preview. This has strong conversion value. The goal is to replicate the same level of interaction, simplicity, and sophistication on the other two landing pages, adapted to each page's audience and domain.

---

## Approach

Each page gets a fully self-contained demo — inline `<style>`, HTML section, report modal, and inline `<script>` — following the exact same pattern as `for-paid-ads.html`.

The demo section is inserted **between the stats section and the CTA section** on each page (organic placement before final conversion ask).

Nav gets a "Try the demo" link on both pages (matching for-paid-ads.html's nav pattern).

---

## Critical Files

| File | What changes |
|---|---|
| `for-product-intelligence.html` | Add `<style>` block (CSS), demo section HTML, report modal HTML, `<script>` block (JS + mock data), nav link |
| `for-organic-growth.html` | Same, plus green colour overrides for all orange accent references in demo CSS |

---

## CSS Strategy

The full demo CSS block from `for-paid-ads.html` (~1100 lines) is copied verbatim into each page's inline `<style>` block.

- **Product intelligence**: no colour overrides needed (uses default `--orange`)
- **Organic growth**: add targeted overrides at end of `<style>` block that replace `var(--orange)` with `var(--green)` for every demo selector (`.wt-dot.active`, `.wt-step-label`, `.plat-btn:hover/.selected`, `.plat-check`, `.metric-card:hover/.selected`, `.metric-card.selected .metric-radio`, `.al-spinner`, `.view-report-btn`, `.rpt-disclosure-btn:hover`, `.rpt-show-more-signals`, `.modal-close:focus-visible`, `.modal-cta-form .email-in:focus`)

---

## Demo Content Design

### `for-product-intelligence.html` — "Your product stack. One brief."

**Step 1 — Tool selection** ("Which tools are you connecting?")
- Mixpanel · Intercom · Linear · Salesforce
- Uses emoji tool indicators (no external SVGs needed — no icons exist for these tools)
- Minimum 2 required to unlock step 2

**Step 2 — Goal selection** ("What are you tracking?")
- 📉 Retention Health — DAU/retention drops, cohort decay
- 🔍 Feature Adoption — which features users actually use vs ignore
- 🎧 Support-to-Product — surface what Intercom tickets reveal about product gaps

**Step 3 — Analysis animation**
- "Reading user event data from Mixpanel…"
- "Correlating support signals with product changes…"
- "Surfacing adoption and retention anomalies…"

**Step 4 — Report preview**
- Hero KPI: D30 Retention / Feature Activation Rate / Ticket Deflection Rate
- Bar chart: "Retention by cohort" or "Adoption by feature"
- KPI strip: Retention, DAU, Adoption%, Open Tickets
- Signals: 2 visible + 1 hidden (cross-tool insight when 2+ tools)
- Disclosure 1: Feature/segment breakdown table (Feature, DAU, Adoption%, Trend, Action)
- Disclosure 2: Product health (Churn risk, NPS proxy, verdict)
- Modal: "Product Intelligence Report"

**PLATFORM_DATA** covers Mixpanel × Intercom × Linear × Salesforce, each with 3 metric variants (retention/adoption/tickets), realistic mock campaigns/segments, sparklines, signals, and unit-econ equivalents.

**Cross-tool signals** (shown as signal[2] when 2+ tools selected):
- retention: "Linear ticket velocity and Intercom escalations spiked 3 days before your D7 retention dropped — the bug shipped before the rollback"
- adoption: "Only 12% of users who activate Feature X reach the 'aha moment' (3 events) — Intercom shows 40% of churned users never triggered it"
- tickets: "Intercom ticket volume spikes 48 hours after every Mixpanel cohort refresh — the refresh is confusing users, not delighting them"

---

### `for-organic-growth.html` — "Your content stack. One brief."

**Step 1 — Tool selection** ("Which tools are you connecting?")
- Google Search Console · Ahrefs · GA4 · Semrush
- Minimum 2 required

**Step 2 — Goal selection** ("What are you optimising for?")
- 📈 Grow Rankings — find pages slipping, find quick wins in positions 4–15
- 🧲 Drive Trial Signups — surface which content clusters convert to trial, not just traffic
- 🗺️ Own Topic Clusters — measure topical authority and cluster gap vs competitors

**Step 3 — Analysis animation**
- "Reading keyword and ranking data…"
- "Mapping content clusters to conversion paths…"
- "Identifying ranking opportunities and traffic drops…"

**Step 4 — Report preview**
- Hero KPI: Avg Position (tracked keywords) / Trial Signups from organic / Cluster Coverage %
- Bar chart: "Traffic by keyword cluster"
- KPI strip: Organic Sessions, Trial Signups, Avg Position, Keywords Ranked
- Signals: 2 visible + 1 hidden (cross-tool insight when 2+ tools)
- Disclosure 1: Keyword/content breakdown table (Page/Cluster, Position, Sessions, Trials, Action)
- Disclosure 2: Content ROI (cost-per-trial equiv., LTV:content-cost ratio, verdict)
- Modal: "Organic Growth Report"

**PLATFORM_DATA** covers GSC × Ahrefs × GA4 × Semrush, each with 3 metric variants (rankings/signups/clusters).

**Cross-tool signals** (shown as signal[2] when 2+ tools):
- rankings: "6 pages ranking positions 4–8 in GSC have 0 internal links from high-authority pages — you're one link away from page-1 for each"
- signups: "Your top-traffic cluster (how-to/tutorials) drives 68% of sessions but only 9% of trials — the intent doesn't match the CTA"
- clusters: "Competitor owns 4 topic clusters you have zero coverage on — all have KD < 40 and 2K+/mo combined search volume"

---

## JS Architecture (per page)

Each page gets an IIFE that mirrors `for-paid-ads.html` exactly in structure:

```
state { step, platforms, metric }
→ wtTogglePlatform / wtSelectMetric
→ wtGoTo → syncStepTo
  → runAnalysis (step 3) → wtGoTo(4)
  → populateBrief (step 4)
→ wtRestart
→ hash management (deep links, GTM events)
→ PLATFORM_DATA (page-specific mock data)
→ CROSS_PLATFORM_SIGNALS (page-specific)
→ report rendering (domain-adapted labels + same helper functions)
→ modal open/close
```

The key JS differences from for-paid-ads.html:
- `PLATFORM_DATA` keys: `'Mixpanel'/'Intercom'/'Linear'/'Salesforce'` or `'GSC'/'Ahrefs'/'GA4'/'Semrush'`
- `PLATFORM_QUALITY` weights for each tool
- `metric` keys: `'retention'/'adoption'/'tickets'` or `'rankings'/'signups'/'clusters'`
- KPI strip IDs: `rpt-kpi-retention`, `rpt-kpi-dau`, `rpt-kpi-adoption`, `rpt-kpi-tickets` (product) / `rpt-kpi-sessions`, `rpt-kpi-signups`, `rpt-kpi-position`, `rpt-kpi-keywords` (organic)
- Hero label, bar chart label, table column headers, unit-econ section label all set dynamically per metric
- Source map maps tool names to API labels ("Mixpanel Events API", "Intercom Conversations API", etc.)

---

## HTML Structure Change: Step 4 KPI Strip

The KPI strip HTML in Step 4 uses different IDs per page:

**Product intelligence**:
- `rpt-kpi-retention-val/trend/delta`
- `rpt-kpi-dau-val/trend/delta`
- `rpt-kpi-adoption-val/trend/delta`
- `rpt-kpi-tickets-val/trend/delta`

**Organic growth**:
- `rpt-kpi-sessions-val/trend/delta`
- `rpt-kpi-signups-val/trend/delta`
- `rpt-kpi-position-val/trend/delta`
- `rpt-kpi-keywords-val/trend/delta`

The `setKPIChips` function is adapted to use these domain-specific keys.

---

## Placement & Nav

**Insertion point**: Before `<!-- CTA -->` comment on each page.

**Nav addition** (same pattern as for-paid-ads.html):
- Add `<a href="#demo-step-1" class="nav-link">Try the demo</a>` to the nav on both pages
- Update nav subtitle span to include `· demo` on both pages

---

## Implementation Order

1. `for-product-intelligence.html` — orange theme, product domain
   - Expand `<style>` block with demo CSS
   - Add demo section HTML + report modal HTML
   - Add `<script>` block with product-domain PLATFORM_DATA and JS
   - Add nav "Try the demo" link
2. `for-organic-growth.html` — green theme, SEO domain
   - Same, plus green colour overrides in CSS

---

## Verification Checklist

### Functional
- [ ] Select 2+ tools → "Set your goal" button unlocks
- [ ] Select 1 tool only → button stays disabled, hint text reads "Select at least 2 to see cross-tool signals"
- [ ] Complete all 4 steps → report preview renders with correct data
- [ ] "View full brief →" opens the modal
- [ ] Modal close button (×) and Escape key both close the modal
- [ ] "Restart" button resets all selections and returns to step 1
- [ ] Deep link: `#demo-step-2` lands on step 2 without animation
- [ ] Deep link: `#demo-report` opens modal directly

### Visual
- [ ] Step progress dots update correctly (active = filled, done = muted blue, future = grey)
- [ ] Height animation plays smoothly between steps (no jump)
- [ ] Report preview fades out at the bottom (mask-image gradient)
- [ ] Organic growth page: all demo orange accents are green (dots, button, borders, spinner, bar fill)

### Mobile (375px)
- [ ] `.plat-grid` collapses to 1 column
- [ ] `.kpi-strip` collapses to 2 columns
- [ ] Hero KPI + sparkline stacks vertically
- [ ] No horizontal scroll

### Accessibility
- [ ] Tab order through wizard is logical
- [ ] `inert` attribute prevents focus on inactive steps
- [ ] Modal traps focus when open
- [ ] `aria-pressed` toggles correctly on platform buttons
- [ ] `aria-live="polite"` on the card announces step changes to screen readers

---

## Commit History

| Commit | Description |
|---|---|
| `863833d` | Add interactive demo scaffold to for-product-intelligence.html |
| `ecdf1c1` | Add demo component implementation plan to docs |
| `075ecf6` | Add JS script block to for-product-intelligence.html demo |
| `efd5166` | Add full interactive demo to for-organic-growth.html |
