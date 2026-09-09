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
 * Selected by `NEXT_PUBLIC_ANALYTICS_PROVIDER`. Unset falls back to `gtm` when
 * a container is configured and `none` otherwise — so an existing deploy keeps
 * its behaviour, and a self-host build that sets neither variable measures
 * nothing without having to opt out of anything.
 *
 * Adding a provider is one file exporting the ten members below, plus a line
 * in `PROVIDERS`. No other file should need to change.
 */

import { gtm } from "./gtm";
import { none } from "./none";

const PROVIDERS = { gtm, none };

function resolve() {
  const requested = process.env.NEXT_PUBLIC_ANALYTICS_PROVIDER;
  if (requested) {
    const chosen = PROVIDERS[requested];
    if (chosen) return chosen;
    // A typo here would otherwise measure nothing and say nothing, which is the
    // failure you find out about a quarter later from an empty dashboard.
    console.warn(
      `[analytics] unknown NEXT_PUBLIC_ANALYTICS_PROVIDER "${requested}" — measuring nothing. ` +
        `Known providers: ${Object.keys(PROVIDERS).join(", ")}.`,
    );
    return none;
  }
  return process.env.NEXT_PUBLIC_GTM_ID ? gtm : none;
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
 * which shares no code with this app. Both feed the trigger list in
 * `scripts/gtm-container-setup.ts`, which is what actually forwards them to GA4 —
 * an event missing from that list reaches the dataLayer and stops there.
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
};

/**
 * The parameter vocabulary. GA4 cannot wildcard event parameters — each one is
 * mapped by name in the container — so a param outside this set is silently
 * dropped on arrival. Adding one means adding it here and in the setup script.
 */
export const AnalyticsParam = {
  Method: "method",       // how they signed up: "google"
  Provider: "provider",   // connector id: "ga4" | "google_ads" | "meta_ads" | ...
  Agent: "agent",         // agent_type that produced an artifact
  Kind: "kind",           // artifact kind, or change-set kind
  Shell: "shell",         // "desktop" | "browser"
  Services: "services",   // execution services someone asked for
  Os: "os",               // marketing-site download target
  Reason: "reason",       // why a site could not be read: invalid_url | unreachable
  Code: "code",           // why a key failed to verify: invalid_key | no_billing | …
  Ok: "ok",               // "true" | "false" on a verify
};

/**
 * Push a custom event. Safe before the provider starts — GTM's dataLayer queues,
 * and a provider that never starts drops it, which is the intent.
 */
export function trackEvent(event, params = {}) {
  if (typeof window === "undefined") return;
  analytics.track(event, params);
}
