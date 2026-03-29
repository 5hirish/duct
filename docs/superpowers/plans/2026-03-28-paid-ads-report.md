# Paid Ads Demo — World-Class Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the basic 3-bullet brief in Step 4 of the interactive demo with a world-class 1-pager report (preview with fade + full modal), data-driven by the metric goal selected in Step 2.

**Architecture:** Single file change (`for-paid-ads-demo.html`). New CSS goes in the existing inline `<style>` block. New HTML replaces Step 4 and adds a modal at end of `<body>`. New JS extends the existing IIFE script: adds a `REPORT_DATA` object, updates `populateBrief()` to populate the report, adds `openReportModal()` / `closeReportModal()`. All `innerHTML` usage is safe — content comes exclusively from the hardcoded `REPORT_DATA` constant, never from user input or external sources.

**Tech Stack:** Vanilla HTML/CSS/JS (ES5-compatible). No build tools. No frameworks. No new files.

---

## File Map

| File | What changes |
|---|---|
| `for-paid-ads-demo.html` lines 264-338 (CSS) | Add new CSS classes for report preview, modal, KPI chips, signal blocks, table, unit economics |
| `for-paid-ads-demo.html` lines 502-532 (Step 4 HTML) | Replace `.brief-shell` with `.report-preview` + modal trigger button |
| `for-paid-ads-demo.html` lines 742-751 (before script) | Add `#report-modal` markup |
| `for-paid-ads-demo.html` lines 753-887 (inline script) | Add `REPORT_DATA`, update `populateBrief()`, add modal functions, update `wtRestart()` |

---

## Task 1: Add CSS for the report preview and modal

**Files:**
- Modify: `for-paid-ads-demo.html` — inline `<style>` block

- [ ] **Step 1: Replace the existing media query block**

Find the existing media query at the bottom of the `<style>` block:
```css
  @media (max-width: 560px) {
    .plat-grid { grid-template-columns: 1fr; }
    .wt-card { padding: 24px 20px; }
  }
```

Replace it with the full CSS block below (which includes the original rules plus all new styles):

