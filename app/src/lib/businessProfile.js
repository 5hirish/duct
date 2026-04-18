"use client";

const STORAGE_KEY = "duct_business_profile";

const DEFAULT_PROFILE = {
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

export function getBusinessProfileDraft() {
  if (typeof window === "undefined") {
    return DEFAULT_PROFILE;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PROFILE;
    const parsed = JSON.parse(raw);
    return mergeProfile(DEFAULT_PROFILE, parsed);
  } catch {
    return DEFAULT_PROFILE;
  }
}

export function saveBusinessProfileDraft(partial) {
  const current = getBusinessProfileDraft();
  const merged = mergeProfile(current, toObject(partial));
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  }
  return merged;
}

export function clearBusinessProfileDraft() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEY);
  }
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

export function getBusinessProfileCompletionFromProfile(profileInput) {
  const profile = mergeProfile(DEFAULT_PROFILE, toObject(profileInput));
  const sections = sectionCompletion(profile);
  const completedSections = sections.filter(Boolean).length;
  const percent = Math.round((completedSections / TOTAL_SECTIONS) * 100);
  return { percent, completedSections, totalSections: TOTAL_SECTIONS };
}

export function getBusinessProfileCompletion() {
  return getBusinessProfileCompletionFromProfile(getBusinessProfileDraft());
}
