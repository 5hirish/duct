// Every route segment that talks to the API waits for the API base.
//
// The desktop shell bundles its own backend and only learns its loopback port
// at runtime, so `BASE` is repointed once at boot and `LocalBackendGate` holds
// rendering until that has happened (see `src/lib/localBackend.js`). A segment
// that renders sooner sends its requests to the *hosted* API instead.
//
// That is not a slow-path bug, it is a sign-out: the session token is stored
// under one key but signed by whichever backend minted it, so a token from the
// wrong one comes back 401 "Invalid token", and `authFetch.endSession` reads
// any 401 as a dead session and clears it. `/start` was ungated and mints a
// guest, so clicking "Audit a site" from inside the desktop app replaced the
// signed-in session with a token the sidecar would never accept.
//
// The rule is per top-level segment because layouts nest — gating a segment
// covers everything under it. Adding to ALLOWED is a deliberate act: it claims
// the subtree reaches no backend at all.
//
// Run: node scripts/check-backend-gate.mjs

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const APP_DIR = fileURLToPath(new URL("../src/app/", import.meta.url));
const LAYOUT_NAMES = ["layout.js", "layout.jsx", "layout.tsx"];

const ALLOWED = {
  api: "route handlers — server-side, they never read the client BASE binding",
  preview: "the component gallery — renders fixtures, never the API",
};

/** A directory is a route only once something under it renders. */
function isRoutable(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (isRoutable(join(dir, entry.name))) return true;
    } else if (/^(page|route)\.(js|jsx|ts|tsx)$/.test(entry.name)) {
      return true;
    }
  }
  return false;
}

function layoutSource(segment) {
  for (const name of LAYOUT_NAMES) {
    const path = join(APP_DIR, segment, name);
    try {
      return { path: `${segment}/${name}`, text: readFileSync(path, "utf8") };
    } catch {
      /* try the next extension */
    }
  }
  return null;
}

// `styles/` and the agent tooling directories live here too; neither renders
// anything, so neither is a segment this rule has an opinion about.
const segments = readdirSync(APP_DIR).filter(
  (entry) => statSync(join(APP_DIR, entry)).isDirectory() && isRoutable(join(APP_DIR, entry))
);

let failed = 0;
for (const segment of segments) {
  if (segment in ALLOWED) {
    console.log(`· ${segment} — exempt: ${ALLOWED[segment]}`);
    continue;
  }

  const layout = layoutSource(segment);
  if (!layout) {
    failed++;
    console.log(`✗ ${segment} — no layout, so nothing gates it. Add one that renders LocalBackendGate.`);
    continue;
  }

  // Imported *and* rendered: an import alone gates nothing, and that is the
  // shape a half-finished edit leaves behind.
  const imported = layout.text.includes("LocalBackendGate.jsx");
  const rendered = layout.text.includes("<LocalBackendGate");
  if (imported && rendered) {
    console.log(`✓ ${segment} — gated in ${layout.path}`);
  } else {
    failed++;
    console.log(
      `✗ ${segment} — ${layout.path} ${imported ? "imports LocalBackendGate but never renders it" : "does not gate its children"}`
    );
  }
}

console.log(failed ? `\n${failed} ungated segment(s)` : "\nevery segment waits for the API base");
process.exit(failed ? 1 : 0);
