#!/usr/bin/env node
/**
 * Every screen and every dialog the app ships is in the screen list.
 *
 * design/tools/screens.mjs lists every screen and how to reach it.
 * `node design/tools/capture.mjs <id>` reads it to shoot a screen at all eight
 * sizes, with only Playwright and the dev server, so a contributor can show a
 * change at every size. The maintainer's design canvas is built from the same
 * captures. Neither works for a screen the list leaves out, and the list
 * went stale silently twice: on 2026-11-15 nine routes and three overlays
 * were missing, and on 2026-11-23 three routes and eleven dialogs were. This
 * reads the source, so it runs without a browser:
 *
 *   - every routed page under src/app must match a screen's route in
 *     screens.mjs, or be in ROUTE_EXEMPT with its reason;
 *   - every file that renders a dialog, sheet or confirmation must name the
 *     screen that opens it in DIALOG_SCREENS, or be exempt with a reason.
 *
 * Fixing a failure needs only the code: add the entry, and run capture.mjs
 * on it to see that it opens. No design tool or account is involved.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(APP, "src");
const { SCREENS } = await import(join(APP, "..", "design/tools/screens.mjs"));
const SCREEN_IDS = new Set(SCREENS.map((s) => s.id));

// Pages that draw nothing of their own, so there is nothing to design.
const ROUTE_EXEMPT = {
  "/generate": "a redirect to /insights/session",
  "/insights/organic-growth/generate": "a redirect to /insights/session",
  "/insights/organic-growth/[slug]": "legacy: reads reports from the backend's disk, nothing links to it",
  "/open/audit/[conversationId]": "a share link that parks the destination and redirects",
};

// Each file that opens a dialog, a sheet or a confirmation, and the screen in
// screens.mjs that shows it open. `null` with a reason when it deliberately
// has none.
const DIALOG_SCREENS = {
  "components/commands/CommandPalette.jsx": "palette",
  "components/insights/InsightsWorkspace.jsx": "insights-focus",
  "components/audit/ShareReport.jsx": "audit-share",
  "app/(app)/execute/page.jsx": "change-set",
  "components/connections/ConnectorDialog.jsx": "toolbox-oauth",
  "components/content/FeedPlanDialog.jsx": "feed-sheet",
  "components/content/PublishModal.jsx": "publish-post",
  "components/content/CloneFromUrlDialog.jsx": "clone-tiktok",
  "components/content/FormatLibrary.jsx": "format-sheet",
  "app/(app)/projects/page.jsx": "delete-project",
  // One destructive confirmation stands for all of them (delete-project):
  // they share ui/alert-dialog and its canon row, and differ only in words.
  "components/ProjectMembers.jsx": null,
  "components/connections/ProviderCard.jsx": null,
  "components/connections/OAuthConnectorCard.jsx": null,
  // Drawn only inside the structured audit report on the free-audit page,
  // which is being retired (#123); the story renders the template report.
  "components/audit/ExecutionOffer.jsx": null,
};

const failures = [];

// --- routes -----------------------------------------------------------------------
const pages = walk(join(SRC, "app")).filter((f) => /\/page\.(js|jsx|tsx)$/.test(f) && !f.includes("/preview/"));
const screenPaths = SCREENS.map((s) => s.route.replace(/[?#].*$/, ""));
for (const file of pages) {
  const route = "/" + relative(join(SRC, "app"), dirname(file))
    .split("/").filter((seg) => seg && !/^\(.*\)$/.test(seg)).join("/");
  const path = route === "/." ? "/" : route.replace(/\/\.$/, "");
  if (ROUTE_EXEMPT[path]) continue;
  const pattern = new RegExp(`^${path.replace(/\[[^\]]+\]/g, "[^/]+").replace(/[.]/g, "\\.")}$`);
  if (!screenPaths.some((p) => pattern.test(p))) {
    failures.push(`page ${path} (${relative(SRC, file)}) has no entry in design/tools/screens.mjs`);
  }
}

// --- dialogs ----------------------------------------------------------------------
const OPENS = /<(Dialog|Sheet|AlertDialog)[\s>]/;
const sources = walk(SRC).filter((f) => /\.(jsx|tsx)$/.test(f) && !/\/(ui|preview|__tests__)\//.test(f));
for (const file of sources) {
  if (!OPENS.test(readFileSync(file, "utf8"))) continue;
  const key = relative(SRC, file);
  if (!(key in DIALOG_SCREENS)) {
    failures.push(`${key} opens a dialog that no screen shows: add one to screens.mjs and name it in DIALOG_SCREENS here`);
  } else if (DIALOG_SCREENS[key] && !SCREEN_IDS.has(DIALOG_SCREENS[key])) {
    failures.push(`${key} names screen "${DIALOG_SCREENS[key]}", which screens.mjs does not have`);
  }
}
for (const key of Object.keys(DIALOG_SCREENS)) {
  if (!sources.some((f) => relative(SRC, f) === key)) failures.push(`DIALOG_SCREENS names ${key}, which no longer exists`);
}

if (failures.length) {
  console.error(`✗ ${failures.length} thing(s) missing from the screen list:`);
  for (const f of failures) console.error(`    ${f}`);
  console.error("\n  Add an entry (its route, and how to open it) to design/tools/screens.mjs, then check it");
  console.error("  opens with `node design/tools/capture.mjs <id>`. Or exempt it here with the reason.");
  console.error("  How it works: design/README.md, \"Every screen is in the list\".");
  process.exit(1);
}
console.log(`screen coverage OK — ${pages.length - Object.keys(ROUTE_EXEMPT).length} pages, ${Object.values(DIALOG_SCREENS).filter(Boolean).length} dialogs on ${SCREENS.length} screens`);

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}
