# Paid Ads Demo — World-Class Report Design

> **Archived (April 2026).** UX spec for the marketing demo Step 4; implementation lives under `site/`. See [`README.md`](README.md) in this folder.


**Date:** 2026-03-28 (updated 2026-03-29 — light modal, disclosure, charts)
**File:** `for-paid-ads-demo.html` (historical name; marketing paid-ads page is now `site/for-paid-ads.html` with shared demo assets under `site/assets/`.)
**Section:** Step 4 of the interactive walkthrough demo

---

## Context

Step 4 ("Your report is ready") shows a credible cross-platform brief. Decision makers (CMOs, growth leads, performance marketing directors) need something they'd trust and act on — a real report that cites its sources, surfaces the right KPIs, prioritises actions by urgency, and stays readable on a light, editorial surface consistent with the rest of the landing page.

The goal is not to build a full product dashboard — it's to make the *demo* feel like the real output they'd get every morning if they signed up.

Research basis: Triple Whale, Databox, WordStream, HubSpot, Supermetrics, AgencyAnalytics best practices for executive-level paid ads reporting. Key finding: lead with business outcome metrics (ROAS, CAC, attributed revenue), not operational metrics; show only 5–7 KPIs on first scan; every section must answer "so what?"; cite data sources prominently; use charts only where they beat text (trend + comparison).

---

## What Changes

**Step 4 of the walkthrough** is redesigned. Everything else on the page stays untouched.

The new Step 4 has two states:

1. **Preview** — visible inside the walkthrough card. Shows the top portion of the report (header + KPI chips + signals), fading out with a gradient. A "View full report →" button sits below the fade.
2. **Modal** — full report in a **light scrim** with a centered **white report sheet** (matches preview / LP). Scrollable body; **CTA bar fixed to the bottom of the sheet** (not a dark full-bleed overlay).

---

## Report Structure (inside the modal)

### 1. Report Header

- Title: "Paid Ads Performance Report"
- Date range + platforms as data-source citation: `Mar 21–28, 2026 · Google Ads · Meta Ads · …`
- One-line verdict in a coloured badge (larger type class: `.rpt-verdict--modal`)

### 2. Hero Metric + Sparkline

- **North-star KPI** for the selected Step 2 goal (CAC / ROAS / Conversions for pipeline): large serif value + delta + status dot.
- **7-day indexed spend sparkline** (inline SVG, demo series in `REPORT_DATA.spendSparkline` per variant).

### 3. ROAS by Campaign (horizontal bars)

- Bar chart built from the same campaign rows as the table (normalized to max ROAS in the set). Labels show campaign name + ROAS value.

### 4. “Also tracking” KPI Strip

- Four KPI chips (`populateBrief` / `setKPIChips`), but the **hero metric chip is hidden** in the modal (`.kpi-chip--modal-hidden`) to avoid duplicating the hero block.

### 5. Signals (progressive disclosure)

- First **two** signal blocks visible by default.
- Third block + **“Show 1 more signal”** toggle (`buildSignalsHTMLModal`, `setupModalSignalToggle`).

### 6. Campaign Performance Table (collapsible)

- Disclosure button: **Campaign breakdown** + meta (`· N campaigns`). Panel **collapsed by default**; expands to the compact table (Campaign | Spend | CPA | ROAS | Action).

### 7. Unit Economics (collapsible)

- Disclosure button: **Unit economics** + summary from `unitEconSummary` (e.g. `· 1.4x LTV:CAC · losing money`). Panel **collapsed by default**; expands to the three-row block.

### 8. Data Sources Footer

- `Data: Google Ads API · Meta Ads Manager · LinkedIn Campaign Manager · as of …`
- Small grey text.

---

## UI Mechanics

### Preview (inside wt-card)

- `.report-preview` / `.report-preview-inner` with CSS mask fade
- Below: `"View full report →"` + trust copy + restart

### Modal

- `#report-modal`: `position:fixed; inset:0; z-index:200`; **backdrop** `rgba(13,15,26,0.45)`; padding; scrollable.
- `.modal-sheet`: white card, border, radius, shadow, `max-height: calc(100vh - 40px)`, **flex column**.
- `.modal-body-scroll`: `flex:1; overflow-y:auto` — report sections.
- `.modal-cta-bar`: **light** bar, top border, subtle blur — email + CTA (not navy slab).
- Opening: `openReportModal()` — `display:block`, lock body scroll, reset **both** overlay and `.modal-body-scroll` scroll positions.
- Closing: × or Escape; `closeReportModal()`.

### Content is data-driven

`REPORT_DATA` maps metric goal → `verdict`, `kpis`, `signals`, `campaigns`, `unitEcon`, **`spendSparkline`**, **`unitEconSummary`**. `populateBrief()` fills preview + modal; disclosure panels reset to collapsed each run.

---

## Styling

All styles stay in the inline `<style>` block in `for-paid-ads-demo.html`. No changes to `assets/duct.css`.

Notable classes:

- `#report-modal`, `.modal-sheet`, `.modal-body-scroll`, `.modal-topbar`, `.modal-close`, `.modal-cta-bar`
- `.rpt-verdict--modal`, `.rpt-hero-visual`, `.kpi-hero-*`, `.kpi-sparkline-*`
- `.rpt-bar-block`, `.rpt-bar-row`, `.rpt-bar-track`, `.rpt-bar-fill`
- `.rpt-disclosure*`, `.rpt-show-more-signals`, `.rpt-signal-extra-wrap`
- `.kpi-chip--modal-hidden`
- `prefers-reduced-motion` trims bar / chevron transitions

**Visual system:** Light surfaces (`#fff`, `var(--off)`), navy text, blue accent `--orange: #2563EB` — aligned with the walkthrough card and landing page.

---

## Files Modified

- `for-paid-ads-demo.html` — styles, Step 4 preview, `#report-modal` markup, `populateBrief()` + helpers (`buildSparklineSVG`, `buildRoasBarsHTML`, `buildSignalsHTMLModal`, disclosure wiring).

---

## Content (demo data)

Three variants (CAC / ROAS / Pipeline) — same narrative as before; owner lines shortened slightly; each variant includes `spendSparkline` and `unitEconSummary` for UI strings.

---

## Verification

1. Run `python3 -m http.server 8090` and open `http://localhost:8090/for-paid-ads-demo.html`
2. Step through the demo (platforms + metric goal)
3. Step 4: preview fade + "View full report →"
4. Modal: light overlay + white sheet; header, hero + sparkline, ROAS bars, three KPI chips, two signals, expand third signal
5. Expand **Campaign breakdown** and **Unit economics** — table and rows match variant
6. CTA bar visible at bottom of sheet without scrolling past all content
7. Escape / × close modal; Restart closes modal
8. CAC / ROAS / Pipeline variants differ in hero, bars, copy, sparkline shape
9. 375px: hero stacks; table scrolls horizontally inside panel; no horizontal page scroll
