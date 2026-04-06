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

export function getLocalReports() {
  return readStore();
}

export function saveLocalReport(slug, payload) {
  const reports = readStore();

  // Mark as locally stored (support both envelope and legacy flat format)
  const meta = payload.briefs?.google_ads?.source_metadata ?? payload.source_metadata;
  if (meta) {
    meta._local = true;
  }

  // Remove existing entry with same slug (update case)
  const filtered = reports.filter((r) => r.slug !== slug);
  filtered.unshift({ slug, payload, savedAt: new Date().toISOString() });

  // Cap at MAX_REPORTS
  if (filtered.length > MAX_REPORTS) {
    filtered.length = MAX_REPORTS;
  }

  writeStore(filtered);
}

export function getLocalReportBySlug(slug) {
  const reports = readStore();
  const entry = reports.find((r) => r.slug === slug);
  return entry ? entry.payload : null;
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
