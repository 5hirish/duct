/**
 * One way to tell the user something while they are not looking at the tab.
 *
 * The rule is OpenCode's: notify only when the window is not focused, never
 * when it is — a banner over the thing you are already reading is noise. The
 * transport depends on where the app runs: the desktop shell has a `notify`
 * command that goes through the OS, the browser has `Notification` behind a
 * permission the sidebar menu asks for. Neither is required; without either
 * this is a no-op.
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

/**
 * Which transport this session actually has: "shell", "browser" or "none".
 *
 * The sidebar's permission item needs this because the two surfaces answer
 * "are notifications on?" in different places. In the shell the OS owns that
 * switch and there is nothing for the page to ask for, so the item cannot be
 * driven off `Notification.permission` the way the browser's is.
 *
 * The shell is asked *first*, and the order is load bearing: the desktop
 * webview does define `window.Notification`, because `tauri-plugin-notification`
 * injects a polyfill over it. Testing for the constructor would therefore call
 * every desktop session a browser one and report a permission the OS never
 * asked for.
 */
export async function notificationSurface() {
  if (await shellCanNotify()) return "shell";
  if (typeof window !== "undefined" && "Notification" in window) return "browser";
  return "none";
}

/**
 * Whether this shell can open the OS page where notifications are switched on.
 *
 * Gated on the capability rather than on `isDesktopShell()`, because a shell
 * installed before `open_notification_settings` would reject the invoke and the
 * sidebar would offer a row that does nothing — and on Linux, where the flag is
 * false because no single such page exists.
 */
export async function canOpenNotificationSettings() {
  const info = await getShellInfo();
  return Boolean(info?.capabilities?.notificationSettings);
}

/**
 * Send the user to the OS notification settings. Resolves to whether it opened;
 * never throws, so a caller can fall back to saying where to look.
 */
export async function openNotificationSettings() {
  try {
    await window.__TAURI__.core.invoke("open_notification_settings");
    return true;
  } catch {
    return false;
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
