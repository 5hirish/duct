# Paid Ads Demo — World-Class Report Design

**Date:** 2026-03-28
**File:** `for-paid-ads-demo.html`
**Section:** Step 4 of the interactive walkthrough demo

---

## Context

The current Step 4 ("Your morning brief is ready") shows three plain bullet-point insights in a dark card. It reads like a toy. Decision makers (CMOs, growth leads, performance marketing directors) need to see something they'd actually trust and act on — a real report that cites its sources, surfaces the right 5–7 KPIs, prioritises actions by urgency, and tells them exactly what to do next.

The goal is not to build a full product dashboard — it's to make the *demo* feel like the real output they'd get every morning if they signed up.

Research basis: Triple Whale, Databox, WordStream, HubSpot, Supermetrics, AgencyAnalytics best practices for executive-level paid ads reporting. Key finding: lead with business outcome metrics (ROAS, CAC, attributed revenue), not operational metrics; show only 5–7 KPIs; every section must answer "so what?"; cite data sources prominently.

---

## What Changes

**Step 4 of the walkthrough** is redesigned. Everything else on the page stays untouched.

The new Step 4 has two states:
1. **Preview** — visible inside the walkthrough card. Shows the top portion of the report (header + KPI chips + first signal), fading out with a gradient. A "View full report →" button sits below the fade.
2. **Modal** — full report in a dark overlay, scrollable, with a floating CTA pinned to the bottom.

---

## Report Structure (inside the modal)

### 1. Report Header
- Title: "Paid Ads Performance Report"
- Date range + platforms as data-source citation: `Mar 21–28, 2026 · Google Ads · Meta Ads · LinkedIn Ads`
- One-line verdict in a coloured badge: e.g. `🔴 Spend up 42%, conversions flat — 2 actions needed`

### 2. KPI Strip (4 chips in a row)
Each chip: metric name, value, delta with arrow, red/yellow/green status dot.

| Metric | Value | Delta | Status |
|---|---|---|---|
| CAC | $312 | ▲43% vs target | 🔴 |
| ROAS | 4.2x | ▲12% WoW | 🟢 |
| Total Spend | $24.8K | ▲42% MoM | — |
| Conversions | 79 | ▼8% WoW | 🔴 |

*Values are dynamic — populated by `populateBrief()` based on the metric goal selected in Step 2.*

### 3. Signals (3 blocks, priority-ordered)
Each signal block:
- Coloured pill label: 🔴 Critical / 🟡 Watch / 🟢 Win
- **Bold issue statement** (one line)
- Impact + recommended action in body text
- Owner tag (e.g. `→ Paid team`)

Content varies by the metric goal chosen in Step 2 (CAC / ROAS / Pipeline).

### 4. Campaign Performance Table
Compact table: Campaign | Spend | CPA | ROAS | Status
Status column uses coloured text only: `Scale ↑`, `Pause`, `Monitor`
3 rows (Google Brand, Meta Prospecting, LinkedIn Brand).

### 5. Unit Economics
3-line block:
- Cost per new subscriber: `$XX`
- LTV:CAC ratio: `X.Xx` (Target: 3.0x)
- Verdict badge: 🔴 Losing money / 🟡 Breakeven / 🟢 Profitable

### 6. Data Sources Footer
`Data: Google Ads API · Meta Ads Manager · LinkedIn Campaign Manager · as of Mar 28, 2026`
Small grey text. This is the "cite your sources" requirement.

---

## UI Mechanics

### Preview (inside wt-card)
- Replace current `.brief-shell` + insights with a `.report-preview` container
- Shows: report header + verdict badge + KPI strip + first signal block
- A CSS `mask-image` linear gradient fades the bottom ~40% to white
- Below the fade: `"View full report →"` button (blue, full-width)
- Below that: existing trust copy + restart button (unchanged)

