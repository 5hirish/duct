/**
 * Client-side localStorage for generated insights.
 *
 * Primary persistence for the /generate flow: JSON from the generate API is saved here.
 * Replace with a real store when accounts exist.
 *
 * Insights are stored as an array in localStorage under STORAGE_KEY.
 * Each entry: { slug, payload, savedAt, routine?, refresh?, ui?, ... }
 * Capped at MAX_INSIGHTS; oldest are pruned on save.
 */

export const LOCAL_INSIGHTS_STORAGE_KEY = "duct_local_insights";
const STORAGE_KEY = LOCAL_INSIGHTS_STORAGE_KEY;
const MAX_INSIGHTS = 50;
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

function withInsightDefaults(entry) {
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

function writeStore(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // storage full — silently fail
  }
}

export function getLocalInsights(projectId = null, mode = null) {
  let entries = readStore();
  if (projectId) {
    entries = entries.filter((entry) => entry.project_id === projectId);
  }
  if (mode) {
    entries = entries.filter((entry) => {
      const entryMode = entry.mode || entry.routine?.mode || null;
      return entryMode === mode;
    });
  }
  return entries;
}

export function saveLocalInsight(slug, payload, routine = null, projectId = null, mode = null) {
  const entries = readStore();

  const meta = payload.briefs?.google_ads?.source_metadata ?? payload.source_metadata;
  if (meta) {
    meta._local = true;
  }

  const filtered = entries.filter((r) => r.slug !== slug);
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

  if (filtered.length > MAX_INSIGHTS) {
    filtered.length = MAX_INSIGHTS;
  }

  writeStore(filtered);
}

export function getLocalInsightBySlug(slug) {
  const entry = getInsightEntry(slug);
  return entry ? entry.payload : null;
}

export function getInsightEntry(slug) {
  const entries = readStore();
  const entry = entries.find((r) => r.slug === slug);
  return withInsightDefaults(entry);
}

export function patchInsightRefresh(slug, patch) {
  const entries = readStore();
  let changed = false;
  const next = entries.map((entry) => {
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

export function patchInsightUi(slug, patch) {
  const entries = readStore();
  let changed = false;
  const next = entries.map((entry) => {
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

export function deleteLocalInsight(slug) {
  const entries = readStore();
  writeStore(entries.filter((r) => r.slug !== slug));
}

export function generateSlug(customerId, dateTo) {
  const ts = Date.now();
  const id = (customerId || "report").replace(/[^a-z0-9]/gi, "");
  return `local-${id}-${dateTo}-${ts}`;
}
