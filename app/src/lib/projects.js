"use client";

const PROJECTS_STORAGE_KEY = "duct_projects";
const ACTIVE_PROJECT_ID_STORAGE_KEY = "duct_active_project_id";
const LEGACY_PROFILE_STORAGE_KEY = "duct_business_profile";

export const DEFAULT_PROJECT_PROFILE = {
  company: {
    name: "",
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

function readProjectsStore() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PROJECTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((project) => withProjectDefaults(project)).filter((project) => project.id);
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
  writeProjectsStore(next);
  if (getActiveProjectId() === id) {
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

export function getActiveProjectId() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(ACTIVE_PROJECT_ID_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setActiveProjectId(id) {
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

export function getActiveProject() {
  const projects = readProjectsStore();
  if (!projects.length) return null;
  const activeId = getActiveProjectId();
  const active = projects.find((project) => project.id === activeId);
  return active || projects[0] || null;
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
    if (!getActiveProjectId() && existing[0]?.id) {
      setActiveProjectId(existing[0].id);
    }
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
