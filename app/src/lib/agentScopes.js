// What a connected agent may do in Duct, in the two tiers the person chooses
// between. The app's copy of backend/service/mcp_server/scopes.py: the scope
// names must match it exactly, because they are what the token carries.
//
// Values and words only, no React: the consent page, the token form and the
// "It will be able to" lists all read the same descriptors, so the three can
// never promise different things.

import { msg } from "@lingui/core/macro";

/** Tier 1, "Set up your project": every connection has it. */
export const SCOPE_PROJECTS = "projects";

export const SCOPE_DATA = "data";
export const SCOPE_MEMORY = "memory";
export const SCOPE_REPORTS = "reports";
export const SCOPE_CHANGES = "changes";
export const SCOPE_CONTENT = "content";
export const SCOPE_MEDIA = "media";

/** Tier 2, "Work on your behalf", in the order the page lists them. */
export const WORK_SCOPES = [SCOPE_DATA, SCOPE_MEMORY, SCOPE_REPORTS, SCOPE_CHANGES, SCOPE_CONTENT, SCOPE_MEDIA];

/** Ticked when the second tier is opened: reading and saving inside Duct. */
export const DEFAULT_WORK_SCOPES = [SCOPE_DATA, SCOPE_MEMORY, SCOPE_REPORTS];

/** Each needs a deliberate tick: they act on the person's tools, their
 *  content or their money, so an agent asking for one never ticks it. */
export const DELIBERATE_SCOPES = [SCOPE_CHANGES, SCOPE_CONTENT, SCOPE_MEDIA];

/** Short names, for a one-line summary of a connection. */
export const SCOPE_NAMES = {
  [SCOPE_DATA]: msg`Data`,
  [SCOPE_MEMORY]: msg`Memory`,
  [SCOPE_REPORTS]: msg`Briefs`,
  [SCOPE_CHANGES]: msg`Proposed changes`,
  [SCOPE_CONTENT]: msg`Content`,
  [SCOPE_MEDIA]: msg`Images`,
};

/** What each lets the agent do, said to a marketer. */
export const SCOPE_ABILITIES = {
  [SCOPE_DATA]: msg`Read the tools you connected, with the totals Duct adds up`,
  [SCOPE_MEMORY]: msg`Look through what Duct remembers about your business, and add to it`,
  [SCOPE_REPORTS]: msg`Read your briefs, write a new one with Duct's method, and save it in Duct`,
  [SCOPE_CHANGES]: msg`Suggest changes to your ad and tag accounts, which wait for you to approve in Duct`,
  [SCOPE_CONTENT]: msg`Read your brand, plans and posts, and save post drafts for you to review`,
  [SCOPE_MEDIA]: msg`Make images with the AI keys you saved in Duct, which your provider charges you for`,
};

/** One clause each, for the consent page's Customise list, where the name
 *  above it already says what it is. The extras say the reassurance in the
 *  same breath, so nothing on the page needs a warning pill. */
export const SCOPE_HINTS = {
  [SCOPE_DATA]: msg`Reads the tools you connected, with Duct's totals`,
  [SCOPE_MEMORY]: msg`Searches and adds to what Duct remembers`,
  [SCOPE_REPORTS]: msg`Writes briefs with Duct's method and saves them`,
  [SCOPE_CHANGES]: msg`Suggests changes to your ad and tag accounts. You approve every one in Duct`,
  [SCOPE_CONTENT]: msg`Drafts posts for you to review. Never posts them`,
  [SCOPE_MEDIA]: msg`Makes images with the keys you saved. Your provider charges you`,
};

/** The extras the agent asked for, which stay off until the person turns
 *  them on; the page opens Customise when there are any, so the ask is seen. */
export function askedExtras(requested) {
  return DELIBERATE_SCOPES.filter((scope) => (requested || []).includes(scope));
}

/** Did the agent ask for anything past project setup? */
export function asksForWork(requested) {
  return (requested || []).some((scope) => WORK_SCOPES.includes(scope));
}

/**
 * Where the picker starts. Closed unless the agent asked for the second
 * tier; when it did, the safe defaults plus whatever else safe it asked for,
 * and never a deliberate one, whatever was asked.
 */
export function initialGrant(requested = []) {
  if (!asksForWork(requested)) {
    return { work: false, scopes: [...DEFAULT_WORK_SCOPES], projectIds: null };
  }
  const asked = requested.filter((scope) => WORK_SCOPES.includes(scope) && !DELIBERATE_SCOPES.includes(scope));
  const scopes = WORK_SCOPES.filter((scope) => DEFAULT_WORK_SCOPES.includes(scope) || asked.includes(scope));
  return { work: true, scopes, projectIds: null };
}

/** Flip one capability, keeping the table order. */
export function toggleScope(scopes, scope, on) {
  const next = new Set(scopes);
  if (on) next.add(scope);
  else next.delete(scope);
  return WORK_SCOPES.filter((s) => next.has(s));
}

/** A grant the person cannot submit, as a code the page words, or null. */
export function grantProblem(grant) {
  if (Array.isArray(grant.projectIds) && grant.projectIds.length === 0) return "no_projects";
  return null;
}

/**
 * The body the approve and mint routes take. Which projects applies to both
 * choices: "Help set up my projects" on one client's project is a grant too.
 * Untouched, it is project setup on every project, exactly what Allow meant
 * before tiers.
 */
export function grantBody(grant) {
  const scopes = grant.work ? [SCOPE_PROJECTS, ...grant.scopes] : [SCOPE_PROJECTS];
  return { scopes, project_ids: grant.projectIds ?? null };
}

/**
 * What a listed connection may do and where, as parts the row joins:
 * the second-tier names it holds, and how many projects (null for all).
 * A row from before tiers carries no scopes and reads as setup alone.
 */
export function grantFacts(row) {
  const scopes = (row?.scopes || []).filter((scope) => WORK_SCOPES.includes(scope));
  const projects = Array.isArray(row?.project_ids) ? row.project_ids.length : null;
  return { scopes, projects };
}
