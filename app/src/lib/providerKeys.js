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
    // What `/api/providers/status` calls the same provider. They differ for
    // Google only, but a per-entry field beats a special case at every call.
    statusId: "anthropic",
    label: "Anthropic",
    header: "X-Provider-Anthropic",
    placeholder: "sk-ant-…",
    prefix: "sk-ant-",
    description: "Claude models. The only provider the Claude Agent SDK (v3) accepts.",
    consoleUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "openai",
    statusId: "openai",
    label: "OpenAI",
    header: "X-Provider-OpenAI",
    placeholder: "sk-…",
    prefix: "sk-",
    description: "GPT models on the LangChain (v1) engine.",
    consoleUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "gemini",
    statusId: "google_genai",
    label: "Google Gemini",
    header: "X-Provider-Gemini",
    placeholder: "AIza…",
    prefix: "",
    description: "Gemini models, and every image Duct generates.",
    consoleUrl: "https://aistudio.google.com/app/apikey",
  },
  {
    // The backend has accepted this header since bring-your-own keys shipped;
    // it was simply never offered here, which made the one provider that
    // actually solves bring-your-own-model the only one you could not bring.
    id: "openrouter",
    statusId: "openrouter",
    label: "OpenRouter",
    header: "X-Provider-OpenRouter",
    placeholder: "sk-or-…",
    prefix: "sk-or-",
    description: "One key, 500+ models — and any OpenAI-compatible gateway you point it at.",
    consoleUrl: "https://openrouter.ai/keys",
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

/**
 * Persist (or, when value is blank, remove) a provider key.
 *
 * **Throws when the desktop keychain rejects the write.** It used to swallow
 * that, which was wrong in exactly one common case: on Linux the keyring is a
 * D-Bus Secret Service daemon that a minimal or headless install may not run at
 * all, so the key silently vanished and the user was left with a settings page
 * that appeared to have saved. The shell returns a message naming the cause
 * (`describe_keyring_error` in `desktop/src-tauri/src/lib.rs`); callers should
 * show it. Reads still degrade quietly — a missing key reads as absent, which
 * is both true and harmless.
 */
export async function setProviderKey(providerId, value) {
  if (typeof window === "undefined") return;
  const trimmed = (value || "").trim();
  if (isTauri()) {
    await window.__TAURI__.core.invoke(trimmed ? "set_provider_key" : "delete_provider_key", {
      provider: providerId,
      key: trimmed,
    });
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
