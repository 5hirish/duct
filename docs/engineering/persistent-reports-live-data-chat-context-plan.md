# Plan: Persistent Reports with Live Data Refresh and Chat-Ready Context

## Context

Currently, generated reports are saved to localStorage as static snapshots (`{ slug, payload, savedAt }`). There's no way to re-fetch fresh data without going through the full 6-step generate wizard again, and there's no structured context that could power a future chat sidebar on the report. 

This plan introduces:
1. **Report routines** — the "recipe" for re-fetching a report is stored alongside the snapshot
2. **Live data refresh** — when a saved report is opened, the backend re-runs fetch+normalize (no LLM) with the stored routine and today's dates
3. **Chat-ready context** — a `ReportContext` React provider that assembles a structured payload any LLM can consume, ready for a future chat sidebar

Everything is localStorage-only (no backend DB), backward compatible with existing saved reports, and does not re-run expensive LLM synthesis on refresh.

---

## Phase 1 — Extended localStorage Schema

**File:** `app/src/lib/localReports.js`

The existing entry shape `{ slug, payload, savedAt }` gains three optional sibling keys: `routine`, `refresh`, `ui`. Old entries without them continue to load unchanged.

```javascript
// NEW entry shape (old entries still work — new keys are optional)
{
  slug: "local-...",
  payload: { /* UnifiedReport — unchanged */ },
  savedAt: "...",

  // routine: what to re-fetch (no tokens, just IDs + config)
  routine: {
    schema_version: 1,
    date_preset: "30",          // "7" | "30" | "90" | "custom"
    custom_date_from: null,     // only when date_preset === "custom"
    custom_date_to: null,
    goal: "maximize_roas",
    custom_goal: "",
    context: "",
    connections: ["google_ads"],
    targets: {
      google_ads: { customer_id: "...", account_name: "...", currency_code: "USD", login_customer_id: "" },
      ga4: { property_id: "..." },       // if selected
      gsc: { site_url: "..." }           // if selected
    },
    business_context: { /* BusinessContext fields */ }
  },

  // refresh: live-data state
  refresh: {
    last_refreshed_at: null,    // ISO or null
    refresh_status: "idle",     // "idle" | "loading" | "error"
    refresh_error: null,
    live_briefs: null           // { google_ads: {...} } or null — overrides payload.briefs at render
  },

  // ui: user overrides and annotations (for chat integration)
  ui: {
    schema_version: 1,
    kpi_overrides: [],          // [{ kpi_id, hidden, custom_label }]
    annotations: [],            // [{ id, target, target_id, text, created_at }]
    action_items: []            // [{ id, text, status, created_at, source, campaign_ref }]
  }
}
```

**Functions to add** (no changes to existing functions):
- `getReportEntry(slug)` — returns full entry (not just payload); used by LocalReportDetail
- `patchReportRefresh(slug, patch)` — merges into `entry.refresh`
- `patchReportUi(slug, patch)` — merges into `entry.ui`
- Modify `saveLocalReport(slug, payload, routine?)` — optional 3rd arg; if present, initializes `routine`, `refresh`, `ui` on the entry

---

## Phase 2 — Backend: `POST /api/reports/refresh`

This re-runs fetch+normalize only (steps 1–2 of the pipeline in `generate.py`). No LLM, no supplementary fetch. Returns fresh `briefs`.

### New file: `backend/routes/reports.py`

```python
router = APIRouter(tags=["reports"])

@router.post("/refresh")
async def refresh_report(req: ReportRefreshRequest) -> ReportRefreshResponse:
    # 1. Resolve dates from preset
    date_from, date_to = resolve_date_range(req.date_preset, req.date_from, req.date_to)
    # 2. For each connector in req.connections: call fetch_connector logic (reused from generate.py)
    # 3. For each connector: call _build_connector_brief (already exists in generate.py)
    # 4. Return { refreshed_at, briefs, date_from, date_to }
```

**Extract shared util:** Move `fetch_connector` inner function logic and `_build_connector_brief` from `generate.py` to `backend/service/pipeline.py` so both routes share it without duplication.

### New schemas in `backend/routes/schemas.py`:

```python
class RefreshRoutineTarget(BaseModel):
    customer_id: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    login_customer_id: str = ""
    property_id: str = ""      # ga4
    site_url: str = ""         # gsc

class ReportRefreshRequest(BaseModel):
    connections: list[str] = []
    date_preset: str = "30"    # "7" | "30" | "90" | "custom"
    date_from: str = ""        # only for "custom"
    date_to: str = ""
    refresh_token: str = ""           # gads OAuth token (from sessionStorage)
    ga4_refresh_token: str = ""
    gsc_refresh_token: str = ""
    targets: dict[str, RefreshRoutineTarget] = {}

class ReportRefreshResponse(BaseModel):
    refreshed_at: str
    briefs: dict[str, Any]
    date_from: str
    date_to: str
```

**Register** in `backend/routes/namespace.py`:
```python
from routes import reports
router.include_router(reports.router, prefix="/api/reports")
```

