/**
 * Engine definitions for the UI.
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

// An agent-type list (insights / audit / blog, two of them "Coming soon") used
// to live here too. Its only reader was AgentDrawer, which nothing mounted and
// whose selection nothing dispatched on; both went in the 2026-10-25 harness
// review. The agents that exist are routes (lib/navigation.js), not a picker.
