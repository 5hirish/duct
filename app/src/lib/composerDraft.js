// The text a person typed into a composer and has not sent, kept across a
// reload and a route change.
//
// One store for both composers — the desk's, which stashes a question around
// a trip to Settings, and the session composer's, which keeps a half-written
// follow-up through a reload — so the guards live once: `localStorage`
// throws in a private window and when storage is full, and a draft is never
// worth an exception, only a quiet loss. The key is the caller's: the shell's
// session key for a thread, the project id for the desk. Pure functions, no
// React, so the behaviour is tested without a DOM.

const PREFIX = "duct_draft:";

function storageKey(key) {
  return `${PREFIX}${key}`;
}

/** The saved text for `key`, or "" — also when storage is unavailable. */
export function readDraft(key) {
  if (!key) return "";
  try {
    return localStorage.getItem(storageKey(key)) || "";
  } catch {
    return "";
  }
}

/** Save `text` under `key`. An emptied box removes the entry rather than
 *  storing "", so a key with nothing to say leaves nothing behind. */
export function writeDraft(key, text) {
  if (!key) return;
  try {
    if (text) localStorage.setItem(storageKey(key), text);
    else localStorage.removeItem(storageKey(key));
  } catch {
    /* private mode / storage full — the text is still on screen */
  }
}

/** Forget the draft for `key`: it was sent, or claimed by the box. */
export function clearDraft(key) {
  if (!key) return;
  try {
    localStorage.removeItem(storageKey(key));
  } catch {
    /* nothing to forget where nothing could be kept */
  }
}
