"use client";

import {
  deleteProjectRemote,
  fetchProjectsRemote,
  hasAuthToken,
  upsertProjectRemote,
} from "./projectsApi";

const PROJECTS_STORAGE_KEY = "duct_projects";
const ACTIVE_PROJECT_ID_STORAGE_KEY = "duct_active_project_id";
const LEGACY_PROFILE_STORAGE_KEY = "duct_business_profile";

export const DEFAULT_PROJECT_PROFILE = {
  company: {
    name: "",
    pitch: "",
    industry: "",
    business_model: "",
    website_url: "",
  },
  targets: {
    monthly_budget: "",
    target_cpa: "",
    target_roas: "",
    primary_kpi: "",
    north_star_metric: "",
    north_star_goal_window: "",
    north_star_constraints: "",
    growth_stage_milestone: "",
    growth_stage_context: "",
  },
  audience: {
    primary_segment: "",
    personas: [],
  },
  competition: {
    compare_against: "",
    competitors: [],
    positioning_statement: "",
  },
  brand_channels: {
    brand_voice: "",
    growth_motions: [],
    context_notes: "",
    active_channels: [],
    seasonality_notes: "",
  },
};

const TOTAL_SECTIONS = 5;

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function toObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function clampArray(value) {
  return Array.isArray(value) ? value : [];
}

function mergeProfile(base, incoming) {
  return {
    company: { ...base.company, ...toObject(incoming.company) },
    targets: { ...base.targets, ...toObject(incoming.targets) },
    audience: {
      ...base.audience,
      ...toObject(incoming.audience),
      personas: clampArray(toObject(incoming.audience).personas ?? base.audience.personas),
    },
    competition: {
      ...base.competition,
      ...toObject(incoming.competition),
      competitors: clampArray(toObject(incoming.competition).competitors ?? base.competition.competitors),
    },
    brand_channels: {
      ...base.brand_channels,
      ...toObject(incoming.brand_channels),
      growth_motions: clampArray(
        toObject(incoming.brand_channels).growth_motions ?? base.brand_channels.growth_motions
      ),
      active_channels: clampArray(
        toObject(incoming.brand_channels).active_channels ?? base.brand_channels.active_channels
      ),
    },
  };
}

function withProjectDefaults(projectInput) {
  const project = toObject(projectInput);
  const profile = mergeProfile(DEFAULT_PROJECT_PROFILE, project);
  return {
    ...profile,
    id: isNonEmptyString(project.id) ? project.id : "",
    name: isNonEmptyString(project.name) ? project.name : profile.company.name || "Untitled project",
    createdAt: isNonEmptyString(project.createdAt) ? project.createdAt : new Date(0).toISOString(),
    updatedAt: isNonEmptyString(project.updatedAt) ? project.updatedAt : new Date(0).toISOString(),
    // Membership metadata from the backend. A project that has never synced is
    // owned by whoever created it locally, so "owner" is the right default.
    role: project.role === "collaborator" ? "collaborator" : "owner",
    ownerEmail: isNonEmptyString(project.ownerEmail) ? project.ownerEmail : "",
  };
}

function nowIso() {
  return new Date().toISOString();
}

function createId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Newest first, id as the tie-break. Order has to be a pure function of the
 * projects themselves: `projects[0]` is the fallback whenever the remembered
 * selection can't be resolved, and a fallback that depends on write order
 * (local prepends vs. whatever order the backend returned) reads to the user
 * as the app forgetting which project they picked.
 */
function sortProjects(projects) {
  return [...projects].sort((a, b) => {
    const byCreated = (b.createdAt || "").localeCompare(a.createdAt || "");
    return byCreated !== 0 ? byCreated : (a.id || "").localeCompare(b.id || "");
  });
}

function readProjectsStore() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PROJECTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return sortProjects(parsed.map((project) => withProjectDefaults(project)).filter((project) => project.id));
  } catch {
    return [];
  }
}

function writeProjectsStore(projects) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(projects));
  } catch {
    // ignore storage write errors
  }
}

// ---------------------------------------------------------------------------
// Backend sync (hybrid: localStorage is the always-current cache, the backend
// is the durable store). Writes to the backend are explicit — callers persist
// at deliberate save points (e.g. the onboarding "Save & Next" button) — so
// localStorage edits don't generate a request per keystroke.
// ---------------------------------------------------------------------------

/** Same-document project-store change — cross-tab writes arrive as "storage". */
export const PROJECTS_CHANGED = "duct:project-changed";

