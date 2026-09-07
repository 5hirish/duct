/**
 * Engine and agent-type definitions for the UI.
 *
 * Mirrors backend/agents/engines.py — keep in sync when adding new engines.
 */

// One engine since the Claude Agent SDK (v3) was removed, and every agent runs
// on it — the per-agent support map listed "v1" five times, so it could no
// longer hide anything, and the Runtime tab was a radio group with one button
// already selected. Both are gone, and with them the picker's ENGINES list,
// getEngine, ENGINE_STATUS and the `duct_engine` storage key: a control whose
// only reachable state is the default is not a setting, it is furniture.
//
// The constant stays because the server is still asked engine-scoped questions
// — the model catalogue, the tier preview, the thinking dial — and this is the
// answer they get. A second engine arrives by restoring the list and a picker
// together, against a backend that actually dispatches it; the v2 mistake was
// shipping the UI half alone.
export const DEFAULT_ENGINE = "v1";

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