```css
  /* ---- Report preview (Step 4) ---- */
  .report-preview {
    position: relative;
    margin-bottom: 20px;
  }
  .report-preview-inner {
    background: var(--navy);
    border-radius: 12px;
    padding: 20px 20px 0;
    max-height: 340px;
    overflow: hidden;
    -webkit-mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
    mask-image: linear-gradient(to bottom, black 55%, transparent 100%);
  }
  .rpt-header { margin-bottom: 14px; }
  .rpt-title {
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    letter-spacing: .04em;
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  .rpt-meta { font-size: 11px; color: #6b6f82; }
  .rpt-verdict {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 10px;
    border-radius: 6px;
    margin-top: 10px;
  }
  .rpt-verdict.red    { background: rgba(239,68,68,.15);  color: #fca5a5; }
  .rpt-verdict.yellow { background: rgba(234,179,8,.15);  color: #fde68a; }
  .rpt-verdict.green  { background: rgba(34,197,94,.15);  color: #86efac; }

  /* KPI strip */
  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 16px;
  }
  .kpi-chip {
    background: #1a1d2e;
    border-radius: 8px;
    padding: 10px 10px 8px;
  }
  .kpi-label {
    font-size: 10px;
    color: #6b6f82;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 4px;
  }
  .kpi-value {
    font-size: 18px;
    font-weight: 700;
    color: #fff;
    line-height: 1;
    margin-bottom: 4px;
  }
  .kpi-delta {
    font-size: 10px;
    color: #6b6f82;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .kpi-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .kpi-dot.red    { background: #ef4444; }
  .kpi-dot.yellow { background: #eab308; }
  .kpi-dot.green  { background: #22c55e; }
  .kpi-dot.grey   { background: #6b6f82; }

  /* Signal blocks */
  .signal-block {
    background: #1a1d2e;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
  }
  .signal-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    padding: 3px 8px;
    border-radius: 4px;
    margin-bottom: 7px;
  }
  .signal-pill.red    { background: rgba(239,68,68,.2);  color: #fca5a5; }
  .signal-pill.yellow { background: rgba(234,179,8,.2);  color: #fde68a; }
  .signal-pill.green  { background: rgba(34,197,94,.2);  color: #86efac; }
  .signal-title {
    font-size: 13px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
    line-height: 1.35;
  }
  .signal-body {
    font-size: 12px;
    color: rgba(255,255,255,.65);
    line-height: 1.5;
  }
  .signal-owner {
    font-size: 11px;
    color: var(--orange);
    margin-top: 5px;
    font-weight: 500;
  }

  /* Campaign table */
  .camp-table-wrap {
    overflow-x: auto;
    margin-bottom: 16px;
    -webkit-overflow-scrolling: touch;
  }
  .camp-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    color: rgba(255,255,255,.8);
    min-width: 340px;
  }
  .camp-table th {
    text-align: left;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #6b6f82;
    padding: 0 10px 8px 0;
    font-weight: 600;
    border-bottom: 1px solid #2a2d3e;
  }
  .camp-table td {
    padding: 9px 10px 9px 0;
    border-bottom: 1px solid #1e2133;
    vertical-align: top;
  }
  .camp-table tr:last-child td { border-bottom: none; }
  .camp-status-scale   { color: #86efac; font-weight: 600; }
  .camp-status-pause   { color: #fca5a5; font-weight: 600; }
  .camp-status-monitor { color: #fde68a; font-weight: 600; }

  /* Unit economics */
  .unit-econ {
    background: #1a1d2e;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 16px;
  }
  .unit-econ-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    color: #6b6f82;
    margin-bottom: 10px;
  }
  .unit-econ-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: rgba(255,255,255,.75);
    padding: 4px 0;
    border-bottom: 1px solid #2a2d3e;
  }
  .unit-econ-row:last-child { border-bottom: none; }
  .unit-econ-val { font-weight: 600; color: #fff; }

  /* Section label */
  .rpt-section-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #6b6f82;
    margin: 18px 0 10px;
  }

  /* Data sources */
  .rpt-sources {
    font-size: 10px;
    color: #6b6f82;
    border-top: 1px solid #2a2d3e;
    padding: 12px 0 20px;
    line-height: 1.6;
  }

  /* View full report button */
  .view-report-btn {
    display: block;
    width: 100%;
    padding: 13px;
    background: var(--navy);
    border: 1.5px solid var(--orange);
    color: var(--orange);
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    text-align: center;
    margin-bottom: 14px;
    transition: background .15s, color .15s;
  }
  .view-report-btn:hover { background: var(--orange); color: #fff; }

  /* ---- Report Modal ---- */
  #report-modal {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 200;
    background: var(--navy);
    overflow-y: auto;
  }
  .modal-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 24px 24px 0;
  }
  .modal-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
  }
  .modal-topbar-title {
    font-size: 12px;
    font-weight: 600;
    color: #6b6f82;
    text-transform: uppercase;
    letter-spacing: .08em;
  }
  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    color: #6b6f82;
    font-size: 22px;
    line-height: 1;
    padding: 4px 6px;
    font-family: inherit;
    border-radius: 6px;
    transition: color .15s, background .15s;
  }
  .modal-close:hover { color: #fff; background: #2a2d3e; }
  .modal-cta-bar {
    position: sticky;
    bottom: 0;
    background: var(--navy);
    border-top: 1px solid #2a2d3e;
    padding: 16px 24px;
    text-align: center;
  }
  .modal-cta-bar .btn-orange {
    display: block;
    width: 100%;
    max-width: 400px;
    margin: 0 auto 8px;
    text-align: center;
  }
  .modal-cta-note {
    font-size: 11px;
    color: #6b6f82;
    margin: 0;
  }

  @media (max-width: 560px) {
    .plat-grid { grid-template-columns: 1fr; }
    .wt-card { padding: 24px 20px; }
    .kpi-strip { grid-template-columns: repeat(2, 1fr); }
  }
```

- [ ] **Step 2: Verify page still renders**