### Modal
- A `<div id="report-modal">` appended to `<body>`, hidden by default (`display:none`)
- Full-screen overlay: `position:fixed; inset:0; z-index:200; overflow-y:auto; background:var(--navy)`
- Contains: close button (top-right ×), full report content, floating CTA bar at bottom
- Floating CTA bar: `position:sticky; bottom:0` — contains "Get this for my real data →" button + trust copy
- Opening: `openReportModal()` JS function, sets `display:block` + `document.body.style.overflow='hidden'`
- Closing: close button or Escape key, restores scroll

### Content is data-driven
`populateBrief()` already builds content based on selected platforms + metric. The report content follows the same pattern — a JS object maps `(metric goal) → report data` (KPI values, signal copy, campaign table rows, unit economics verdict). No hardcoded strings in the HTML.

---

## Styling

All styles go in the existing inline `<style>` block in `for-paid-ads-demo.html`. No changes to `assets/duct.css`.

New CSS classes needed:
- `.report-preview` — container with fade mask
- `.report-preview-fade` — gradient overlay at bottom of preview
- `.rpt-header` — report title + date + source line
- `.rpt-verdict` — coloured one-line verdict badge
- `.kpi-strip` — 4-column grid of KPI chips
- `.kpi-chip` — individual KPI card (metric, value, delta, dot)
- `.signal-block` — signal container (label pill + copy)
- `.signal-pill` — 🔴/🟡/🟢 pill label
- `.camp-table` — campaign performance table
- `.unit-econ` — unit economics block
- `.rpt-sources` — data sources footer
- `#report-modal` — modal overlay
- `.modal-close` — × button
- `.modal-cta-bar` — sticky bottom CTA

Dark background throughout: `var(--navy)`. White/light text. Orange/blue accents matching page's `--orange: #2563EB`.

---

## Files Modified

- `for-paid-ads-demo.html` — only file touched:
  - Inline `<style>` block: new CSS classes above
  - Step 4 HTML (lines ~502–532): replace `.brief-shell` with `.report-preview` + modal trigger
  - `<body>` end: add `#report-modal` markup
  - Inline `<script>`: extend `populateBrief()` to populate report data; add `openReportModal()` / `closeReportModal()`

---

## Content (demo data)

Report data is keyed to Step 2 metric selection. Three variants:

**CAC variant** (most common — show by default if no selection)
- Verdict: 🔴 Spend up 42%, CAC 43% over target — pause Meta Prospecting
- Critical signal: Meta Prospecting CAC at $312 vs $218 target → pause/reduce budget 30%
- Watch: LinkedIn CTR down 38% WoW → creative fatigue on top 3 ads
- Win: Google Brand ROAS 4.2x → increase budget 20%

**ROAS variant**
- Verdict: 🟡 Blended ROAS 2.1x — one campaign dragging average down
- Critical: Meta Prospecting ROAS 0.8x → losing $1.25 for every $1 spent
- Watch: Google Display impressions up 80%, ROAS down to 1.2x
- Win: Google Brand ROAS 4.2x, scaling headroom available

**Pipeline variant**
- Verdict: 🟡 79 conversions this week, MQL→deal rate dropped to 18%
- Critical: LinkedIn ad-attributed deals stalled — 0 new deals past 14 days
- Watch: Google Brand driving highest MQL quality (32% deal rate) but under-budgeted
- Win: Meta retargeting driving 3x more pipeline per dollar than prospecting

---

## Verification

1. Run `python3 -m http.server 8080` and open `http://localhost:8080/for-paid-ads-demo.html`
2. Step through the demo (pick 2+ platforms, pick a metric goal)
3. Step 4 shows the report preview with fade + "View full report →" button
4. Clicking the button opens the modal with all 6 sections populated
5. Escape key and × button close the modal
6. Floating CTA bar visible at bottom of modal, scrolls with content
7. Restart demo resets to Step 1 — modal closes if open
8. All 3 metric variants (CAC / ROAS / Pipeline) show different report content
9. Page loads fast on mobile (375px) — table scrolls horizontally if needed
