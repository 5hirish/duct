/**
 * Bring-your-own provider API keys (client-side).
 *
 * Storage is shell-aware behind one async interface:
 *   - Web build  → `sessionStorage` (ephemeral, per browser session).
 *   - Desktop (Tauri) → the OS keychain via a Rust `invoke` command. Wired in
 *     the desktop phase; guarded by `isTauri()` so it never runs in the browser.
 *
 * Keys are sent to the backend per request as `X-Provider-*` headers (see
 * `providerKeyHeaders`). They are never persisted on our servers — the backend
 * prefers a supplied key over its own and uses it only for that request.
 */

export const PROVIDERS = [
  {
    id: "anthropic",
    label: "Anthropic (Claude)",
    header: "X-Provider-Anthropic",
    placeholder: "sk-ant-…",
    prefix: "sk-ant-",
    description: "Powers the Claude Agent SDK engine (v3).",
    // What this key actually unlocks. Claude runs nearly everything, so most
    // testers only need this one — call that out.
    powers: "SEO Audit, Content Studio, Content Planner, and the default Insights engine (v3)",
    recommended: true,
    consoleUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "openai",
    label: "OpenAI",
    header: "X-Provider-OpenAI",
    placeholder: "sk-…",
    prefix: "sk-",
    description: "GPT models on the LangChain (v1) and ADK (v2) engines.",
    powers: "Insights only — when you switch the engine to OpenAI (v1/v2)",
    recommended: false,
    consoleUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    header: "X-Provider-Gemini",
    placeholder: "AIza…",
    prefix: "",
    description: "Default models for the LangChain (v1) and ADK (v2) engines.",
    powers: "Insights only — on the Gemini (v1/v2) engines",
    recommended: false,
    consoleUrl: "https://aistudio.google.com/app/apikey",
  },
];

const STORAGE_PREFIX = "duct_provider_key_";

function isTauri() {
  return typeof window !== "undefined" && Boolean(window.__TAURI__);
}

/** Read a stored provider key. Returns "" when unset or storage is unavailable. */
export async function getProviderKey(providerId) {
  if (typeof window === "undefined") return "";
  if (isTauri()) {
    try {
      return (await window.__TAURI__.core.invoke("get_provider_key", { provider: providerId })) || "";
    } catch {
      return "";
    }
  }
  try {
    return window.sessionStorage.getItem(STORAGE_PREFIX + providerId) || "";
  } catch {
    return "";
  }
}

/** Persist (or, when value is blank, remove) a provider key. */
export async function setProviderKey(providerId, value) {
  if (typeof window === "undefined") return;
  const trimmed = (value || "").trim();
  if (isTauri()) {
    try {
      await window.__TAURI__.core.invoke(trimmed ? "set_provider_key" : "delete_provider_key", {
        provider: providerId,
        key: trimmed,
      });
    } catch {
      /* keychain unavailable — ignore for the web/dev path */
    }
    return;
  }
  try {
    if (trimmed) window.sessionStorage.setItem(STORAGE_PREFIX + providerId, trimmed);
    else window.sessionStorage.removeItem(STORAGE_PREFIX + providerId);
  } catch {
    /* storage unavailable (e.g. private mode) — ignore */
  }
}

/** Remove a stored provider key. */
export async function clearProviderKey(providerId) {
  return setProviderKey(providerId, "");
}

/**
 * Build the `X-Provider-*` request headers for whichever keys are set.
 * Returns `{}` server-side or when no keys are stored.
 */
export async function providerKeyHeaders() {
  const headers = {};
  if (typeof window === "undefined") return headers;
  for (const provider of PROVIDERS) {
    const key = await getProviderKey(provider.id);
    if (key) headers[provider.header] = key;
  }
  return headers;
}
