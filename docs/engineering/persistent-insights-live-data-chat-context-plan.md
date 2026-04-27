# Plan: Persistent Insights with Live Data Refresh and Chat-Ready Context

> This plan supersedes `persistent-reports-live-data-chat-context-plan.md`. "Reports" is now "Insights" everywhere — in routes, schemas, component names, and localStorage keys.

## Context

Generated insights need to be:
1. **Persistent** — saved to localStorage with their full structure so they can be reopened
2. **Live** — when reopened, fresh data is fetched automatically using the stored routine (connections + date logic), without re-running LLM synthesis
3. **Chat-ready** — the insight state is held in a React context structured for a future LLM chat sidebar

Everything is localStorage-only (no backend DB), backward compatible with existing saved entries.

---

## Current State (What's Already Built)

Most of this plan is **already implemented**. The doc below reflects the actual code as of 2026-04-28.

### Backend — already done

| File | Status | What it does |
|------|--------|-------------|
| `backend/routes/reports.py` | ✅ Built | `POST /api/insights/refresh` endpoint |
| `backend/routes/schemas.py` | ✅ Built | `InsightRefreshRequest`, `InsightRefreshResponse`, `UnifiedInsight`, `InsightMetadata` |
| `backend/service/pipeline.py` | ✅ Built | `resolve_date_range`, `fetch_connector_payload`, `build_connector_brief`, `normalize_connections`, `now_iso` |
| `backend/routes/namespace.py` | ✅ Built | `reports.router` mounted at `/api/insights` with tag `"insights"` |

**API contract (live):**

```
POST /api/insights/refresh
Body: InsightRefreshRequest {
  connections: list[str]
  date_preset: "7" | "30" | "90" | "custom"
  date_from: str  (only for "custom")
  date_to: str
  refresh_token: str        (Google Ads OAuth token)
  ga4_refresh_token: str
  gsc_refresh_token: str
  targets: dict[str, InsightRefreshTarget] {
    google_ads: { customer_id, account_name, currency_code, login_customer_id }
    ga4:        { property_id }
    gsc:        { site_url }
  }
}
Response: InsightRefreshResponse {
  refreshed_at: str   (ISO 8601)
  briefs: dict        (connector_id → brief dict — same shape as UnifiedInsight.briefs)
  date_from: str
  date_to: str
}
```

No LLM is called. Fetch + normalize only. Synthesis from the original save is preserved.

### Frontend — already done

| File | Status | What it does |
|------|--------|-------------|
| `app/src/lib/localReports.js` | ✅ Built | Full routine/refresh/ui schema; all helpers implemented |
| `app/src/lib/api.js` | ✅ Built | `refreshReportBriefs(routine)` calls `POST /api/insights/refresh` |
| `app/src/components/ReportContext.js` | ✅ Built | `ReportContextProvider`, `useReportContext`, `chatPayload` |

**localStorage schema (live):**

```javascript
// Key: "duct_local_reports"  (storage key unchanged for now — see migration note)
{
  slug: "local-{customerId}-{dateTo}-{timestamp}",
  payload: { /* UnifiedInsight envelope */ },
  savedAt: "2026-04-28T...",
  project_id: null,     // for future multi-project support
  mode: "paid_ads",     // insight mode

  routine: {
    schema_version: 1,
    date_preset: "30",          // "7" | "30" | "90" | "custom"
    custom_date_from: null,
    custom_date_to: null,
    goal: "maximize_roas",
    custom_goal: "",
    context: "",
    connections: ["google_ads"],
    targets: {
      google_ads: { customer_id, account_name, currency_code, login_customer_id },
      ga4: { property_id },
      gsc: { site_url }
    },
    business_context: { /* BusinessContext fields */ },
    mode: "paid_ads"
  },

  refresh: {
    last_refreshed_at: null,    // ISO or null
    refresh_status: "idle",     // "idle" | "loading" | "error"
    refresh_error: null,
    live_briefs: null           // overrides payload.briefs when present
  },

  ui: {
    schema_version: 1,
    kpi_overrides: [],          // [{ kpi_id, hidden, custom_label }]
    annotations: [],            // [{ id, target, target_id, text, created_at }]
    action_items: []            // [{ id, text, status, created_at, source, campaign_ref }]
  }
}
```

