"use client";

import { useEffect, useRef } from "react";

/**
 * Keyboard shortcuts, declared where they are owned.
 *
 * Duct had exactly one shortcut before this (shadcn's ⌘B sidebar toggle), which
 * on desktop is the difference between an app and a bookmarked website. The
 * point of a hook rather than one global keydown switch is that a surface can
 * own its own shortcut and unregister it when it unmounts — a central table of
 * every binding in the app goes stale the moment a route changes.
 *
 * Combos are written platform-neutrally as "mod+k": `mod` is ⌘ on macOS and
 * Ctrl elsewhere, so nothing has to branch on the platform at the call site.
 */

const isMac = () =>
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

/** Parse "mod+shift+k" into the pieces an event can be checked against. */
function parseCombo(combo) {
  const parts = String(combo).toLowerCase().split("+").map((p) => p.trim());
  return {
    key: parts[parts.length - 1],
    mod: parts.includes("mod"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt"),
  };
}

export function matchesCombo(event, combo) {
  const { key, mod, shift, alt } = parseCombo(combo);
  const modDown = isMac() ? event.metaKey : event.ctrlKey;
  // The opposite modifier must NOT be held, or Ctrl+K on a Mac would fire a
  // binding the user meant for the terminal underneath.
  const otherMod = isMac() ? event.ctrlKey : event.metaKey;
  return (
    (event.key || "").toLowerCase() === key &&
    modDown === mod &&
    !otherMod &&
    event.shiftKey === shift &&
    event.altKey === alt
  );
}

/** True when the event came from somewhere the user is typing. */
export function isTypingTarget(target) {
  if (!target) return false;
  const tag = (target.tagName || "").toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    Boolean(target.isContentEditable)
  );
}

/**
 * Bind a global shortcut for as long as the component is mounted.
 *
 * @param combo    e.g. "mod+k", "mod+shift+p", "escape"
 * @param handler  called with the event; the default is to preventDefault
 * @param options  { enabled = true, allowInInput = false }
 *
 * `allowInInput` is off by default so a shortcut cannot eat a keystroke meant
 * for a text field — the exception is the palette's own opener, which should
 * work from anywhere.
 */
export function useShortcut(combo, handler, options = {}) {
  const { enabled = true, allowInInput = false } = options;
  // Held in a ref so an inline arrow at the call site — which is how these are
  // always written — doesn't tear down and re-add the listener every render.
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return undefined;
    const onKeyDown = (event) => {
      if (!matchesCombo(event, combo)) return;
      if (!allowInInput && isTypingTarget(event.target)) return;
      event.preventDefault();
      handlerRef.current(event);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [combo, enabled, allowInInput]);
}

/** Render a combo the way this platform writes it: "⌘K" / "Ctrl+K". */
export function formatShortcut(combo) {
  const { key, mod, shift, alt } = parseCombo(combo);
  const mac = isMac();
  const parts = [];
  if (mod) parts.push(mac ? "⌘" : "Ctrl");
  if (shift) parts.push(mac ? "⇧" : "Shift");
  if (alt) parts.push(mac ? "⌥" : "Alt");
  parts.push(key.length === 1 ? key.toUpperCase() : key.charAt(0).toUpperCase() + key.slice(1));
  return mac ? parts.join("") : parts.join("+");
}
