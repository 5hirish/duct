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

export const STORAGE_LABELS = {
  [STORAGE_CLOUD]: "Cloud",
  [STORAGE_LOCAL]: "This device",
  [STORAGE_KEYCHAIN]: "Keychain",
  [STORAGE_SESSION]: "This session",
  [STORAGE_NONE]: "Not stored",
};

/** The clause under the badge, where there is room for one. */
export const STORAGE_DETAIL = {
  [STORAGE_CLOUD]:
    "Encrypted on Duct's servers. Available to agent runs and scheduled briefs.",
  [STORAGE_LOCAL]:
    "In Duct's database on this machine. It never leaves the device, and nothing scheduled elsewhere can use it.",
  [STORAGE_KEYCHAIN]:
    "In this machine's OS keychain. Duct's backend cannot read it — the app sends it per request.",
  [STORAGE_SESSION]:
    "In this browser tab only. It is gone when you close the tab, and agent runs cannot use it.",
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