**`localReports.js` exports (live):**
- `saveLocalReport(slug, payload, routine?, projectId?, mode?)` — creates entry with routine/refresh/ui initialized
- `getLocalReports(projectId?, mode?)` — filtered list
- `getLocalReportBySlug(slug)` — returns `entry.payload` (backward compat)
- `getReportEntry(slug)` — returns full entry with defaults filled in
- `patchReportRefresh(slug, patch)` — merges into `entry.refresh`
- `patchReportUi(slug, patch)` — merges into `entry.ui`
- `deleteLocalReport(slug)`, `generateSlug(customerId, dateTo)`

**`api.js` (live):**
- `refreshReportBriefs(routine)` — reads tokens from `sessionStorage`, posts to `/api/insights/refresh`

---

## What Still Needs to Be Done

### 1. Rename localStorage key (migration)

The storage key is still `"duct_local_reports"` — the constant `LOCAL_REPORTS_STORAGE_KEY` and `STORAGE_KEY` in `localReports.js` need to become `"duct_local_insights"`.

This requires a one-time migration on app load: read from old key, write to new key, delete old key.

```javascript
// app/src/lib/localReports.js
const OLD_STORAGE_KEY = "duct_local_reports";
export const LOCAL_INSIGHTS_STORAGE_KEY = "duct_local_insights";
const STORAGE_KEY = LOCAL_INSIGHTS_STORAGE_KEY;

// Run once at module init — migrate old key to new key
function migrateStorageKey() {
  if (typeof localStorage === "undefined") return;
  const old = localStorage.getItem(OLD_STORAGE_KEY);
  if (old && !localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, old);
    localStorage.removeItem(OLD_STORAGE_KEY);
  }
}
migrateStorageKey();
```

### 2. Rename frontend functions and exports to "Insight" terminology

The function names still use `Report` internally (`saveLocalReport`, `getReportEntry`, `patchReportRefresh`, etc.). These should be aliased or renamed to `saveLocalInsight`, `getInsightEntry`, `patchInsightRefresh`, etc. — but keep the old names as re-exports for backward compatibility during the transition.

```javascript
// New canonical names
export const saveLocalInsight = saveLocalReport;
export const getInsightEntry = getReportEntry;
export const getLocalInsights = getLocalReports;
export const patchInsightRefresh = patchReportRefresh;
export const patchInsightUi = patchReportUi;
export const deleteLocalInsight = deleteLocalReport;
```

### 3. Rename `refreshReportBriefs` → `refreshInsightBriefs` in `api.js`

```javascript
// app/src/lib/api.js
export async function refreshInsightBriefs(routine) { ... }
// keep old name as alias during transition
export const refreshReportBriefs = refreshInsightBriefs;
```

### 4. `LocalReportDetail.jsx` → `LocalInsightDetail.jsx` — auto-refresh wiring

The component needs to:
1. Call `getInsightEntry(slug)` instead of `getLocalReportBySlug(slug)`
2. On load, if `entry.routine` exists and tokens are in `sessionStorage`, auto-call `refreshInsightBriefs`
3. Use `entry.refresh.live_briefs` in preference to `entry.payload.briefs` for rendering
4. Show a refresh status bar: `"Refreshing…"` | `"Live data as of {time}"` | `"Could not refresh — showing saved data"` + manual Refresh button

