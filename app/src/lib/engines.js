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
    defaultModel: "Gemini 3.8 Flash",
    description: "Multi-provider tool calling.",
  },
];

// One engine since the Claude Agent SDK (v3) was removed. The list, the picker
// and the per-agent support map are kept rather than inlined: they are what a
// second engine would arrive through, and the "engine cannot run this agent"
// affordance is the thing that stops a repeat of v2 (the UI offered an engine
// the backend silently did not serve).
export const DEFAULT_ENGINE = "v1";
export const ENGINE_STORAGE_KEY = "duct_engine";

// Engine availability states reported by GET /api/engines/status. There is no
// recoverable "needs auth" any more: without an API key the engine is inactive,
// because the subscription path went with the Agent SDK.
export const ENGINE_STATUS = {
  ACTIVE: "active",
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
// The consolidation onto one harness is finished: every agent runs on v1, so
// every entry names it. The map stays because it is what an entry claiming an
// engine the backend does not dispatch gets checked against.
// ---------------------------------------------------------------------------
export const AGENT_ENGINE_SUPPORT = {
  organic_growth: ["v1"],
  product_intelligence: ["v1"],
  paid_ads: ["v1"],
  seo_audit: ["v1"],
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
