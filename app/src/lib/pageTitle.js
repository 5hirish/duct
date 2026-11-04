"use client";

// The page's own title, as the top bar needs to know it.
//
// A framed screen says its name once, in PageHeader's <h1>. The top bar used
// to say it again, so every screen opened on its title twice, one above the
// other. Now the two take turns, the way a large title does on Apple's
// platforms: the bar stays quiet while the page's title is on screen, and
// takes the title over once it scrolls away. PageHeader publishes here; the
// bar (components/AppNav.jsx) reads with useSyncExternalStore.
//
// One page header a screen (check:layout holds that), so one slot is enough.

const EMPTY = Object.freeze({ present: false, visible: false, title: "", back: null });

let current = EMPTY;
const listeners = new Set();

export function publishPageTitle(next) {
  const merged = { ...current, ...next };
  if (
    merged.present === current.present &&
    merged.visible === current.visible &&
    merged.title === current.title &&
    // The label can be an element (<Trans>Home</Trans> from a server page),
    // new on every render, so the parent is the same parent by its address.
    merged.back?.href === current.back?.href
  ) {
    return;
  }
  current = merged;
  for (const listener of listeners) listener();
}

export function clearPageTitle() {
  current = EMPTY;
  for (const listener of listeners) listener();
}

export function subscribePageTitle(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pageTitleSnapshot() {
  return current;
}

/** The server never has a page header mounted. */
export function pageTitleServerSnapshot() {
  return EMPTY;
}
