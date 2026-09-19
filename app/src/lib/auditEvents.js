/**
 * Step IDs and labels for the SEO Audit Agent — mirror of backend
 * agents/audit/events.py. The event names themselves are the shared
 * vocabulary in lib/agentEvents.js; `AuditEvent` is that object.
 */

import { msg } from "@lingui/core/macro";
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

// Message descriptors, not strings: this table is module-level, so it is
// rendered with `i18n._(STEP_LABELS[id])` in the component that shows it.
export const STEP_LABELS = Object.freeze({
  [AuditStep.RESOLVE_URL]:      msg`Resolving website`,
  [AuditStep.FETCH_SITEMAP]:    msg`Fetching sitemap`,
  [AuditStep.CRAWL_PAGES]:      msg`Crawling pages`,
  [AuditStep.ENRICHING]:        msg`Researching competitors`,
  [AuditStep.SYNTHESIZE_AUDIT]: msg`AI synthesis`,
});
