/**
 * Where a credential physically lives — the question "is this in the cloud or
 * on my machine?".
 *
 * Deliberately NOT `SOURCE_LABELS` in `modelTiers.js`, which looks like it
 * answers this and does not: that vocabulary is about *whose* key a run spends
 * (`user` / `stored` / `env` / `cloud` / `subscription`), which is a
 * provenance and billing question. The two axes cross — a `user` key can be
 * sitting in an OS keychain or in a browser tab that is about to be closed —
 * so collapsing them would make one of them wrong.
 *
 * Four answers, and the shell decides which "server-side" means:
 *
 *   cloud     — encrypted on Duct's servers. Survives everything, and is the
 *               only store an agent run or a scheduled brief can reach.
 *   local     — the same storage, when the server is the desktop app's own
 *               sidecar. Still "server-side", but the server is this laptop,
 *               so calling it Cloud would be a lie.
 *   keychain  — the OS keychain, desktop only. Never leaves the device and is
 *               not readable by Duct's backend at all.
 *   session   — this browser tab. Gone on close, and invisible to anything
 *               that runs without a browser attached.
 */

export const STORAGE_CLOUD = "cloud";
export const STORAGE_LOCAL = "local";
export const STORAGE_KEYCHAIN = "keychain";
export const STORAGE_SESSION = "session";
export const STORAGE_NONE = "none";

// Named for the consequence, not the mechanism. "Cloud" and "Database" are
// facts about our infrastructure; what someone deciding whether to connect an
// account actually needs to know is whether this survives closing the app, and
// whether it leaves their machine. The mechanism still gets said — in the
// detail line below, where there is room to say it accurately.
export const STORAGE_LABELS = {
  [STORAGE_CLOUD]: "Saved to your account",
  [STORAGE_LOCAL]: "On this device",
  [STORAGE_KEYCHAIN]: "In your keychain",
  [STORAGE_SESSION]: "This session only",
  [STORAGE_NONE]: "Not stored",
};

/**
 * The clause under the badge — and the second line of its tooltip.
 *
 * One sentence each, deliberately. These were two, and the tooltip they feed
 * is a 15rem box: the first sentence pushed the one that actually answers the
 * question ("can a scheduled report use this?") onto a fourth line nobody
 * reads. Where the mechanism still matters it is kept, compressed into a
 * clause rather than given a sentence of its own.
 */
export const STORAGE_DETAIL = {
  [STORAGE_CLOUD]:
    "Encrypted on Duct's servers, so any device \u2014 and any report that runs while you are away \u2014 can use it.",
  [STORAGE_LOCAL]:
    "Encrypted on this computer only, so nothing running elsewhere can use it, including scheduled reports.",
  [STORAGE_KEYCHAIN]:
    "Held by your operating system's keychain on this computer. Duct's servers never see it.",
  [STORAGE_SESSION]:
    "Kept only until you close the app, and reports that run without you cannot use it.",
  [STORAGE_NONE]: "Nothing stored yet.",
};

/**
 * Session storage is the one that surprises people — it looks connected and
 * silently is not, which is the whole reason these labels exist.
 */
export const STORAGE_TONE = {
  [STORAGE_CLOUD]: "green",
  [STORAGE_LOCAL]: "green",
  [STORAGE_KEYCHAIN]: "green",
  [STORAGE_SESSION]: "yellow",
  [STORAGE_NONE]: "grey",
};

/**
 * What "saved on the server" means for the shell you are in.
 *
 * `localSidecar` comes from `isLocalBackendActive()`. The desktop app bundles
 * its own backend, so a row "stored server-side" there is a row in a SQLite
 * file in the user's own data directory — the same durability guarantee, an
 * entirely different privacy one.
 */
export function serverStorage({ localSidecar = false } = {}) {
  return localSidecar ? STORAGE_LOCAL : STORAGE_CLOUD;
}

/**
 * Where a stored row lives, preferring what the backend said over what the
 * browser can infer.
 *
 * The inference is wrong in a case we actually run: `isLocalBackendActive()`
 * only reports that a sidecar answered the request, and a sidecar pointed at a
 * deployment's Postgres stores nothing on this machine. That labelled a
 * credential sitting in staging "On this device" — a privacy claim, made
 * confidently, in the wrong direction.
 *
 * So the row's own `storage` wins when the server sent one. The inference
 * survives only as the fallback for a backend too old to report it, where
 * "a sidecar is serving" remains the best available guess.
 */
export function rowStorage(row, { localSidecar = false } = {}) {
  const reported = row?.storage;
  if (reported === STORAGE_CLOUD || reported === STORAGE_LOCAL) return reported;
  return serverStorage({ localSidecar });
}
