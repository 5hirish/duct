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

import { chatgptCredential } from "./chatgpt.js";

/**
 * The tiles, in the order they are drawn.
 *
 * `description` is what the user reads, so it names what the key buys them and
 * nothing about how Duct spends it: no engine names, no SDK names, no model
 * ids. The previous set said "on the LangChain (v1) engine" on two tiles and
 * "gpt-image-2" on a third — three implementation details on a settings page
 * whose reader is deciding which vendor to open an account with.
 *
 * `backend/routes/providers.py` holds the same sentences for the same tiles
 * (it answers `/providers/status`, which repaints them). Change both.
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
    description: "Claude models. Needs an API key — a Claude Pro or Max plan can't be used here.",
    consoleUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "openai",
    statusId: "openai",
    label: "OpenAI",
    header: "X-Provider-OpenAI",
    placeholder: "sk-…",
    prefix: "sk-",
    description: "GPT models and images, or your own ChatGPT Plus or Pro plan.",
    // Only OpenAI has a consumer plan Duct can run on, so the dialog's
    // "set it up" section is keyed off this rather than off the id. If a
    // second provider ever opens one up, it gets the flag, not a new branch.
    hasPlan: true,
    consoleUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "gemini",
    statusId: "google_genai",
    label: "Google Gemini",
    header: "X-Provider-Gemini",
    placeholder: "AIza…",
    prefix: "",
    description: "Gemini models. Duct's first pick for drawing images.",
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
    description: "One key, 500+ models — and any OpenAI-compatible service you point it at.",
    consoleUrl: "https://openrouter.ai/keys",
  },
  {
    id: "xai",
    statusId: "xai",
    label: "xAI",
    header: "X-Provider-XAI",
    placeholder: "xai-…",
    prefix: "xai-",
    description: "Grok models, and Grok's own image generation.",
    consoleUrl: "https://console.x.ai",
  },
];

const STORAGE_PREFIX = "duct_provider_key_";
const OPENAI_HEADER = PROVIDERS.find((p) => p.id === "openai").header;

function isTauri() {
  return typeof window !== "undefined" && Boolean(window.__TAURI__);
}

/**
 * Keys this page has already read from the desktop keychain.
 *
 * Every request reads every provider's key (`providerKeyHeaders`), and the
 * memory catch-up reads them again every half hour. A signed release reads its
 * own items silently, so that costs nothing. When macOS does ask (a keychain
 * locked after a password change, an item written by a differently signed
 * build) and the answer is "Allow" rather than "Always Allow", it asks again on
 * every read: every message, and a dialog out of nowhere every half hour.
 * Holding what was read makes it once per launch, and exposes nothing new, since
 * each read hands this page the key anyway. Only keys are held: a refusal is
 * retried on the next read, and an absence costs no prompt to check again.
 */
const keychainKeys = new Map();

/**
 * Read a stored provider key, and say why when the store refused.
 *
 * Returns `{ key }`, with `key` "" when none is set, or `{ key: "", error }`
 * when the desktop keychain would not answer. A refusal is not an absence: the
 * key card must not tell someone whose key is sitting in the keychain that none
 * is set, because the fix is different. `chatgptStatus` draws the same line for
 * the sign-in.
 */
export async function readProviderKey(providerId) {
  if (typeof window === "undefined") return { key: "" };
  if (isTauri()) {
    if (keychainKeys.has(providerId)) return { key: keychainKeys.get(providerId) };
    try {
      const key = (await window.__TAURI__.core.invoke("get_provider_key", { provider: providerId })) || "";
      if (key) keychainKeys.set(providerId, key);
      return { key };
    } catch (err) {
      return { key: "", error: String(err?.message ?? err) };
    }
  }
  try {
    return { key: window.sessionStorage.getItem(STORAGE_PREFIX + providerId) || "" };
  } catch {
    return { key: "" };
  }
}

/** Read a stored provider key. Returns "" when unset or storage is unavailable. */
export async function getProviderKey(providerId) {
  return (await readProviderKey(providerId)).key;
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
 * show it. `getProviderKey` still degrades quietly, since a request has no one
 * to tell; `readProviderKey` reports the refusal for the card that can.
 */
export async function setProviderKey(providerId, value) {
  if (typeof window === "undefined") return;
  const trimmed = (value || "").trim();
  if (isTauri()) {
    keychainKeys.delete(providerId);
    const invoke = window.__TAURI__.core.invoke;
    if (!trimmed) {
      await invoke("delete_provider_key", { provider: providerId });
      return;
    }
    try {
      await invoke("set_provider_key", { provider: providerId, key: trimmed });
    } catch (first) {
      // An item a differently signed build wrote can refuse the overwrite as
      // well as the read, and then pasting the key again, the fix the card
      // offers, fails the same way. Deleting first costs nothing, since the item
      // was unusable, and it is what `store()` in chatgpt.rs does for the
      // sign-in. Here rather than in the shell because the page is deployed and
      // the shell is not: this reaches every copy already installed.
      try {
        await invoke("delete_provider_key", { provider: providerId });
        await invoke("set_provider_key", { provider: providerId, key: trimmed });
      } catch {
        throw first;
      }
    }
    keychainKeys.set(providerId, trimmed);
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

/** The account id that rides beside a ChatGPT access token in the OpenAI slot. */
export const OPENAI_ACCOUNT_HEADER = "X-OpenAI-Account-Id";

/**
 * Build the `X-Provider-*` request headers for whichever keys are set.
 * Returns `{}` server-side or when no keys are stored.
 *
 * A pasted OpenAI key wins over a ChatGPT sign-in: the key is the supported
 * path with predictable limits, and the backend applies the same rule.
 * Without one, a desktop sign-in fills the OpenAI slot with the plan's access
 * token — the backend tells the two apart by shape, not by header name.
 */
export async function providerKeyHeaders() {
  const headers = {};
  if (typeof window === "undefined") return headers;
  for (const provider of PROVIDERS) {
    const key = await getProviderKey(provider.id);
    if (key) headers[provider.header] = key;
  }
  if (!headers[OPENAI_HEADER]) {
    const cred = await chatgptCredential().catch(() => null);
    if (cred?.accessToken) {
      headers[OPENAI_HEADER] = cred.accessToken;
      if (cred.accountId) headers[OPENAI_ACCOUNT_HEADER] = cred.accountId;
    }
  }
  return headers;
}