/** Notify same-document listeners (sidebar, projects page) to re-read the store. */
function notifyProjectsChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("storage"));
  window.dispatchEvent(new Event(PROJECTS_CHANGED));
}

/**
 * Explicitly persist a project to the backend (upsert by id). Best-effort and
 * safe to fire-and-forget; no-ops when signed out. Returns the server copy or null.
 */
export function pushProjectToBackend(project) {
  return upsertProjectRemote(project);
}

export function getProjects() {
  return readProjectsStore();
}

export function getProjectById(projectId) {
  if (!isNonEmptyString(projectId)) return null;
  const projects = readProjectsStore();
  return projects.find((project) => project.id === projectId) || null;
}

export function saveProject(projectInput) {
  const project = withProjectDefaults(projectInput);
  const timestamp = nowIso();
  const base = {
    ...project,
    updatedAt: timestamp,
    createdAt: isNonEmptyString(project.createdAt) && project.createdAt !== new Date(0).toISOString()
      ? project.createdAt
      : timestamp,
    name: isNonEmptyString(project.name) ? project.name : project.company.name || "Untitled project",
  };

  if (!base.id) {
    base.id = createId();
  }

  const projects = readProjectsStore();
  const idx = projects.findIndex((item) => item.id === base.id);
  const next = idx >= 0 ? [...projects.slice(0, idx), base, ...projects.slice(idx + 1)] : [base, ...projects];
  writeProjectsStore(next);
  return base;
}

export function deleteProject(id) {
  if (!isNonEmptyString(id)) return;
  const projects = readProjectsStore();
  const next = projects.filter((project) => project.id !== id);
  // Read the remembered pick before the store changes under it, so deleting a
  // project the user wasn't on leaves their selection alone.
  const wasActive = readStoredActiveProjectId() === id;
  writeProjectsStore(next);
  deleteProjectRemote(id);
  if (wasActive) {
    setActiveProjectId(next[0]?.id || "");
  }
}

export function createProject(partial = {}) {
  const timestamp = nowIso();
  const partialObj = toObject(partial);
  const merged = mergeProfile(DEFAULT_PROJECT_PROFILE, partialObj);
  const project = saveProject({
    ...merged,
    id: createId(),
    name: partialObj.name || merged.company.name || "Untitled project",
    createdAt: timestamp,
    updatedAt: timestamp,
  });
  return project;
}

// ---------------------------------------------------------------------------
// Active project
//
// The project picked in the sidebar is remembered in localStorage and survives
// reloads, navigation and restarts. Reads go through resolveActiveProjectId so
// that the stored id and what the UI shows can never drift apart: a reader that
// silently falls back to "the first project" without writing that choice back
// leaves the switcher showing one project while getActiveProjectId() hands the
// rest of the app an empty string.
// ---------------------------------------------------------------------------