Run `python3 -m http.server 8080`, open `http://localhost:8080/for-paid-ads-demo.html`.
Expected: Page loads, no layout breaks, no console errors.

- [ ] **Step 3: Commit**

```bash
cd "/Users/work/Workspace/Alleviate Lab/duct"
git add for-paid-ads-demo.html
git commit -m "style: add CSS for world-class report preview and modal in paid ads demo"
```

---

## Task 2: Replace Step 4 HTML with report preview

**Files:**
- Modify: `for-paid-ads-demo.html` — the `<!-- STEP 4: Brief -->` block (lines ~502-532)

- [ ] **Step 1: Replace the Step 4 block**

Find the entire Step 4 block (from `<!-- STEP 4: Brief -->` through the closing `</div>` of `wt-step-4`) and replace it with:

```html
<!-- STEP 4: Brief -->
<div class="wt-step" id="wt-step-4">
<p class="wt-step-label">Step 4 of 4</p>
<p class="wt-step-title">Your report is ready</p>
<p class="wt-step-sub" id="wt-brief-sub">Here's what Duct found across your ad stack.</p>

<div class="report-preview">
  <div class="report-preview-inner">
    <div class="rpt-header">
      <p class="rpt-title">Paid Ads Performance Report</p>
      <p class="rpt-meta" id="rpt-meta"></p>
      <div class="rpt-verdict" id="rpt-verdict"></div>
    </div>
    <p class="rpt-section-label">Key Metrics</p>
    <div class="kpi-strip">
      <div class="kpi-chip">
        <p class="kpi-label">CAC</p>
        <p class="kpi-value" id="kpi-cac-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="kpi-cac-dot"></span><span id="kpi-cac-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">ROAS</p>
        <p class="kpi-value" id="kpi-roas-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="kpi-roas-dot"></span><span id="kpi-roas-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">Spend</p>
        <p class="kpi-value" id="kpi-spend-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="kpi-spend-dot"></span><span id="kpi-spend-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">Conversions</p>
        <p class="kpi-value" id="kpi-conv-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="kpi-conv-dot"></span><span id="kpi-conv-delta"></span></div>
      </div>
    </div>
    <p class="rpt-section-label">Signals</p>
    <div id="rpt-signals"></div>
  </div>
</div>

<button class="view-report-btn" onclick="openReportModal()">View full report &#8594;</button>
<div style="text-align:center;margin-bottom:10px">
  <p style="font-size:12px;color:var(--navy-3);margin:0 0 8px">Free during beta &middot; Connects in under 5 minutes &middot; No data stored without your approval</p>
  <button onclick="wtRestart()" class="wt-restart-btn" aria-label="Restart demo">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-.49-3.5"/></svg>
    Restart demo
  </button>
</div>
</div>
```

- [ ] **Step 2: Check Step 4 renders (empty but structured)**

Step through the demo in the browser. Step 4 should show an empty dark card with the fade and the "View full report" button. KPI chips and signals will be empty until Task 4.

- [ ] **Step 3: Commit**

```bash
cd "/Users/work/Workspace/Alleviate Lab/duct"
git add for-paid-ads-demo.html
git commit -m "feat: replace Step 4 brief with report preview shell"
```

---

## Task 3: Add the modal HTML

**Files:**
- Modify: `for-paid-ads-demo.html` — add modal before the inline `<script>` tag

- [ ] **Step 1: Add modal markup**

Find this line (comes after `</footer>`):
```html
<script>
(function() {
```

Insert the following immediately before that `<script>` tag:

```html
<!-- REPORT MODAL -->
<div id="report-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
  <div class="modal-inner">
    <div class="modal-topbar">
      <span class="modal-topbar-title" id="modal-title">Paid Ads Performance Report</span>
      <button class="modal-close" onclick="closeReportModal()" aria-label="Close report">&times;</button>
    </div>

    <div class="rpt-header">
      <p class="rpt-title">Paid Ads Performance Report</p>
      <p class="rpt-meta" id="modal-rpt-meta"></p>
      <div class="rpt-verdict" id="modal-rpt-verdict"></div>
    </div>

    <p class="rpt-section-label">Key Metrics</p>
    <div class="kpi-strip">
      <div class="kpi-chip">
        <p class="kpi-label">CAC</p>
        <p class="kpi-value" id="modal-kpi-cac-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="modal-kpi-cac-dot"></span><span id="modal-kpi-cac-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">ROAS</p>
        <p class="kpi-value" id="modal-kpi-roas-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="modal-kpi-roas-dot"></span><span id="modal-kpi-roas-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">Spend</p>
        <p class="kpi-value" id="modal-kpi-spend-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="modal-kpi-spend-dot"></span><span id="modal-kpi-spend-delta"></span></div>
      </div>
      <div class="kpi-chip">
        <p class="kpi-label">Conversions</p>
        <p class="kpi-value" id="modal-kpi-conv-val"></p>
        <div class="kpi-delta"><span class="kpi-dot" id="modal-kpi-conv-dot"></span><span id="modal-kpi-conv-delta"></span></div>
      </div>
    </div>

    <p class="rpt-section-label">Signals</p>
    <div id="modal-rpt-signals"></div>

    <p class="rpt-section-label">Campaign Performance</p>
    <div class="camp-table-wrap">
      <table class="camp-table">
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Spend</th>
            <th>CPA</th>
            <th>ROAS</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="modal-camp-tbody"></tbody>
      </table>
    </div>

    <p class="rpt-section-label">Unit Economics</p>
    <div class="unit-econ">
      <p class="unit-econ-title">Cost Efficiency</p>
      <div class="unit-econ-row">
        <span>Cost per new subscriber</span>
        <span class="unit-econ-val" id="modal-ue-cps"></span>
      </div>
      <div class="unit-econ-row">
        <span>LTV:CAC ratio <span style="color:#6b6f82">(Target: 3.0x)</span></span>
        <span class="unit-econ-val" id="modal-ue-ltv"></span>
      </div>
      <div class="unit-econ-row">
        <span>Verdict</span>
        <span class="unit-econ-val" id="modal-ue-verdict"></span>
      </div>
    </div>

    <p class="rpt-sources" id="modal-rpt-sources"></p>

  </div>

  <div class="modal-cta-bar">
    <a href="#cta" class="btn btn-orange btn-lg" onclick="closeReportModal()">Get this for my real data &rarr;</a>
    <p class="modal-cta-note">Free during beta &middot; Connects in under 5 minutes &middot; No data stored without your approval</p>
  </div>
</div>
<!-- END REPORT MODAL -->
```

- [ ] **Step 2: Verify modal element exists**

In browser DevTools console run: `document.getElementById('report-modal')`
Expected: returns the element. Modal not visible (display:none via CSS).

- [ ] **Step 3: Commit**

```bash
cd "/Users/work/Workspace/Alleviate Lab/duct"
git add for-paid-ads-demo.html
git commit -m "feat: add report modal HTML structure"
```

---

## Task 4: Add JS — REPORT_DATA, updated populateBrief(), modal functions

**Files:**
- Modify: `for-paid-ads-demo.html` — inline `<script>` IIFE

**Note on innerHTML usage:** All `innerHTML` assignments in this task set content from the `REPORT_DATA` constant defined in the same script. This data is never derived from user input or external sources, so there is no XSS risk.

- [ ] **Step 1: Add REPORT_DATA after the INSIGHTS object**

Inside the IIFE, find the closing `};` of `var INSIGHTS = { ... }` (the object ending after the `pipeline` array). Add `REPORT_DATA` immediately after:

```javascript
  /* ---- Report data, keyed by metric ---- */
  var REPORT_DATA = {
    cac: {
      verdictClass: 'red',
      verdictText: '\uD83D\uDD34 Spend up 42%, CAC 43% over target \u2014 pause Meta Prospecting',
      kpis: {
        cac:   { val: '$312',   delta: '\u254243% vs $218 target', dot: 'red' },
        roas:  { val: '4.2x',   delta: '\u254212% WoW',           dot: 'green' },
        spend: { val: '$24.8K', delta: '\u254242% MoM',           dot: 'grey' },
        conv:  { val: '79',     delta: '\u25BC8% WoW',            dot: 'red' }
      },
      signals: [
        { level: 'red',
          pill: '\uD83D\uDD34 Critical',
          title: 'Meta Prospecting CAC at $312 \u2014 43% over your $218 target',
          body:  'Spend increased 38% MoM but conversions fell 8%. Pause or cut Meta Prospecting budget by 30% until creative is refreshed.',
          owner: '\u2192 Paid team \u00B7 action this week' },
        { level: 'yellow',
          pill: '\uD83D\uDFE1 Watch',
          title: 'LinkedIn CTR down 38% WoW \u2014 creative fatigue setting in',
          body:  'Top 3 LinkedIn ads have been running 6+ weeks. Frequency is rising. Refresh creative before CTR decline hits CPA.',
          owner: '\u2192 Creative team \u00B7 action next sprint' },
        { level: 'green',
          pill: '\uD83D\uDFE2 Win',
          title: 'Google Brand ROAS at 4.2x \u2014 room to scale',
          body:  'Brand campaign is significantly outperforming target (3.0x). Increasing budget by 20% could add 15\u201320 conversions at current efficiency.',
          owner: '\u2192 Paid team \u00B7 increase budget' }
      ],
      campaigns: [
        { name: 'Google Brand',     spend: '$8.2K',  cpa: '$98',  roas: '4.2x', status: 'Scale \u2191', cls: 'camp-status-scale' },
        { name: 'Meta Prospecting', spend: '$11.4K', cpa: '$312', roas: '0.8x', status: 'Pause',        cls: 'camp-status-pause' },
        { name: 'LinkedIn Brand',   spend: '$5.2K',  cpa: '$187', roas: '1.9x', status: 'Monitor',      cls: 'camp-status-monitor' }
      ],
      unitEcon: { cps: '$218', ltv: '1.4x', verdict: '\uD83D\uDD34 Losing money' }
    },
    roas: {
      verdictClass: 'yellow',
      verdictText: '\uD83D\uDFE1 Blended ROAS 2.1x \u2014 Meta Prospecting dragging the average down',
      kpis: {
        cac:   { val: '$231',   delta: '\u25426% vs target', dot: 'yellow' },
        roas:  { val: '2.1x',   delta: '\u25BC18% WoW',     dot: 'red' },
        spend: { val: '$24.8K', delta: '\u254242% MoM',      dot: 'grey' },
        conv:  { val: '79',     delta: '\u25BC8% WoW',       dot: 'red' }
      },
      signals: [
        { level: 'red',
          pill: '\uD83D\uDD34 Critical',
          title: 'Meta Prospecting ROAS at 0.8x \u2014 losing $1.25 for every $1 spent',
          body:  'This campaign alone is pulling blended ROAS from 3.1x to 2.1x. Pause immediately or shift budget to Google Brand which is at 4.2x.',
          owner: '\u2192 Paid team \u00B7 action this week' },
        { level: 'yellow',
          pill: '\uD83D\uDFE1 Watch',
          title: 'Google Display ROAS dropped to 1.2x \u2014 impressions up 80%, conversions flat',
          body:  'Audience expansion appears to be broadening reach without improving conversion quality. Review targeting before scaling further.',
          owner: '\u2192 Paid team \u00B7 review targeting' },
        { level: 'green',
          pill: '\uD83D\uDFE2 Win',
          title: 'Google Brand ROAS at 4.2x with headroom to scale',
          body:  'Brand campaign is capped by budget, not performance. Reallocating $2K from Meta Prospecting to Google Brand would improve blended ROAS immediately.',
          owner: '\u2192 Paid team \u00B7 reallocate budget' }
      ],
      campaigns: [
        { name: 'Google Brand',     spend: '$8.2K',  cpa: '$98',  roas: '4.2x', status: 'Scale \u2191', cls: 'camp-status-scale' },
        { name: 'Google Display',   spend: '$4.1K',  cpa: '$201', roas: '1.2x', status: 'Monitor',      cls: 'camp-status-monitor' },
        { name: 'Meta Prospecting', spend: '$12.5K', cpa: '$312', roas: '0.8x', status: 'Pause',        cls: 'camp-status-pause' }
      ],
      unitEcon: { cps: '$231', ltv: '1.9x', verdict: '\uD83D\uDFE1 Breakeven' }
    },
    pipeline: {
      verdictClass: 'yellow',
      verdictText: '\uD83D\uDFE1 79 conversions this week \u2014 MQL\u2192deal rate dropped to 18%',
      kpis: {
        cac:   { val: '$231',    delta: '\u25426% WoW',  dot: 'yellow' },
        roas:  { val: '2.8x',    delta: '\u25BC4% WoW',  dot: 'yellow' },
        spend: { val: '$24.8K',  delta: '\u254242% MoM', dot: 'grey' },
        conv:  { val: '79 MQLs', delta: '\u25BC8% WoW',  dot: 'red' }
      },
      signals: [
        { level: 'red',
          pill: '\uD83D\uDD34 Critical',
          title: 'LinkedIn ad-attributed deals stalled \u2014 0 new deals in 14 days',
          body:  'LinkedIn is generating MQLs but none are progressing past initial call. Review ICP alignment on LinkedIn targeting and check sales follow-up cadence.',
          owner: '\u2192 Marketing + Sales \u00B7 align this week' },
        { level: 'yellow',
          pill: '\uD83D\uDFE1 Watch',
          title: 'Google Brand driving highest MQL quality (32% deal rate) but under-budgeted',
          body:  'Brand keywords convert MQLs to deals 2x faster than any other channel. Budget is $8.2K vs $12.5K on Meta which has a 9% deal rate.',
          owner: '\u2192 Paid team \u00B7 rebalance budget' },
        { level: 'green',
          pill: '\uD83D\uDFE2 Win',
          title: 'Meta retargeting driving 3x more pipeline per dollar than prospecting',
          body:  'Retargeting audiences (site visitors + email list) converting at $68 CPL vs $312 for cold prospecting. Increasing retargeting budget by $2K would add ~29 MQLs.',
          owner: '\u2192 Paid team \u00B7 increase retargeting' }
      ],
      campaigns: [
        { name: 'Google Brand',     spend: '$8.2K',  cpa: '$98',  roas: '4.2x', status: 'Scale \u2191', cls: 'camp-status-scale' },
        { name: 'Meta Retargeting', spend: '$4.8K',  cpa: '$68',  roas: '3.8x', status: 'Scale \u2191', cls: 'camp-status-scale' },
        { name: 'LinkedIn Ads',     spend: '$11.8K', cpa: '$287', roas: '1.1x', status: 'Monitor',      cls: 'camp-status-monitor' }
      ],
      unitEcon: { cps: '$231', ltv: '2.4x', verdict: '\uD83D\uDFE1 Breakeven' }
    }
  };
```

