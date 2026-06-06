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
    key: "v2",
    badge: "v2",
    label: "Google ADK",
    defaultModel: "Gemini 2.5 Flash",
    description: "Sequential subagents. Session state.",
    supportsOAuth: false,
  },
  {
    key: "v3",
    badge: "v3",
    label: "Claude Agent SDK",
    defaultModel: "Claude Sonnet 4.6",
    description: "Subagents. MCP. Disk-backed sessions.",
    supportsOAuth: true,
  },
];

export const DEFAULT_ENGINE = "v3";
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
