#!/usr/bin/env node
/**
 * The design system, as a test over the source.
 *
 * Every finding in `docs/engineering/2026-09-06-design-system-contrast-review.md`
 * had been fixed once before, somewhere in the tree, and had come back. The
 * spinner's own docblock says twelve hand-rolled rings were consolidated into
 * it; seventeen `Loader2`s had arrived since. `DESIGN.md` said "no invented
 * sizes" beside 228 invented sizes. Prose in a guide cannot hold a convention
 * that a hundred files can each break in isolation — so this is the same move
 * the backend makes with `test_harness_boundaries.py`: state the rule as code,
 * and make breaking it fail.
 *
 * It is a **ratchet**, not a big bang. Each rule carries an `allow` list of the
 * files that still break it, with the reason. Removing a name is permanent:
 * the file can never regress. Adding one is a deliberate act and needs a
 * sentence saying why, exactly like the backend's allowlist.
 *
 * Run: `npm run check:design` (part of `check:parity`).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(jsx?|tsx?)$/.test(full)) out.push(full);
  }
  return out;
}

/** Comments carry reasoning about the old code, so they are not the code. */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + m.slice(p.length).replace(/./g, " "));
}

const HUES =
  "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone";

const RULES = [
  {
    id: "no-arbitrary-type",
    why: "Type is a two-size system plus `text-2xs` (11px). An invented size is a fourth scale nobody agreed to, and 179 of the 228 that existed were at or below 11px on muted grey.",
    fix: "Use text-xs, text-sm, or text-2xs for genuinely decorative labels.",
    re: /\btext-\[\d+(?:\.\d+)?(px|rem)\]/g,
    allow: new Map(),
  },
  {
    id: "no-palette-colour",
    why: "A raw Tailwind hue has no dark partner and no contrast guarantee. Eight hues were standing in for four meanings, and the ones used as text measured 2.1–2.7:1.",
    fix: "Use a semantic token: success, warning, destructive, info, primary, muted-foreground, brand.",
    re: new RegExp(String.raw`\b(?:dark:)?(?:text|bg|border|ring|fill|stroke|divide|from|to|via|shadow|outline|decoration)-(?:${HUES})-\d{2,3}\b`, "g"),
    allow: new Map([
      // Google's brand spec for the sign-in button. The review calls this out
      // as the one legitimate colour island in the tree.
      ["components/GoogleSignInButton.jsx", "Google's published button spec"],
      // The generated audit report declares itself a light document (see the
      // token block at its root); its palette is print, not app chrome.
      ["components/audit/AuditReportV1.jsx", "light-only document, declares color-scheme"],
      ["components/audit/ExecutionOffer.jsx", "the audit document's own modal"],
      // The preview route's job is to show what the tokens resolve to, which
      // means naming colours that are not tokens.
      ["app/preview/system.jsx", "renders the palette itself"],
      ["app/preview/TokenSheet.jsx", "renders the palette itself"],
    ]),
  },
  {
    id: "no-hex-in-jsx",
    why: "A hex is a light-mode decision written where nothing can revisit it. Sixty of them inside a component whose shell used tokens is what produced a white table on a dark page.",
    fix: "Use a token, or declare the subtree a document by redefining the tokens on it.",
    re: /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![0-9a-fA-F])/g,
    allow: new Map([
      ["components/GoogleSignInButton.jsx", "Google's published button spec"],
      ["components/audit/AuditReportV1.jsx", "light-only document, declares color-scheme"],
      ["components/audit/ExecutionOffer.jsx", "the audit document's own modal"],
      ["components/workspace/CodeBlock.jsx", "the editor chrome is dark in both themes, deliberately"],
      ["app/preview/system.jsx", "renders the palette itself"],
      ["app/preview/TokenSheet.jsx", "renders the palette itself"],
      ["app/preview/inspect.js", "measures colours, so it parses and prints them"],
      ["components/audit/AuditReport.jsx", "one dashed rule drawn to match the report it frames"],
      ["components/content/platformGlyphs.jsx", "third-party platform brand marks"],
      ["components/GoogleAdsReport.js", "light-only report, same exception as AuditReportV1"],
      // Browser and OS chrome. `themeColor` and the PWA manifest are read
      // before any stylesheet exists, so they cannot be a custom property.
      ["app/layout.js", "themeColor meta — read before CSS loads"],
      ["app/manifest.js", "PWA manifest — read by the OS, not the page"],
      ["app/(public)/layout.jsx", "themeColor meta — read before CSS loads"],
      ["app/(start)/layout.jsx", "themeColor meta — read before CSS loads"],
      // Colours that are content rather than chrome: the user's own brand
      // palette, and the previews of what a slide style looks like.
      ["components/content/BrandContextForm.jsx", "placeholders showing the user's own brand hexes"],
      ["components/content/StyleGallery.jsx", "previews of what each slide style paints"],
      // Off-screen render surfaces and exported artwork: a slide is a picture
      // with its own ground, and it is captured, not displayed.
      ["lib/slideCapture.js", "the off-screen capture frame, never on screen"],
      ["lib/slideDoc.js", "the exported slide document's own ground"],
      ["lib/themes.js", "per-insight accent marks, part of the report's identity"],
    ]),
  },
  {
    id: "no-native-confirm",
    why: "An OS modal cannot say what will happen, cannot be destructive, cannot be seen in /preview, and on the desktop webview reads as the browser accusing the user.",
    fix: "useConfirm() or <ConfirmDialog> from components/ui/confirm-dialog.",
    re: /\bwindow\.(confirm|alert|prompt)\s*\(/g,
    allow: new Map(),
  },
  {
    id: "no-loader2",
    why: "ui/spinner exists because twelve hand-rolled rings were consolidated into it. Seventeen Loader2s arrived afterwards, because nothing checked.",
    fix: "<Spinner /> from components/ui/spinner — it takes its colour from currentColor.",
    re: /\bLoader2\b/g,
    allow: new Map(),
  },
  {
    id: "no-opacity-on-muted",
    why: "--muted-foreground is 7.8:1 because secondary text still has to be read. Halving it is not a lighter shade, it is 3.9:1, and the sites doing it were the 10px ones.",
    fix: "Use text-muted-foreground as it is; if it needs to be quieter, it needs to be less text.",
    re: /\btext-muted-foreground\/\d+\b/g,
    allow: new Map(),
  },
  {
    id: "no-viewport-prefix-in-content",
    why: "The sidebar takes 16rem out of the window, and both agent panes are user-resizable, so `sm:` can fire while the box you are in is 300px. Each layout region declares a container for exactly this reason (app/AGENTS.md).",
    fix: "Use Tailwind's @-variants (@md, @xl, @3xl…), which ask the container.",
    re: /(?<=["' ])(?:sm|md|lg|xl|2xl):(?=[a-z[])/g,
    allow: new Map([
      // The genuine device concerns app/AGENTS.md lists: overlays positioned
      // against the window, the mobile pane toggle, and the iOS zoom guard.
      ["components/workspace/SplitWorkspace.jsx", "the mobile pane toggle is a device concern"],
      ["components/ConnectionBanner.jsx", "fixed to the viewport, not to a container"],
      ["components/CookieConsent.jsx", "fixed to the viewport, not to a container"],
      ["components/ui/sidebar.tsx", "the sidebar's mobile sheet is a device concern"],
      ["components/ui/dialog.tsx", "overlay sized against the window"],
      ["components/ui/sheet.tsx", "overlay sized against the window"],
      ["components/ui/alert-dialog.tsx", "overlay sized against the window"],
      ["components/audit/ShareReport.jsx", "dialog sized against the window"],
      ["components/audit/AuditReportV1.jsx", "light-only document, printed at one width"],
      ["components/audit/ExecutionOffer.jsx", "the audit document's own modal"],
      ["components/commands/CommandPaletteTrigger.jsx", "hides the trigger's label on phones"],
      ["app/(app)/execute/page.jsx", "dialog sized against the window"],
      ["app/(auth)", "the sign-in split is a device concern"],
      ["app/(start)", "the onboarding split is a device concern"],
      ["app/(public)", "a public marketing page, sized against the window"],
      ["app/preview", "the preview harness sizes frames to devices on purpose"],
      ["components/onboarding", "the onboarding split is a device concern"],
      ["components/ui/breadcrumb.tsx", "primitive, rendered in chrome as well as content"],
      ["app/not-found.js", "a bare page with no app shell around it"],
    ]),
  },
];

/** `md:text-sm` is the iOS zoom guard, which every chat input needs. */
const EXEMPT_MATCH = new Set(["md:"]);
const EXEMPT_LINE = /md:text-sm/;

let failures = 0;
const summary = [];

for (const rule of RULES) {
  const hits = [];
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file);
    const allowed = [...rule.allow.keys()].some((k) => rel === k || rel.startsWith(k + "/"));
    if (allowed) continue;

    const text = stripComments(readFileSync(file, "utf8"));
    const lines = text.split("\n");
    rule.re.lastIndex = 0;
    for (const m of text.matchAll(rule.re)) {
      const line = text.slice(0, m.index).split("\n").length;
      if (EXEMPT_MATCH.has(m[0]) && EXEMPT_LINE.test(lines[line - 1] || "")) continue;
      hits.push(`${rel}:${line}  ${m[0].trim()}`);
    }
  }

  if (hits.length) {
    failures += hits.length;
    console.error(`\n✗ ${rule.id} — ${hits.length} violation(s)`);
    console.error(`  ${rule.why}`);
    console.error(`  → ${rule.fix}`);
    for (const h of hits.slice(0, 25)) console.error(`    ${h}`);
    if (hits.length > 25) console.error(`    … and ${hits.length - 25} more`);
  } else {
    summary.push(`✓ ${rule.id}${rule.allow.size ? ` (${rule.allow.size} allowed)` : ""}`);
  }
}

console.log(summary.join("\n"));

if (failures) {
  console.error(
    `\n${failures} violation(s). These are the conventions in app/DESIGN.md, held here so they` +
      `\nstay held — see docs/engineering/2026-09-06-design-system-contrast-review.md for what` +
      `\neach one cost the last time it drifted. If a file genuinely has to break a rule, add it` +
      `\nto that rule's \`allow\` map with the reason; that is a decision, not a way to quiet the check.\n`
  );
  process.exit(1);
}

console.log("\ndesign system OK");