**Date resolution helper** (pure Python, ~10 lines, put in `backend/service/pipeline.py`):
```python
def resolve_date_range(preset, custom_from, custom_to):
    today = date.today()
    if preset == "custom":
        return custom_from, custom_to
    days = {"7": 7, "30": 30, "90": 90}.get(preset, 30)
    return str(today - timedelta(days=days)), str(today)
```

---

## Phase 3 — Frontend: Live Refresh

### `app/src/lib/api.js` — add `refreshReportBriefs(routine)`

Reads OAuth tokens from `sessionStorage`, posts to `/api/reports/refresh`, returns `{ refreshed_at, briefs, date_from, date_to }`.

### `app/src/app/(app)/generate/page.jsx` — pass routine to `saveLocalReport`

In `handleSave`, assemble the `routine` object from wizard state (connections, date preset, goal, targets from selected accounts, business context) and pass as 3rd arg to `saveLocalReport`.

### `app/src/components/LocalReportDetail.jsx` — auto-refresh on load

```
useEffect:
  1. Read full entry via getReportEntry(slug)
  2. If entry.routine exists AND sessionStorage has tokens:
     - Set refreshStatus = "loading"
     - Call refreshReportBriefs(entry.routine)
     - On success: patchReportRefresh(...), setLiveBriefs(result.briefs)
     - On error: patchReportRefresh({ status: "error", error: msg })
  3. If no routine: render from entry.payload as before (backward compat)

Render:
  - brief = liveBriefs?.google_ads ?? payload.briefs?.google_ads ?? payload
  - Show refresh bar: "Refreshing..." | "Live data as of X" | "Could not refresh — showing saved data" + manual Refresh button
```

---

## Phase 4 — Chat-Ready Context

### New file: `app/src/components/ReportContext.js`

A React context that sits between `LocalReportDetail` and `GoogleAdsReport`. It holds the full resolved state plus a `chatPayload` object.

```javascript
// chatPayload shape (consumed by future LLM chat)
{
  report_id, generated_at, last_refreshed_at,
  goal, custom_goal, connectors, date_window: { current, previous },
  account: { name, currency },
  kpis: { spend, conversions, cpa, roas },       // formatted strings
  trends: { spend, conversions, cpa, roas },      // delta objects
  narrative,                                       // from synthesis or brief
  findings: [ { ...finding, category: "win"|"risk" } ],
  recommended_actions: [],
  campaigns: [ { name, spend, roas, cpa, action } ],
  annotations: [],       // from ui.annotations
  action_items: [],      // from ui.action_items
  business_context,
  summary_text           // pre-flattened string for LLM system prompt injection
}
```

`LocalReportDetail` wraps its return in `<ReportContextProvider entry={entry} liveBriefs={liveBriefs}>`. Future chat sidebar just calls `useReportContext().chatPayload`.

---

## Implementation Sequence

1. **Storage layer** — extend `localReports.js` (add helpers, modify `saveLocalReport`)
2. **Wizard save** — update `handleSave` in `generate/page.jsx` to pass routine
3. **Backend schemas** — add `ReportRefreshRequest`, `RefreshRoutineTarget`, `ReportRefreshResponse` to `schemas.py`
4. **Backend util** — extract `resolve_date_range` + shared fetch/normalize logic to `service/pipeline.py`
5. **Backend route** — create `routes/reports.py`, register in `namespace.py`
6. **Frontend API** — add `refreshReportBriefs` to `api.js`
7. **LocalReportDetail** — switch to `getReportEntry`, add auto-refresh logic + refresh status bar
8. **ReportContext** — new file, wrap `LocalReportDetail` render
9. **Reports list badge** — add "Live" badge to entries that have a `routine`

---

## Critical Files

| File | Change |
|------|--------|
| `app/src/lib/localReports.js` | Add helpers, extend `saveLocalReport` |
| `app/src/app/(app)/generate/page.jsx` | Assemble + pass routine in `handleSave` |
| `app/src/lib/api.js` | Add `refreshReportBriefs` |
| `app/src/components/LocalReportDetail.jsx` | Auto-refresh, use `getReportEntry`, refresh bar |
| `app/src/components/ReportContext.js` | New file — context + `chatPayload` builder |
| `app/src/components/ReportsList.jsx` | Add "Live" badge for routine-enabled reports |
| `backend/routes/schemas.py` | Add 3 new schemas |
| `backend/routes/reports.py` | New file — refresh endpoint |
| `backend/service/pipeline.py` | New file — shared fetch/normalize + date resolution |
| `backend/routes/namespace.py` | Register reports router |
| `backend/routes/generate.py` | Refactor to use shared pipeline utils |

---

## Verification

1. Generate a new report → save → inspect localStorage: entry should have `routine`, `refresh`, `ui` keys
2. Navigate away, reopen report → see "Refreshing data…" → see "Live data as of [timestamp]"
3. Open report with no sessionStorage tokens → graceful fallback to saved data, no error crash
4. Old saved reports (no `routine`) still load correctly
5. `POST /api/reports/refresh` with curl: returns `{ refreshed_at, briefs, date_from, date_to }` without LLM cost
6. `console.log(useReportContext().chatPayload)` from a test component shows structured data with `summary_text` populated
