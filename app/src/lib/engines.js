/**
 * Engine and agent-type definitions for the UI.
 *
 * Mirrors backend/agents/engines.py — keep in sync when adding new engines.
 */

export const ENGINES = [
  {
    key: "v1",
    badge: "v1",
    label: "LangChain",
    defaultModel: "Gemini 2.5 Flash",
    description: "Stable. Multi-provider tool calling.",
    supportsOAuth: false,
  },
  {
    key: "v3",
    badge: "v3",
    label: "Claude Agent SDK",
    defaultModel: "Claude Sonnet 5",
    description: "Subagents. MCP. Disk-backed sessions.",
    supportsOAuth: true,
  },
];

// v1 to match the backend: `generate_engine` defaults to v1, audit does too,
// and Content Studio now runs on v1 only. The "v3 only" pill affordance stays
// for any future agent that lands on one engine first.
export const DEFAULT_ENGINE = "v1";
export const ENGINE_STORAGE_KEY = "duct_engine";

// Engine availability states reported by GET /api/engines/status.
export const ENGINE_STATUS = {
  ACTIVE: "active",
  NEEDS_AUTH: "needs_auth",
  INACTIVE: "inactive",
};

export function getEngine(key) {
  return ENGINES.find((e) => e.key === key) ?? ENGINES[0];
}

// ---------------------------------------------------------------------------
// Agent types
// ---------------------------------------------------------------------------

export const AGENT_TYPES = [
  {
    key: "insights",
    label: "Insights",
    icon: "✦",
    available: true,
    description: "Paid media & organic growth intelligence.",
  },
  {
    key: "audit",
    label: "Audit",
    icon: "🔍",
    available: false,
    description: "SEO audit and content gap analysis.",
    hint: "Coming soon",
  },
  {
    key: "blog",
    label: "Blog",
    icon: "✍︎",
    available: false,
    description: "AI-drafted blog posts from audit findings.",
    hint: "Coming soon",
  },
];

export const DEFAULT_AGENT_TYPE = "insights";
export const AGENT_TYPE_STORAGE_KEY = "duct_agent_type";

export function getAgentType(key) {
  return AGENT_TYPES.find((a) => a.key === key) ?? AGENT_TYPES[0];
}

// ---------------------------------------------------------------------------
// Agent ↔ engine support
//
// Which inference engines can run each sidebar agent. Mirrors the runner
// implementations under backend/agents/<agent>/. Keys are the AppSidebar NAV
// item keys. Keep in sync when an agent gains or loses an engine runner — an
// entry claiming an engine the backend does not dispatch is the exact bug that
// retired v2 (the UI offered it while silently serving v1).
//
// Current state of the consolidation onto one harness:
//   - insights   — v1 only; the v3 runner was removed (nothing dispatched it).
//   - seo_audit  — both, and `routes/audit.py` now defaults to v1.
//   - tiktok_studio — v1 only; its v3 runner was ported to deepagents and
//     removed, so Content Studio runs on any provider the user brings a key for.
// ---------------------------------------------------------------------------
export const AGENT_ENGINE_SUPPORT = {
  organic_growth: ["v1"],
  product_intelligence: ["v1"],
  paid_ads: ["v1"],
  seo_audit: ["v1", "v3"],
  tiktok_studio: ["v1"],
};

// True when `engineKey` can run the agent `agentKey`. Fail-open for unknown
// agents so a new nav item is never hidden by a missing entry here.
export function engineSupportsAgent(engineKey, agentKey) {
  const engines = AGENT_ENGINE_SUPPORT[agentKey];
  return !engines || engines.includes(engineKey);
}

// The engines that DO support `agentKey`, as full engine objects — used to
// tell the user which engine to switch to in the "Not supported" tooltip.
export function supportingEngines(agentKey) {
  return (AGENT_ENGINE_SUPPORT[agentKey] ?? []).map(getEngine);
}
