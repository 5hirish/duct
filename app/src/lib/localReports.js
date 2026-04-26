/**
 * Client-side localStorage CRUD for generated reports.
 *
 * Primary persistence for the /generate flow: JSON from POST /api/generate is saved here.
 * Replace with a real store when accounts exist.
 *
 * Reports are stored as an array in localStorage under STORAGE_KEY.
 * Each entry: { slug, payload, savedAt }
 * Capped at MAX_REPORTS; oldest are pruned on save.
 */

export const LOCAL_REPORTS_STORAGE_KEY = "duct_local_reports";
const STORAGE_KEY = LOCAL_REPORTS_STORAGE_KEY;
const MAX_REPORTS = 50;
const UI_SCHEMA_VERSION = 1;
const ROUTINE_SCHEMA_VERSION = 1;

function defaultRefreshState() {
  return {
    last_refreshed_at: null,
    refresh_status: "idle",
    refresh_error: null,
    live_briefs: null,
  };
}

function defaultUiState() {
  return {
    schema_version: UI_SCHEMA_VERSION,
    kpi_overrides: [],
    annotations: [],
    action_items: [],
  };
}

function withReportDefaults(entry) {
  if (!entry) return null;
  return {
    ...entry,
    refresh: { ...defaultRefreshState(), ...(entry.refresh || {}) },
    ui: { ...defaultUiState(), ...(entry.ui || {}) },
  };
}

function readStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeStore(reports) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reports));
  } catch {
    // storage full — silently fail
  }
}

export function getLocalReports(projectId = null, mode = null) {
  let reports = readStore();
  if (projectId) {
    reports = reports.filter((entry) => entry.project_id === projectId);
  }
  if (mode) {
    reports = reports.filter((entry) => {
      const entryMode = entry.mode || entry.routine?.mode || null;
      return entryMode === mode;
    });
  }
  return reports;
}

export function saveLocalReport(slug, payload, routine = null, projectId = null, mode = null) {
  const reports = readStore();

  // Mark as locally stored (support both envelope and legacy flat format)
  const meta = payload.briefs?.google_ads?.source_metadata ?? payload.source_metadata;
  if (meta) {
    meta._local = true;
  }

  // Remove existing entry with same slug (update case)
  const filtered = reports.filter((r) => r.slug !== slug);
  const nextEntry = {
    slug,
    payload,
    savedAt: new Date().toISOString(),
    project_id: projectId || null,
    mode: mode || null,
    ...(routine
      ? {
          routine: {
            schema_version: ROUTINE_SCHEMA_VERSION,
            ...routine,
          },
          refresh: defaultRefreshState(),
          ui: defaultUiState(),
        }
      : {}),
  };
  filtered.unshift(nextEntry);

  // Cap at MAX_REPORTS
  if (filtered.length > MAX_REPORTS) {
    filtered.length = MAX_REPORTS;
  }

  writeStore(filtered);
}

export function getLocalReportBySlug(slug) {
  const entry = getReportEntry(slug);
  return entry ? entry.payload : null;
}

export function getReportEntry(slug) {
  const reports = readStore();
  const entry = reports.find((r) => r.slug === slug);
  return withReportDefaults(entry);
}

export function patchReportRefresh(slug, patch) {
  const reports = readStore();
  let changed = false;
  const next = reports.map((entry) => {
    if (entry.slug !== slug) return entry;
    changed = true;
    const refresh = {
      ...defaultRefreshState(),
      ...(entry.refresh || {}),
      ...(patch || {}),
    };
    return { ...entry, refresh };
  });
  if (changed) writeStore(next);
}

export function patchReportUi(slug, patch) {
  const reports = readStore();
  let changed = false;
  const next = reports.map((entry) => {
    if (entry.slug !== slug) return entry;
    changed = true;
    const ui = {
      ...defaultUiState(),
      ...(entry.ui || {}),
      ...(patch || {}),
    };
    return { ...entry, ui };
  });
  if (changed) writeStore(next);
}

export function deleteLocalReport(slug) {
  const reports = readStore();
  writeStore(reports.filter((r) => r.slug !== slug));
}

export function generateSlug(customerId, dateTo) {
  const ts = Date.now();
  const id = (customerId || "report").replace(/[^a-z0-9]/gi, "");
  return `local-${id}-${dateTo}-${ts}`;
}
