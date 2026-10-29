"use client";

/**
 * The analytics seam.
 *
 * Everything above this line decides *whether* to measure — `lib/consent.js`
 * for the rule, `ProductAnalytics` for the flow. Everything below it decides
 * *how*, and names a vendor. Mirrors `desktop/src-tauri/src/telemetry/` on the
 * Rust side, for the same reason: the builds we distribute measure, and a fork
 * should be able to drop that or replace it without reading our consent logic.
 *
 * A provider may still refuse a surface on its own account, when the risk is
 * what the provider *is* rather than measurement as such: `gtm` reports itself
 * unconfigured inside the desktop shell because a tag container is a loader for
 * scripts configured elsewhere. A provider that bundles its own code need not.
 *
 * Selected by `NEXT_PUBLIC_ANALYTICS_PROVIDER`, a comma-separated list. Unset
 * means every provider whose own variable is set (`NEXT_PUBLIC_POSTHOG_KEY`,
 * `NEXT_PUBLIC_GTM_ID`), so a self-host build that sets none of them measures
 * nothing without having to opt out of anything. More than one runs as one:
 * every call goes to each, so the consent flow above never learns how many.
 *
 * Adding a provider is one file exporting the twelve members below, plus a
 * line in `PROVIDERS`. No other file should need to change. Error reporting
 * (`startErrorReporting`, `captureException`) lives on the same seam because
 * the vendor that measures is also the vendor that collects crashes, and two
 * seams would name it twice.
 */

import { gtm } from "./gtm";
import { none } from "./none";
import { posthog } from "./posthog";

const PROVIDERS = { posthog, gtm, none };

const CONFIGURED_BY = {
  posthog: () => Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY),
  gtm: () => Boolean(process.env.NEXT_PUBLIC_GTM_ID),
};

/** Several providers behind the one interface: each call fans out, any running counts. */
function combine(list) {
  if (list.length === 0) return none;
  if (list.length === 1) return list[0];
  const each = (method) => (...args) => {
    for (const provider of list) provider[method](...args);
  };
  return {
    id: list.map((p) => p.id).join("+"),
    isConfigured: () => list.some((p) => p.isConfigured()),
    startErrorReporting: each("startErrorReporting"),
    setDefaults: each("setDefaults"),
    setConsent: each("setConsent"),
    forgetStoredData: each("forgetStoredData"),
    start: each("start"),
    isRunning: () => list.some((p) => p.isRunning()),
    track: each("track"),
    identify: each("identify"),
    reset: each("reset"),
    captureException: each("captureException"),
  };
}

function resolve() {
  const requested = process.env.NEXT_PUBLIC_ANALYTICS_PROVIDER;
  if (requested) {
    const names = requested.split(",").map((name) => name.trim()).filter(Boolean);
    const unknown = names.filter((name) => !PROVIDERS[name]);
    if (unknown.length) {
      // A typo here would otherwise measure nothing and say nothing, which is the
      // failure you find out about a quarter later from an empty dashboard.
      console.warn(
        `[analytics] unknown NEXT_PUBLIC_ANALYTICS_PROVIDER "${unknown.join(", ")}" — ignored. ` +
          `Known providers: ${Object.keys(PROVIDERS).join(", ")}.`,
      );
    }
    return combine(names.filter((name) => PROVIDERS[name] && name !== "none").map((name) => PROVIDERS[name]));
  }
  return combine(Object.keys(CONFIGURED_BY).filter((name) => CONFIGURED_BY[name]()).map((name) => PROVIDERS[name]));
}

export const analytics = resolve();

/**
 * Every event Duct sends, and the only place their names are written.
 *
 * Deliberately small. These eight answer the questions an MVP has to answer —
 * did they sign up, did they connect something, did the product produce
 * anything, do they come back, do they let it act, do they invite anyone, do
 * they want the paid thing — and nothing else earns a place until one of those
 * is answered. Passive view events are absent on purpose: a screen that opens
 * automatically measures the router, not the user.
 *
 * `download_started` lives on the marketing site (`site/assets/duct-download.js`),
 * which shares no code with this app. PostHog takes every event by name, as
 * sent. GA4 takes only what the trigger list in `scripts/gtm-container-setup.ts`
 * forwards — an event missing from that list reaches the dataLayer and stops
 * there.
 */
