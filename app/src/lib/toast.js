"use client";

/**
 * Minimal dependency-free toast bus.
 *
 * A singleton event channel so any module — a page, or a plain lib/* caller —
 * can raise a toast without threading a React context through. `<Toaster />`
 * (components/Toaster.jsx, mounted once in the app shell) subscribes and renders
 * the stack at the top of the app. Kept out of React context on purpose so
 * non-component code can call `toast()` too.
 */

let _id = 0;
const listeners = new Set();

/**
 * Show a toast. Returns the id (pass to `dismissToast`).
 * @param {string} message
 * @param {{variant?: "default"|"error"|"success", duration?: number, title?: string}} [opts]
 *   variant styles the accent; duration ms (0 = sticky until dismissed).
 */
export function toast(message, { variant = "default", duration = 6000, title } = {}) {
  const t = { id: ++_id, message, variant, duration, title };
  listeners.forEach((fn) => fn({ type: "add", toast: t }));
  return t.id;
}

export const toastError = (message, opts = {}) => toast(message, { ...opts, variant: "error" });
export const toastSuccess = (message, opts = {}) => toast(message, { ...opts, variant: "success" });

/** Dismiss a toast early by id. */
export function dismissToast(id) {
  listeners.forEach((fn) => fn({ type: "remove", id }));
}

/** Subscribe to toast events. Returns an unsubscribe fn. */
export function subscribeToasts(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
