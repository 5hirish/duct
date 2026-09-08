/**
 * Merge what the audit learned about a site into its project.
 *
 * The runner emits `PROJECT_DRAFT` twice — layer "crawl" (deterministic: name,
 * pitch, URL, favicon, pillars, social channels) before enrichment, and layer
 * "inferred" (industry, business model, personas, voice, competitors) after —
 * each field carrying its provenance. This is the only place those events
 * touch the project store, and it holds the three rules that make a draft safe:
 *
 *   1. a value the user set (provenance "user") is never overwritten;
 *   2. a non-empty crawl value is never overwritten by an inferred one — what
 *      the site says beats what a model guessed about it;
 *   3. a non-empty field with NO recorded provenance is treated as the user's.
 *      Every project made before drafts existed is in that state, and a human
 *      typing it was the only way a field got filled — so without this rule
 *      the first draft to reach an older project silently replaces its name,
 *      pitch, industry, personas and competitors with guesses about a site.
 *
 * Provenance lives on the project as `project.provenance[field]`, which the
 * project-context surface renders as a chip with a one-click confirm.
 */

import {
  UNTITLED_PROJECT,
  createProject,
  getProjectById,
  projectsForSite,
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

/**
 * Whether this field counts as "already filled in" for rule 3.
 *
 * The placeholder name is not content — a project the store just created
 * carries it, nobody chose it, and treating it as typed would leave every new
 * project called "Untitled project" forever.
 */
function isBlank(key, value) {
  if (isEmpty(value)) return true;
  return key === "name" && value === UNTITLED_PROJECT;
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
    const filled = !isBlank(key, existing);
    // Rule 3: nothing recorded, but something is there — a person put it there.
    if (filled && !current) continue;
    if (filled && current === PROVENANCE_CRAWL && field.provenance === PROVENANCE_INFERRED) {
      continue;
    }
    next = setPath(next, path, field.value);
    provenance[key] = field.provenance || PROVENANCE_INFERRED;
  }
  return { ...next, provenance };
}

/** The site a draft is about, from whichever layer carried it. */
export function draftSite(draft) {
  return draft?.fields?.website_url?.value || "";
}

/**
 * Merge a draft into the project it belongs to and persist it — locally now,
 * to the backend best-effort (a guest is a real user, so this is a real
 * write). Returns the saved project.
 *
 * `projectId` is the caller's answer to "which project", and every caller
 * that knows it passes it. Without one this resolves by the drafted site and
 * creates a project when nothing matches — deliberately never "whatever is
 * active", which is how a crawl of one site ended up rewriting a different
 * site's project. An ambiguous match (two projects, one site) also creates:
 * guessing between them is the single outcome that loses work.
 *
 * `createNew` is the user having said "a separate project, please" about a
 * site they already have one for. Without it the site match would hand them
 * back the project they just declined.
 */
export function applyProjectDraft(draft, { projectId = null, createNew = false } = {}) {
  let project = projectId ? getProjectById(projectId) : null;
  if (!project && !createNew) {
    const matches = projectsForSite(draftSite(draft));
    project = matches.length === 1 ? matches[0] : null;
  }
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
