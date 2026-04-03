/**
 * Client-side localStorage CRUD for generated reports.
 *
 * Reports are stored as an array in localStorage under STORAGE_KEY.
 * Each entry: { slug, payload, savedAt }
 * Capped at MAX_REPORTS; oldest are pruned on save.
 */

const STORAGE_KEY = "duct_local_reports";
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

  // Mark as locally stored
  if (payload.source_metadata) {
    payload.source_metadata._local = true;
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