- [ ] **Step 2: Add helper functions before populateBrief()**

Find the comment `/* ---- Populate brief ---- */` and insert these helpers immediately before it:

```javascript
  /* ---- Report helpers ---- */
  function buildSignalsHTML(signals) {
    var html = '';
    for (var i = 0; i < signals.length; i++) {
      var s = signals[i];
      html += '<div class="signal-block">' +
        '<span class="signal-pill ' + s.level + '">' + s.pill + '</span>' +
        '<p class="signal-title">' + s.title + '</p>' +
        '<p class="signal-body">' + s.body + '</p>' +
        '<p class="signal-owner">' + s.owner + '</p>' +
        '</div>';
    }
    return html;
  }

  function buildCampRowsHTML(campaigns) {
    var html = '';
    for (var i = 0; i < campaigns.length; i++) {
      var c = campaigns[i];
      html += '<tr>' +
        '<td>' + c.name + '</td>' +
        '<td>' + c.spend + '</td>' +
        '<td>' + c.cpa + '</td>' +
        '<td>' + c.roas + '</td>' +
        '<td class="' + c.cls + '">' + c.status + '</td>' +
        '</tr>';
    }
    return html;
  }

  function setKPIChips(prefix, kpis) {
    var pairs = [
      ['cac', kpis.cac], ['roas', kpis.roas], ['spend', kpis.spend], ['conv', kpis.conv]
    ];
    for (var i = 0; i < pairs.length; i++) {
      var key = pairs[i][0];
      var k   = pairs[i][1];
      document.getElementById(prefix + 'kpi-' + key + '-val').textContent   = k.val;
      document.getElementById(prefix + 'kpi-' + key + '-delta').textContent = k.delta;
      document.getElementById(prefix + 'kpi-' + key + '-dot').className     = 'kpi-dot ' + k.dot;
    }
  }
```