function readStoredActiveProjectId() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(ACTIVE_PROJECT_ID_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function writeStoredActiveProjectId(id) {
  if (typeof window === "undefined") return;
  try {
    if (!id) {
      window.localStorage.removeItem(ACTIVE_PROJECT_ID_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(ACTIVE_PROJECT_ID_STORAGE_KEY, id);
  } catch {
    // ignore storage write errors
  }
}

/**
 * The remembered selection, resolved against `projects` and repaired in place.
 *
 * Returns the stored id when it still names a real project. Otherwise falls
 * back to the first project and persists that fallback, so every later read
 * agrees. Repairs deliberately do NOT notify — they are not a user action, and
 * a listener that re-reads on notify would bounce straight back in here.
 *
 * An empty list is treated as "nothing to resolve against yet", not as "the
 * selection is invalid": the store is empty on first paint of a fresh device,
 * before hydrateProjectsFromBackend has run, and forgetting the pick there is
 * exactly the reset this is meant to prevent.
 */
export function resolveActiveProjectId(projects = readProjectsStore()) {
  if (typeof window === "undefined") return "";
  const stored = readStoredActiveProjectId();
  if (!projects.length) return "";
  if (stored && projects.some((project) => project.id === stored)) return stored;
  const fallback = projects[0]?.id || "";
  if (fallback !== stored) writeStoredActiveProjectId(fallback);
  return fallback;
}

export function getActiveProjectId() {
  return resolveActiveProjectId();
}

/** Remember `id` as the active project. No-op (and no event) when unchanged. */
export function setActiveProjectId(id) {
  if (typeof window === "undefined") return;
  const next = isNonEmptyString(id) ? id : "";
  if (next === readStoredActiveProjectId()) return;
  writeStoredActiveProjectId(next);
  notifyProjectsChanged();
}

export function getActiveProject() {
  const projects = readProjectsStore();
  if (!projects.length) return null;
  const activeId = resolveActiveProjectId(projects);
  return projects.find((project) => project.id === activeId) || projects[0] || null;
}

function sectionCompletion(profile) {
  const companyDone =
    isNonEmptyString(profile.company.name) &&
    isNonEmptyString(profile.company.industry) &&
    isNonEmptyString(profile.company.business_model);

  const targetsDone =
    isNonEmptyString(profile.targets.north_star_metric) &&
    isNonEmptyString(profile.targets.north_star_goal_window) &&
    isNonEmptyString(profile.targets.growth_stage_milestone);

  const audienceDone =
    isNonEmptyString(profile.audience.primary_segment) &&
    profile.audience.personas.some(
      (persona) =>
        persona &&
        (isNonEmptyString(persona.name) || isNonEmptyString(persona.description) || isNonEmptyString(persona.priority))
    );

  const competitionDone = isNonEmptyString(profile.competition.compare_against);

  const brandChannelsDone =
    isNonEmptyString(profile.brand_channels.brand_voice) ||
    profile.brand_channels.growth_motions.length > 0 ||
    isNonEmptyString(profile.brand_channels.context_notes);

  return [companyDone, targetsDone, audienceDone, competitionDone, brandChannelsDone];
}

export function getProjectCompletion(projectInput) {
  const profile = mergeProfile(DEFAULT_PROJECT_PROFILE, toObject(projectInput));
  const sections = sectionCompletion(profile);
  const completedSections = sections.filter(Boolean).length;
  const percent = Math.round((completedSections / TOTAL_SECTIONS) * 100);
  return { percent, completedSections, totalSections: TOTAL_SECTIONS };
}

export function migrateFromLegacyProfile() {
  if (typeof window === "undefined") return null;

  const existing = readProjectsStore();
  if (existing.length > 0) {
    resolveActiveProjectId(existing);
    return existing[0] || null;
  }

  let legacy = null;
  try {
    const raw = window.localStorage.getItem(LEGACY_PROFILE_STORAGE_KEY);
    if (raw) legacy = JSON.parse(raw);
  } catch {
    legacy = null;
  }
  if (!legacy) return null;

  const merged = mergeProfile(DEFAULT_PROJECT_PROFILE, toObject(legacy));
  const created = createProject({
    ...merged,
    name: merged.company.name || "Project 1",
  });
  if (created?.id) setActiveProjectId(created.id);
  return created || null;
}

/**
 * Load projects from the backend and reconcile with the local cache.
 *
 * - Server rows win when the same id exists in both, unless the local copy is
 *   strictly newer (by updatedAt) — then the local copy is pushed back up.
 * - Local-only projects (created before sync, or while signed out) are kept and
 *   uploaded so nothing is lost.
 * Safe no-op when signed out / no token. Notifies listeners on completion.
 */
export async function hydrateProjectsFromBackend() {
  if (typeof window === "undefined" || !hasAuthToken()) return;

  const remote = await fetchProjectsRemote();
  const local = readProjectsStore();

  const byId = new Map();
  for (const p of remote) byId.set(p.id, withProjectDefaults(p));

  const toPushUp = [];
  for (const lp of local) {
    const rp = byId.get(lp.id);
    if (!rp) {
      // Local-only project — keep it and upload.
      byId.set(lp.id, lp);
      toPushUp.push(lp);
    } else if ((lp.updatedAt || "") > (rp.updatedAt || "")) {
      // Local edits are newer — prefer them and re-upload. Membership is the
      // server's call, though, so role/owner always come from the remote copy.
      byId.set(lp.id, { ...lp, role: rp.role, ownerEmail: rp.ownerEmail });
      toPushUp.push(lp);
    }
  }

  const merged = sortProjects(Array.from(byId.values()));
  writeProjectsStore(merged);

  // Keep the remembered project. It is only re-pointed when the project it
  // names is genuinely gone (deleted on another device), never just because
  // the server handed the list back in a different order.
  resolveActiveProjectId(merged);

  for (const p of toPushUp) upsertProjectRemote(p);

  notifyProjectsChanged();
}