export const AnalyticsEvent = {
  // Acquisition — the denominator for everything below.
  SignUp: "sign_up",

  // Activation: connected a tool, and the product made something.
  ConnectorConnected: "connector_connected",
  ArtifactGenerated: "artifact_generated",

  // Adoption: came back, let it act, brought someone.
  AppOpened: "app_opened",
  ExecutionApproved: "execution_approved",
  TeamMemberInvited: "team_member_invited",

  // Demand for the paid thing.
  ExecutionInterestSubmitted: "execution_interest_submitted",

  // Onboarding: the steps between first launch and the first finding, so a
  // drop-off has a place. `code` on a failed verify is the one to read first —
  // if `no_billing` dominates, the provider step's copy leads with it.
  OnboardingStarted: "onboarding_started",
  OnboardingSiteFound: "onboarding_site_found",
  OnboardingSiteFailed: "onboarding_site_failed",
  ProviderVerified: "provider_verified",
  ProviderSkipped: "provider_skipped",
  OnboardingAuditStarted: "onboarding_audit_started",
  // The report reached someone: `method` is "link" (copied) or "invite".
  AuditShared: "audit_shared",
  // A guest took the sign-in that also connects Search Console + Analytics,
  // from the connector prompt on the onboarding audit. Fired at the click,
  // before Google; whether the scopes were granted shows up as
  // connector_connected rows on the account, not here.
  SignInToConnect: "signin_to_connect",
  // An MCP server saved to the account, by sign-in, key or neither. Its own
  // event rather than connector_connected, which counts Duct's connectors:
  // `provider` is the preset id or "custom" for one added by URL, `method`
  // how it signs in (oauth | key | none). Fired once the server is saved,
  // never at the click — a sign-in abandoned at the vendor is not a connect.
  McpServerConnected: "mcp_server_connected",
};

/**
 * The parameter vocabulary. GA4 cannot wildcard event parameters — each one is
 * mapped by name in the container — so a param outside this set is silently
 * dropped on arrival there (PostHog keeps it). Adding one means adding it here
 * and in the setup script.
 */
export const AnalyticsParam = {
  Method: "method",       // how they signed up: "google"; how an MCP server signs in: "oauth" | "key" | "none"
  Provider: "provider",   // connector id: "ga4" | "google_ads" | "meta_ads" | ...
  Agent: "agent",         // agent_type that produced an artifact
  Kind: "kind",           // artifact kind, or change-set kind
  Services: "services",   // execution services someone asked for
  Os: "os",               // marketing-site download target
  Reason: "reason",       // why a site could not be read: invalid_url | unreachable
  Code: "code",           // why a key failed to verify: invalid_key | no_billing | …
  Ok: "ok",               // "true" | "false" on a verify
  Documents: "documents", // files read beside the site when an onboarding audit starts: "0".."5"
};

/**
 * Push a custom event. Safe before the provider starts — GTM's dataLayer queues,
 * and a provider that never starts drops it, which is the intent.
 */
export function trackEvent(event, params = {}) {
  if (typeof window === "undefined") return;
  analytics.track(event, params);
}

/**
 * Start error reporting, from the first client module (`instrumentation-client`).
 * Light by design: it listens for errors at once and loads the reporter when
 * the page is idle, so a crash during hydration is still caught and the first
 * paint carries none of the reporter's weight.
 */
export function startErrorReporting() {
  if (typeof window === "undefined") return;
  analytics.startErrorReporting();
}

/**
 * Report an error something caught: an error boundary, a failed save worth
 * knowing about. Uncaught errors need no call; they are reported already.
 */
export function reportError(error, properties = {}) {
  if (typeof window === "undefined" || !error) return;
  analytics.captureException(error, properties);
}
