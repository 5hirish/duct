/**
 * The onboarding sign-in bundle, from the app's side.
 *
 * The audit agent asks a guest for Search Console once, after the report.
 * A guest has no account to attach a connection to, so at that moment — and
 * only there — the Google sign-in also asks for the Search Console and
 * Analytics read scopes: one consent, and the user comes back signed in with
 * the source connected (`backend/service/signin_sources.py` stores it).
 *
 * "Only there" is enforced by where the arming happens: the connector prompt
 * on the onboarding audit calls `armSignInSources()`, and nothing else does.
 * The sign-in page consumes the arming when it builds the authorize URL, so
 * the Share dialog, an invitation, or a plain visit to the login page all
 * stay identity-only. The arming also expires on its own, so a prompt that
 * was walked away from cannot widen a sign-in ten minutes later.
 */

import { isGuestToken } from "./guest";

export const SIGNIN_SOURCES_KEY = "duct_signin_sources";
export const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";
// The bundle's name on the wire (`?sources=`). One exists.
export const ONBOARDING_BUNDLE = "onboarding";
// Connectors the bundle covers — the prompt offers the sign-in route only for
// these; any other source keeps the ordinary connect button.
export const BUNDLED_CONNECTORS = ["gsc", "ga4"];
// What the resumed conversation is asked to do once the user is back.
export const KICKOFF_SOURCES = "sources";

const ARMED_TTL_MS = 10 * 60 * 1000;

/** Whether `connectorId` is one the bundle can connect for a guest. */
export function canSignInToConnect(connectorId) {
  return BUNDLED_CONNECTORS.includes(connectorId) && isGuestToken();
}

/** Ask the next sign-in to bundle the read scopes. */
export function armSignInSources() {
  try {
    sessionStorage.setItem(SIGNIN_SOURCES_KEY, JSON.stringify({ bundle: ONBOARDING_BUNDLE, at: Date.now() }));
  } catch {
    /* no storage: the sign-in is identity-only, the prompt says so after */
  }
}

function readArmed() {
  try {
    const raw = sessionStorage.getItem(SIGNIN_SOURCES_KEY);
    if (!raw) return "";
    const { bundle, at } = JSON.parse(raw);
    if (bundle !== ONBOARDING_BUNDLE || Date.now() - Number(at || 0) > ARMED_TTL_MS) return "";
    return bundle;
  } catch {
    return "";
  }
}

/** The armed bundle name, or "" — without disarming. For the note on the sign-in page. */
export function peekSignInSources() {
  return readArmed();
}

/** The armed bundle name, or "", and disarms either way. Called once per sign-in attempt. */
export function consumeSignInSources() {
  const bundle = readArmed();
  try {
    sessionStorage.removeItem(SIGNIN_SOURCES_KEY);
  } catch {
    /* nothing to clear */
  }
  return bundle;
}

/** Where sign-in should land afterwards. Same-origin paths only; the sign-in page re-checks. */
export function parkPostSignInRedirect(path) {
  try {
    sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, path);
  } catch {
    /* they land on the desk after sign-in instead */
  }
}

/** The share-link form of a conversation, with the kickoff the resume should run. */
export function resumeAuditPath({ conversationId, projectId, siteUrl, kickoff = "" }) {
  const qs = new URLSearchParams();
  if (projectId) qs.set("p", projectId);
  if (siteUrl) qs.set("u", siteUrl);
  if (kickoff) qs.set("kickoff", kickoff);
  const query = qs.toString();
  return `/open/audit/${encodeURIComponent(conversationId)}${query ? `?${query}` : ""}`;
}