```jsx
useEffect(() => {
  const entry = getInsightEntry(slug);
  if (!entry) { setNotFound(true); return; }
  setEntry(entry);

  const hasTokens = !!sessionStorage.getItem("gads_refresh_token");
  if (entry.routine && hasTokens) {
    setRefreshStatus("loading");
    refreshInsightBriefs(entry.routine)
      .then(result => {
        patchInsightRefresh(slug, {
          live_briefs: result.briefs,
          last_refreshed_at: result.refreshed_at,
          refresh_status: "idle",
          refresh_error: null,
        });
        setLiveBriefs(result.briefs);
        setRefreshStatus("idle");
      })
      .catch(err => {
        patchInsightRefresh(slug, { refresh_status: "error", refresh_error: err.message });
        setRefreshStatus("error");
      });
  }
}, [slug]);

// Prefer live data; fall back to saved payload
const activeBriefs = liveBriefs ?? entry?.payload?.briefs;
const brief = activeBriefs?.google_ads ?? entry?.payload;
```

### 5. `generate/page.jsx` — pass routine when saving

In `handleSave`, assemble and pass the `routine` object:

```javascript
const routine = {
  date_preset: datePreset,           // from wizard state
  custom_date_from: datePreset === "custom" ? dateFrom : null,
  custom_date_to: datePreset === "custom" ? dateTo : null,
  goal,
  custom_goal: goal === "custom" ? customGoal : "",
  context,
  connections: selectedConnections,
  mode: insightMode,                 // "paid_ads" | "organic_growth"
  targets: {
    ...(selectedConnections.includes("google_ads") && {
      google_ads: { customer_id: selectedAdsCustomerId, account_name, currency_code, login_customer_id: "" }
    }),
    ...(selectedConnections.includes("ga4") && { ga4: { property_id: selectedGa4PropertyId } }),
    ...(selectedConnections.includes("gsc") && { gsc: { site_url: selectedGscSiteUrl } }),
  },
  business_context: businessContext,
};

saveLocalInsight(slug, report, routine, projectId, insightMode);
```

### 6. `ReportContext.js` → `InsightContext.js` — rename + align with `dashboard_spec`

