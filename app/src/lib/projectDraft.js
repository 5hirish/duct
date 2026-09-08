/**
 * Merge what the audit learned about a site into its project.
 *
 * The runner emits `PROJECT_DRAFT` twice — layer "crawl" (deterministic: name,
 * pitch, URL, favicon, pillars, social channels) before enrichment, and layer
 * "inferred" (industry, business model, personas, voice, competitors) after —
 * each field carrying its provenance. This is the only place those events
 * touch the project store, and it holds the two rules that make a draft safe:
 *
 *   1. a value the user set (provenance "user") is never overwritten;
 *   2. a non-empty crawl value is never overwritten by an inferred one — what
 *      the site says beats what a model guessed about it.
 *
 * Provenance lives on the project as `project.provenance[field]`, which the
 * project-context surface renders as a chip with a one-click confirm.
 */

import {
  createProject,
  getActiveProject,
  getProjectById,
  pushProjectToBackend,
  saveProject,
  setActiveProjectId,
} from "./projects";

export const PROVENANCE_USER = "user";
export const PROVENANCE_CRAWL = "crawl";
export const PROVENANCE_INFERRED = "inferred";

// Where each drafted field lands in the project profile. A field the backend
// emits that is not listed here is ignored, never spread somewhere new.
const FIELD_PATHS = Object.freeze({
  name: ["name"],
  company_name: ["company", "name"],
  pitch: ["company", "pitch"],
  website_url: ["company", "website_url"],
  favicon: ["company", "favicon"],
  industry: ["company", "industry"],
  business_model: ["company", "business_model"],
  personas: ["audience", "personas"],
  compare_against: ["competition", "compare_against"],
  competitors: ["competition", "competitors"],
  brand_voice: ["brand_channels", "brand_voice"],
  active_channels: ["brand_channels", "active_channels"],
  content_pillars: ["brand_channels", "content_pillars"],
});

function isEmpty(value) {
  if (value == null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

function getPath(obj, path) {
  return path.reduce((acc, key) => (acc && typeof acc === "object" ? acc[key] : undefined), obj);
}

function setPath(obj, path, value) {
  if (path.length === 1) return { ...obj, [path[0]]: value };
  const [head, ...rest] = path;
  const child = obj?.[head] && typeof obj[head] === "object" ? obj[head] : {};
  return { ...obj, [head]: setPath(child, rest, value) };
}

/** Pure: the project with one draft event's fields merged in. */
export function mergeDraft(project, draft) {
  const provenance = { ...(project?.provenance || {}) };
  let next = { ...project };
  for (const [key, field] of Object.entries(draft?.fields || {})) {
    const path = FIELD_PATHS[key];
    if (!path || !field || isEmpty(field.value)) continue;
    const current = provenance[key];
    if (current === PROVENANCE_USER) continue;
    const existing = getPath(next, path);
    if (!isEmpty(existing) && current === PROVENANCE_CRAWL && field.provenance === PROVENANCE_INFERRED) {
      continue;
    }
    next = setPath(next, path, field.value);
    provenance[key] = field.provenance || PROVENANCE_INFERRED;
  }
  return { ...next, provenance };
}

/**
 * Merge a draft into the project it belongs to and persist it — locally now,
 * to the backend best-effort (a guest is a real user, so this is a real
 * write). Creates the project when there is none yet. Returns the saved
 * project.
 */
export function applyProjectDraft(draft, { projectId = null } = {}) {
  let project = (projectId && getProjectById(projectId)) || getActiveProject();
  if (!project) {
    project = createProject({});
    setActiveProjectId(project.id);
  }
  const saved = saveProject(mergeDraft(project, draft));
  pushProjectToBackend(saved);
  return saved;
}

/** The user confirmed (or typed) this field: a later draft leaves it alone. */
export function markConfirmed(project, key) {
  return { ...project, provenance: { ...(project?.provenance || {}), [key]: PROVENANCE_USER } };
}
