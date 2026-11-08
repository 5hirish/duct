#!/usr/bin/env node
/**
 * Every routed screen in the app shell is framed by PageHeader.
 *
 * The 2026-11-02 UI audit measured what happens when each page composes its
 * own header: titles at six left edges, three sizes and three weights, and
 * half the screens opening on a paragraph explaining themselves. `check:design`
 * stops a hand-made <h1>; this stops a page from having no frame at all, which
 * is the other way to drift.
 *
 * A route is exempt only as a workspace: the full-bleed agent screens listed
 * in the (app) layout's FULL_BLEED_PREFIXES, read from that file so the two
 * lists cannot disagree, plus the bare redirects. A page that hands its whole
 * body to one component names it in DELEGATES, and that component must render
 * the header instead.
 *
 * Run: `node scripts/check-page-frame.mjs` (part of `check:parity`).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const ROUTES = join(SRC, "app", "(app)");

// Pages whose body is one component, and the component that frames them.
const DELEGATES = {
  "insights/organic-growth/page.jsx": [
    "components/insights/Desk.jsx",
    "components/insights/desk/DeskDayOne.jsx",
  ],
};

// Pages that render nothing but a redirect.
const REDIRECTS = new Set(["generate/page.jsx", "insights/organic-growth/generate/page.jsx"]);

function pages(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...pages(full));
    else if (/^page\.(jsx?|tsx?)$/.test(entry)) out.push(full);
  }
  return out;
}

const layout = readFileSync(join(ROUTES, "layout.js"), "utf8");
const block = layout.match(/FULL_BLEED_PREFIXES\s*=\s*\[([\s\S]*?)\]/);
if (!block) {
  console.error("✗ could not read FULL_BLEED_PREFIXES from app/(app)/layout.js");
  process.exit(1);
}
const fullBleed = [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);

const failures = [];
let checked = 0;
for (const file of pages(ROUTES)) {
  const rel = relative(ROUTES, file);
  const route = "/" + dirname(rel).replace(/\\/g, "/").replace(/^\.$/, "");
  if (REDIRECTS.has(rel)) continue;
  // Same test as the layout: a prefix match on the route.
  if (fullBleed.some((prefix) => route.startsWith(prefix) || `${route}/`.startsWith(prefix))) continue;
  checked += 1;
  const sources = DELEGATES[rel] ? DELEGATES[rel].map((p) => join(SRC, p)) : [file];
  const framed = sources.every((p) => /\bPageHeader\b/.test(readFileSync(p, "utf8")));
  if (!framed) failures.push(`${route}  (${DELEGATES[rel] ? DELEGATES[rel].join(", ") : `app/(app)/${rel}`})`);
}

if (failures.length) {
  console.error(`✗ ${failures.length} screen(s) without PageHeader:`);
  for (const f of failures) console.error(`    ${f}`);
  console.error(
    "\n  Wrap the screen in <Page> with <PageHeader title=… /> from components/ui/page." +
      "\n  A full-bleed agent workspace belongs in FULL_BLEED_PREFIXES in app/(app)/layout.js instead."
  );
  process.exit(1);
}
console.log(`page frame OK — ${checked} screens framed, ${fullBleed.length} workspace prefixes exempt`);
