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

/**
 * Provider catalogue rendered by the Providers settings panel.
 *
 * `powers` is an array so the UI can show one scannable chip per agent. A
 * provider that supports a non-API credential carries an `oauth` block; the
 * card then offers an API-key / OAuth-token choice. The choice is only a UI
 * hint — the backend routes the credential by its prefix (see
 * `agents/core/claude_sdk.is_anthropic_oauth_token`), so the same
 * `X-Provider-*` header carries either kind.
 */
export const PROVIDERS = [
  {
    id: "anthropic",
    label: "Anthropic",
    header: "X-Provider-Anthropic",
    // API-key credential (the default).
    placeholder: "sk-ant-api03-…",
    prefix: "sk-ant-api",
    consoleUrl: "https://console.anthropic.com/settings/keys",
    description:
      "Runs the audit, content, and the default insights engine — for most of Duct it's the only key you need.",
    powers: ["SEO Audit", "Content Studio", "Content Planner", "Insights (default)"],
    recommended: true,
    // Claude Pro/Max subscribers can authenticate with an OAuth token instead
    // of paying per-token on an API key.
    oauth: {
      placeholder: "sk-ant-oat01-…",
      prefix: "sk-ant-oat",
      // No web console — it's minted by a CLI command.
      setup: "claude setup-token",
      hint: "Runs on your Claude Pro or Max subscription instead of API billing.",
    },
  },
  {
    id: "openai",
    label: "OpenAI",
    header: "X-Provider-OpenAI",
    placeholder: "sk-…",
    prefix: "sk-",
    consoleUrl: "https://platform.openai.com/api-keys",
    description: "GPT models for the insights engine — only when you switch the engine to OpenAI.",
    powers: ["Insights (v1/v2)"],
    recommended: false,
  },
  {
    id: "gemini",
    label: "Google Gemini",
    header: "X-Provider-Gemini",
    placeholder: "AIza…",
    prefix: "",
    consoleUrl: "https://aistudio.google.com/app/apikey",
    description: "Gemini models for the insights engine — only when you switch the engine to Gemini.",
    powers: ["Insights (v1/v2)"],
    recommended: false,
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
