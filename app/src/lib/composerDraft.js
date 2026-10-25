// The text a person typed into a composer and has not sent, kept across a
// reload and a route change.
//
// sessionStorage on purpose, for the reason lib/agentSessionHandle.js gives
// for the session handle: it is per tab and dies with the tab. The key names
// a thread or a project, never a user, so a store that outlived the tab
// would hand one account's half-written question to the next sign-in on a
// shared browser, and sign-out clears nothing here. A draft is worth a
// reload, not tomorrow.
//
// One store for both composers — the desk's, which stashes a question around
// a trip to Settings, and the session composer's, which keeps a half-written
// follow-up through a reload — so the guards live once: the storage accessor
// throws in a private window and an embedded webview, and a draft is never
// worth an exception, only a quiet loss. Pure functions, no React, so the
// behaviour is tested without a DOM.

const PREFIX = "duct_draft:";

function storageKey(key) {
  return `${PREFIX}${key}`;
}

/** The saved text for `key`, or "" — also when storage is unavailable. */
export function readDraft(key) {
  if (!key) return "";
  try {
    return sessionStorage.getItem(storageKey(key)) || "";
  } catch {
    return "";
  }
}

/** Save `text` under `key`. An emptied box removes the entry rather than
 *  storing "", so a key with nothing to say leaves nothing behind. */
export function writeDraft(key, text) {
  if (!key) return;
  try {
    if (text) sessionStorage.setItem(storageKey(key), text);
    else sessionStorage.removeItem(storageKey(key));
  } catch {
    /* private mode / storage full — the text is still on screen */
  }
}

/** Forget the draft for `key`: it was sent, or claimed by the box. */
export function clearDraft(key) {
  if (!key) return;
  try {
    sessionStorage.removeItem(storageKey(key));
  } catch {
    /* nothing to forget where nothing could be kept */
  }
}