- [ ] **Step 3: Replace the populateBrief() function**

Find and replace the existing `/* ---- Populate brief ---- */` function:
```javascript
  /* ── Populate brief ── */
  function populateBrief() {
    var platList = state.platforms.join(' + ');
    var metricLabel = { cac: 'lower CAC', roas: 'higher ROAS', pipeline: 'more pipeline' }[state.metric] || 'your goal';
    document.getElementById('wt-brief-header').textContent = '\u26A1 Duct found 3 signals for ' + platList;
    document.getElementById('wt-brief-sub').textContent = 'Optimised for ' + metricLabel + ' across ' + platList + '.';
    var bank = INSIGHTS[state.metric] || INSIGHTS.roas;
    document.getElementById('bi-text-1').innerHTML = fillInsight(bank[0]);
    document.getElementById('bi-text-2').innerHTML = fillInsight(bank[1]);
    document.getElementById('bi-text-3').innerHTML = fillInsight(bank[2]);
  }
```

Replace with:

```javascript
  /* ---- Populate report (preview + modal) ---- */
  function populateBrief() {
    var metricKey = state.metric || 'cac';
    var d = REPORT_DATA[metricKey];
    var platList = state.platforms.join(' \u00B7 ');
    var metricLabel = { cac: 'lower CAC', roas: 'higher ROAS', pipeline: 'more pipeline' }[metricKey];
    var meta = 'Mar 21\u201328, 2026 \u00B7 ' + platList;
    var sources = 'Data: Google Ads API \u00B7 Meta Ads Manager \u00B7 LinkedIn Campaign Manager \u00B7 as of Mar 28, 2026 \u00B7 Optimised for ' + metricLabel;

    document.getElementById('wt-brief-sub').textContent = 'Optimised for ' + metricLabel + ' \u00B7 ' + platList;

    /* Preview */
    document.getElementById('rpt-meta').textContent = meta;
    var pv = document.getElementById('rpt-verdict');
    pv.className = 'rpt-verdict ' + d.verdictClass;
    pv.textContent = d.verdictText;
    setKPIChips('kpi-', d.kpis);
    document.getElementById('rpt-signals').innerHTML = buildSignalsHTML(d.signals);

    /* Modal */
    document.getElementById('modal-rpt-meta').textContent = meta;
    var mv = document.getElementById('modal-rpt-verdict');
    mv.className = 'rpt-verdict ' + d.verdictClass;
    mv.textContent = d.verdictText;
    setKPIChips('modal-kpi-', d.kpis);
    document.getElementById('modal-rpt-signals').innerHTML = buildSignalsHTML(d.signals);
    document.getElementById('modal-camp-tbody').innerHTML = buildCampRowsHTML(d.campaigns);
    document.getElementById('modal-ue-cps').textContent     = d.unitEcon.cps;
    document.getElementById('modal-ue-ltv').textContent     = d.unitEcon.ltv;
    document.getElementById('modal-ue-verdict').textContent = d.unitEcon.verdict;
    document.getElementById('modal-rpt-sources').textContent = sources;
  }
```

- [ ] **Step 4: Add openReportModal() and closeReportModal()**

Find `window.wtRestart = function()` and insert the following immediately before it:

```javascript
  /* ---- Modal open / close ---- */
  window.openReportModal = function() {
    var modal = document.getElementById('report-modal');
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
    modal.scrollTop = 0;
  };

  window.closeReportModal = function() {
    document.getElementById('report-modal').style.display = 'none';
    document.body.style.overflow = '';
  };

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeReportModal(); }
  });
```

- [ ] **Step 5: Update wtRestart() to close modal**

Inside `window.wtRestart`, find:
```javascript
    document.getElementById('wt-step-1').classList.add('active');
    updateProgress();
```

Add `closeReportModal();` on the next line:
```javascript
    document.getElementById('wt-step-1').classList.add('active');
    updateProgress();
    closeReportModal();
```

- [ ] **Step 6: Full verification in browser**

Start server: `python3 -m http.server 8080`
Open: `http://localhost:8080/for-paid-ads-demo.html`

Run through this checklist:

1. Select Google Ads + Meta, choose **Lower CAC** → arrive at Step 4
   - Preview shows red verdict badge, 4 KPI chips, 3 signal blocks, bottom fades out
2. Click **"View full report"** → modal opens over full screen
   - All 6 sections visible: header, KPIs, signals, campaign table, unit economics, data sources
   - Floating CTA bar stuck to bottom of modal
3. Press **Escape** → modal closes
4. Open modal again → click **×** → modal closes
5. Click **Restart demo** → modal closes, returns to Step 1
6. Run through demo again, select **Higher ROAS** → Step 4 shows different verdict (yellow) + ROAS signals
7. Run through demo again, select **More pipeline** → Step 4 shows pipeline signals, stalled LinkedIn deals
8. Resize browser to 375px wide:
   - KPI strip shows 2 columns
   - Campaign table scrolls horizontally inside modal
   - Modal CTA bar visible at bottom

- [ ] **Step 7: Commit**

```bash
cd "/Users/work/Workspace/Alleviate Lab/duct"
git add for-paid-ads-demo.html
git commit -m "feat: implement world-class paid ads report with preview, modal, and 3 metric variants"
```

---

## Self-Review

**Spec coverage:**
- Report header with date + platforms: Task 2 (preview), Task 3 (modal)
- Verdict badge coloured: Task 4 `verdictClass` + `.rpt-verdict.red/yellow/green`
- 4 KPI chips with delta + status dot: Tasks 2, 3, 4 `setKPIChips()`
- 3 signals (Critical/Watch/Win) with owner: Tasks 2, 3, 4 `buildSignalsHTML()`
- Campaign table (5 columns): Task 3 HTML + Task 4 `buildCampRowsHTML()`
- Unit economics (CPS, LTV:CAC, verdict): Task 3 HTML + Task 4
- Data sources footer: Task 3 HTML + Task 4 `sources` textContent
- Preview with fade mask: Task 1 `mask-image` CSS + Task 2 HTML
- "View full report" button: Task 2
- Modal (full-screen, dark, scrollable): Task 1 CSS + Task 3 HTML
- Floating CTA sticky in modal: Task 1 `.modal-cta-bar { position: sticky }`
- Close via × and Escape: Task 4
- wtRestart() closes modal: Task 4
- 3 metric variants (CAC/ROAS/Pipeline): Task 4 `REPORT_DATA`
- All styles in inline style block, no duct.css changes: confirmed
- No new files: confirmed

**Placeholder scan:** All signal copy, KPI values, campaign rows, unit economics are concrete strings. No TBDs.

**Type consistency:**
- `setKPIChips('kpi-', ...)` → IDs `kpi-cac-val`, `kpi-roas-val` etc — match Task 2 HTML
- `setKPIChips('modal-kpi-', ...)` → IDs `modal-kpi-cac-val` etc — match Task 3 HTML
- `buildSignalsHTML` and `buildCampRowsHTML` return strings → consumed via `innerHTML` on `rpt-signals`, `modal-rpt-signals`, `modal-camp-tbody` — all present in Tasks 2 and 3
- `d.campaigns[i].cls` → used in `buildCampRowsHTML` as className — matches `REPORT_DATA` field name `cls`
