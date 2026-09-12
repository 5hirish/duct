/**
 * "Continue with ChatGPT" — the user's own ChatGPT plan as Duct's OpenAI
 * credential, desktop only.
 *
 * The shell does the work (`desktop/src-tauri/src/chatgpt.rs`): it runs the
 * OAuth in the system browser, keeps the refresh token in the OS keychain, and
 * hands this module an hour-long access token plus the account id. Those two
 * go out as request headers the way an API key does — `X-Provider-OpenAI` and
 * `X-OpenAI-Account-Id` — so the backend never learns how to mint another.
 *
 * Gated on the `chatgptAuth` capability, never on the shell version: an older
 * shell reports no flag and the API-key path is all it shows.
 */

// Extension included on purpose: the parity checks in `app/scripts/` import
// this graph with raw Node ESM, which does not resolve an extensionless
// specifier the way the bundler does. Getting this wrong fails `make check`
// with a module-not-found several files away from the cause.
import { getShellInfo, isDesktopShell } from "./shell.js";

/** The shell said "revoked": the user signed out of ChatGPT or removed Duct. */
export const CHATGPT_REVOKED = "revoked";
/**
 * The shell said "cancelled": the sign-in was abandoned on purpose — the
 * Cancel button, or a newer sign-in taking the port over. Quiet, not an error.
 */
export const CHATGPT_CANCELLED = "cancelled";

const PLAN_LABELS = { plus: "ChatGPT Plus", pro: "ChatGPT Pro", team: "ChatGPT Team", free: "ChatGPT Free" };

/** The plan as the user would name it, from the `plan_type` claim the shell reports. */
export function planLabel(planType) {
  return PLAN_LABELS[String(planType || "").toLowerCase()] || (planType ? `ChatGPT ${planType}` : "ChatGPT");
}

let capabilityPromise = null;

/** Whether this shell can run the sign-in at all. Cached: the answer never changes mid-session. */
export function chatgptAuthAvailable() {
  if (!isDesktopShell()) return Promise.resolve(false);
  if (!capabilityPromise) {
    capabilityPromise = getShellInfo()
      .then((info) => Boolean(info?.capabilities?.chatgptAuth))
      .catch(() => false);
  }
  return capabilityPromise;
}

function invoke(command, args) {
  return window.__TAURI__.core.invoke(command, args);
}

/** `{ connected, plan_type, email, account_id }` — never a token. */
export async function chatgptStatus() {
  if (!(await chatgptAuthAvailable())) return { connected: false };
  try {
    return (await invoke("chatgpt_status")) || { connected: false };
  } catch {
    return { connected: false };
  }
}

/**
 * Run the sign-in. Resolves with the status once the shell holds the bundle;
 * rejects with the shell's sentence when the browser round trip did not
 * finish (timeout, decline, port in use).
 */
export async function chatgptLogin() {
  if (!(await chatgptAuthAvailable())) {
    throw new Error("Signing in with ChatGPT needs the Duct desktop app.");
  }
  return invoke("chatgpt_login");
}

/**
 * Abandon a sign-in still waiting on the browser. The pending `chatgptLogin()`
 * rejects with `CHATGPT_CANCELLED` and the loopback port is released, so the
 * next attempt can bind it. Harmless when nothing is waiting.
 *
 * Tolerates a shell that predates the command: that shell's login still ends
 * on its own timeout, and there is nothing better to do than let it.
 */
export async function chatgptLoginCancel() {
  if (!(await chatgptAuthAvailable())) return;
  try {
    await invoke("chatgpt_login_cancel");
  } catch {
    /* older shell: no such command */
  }
}

/** Whether a login rejection is the quiet kind — cancelled, not failed. */
export function isChatgptCancelled(err) {
  return String(err?.message ?? err) === CHATGPT_CANCELLED;
}

export async function chatgptLogout() {
  if (!(await chatgptAuthAvailable())) return;
  await invoke("chatgpt_logout");
}

/**
 * The two header values for one request, or null when there is no sign-in.
 * The shell refreshes a token that is about to expire before answering, so
 * what comes back is always good for the request about to be made. Throws
 * `CHATGPT_REVOKED` when the refresh was refused — the caller shows the
 * button again rather than sending a dead token.
 */
export async function chatgptCredential() {
  if (!(await chatgptAuthAvailable())) return null;
  try {
    const cred = await invoke("chatgpt_credential");
    if (!cred?.access_token) return null;
    return { accessToken: cred.access_token, accountId: cred.account_id || "" };
  } catch (err) {
    if (String(err) === CHATGPT_REVOKED || String(err?.message) === CHATGPT_REVOKED) {
      throw new Error(CHATGPT_REVOKED);
    }
    return null;
  }
}
