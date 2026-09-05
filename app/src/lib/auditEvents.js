/**
 * Step IDs and labels for the SEO Audit Agent — mirror of backend
 * agents/audit/events.py. The event names themselves are the shared
 * vocabulary in lib/agentEvents.js; `AuditEvent` is that object.
 */

import { AgentEvent } from "./agentEvents";

// The shared vocabulary, under the name this file has always exported. The
// audit-specific part of this module is the step ids and labels below.
export const AuditEvent = AgentEvent;

export const AuditStep = Object.freeze({
  RESOLVE_URL:      "resolve_url",
  FETCH_SITEMAP:    "fetch_sitemap",
  CRAWL_PAGES:      "crawl_pages",
  ENRICHING:        "enriching",        // shared step — must match AgentStep.ENRICHING
  SYNTHESIZE_AUDIT: "synthesize_audit",
});

export const STEP_LABELS = Object.freeze({
  [AuditStep.RESOLVE_URL]:      "Resolving website",
  [AuditStep.FETCH_SITEMAP]:    "Fetching sitemap",
  [AuditStep.CRAWL_PAGES]:      "Crawling pages",
  [AuditStep.ENRICHING]:        "Researching competitors",
  [AuditStep.SYNTHESIZE_AUDIT]: "AI synthesis",
});