The existing `ReportContext.js` needs to be updated to:
- Be renamed `InsightContext.js` (or export from both paths during transition)
- Include `dashboard_spec` from `synthesis` in the context value — this is needed for `InsightDashboard` (from the intelligent insights plan) to read the agent-specified block layout
- Include `supplementary` data from the envelope (once it's surfaced — see intelligent insights plan)

```javascript
// app/src/components/InsightContext.js
export function InsightContextProvider({ entry, liveBriefs, children }) {
  const value = useMemo(() => {
    if (!entry) return null;
    const payload = entry.payload;
    const activeBriefs = liveBriefs ?? payload?.briefs;
    const brief = activeBriefs?.google_ads ?? payload;
    const synthesis = payload?.synthesis ?? null;
    const supplementary = payload?.supplementary ?? {};  // NEW — from UnifiedInsight v3

    return {
      brief,
      synthesis,
      activeBriefs,
      supplementary,                                      // NEW
      dashboard_spec: synthesis?.dashboard_spec ?? null, // NEW — agent-specified layout
      routine: entry.routine ?? null,
      refresh: entry.refresh ?? null,
      ui: entry.ui ?? { kpi_overrides: [], annotations: [], action_items: [] },
      chatPayload: buildChatPayload({ brief, synthesis, entry }),
    };
  }, [entry, liveBriefs]);

  return <InsightContext.Provider value={value}>{children}</InsightContext.Provider>;
}
```

### 7. `InsightsList` / `ReportsList` — "Live" badge

Add a visual indicator to insight cards that have a `routine` stored (meaning they support auto-refresh):

```jsx
{entry.routine && (
  <span className="insight-badge-live">Live</span>
)}
{entry.refresh?.last_refreshed_at && (
  <span className="insight-meta-refresh">
    Refreshed {formatTimeAgo(entry.refresh.last_refreshed_at)}
  </span>
)}
```

---

## Alignment With `intelligent-insights-architecture-plan.md`

The two plans connect at these points:

| Intelligent Insights Plan | This Plan |
|--------------------------|-----------|
| `UnifiedInsight.supplementary` field (Phase 4 in generate.py) | `InsightContext` must expose `supplementary` so `InsightDashboard` can resolve block data sources |
| `synthesis.dashboard_spec` (agent-emitted block layout) | `InsightContext` must expose `dashboard_spec` — `InsightDashboard` reads it from context |
| `InsightDashboard.jsx` (new root renderer) | Replaces `GoogleAdsReport.js` in `LocalInsightDetail` — receives props from context |
| `localReports.js` `live_briefs` in `refresh` | `resolveBlockData()` in `insightData.js` uses `live_briefs ?? payload.briefs` as the data source |
| Tool registry / `UnifiedInsight v3` | When `supplementary` is added to the envelope, `saveLocalInsight` stores it in `payload.supplementary`; `InsightContext` passes it to the dashboard |

---

## Naming Cleanup Summary

| Old name | New name | Where |
|----------|----------|-------|
| `persistent-reports-live-data-chat-context-plan.md` | `persistent-insights-live-data-chat-context-plan.md` | docs |
| `duct_local_reports` | `duct_local_insights` | localStorage key |
| `LOCAL_REPORTS_STORAGE_KEY` | `LOCAL_INSIGHTS_STORAGE_KEY` | `localReports.js` |
| `saveLocalReport` | `saveLocalInsight` | `localReports.js` |
| `getReportEntry` | `getInsightEntry` | `localReports.js` |
| `getLocalReports` | `getLocalInsights` | `localReports.js` |
| `patchReportRefresh` | `patchInsightRefresh` | `localReports.js` |
| `patchReportUi` | `patchInsightUi` | `localReports.js` |
| `deleteLocalReport` | `deleteLocalInsight` | `localReports.js` |
| `refreshReportBriefs` | `refreshInsightBriefs` | `api.js` |
| `ReportContext.js` | `InsightContext.js` | `app/src/components/` |
| `useReportContext` | `useInsightContext` | component imports |
| `LocalReportDetail.jsx` | `LocalInsightDetail.jsx` | `app/src/components/` |
| `GoogleAdsReport.js` | `InsightDashboard.jsx` | `app/src/components/` |
| `ReportsList.jsx` | `InsightsList.jsx` (or keep, update internals) | `app/src/components/` |
| `POST /api/reports/refresh` | `POST /api/insights/refresh` | backend route — ✅ already done |
| `ReportRequest` | keep as-is (internal shim) | `backend/routes/schemas.py` |
| `UnifiedReport` | `UnifiedInsight` | `backend/routes/schemas.py` — ✅ already done |

---

## Remaining Work — Ordered

1. `localReports.js` — rename storage key + add migration + add insight-named aliases
2. `api.js` — rename `refreshReportBriefs` → `refreshInsightBriefs` + alias
3. `LocalReportDetail.jsx` → `LocalInsightDetail.jsx` — auto-refresh wiring (section 4 above)
4. `generate/page.jsx` — pass `routine` + `mode` to `saveLocalInsight` on save
5. `ReportContext.js` → `InsightContext.js` — add `supplementary`, `dashboard_spec` to context value
6. `InsightsList` / `ReportsList` — add "Live" badge + last-refreshed timestamp
7. (Deferred — depends on intelligent insights plan) `InsightDashboard.jsx` replace `GoogleAdsReport.js` once `dashboard_spec` + `supplementary` are in the envelope

---

## Verification

1. Generate an insight → save → inspect localStorage under `"duct_local_insights"`: entry has `routine`, `refresh`, `ui`
2. Open a saved insight → see `"Refreshing…"` → see `"Live data as of {time}"`, KPIs update
3. Open with no `sessionStorage` tokens → falls back to saved data, no crash
4. Old entries under `"duct_local_reports"` → migrated automatically on first load
5. `POST /api/insights/refresh` with curl → returns `{ refreshed_at, briefs, date_from, date_to }`, no LLM call
6. `useInsightContext().chatPayload` contains `summary_text` + `dashboard_spec` once synthesis emits it
7. "Live" badge appears on insight cards that have a stored `routine`
