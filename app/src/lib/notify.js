/**
 * One way to tell the user something while they are not looking at the tab.
 *
 * The rule is OpenCode's: notify only when the window is not focused, never
 * when it is — a banner over the thing you are already reading is noise. The
 * transport depends on where the app runs: the desktop shell has a `notify`
 * command that goes through the OS (the webview has no Notification API on a
 * remote origin), the browser has `Notification` behind a permission the
 * sidebar menu asks for. Neither is required; without either this is a no-op.
 */

import { getShellInfo, isDesktopShell } from "./shell";

let shellNotifications = null; // null = not asked yet; then true/false

async function shellCanNotify() {
  if (!isDesktopShell()) return false;
  if (shellNotifications === null) {
    const info = await getShellInfo();
    shellNotifications = Boolean(info?.capabilities?.notifications);
  }
  return shellNotifications;
}

/** True while the page is visible and its window focused. */
export function pageIsBeingLookedAt() {
  if (typeof document === "undefined") return true;
  if (document.visibilityState === "hidden") return false;
  try {
    return document.hasFocus();
  } catch {
    return true;
  }
}

/** Whether the browser side is able to notify right now. */
export function browserCanNotify() {
  return typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted";
}

/**
 * Show `{ title, body }` if the user is elsewhere. `tag` collapses repeats —
 * two "done" notices for one thread become one. Resolves to whether anything
 * was shown; never throws.
 */
export async function notifyIfAway({ title, body = "", tag = "" }) {
  if (pageIsBeingLookedAt()) return false;
  try {
    if (await shellCanNotify()) {
      await window.__TAURI__.core.invoke("notify", { title, body });
      return true;
    }
    if (browserCanNotify()) {
      const n = new Notification(title, { body, tag: tag || undefined, icon: "/favicon.ico" });
      // Clicking the notice brings the tab back — what the notice was for.
      n.onclick = () => {
        try { window.focus(); } catch { /* not allowed here */ }
        n.close();
      };
      return true;
    }
  } catch {
    /* a shell too old for the command, or a browser that changed its mind */
  }
  return false;
}
