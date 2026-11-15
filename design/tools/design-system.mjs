#!/usr/bin/env node
// The Duct Design System's files, from the code. Writes OUT/design-system/project/:
//
//   tokens.json                      every colour token in both themes, read from
//                                    app/src/app/styles (tokens.css, theme.css,
//                                    onboarding.css), plus type, spacing, radii
//   components/bundle.css            the app's stylesheet (capture.mjs's), minus
//                                    the token values tokens.json now owns
//   components/<Comp>/preview.html   the component as the app renders it in
//                                    /preview, as static markup
//   components/<Comp>/README.md      its rule, parsed from app/DESIGN.md's canon
//   assets/<Group>/*                 logos, mosaic panels, connector marks
//   assets.json                      those files' sizes and types, for the index
//
// The system's brand book (README.md), its cover and its index are kept in the
// artifact, not here: the book is condensed by hand from app/DESIGN.md, which
// stays the source when the two disagree.
//
//   node design/tools/capture.mjs            # first: it writes the stylesheet
//   node design/tools/design-system.mjs      # needs the app's dev server for /preview
//   node design/tools/design-system.mjs --blobs blobs.json   # after the uploads: point
//                                            # previews' images at the uploaded copies
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const STYLES = join(REPO, "app/src/app/styles");
const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design"));
const DS = join(OUT, "design-system", "project");
const APP = process.env.APP || "http://localhost:3003";
const args = process.argv.slice(2);
const blobsFile = args.includes("--blobs") ? args[args.indexOf("--blobs") + 1] : null;
const MIME = { ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif" };
const FONTS = "https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap";

if (blobsFile) {
  pointImagesAtUploads(JSON.parse(readFileSync(blobsFile, "utf8")));
  process.exit(0);
}

mkdirSync(join(DS, "components"), { recursive: true });

// --- tokens -----------------------------------------------------------------------
// What each colour is for, in a line. The values come from the stylesheets; the
// words come from DESIGN.md and the comments beside each declaration.
const USAGE = {
  orange: "The literal brand orange the site and the wordmark's dot paint. A mark, never text: white on it is 3.1:1.",
  "orange-h": "Hover for a fill painted in the literal orange, on the marketing site.",
  navy: "The site's ink and the sign-in half's ground. Brand, not a theme colour: never paint app UI with it.",
  "navy-2": "Secondary navy on the marketing site.",
  "navy-3": "Muted navy on the marketing site.",
  white: "Pure white, the brand's paper.",
  off: "The site's off-white section ground.",
  background: "The page. Light is white; dark is warm charcoal, never navy or black.",
  foreground: "Body text and headings on background, card and popover.",
  card: "A Card's ground. The same white as background in light, one step lighter in dark (elevation lightens).",
  "card-foreground": "Text on card.",
  popover: "Menus, popovers, dialogs: the highest surface.",
  "popover-foreground": "Text on popover.",
  primary: "The one accent, as a FILL: the primary button, checks, tints, the hero card's border. Same orange in both themes with white on it. Never text: use brand.",
  "primary-foreground": "Label on a primary fill.",
  secondary: "Secondary button and quiet fills.",
  "secondary-foreground": "Text on secondary.",
  muted: "Quiet grounds: skeletons, code, a row's hover, chips.",
  "muted-foreground": "Secondary text: status lines, metadata, captions. 4.5:1 or better on background and card in both themes.",
  accent: "Hover and selected ground for menu items and ghost buttons.",
  "accent-foreground": "Text on accent.",
  destructive: "Failure and destruction: errors, the delete action (as a 10% tint with this as text), the failed state.",
  "destructive-foreground": "Text on a solid destructive fill, only where a tint cannot work.",
  success: "Good movement and done: an up delta that is good, Connected, Applied. Never decoration.",
  "success-foreground": "Text on a solid success fill.",
  warning: "Waiting: needs you, paused, stale. Always with a word or icon beside the colour.",
  "warning-foreground": "Text on a solid warning fill.",
  info: "Moving, or a state that is neither win nor problem (a key that works but isn't yours). Never a second accent.",
  "info-foreground": "Text on a solid info fill.",
  brand: "The brand orange as TEXT: links on hover, the scheduled count, an orange word. Equal to primary in light, lifted in dark.",
  "brand-foreground": "Text on a brand fill in dark.",
  border: "Hairlines between things already told apart: card edges, row dividers. A whisper on purpose.",
  input: "The fill behind a field and the track behind a switch. A surface, not an edge.",
  control: "The edge that says 'this is a field you can type in', about 2:1. The focused field gets ring at 3:1.",
  ring: "The focus ring, 3:1 or better on every surface it lands on.",
  "chart-1": "First chart series: the orange.",
  "chart-2": "Second chart series: warm ink.",
  "chart-3": "Third chart series: blue.",
  "chart-4": "Fourth chart series: sand.",
  "chart-5": "Fifth chart series: green.",
  sidebar: "The app sidebar's ground: a warm step off the page in light, a step above it in dark.",
  "sidebar-foreground": "Sidebar text.",
  "sidebar-primary": "The sidebar's accent fill.",
  "sidebar-primary-foreground": "Text on sidebar-primary.",
  "sidebar-accent": "The current page's row and a row's hover in the sidebar.",
  "sidebar-accent-foreground": "Text on sidebar-accent.",
  "sidebar-border": "The sidebar's edge and its dividers.",
  "sidebar-ring": "Focus ring inside the sidebar.",
  "tessera-cream": "Mosaic stone: the cream field of the threshold panels and the aqueduct's stones.",
  "tessera-grey": "Mosaic stone: grey, for joints and shade.",
  "tessera-ochre": "Mosaic stone: ochre, the warm detail stone; also onboarding's small labels.",
  "tessera-basalt": "Mosaic stone: basalt, the dark border stone.",
  "tessera-glass": "Mosaic stone: glass. Blue is water, and nothing else on a mosaic page is blue.",
  "tessera-terracotta": "Mosaic stone: terracotta, the brand orange. Consequence: the stone that marks what changed.",
  "start-ground": "The ground of /start and the sign-in half, flipping with the theme.",
};

const light = {
  ...declarations(read("tokens.css"), ":root"),
  ...declarations(read("onboarding.css"), ":root"),
};
const dark = {
  ...declarations(read("theme.css"), ".dark"),
  ...darkOf(read("onboarding.css")),
};
const colorNames = Object.keys(USAGE).filter((n) => light[n] && isColor(light[n]));
const tokens = {
  name: "Duct",
  version: 1,
  meta: {
    source: "github",
    repo: "5hirish/duct",
    ref: `main@${gitHead() || "unknown"}`,
    package: "app",
    paths: {
      tokens: ["app/src/app/styles/tokens.css", "app/src/app/styles/theme.css", "app/src/app/styles/onboarding.css"],
      docs: ["app/DESIGN.md"],
      assets: ["app/src/app/icon.svg", "app/public/art/mosaic", "app/public/icons"],
    },
    synced: new Date().toISOString().slice(0, 10),
  },
  color: {
    themes: [{ id: "light", name: "Light" }, { id: "dark", name: "Dark" }],
    tokens: colorNames.map((name) => {
      const value = { light: colorValue(light[name]) };
      // `var(--orange, …)` is the brand orange by name: kept as an alias.
      if (/^var\(--orange\b/.test(light[name])) value.light = "{orange}";
      if (dark[name] && dark[name] !== light[name]) value.dark = colorValue(dark[name]);
      return { name, value, usage: USAGE[name] };
    }),
  },
  type: {
    fonts: [],
    families: {
      "dm-sans": '"DM Sans", ui-sans-serif, system-ui, sans-serif',
      "jetbrains-mono": '"JetBrains Mono", ui-monospace, monospace',
      serif: 'Georgia, "Times New Roman", Times, serif',
    },
    groups: [
      {
        name: "Display",
        family: "serif",
        styles: [
          { name: "hero", fontSize: "36px", lineHeight: 1.25, fontWeight: 400, letterSpacing: "-0.025em", sample: "Good morning, Maya", usage: "The home screen's greeting (PageHeader size=\"hero\") and the signed-out front door. Nowhere else in the app." },
          { name: "wordmark", fontSize: "20px", lineHeight: 1.2, fontWeight: 700, sample: "duct", usage: "The wordmark, lowercase, with the orange dot." },
        ],
      },
      {
        name: "Text",
        family: "dm-sans",
        styles: [
          { name: "title", fontSize: "24px", lineHeight: 1.25, fontWeight: 600, letterSpacing: "-0.025em", sample: "1 thing needs you.", usage: "The page title, drawn only by PageHeader: one per screen, the same size and left edge on every screen." },
          { name: "body", fontSize: "14px", lineHeight: "20px", fontWeight: 400, sample: "Duct checks a number before it trusts it.", usage: "Everything that is read: rows, cards, forms, chat." },
          { name: "heading", fontSize: "14px", lineHeight: "20px", fontWeight: 600, sample: "Still open", usage: "Section and card headings: body size, heavier. Hierarchy comes from weight and colour, not size." },
          { name: "meta", fontSize: "12px", lineHeight: "16px", fontWeight: 400, sample: "2 days ago · Google Ads", usage: "Metadata, captions, badges, status lines in dense rows." },
          { name: "micro", fontSize: "11px", lineHeight: "16px", fontWeight: 500, sample: "NEW", usage: "Decoration only (a kbd hint, a counter in a chip). Nothing a person must read or act on goes below meta." },
        ],
      },
      {
        name: "Figures and code",
        family: "jetbrains-mono",
        styles: [
          { name: "numeric", fontSize: "14px", lineHeight: "20px", fontWeight: 400, sample: "€18,400  812  +14%", usage: "The .numeric class: table columns and live counters that must line up. DM Sans has no tabular figures. Not for a number inside a sentence." },
          { name: "code", fontSize: "12px", lineHeight: "18px", fontWeight: 400, sample: "npx skills add 5hirish/duct", usage: "Code blocks, setup lines, ids." },
        ],
      },
    ],
  },
  spacing: {
    note: "An 8px grid with one meaning per step. Space between groups always exceeds space within them.",
    tokens: [
      { name: "space-1", value: "4px", usage: "Inside dense meta rows (gap-1, gap-1.5)." },
      { name: "space-2", value: "8px", usage: "Icon to label, label to its field, button to button (gap-2)." },
      { name: "space-3", value: "12px", usage: "Card to card in a grid (gap-3); inside a small card." },
      { name: "space-4", value: "16px", usage: "Inside a card between its groups, section heading to content, the page gutter on a phone (gap-4, p-4)." },
      { name: "space-6", value: "24px", usage: "Card padding (p-6)." },
      { name: "space-8", value: "32px", usage: "The page gutter on a desktop and the page's top padding." },
      { name: "space-10", value: "40px", usage: "Section to section, header to content: Page's rhythm." },
    ],
  },
  radius: {
    note: "Concentric: controls 8, cards 11, dialogs 14. A field is a rectangle; capsules are for badges and chips only.",
    tokens: [
      { name: "radius", value: "8px", usage: "The base every radius is cut from (--radius, 0.5rem)." },
      { name: "radius-sm", value: "4.8px", usage: "Checkboxes and inner marks (rounded-sm)." },
      { name: "radius-md", value: "6.4px", usage: "Small controls inside a control (rounded-md)." },
      { name: "radius-lg", value: "8px", usage: "Buttons, inputs, selects, textareas (rounded-lg)." },
      { name: "radius-xl", value: "11.2px", usage: "Cards and panels (rounded-xl)." },
      { name: "radius-2xl", value: "14.4px", usage: "Dialogs and sheets (rounded-2xl)." },
      { name: "radius-full", value: "9999px", usage: "Badges, chips and round icon buttons only." },
    ],
  },
  shadow: {
    note: "Quiet. Depth comes from borders and a background shift, not glow.",
    tokens: [
      { name: "shadow-xs", value: "0 1px 2px 0 rgba(0, 0, 0, 0.05)", usage: "The primary button and a checkbox. Nothing on cards." },
      { name: "shadow-overlay", value: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)", usage: "Menus, popovers and dialogs (shadow-lg): the only surfaces that float." },
    ],
  },
};
writeFileSync(join(DS, "tokens.json"), JSON.stringify(tokens, null, 2));
console.log(`tokens: ${tokens.color.tokens.length} colours × 2 themes, ${tokens.type.groups.reduce((a, g) => a + g.styles.length, 0)} type styles`);

// --- bundle.css -----------------------------------------------------------------------
// One source for every value: a token tokens.json declares is taken out of the
// :root and .dark blocks here, so a value changed on the system's page wins.
const captured = join(OUT, "boards", "duct-app.css");
if (!existsSync(captured)) throw new Error(`no ${captured}: run capture.mjs first`);
const owned = new Set(colorNames);
const css = readFileSync(captured, "utf8")
  .replace(/^\/\*[\s\S]*?\*\/\n/, "")
  // The boards carry the app's font files; the system loads the same families
  // from Google Fonts (FONTS) and has no img/ folder to point a face at.
  .replace(/@font-face\s*\{[^}]*url\(["']?img\/[^}]*\}/g, "")
  // Nested too: the compiler repeats each block inside @supports (color: lab())
  // with lab() values, and those would win over the system's tokens.css.
  .replace(/(^|\n)([ \t]*)(:root|\.dark)\s*\{([^{}]*)\}/g, (m, lead, indent, sel, body) => {
    const kept = body.split(";").filter((d) => {
      const name = /^\s*--([A-Za-z0-9-]+)\s*:/.exec(d)?.[1];
      return !(name && owned.has(name));
    }).join(";");
    return `${lead}${indent}${sel} {${kept}}`;
  });
writeFileSync(join(DS, "components", "bundle.css"),
  `@import url("${FONTS}");\n/* Duct app stylesheet, captured by design/tools/capture.mjs; the token values live in tokens.json. */\n` +
  // The app hangs DM Sans and JetBrains Mono on next/font's class; the system's
  // families take those two variables instead (tokens.json type.families).
  `${css}\n`);

// --- assets ----------------------------------------------------------------------------
const ASSET_GROUPS = {
  Logos: [join(REPO, "app/src/app/icon.svg"), join(REPO, "app/src/app/apple-icon.svg")],
  Mosaic: readdirSync(join(REPO, "app/public/art/mosaic")).filter((f) => f.endsWith(".webp")).map((f) => join(REPO, "app/public/art/mosaic", f)),
  // icon.svg in there is Duct's own mark again, already under Logos.
  Connectors: readdirSync(join(REPO, "app/public/icons")).filter((f) => f.endsWith(".svg") && f !== "icon.svg").map((f) => join(REPO, "app/public/icons", f)),
};
const GROUP_README = {
  Logos: "# Logos\n\nThe app icon: a navy (`navy`) rounded square with a white Georgia \"d\" and the orange (`orange`) dot. `icon.svg` for every size, `apple-icon.svg` for the home screen. Fixed inks: never recolour them. The wordmark has no file: it is \"duct\" set lowercase in the `serif` family (`wordmark` style) followed by a dot in `orange`.\n",
  Mosaic: "# Mosaic\n\nThe threshold panels, the app's one illustration system: square Roman mosaics, generated from masters in the repository, never hand-edited. One per screen, where someone arrives, never below 240px, always `aria-hidden` with the real heading as text beside it. `fons` front door · `salve` first run · `nihil` empty · `otium` all caught up · `fractum` something broke · `cdiv` 404 · `cave-canem` 403.\n",
  Connectors: "# Connectors\n\nThe vendors' own marks, as the Toolbox, the desk and the activity rows show them: a mark on a tile tells where an item came from before it is read. Full colour as the vendor draws it; never recoloured, never a substitute for the vendor's name in text. Trademarks of their owners.\n",
  Images: "# Images\n\nPictures the component previews show.\n",
};
const assets = [];
for (const [group, files] of Object.entries(ASSET_GROUPS)) {
  mkdirSync(join(DS, "assets", group), { recursive: true });
  for (const f of files) {
    copyFileSync(f, join(DS, "assets", group, basename(f)));
    writeFileSync(join(DS, "assets", group, "README.md"), GROUP_README[group]);
    assets.push({ group, name: basename(f), path: `assets/${group}/${basename(f)}`, size: statSync(f).size, type: MIME[extname(f)] });
  }
}
writeFileSync(join(OUT, "design-system", "assets.json"), JSON.stringify(assets, null, 1));
console.log(`assets: ${assets.length} files in ${Object.keys(ASSET_GROUPS).length} groups`);

// --- components ----------------------------------------------------------------------------
const { COMPONENTS } = await import("./components.mjs");
const canon = parseCanon(readFileSync(join(REPO, "app/DESIGN.md"), "utf8"));
const req = createRequire(import.meta.url);
const { chromium } = req(req.resolve("playwright", { paths: [process.env.PLAYWRIGHT_FROM || join(REPO, "site")] }));
const browser = await chromium.launch({ headless: true });
const images = new Set();
try {
  const context = await browser.newContext({ viewport: { width: 760, height: 900 }, colorScheme: "light" });
  await context.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.startsWith("/ingest")) return route.abort();
    return ["localhost", "127.0.0.1"].includes(u.hostname) ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  for (const c of COMPONENTS) {
    mkdirSync(join(DS, "components", c.name), { recursive: true });
    const rows = canon.filter((r) => c.canon?.includes(r.job));
    writeFileSync(join(DS, "components", c.name, "README.md"), readme(c, rows));
    if (!c.scene) continue;
    await page.goto(`${APP}/preview/frame?scene=${c.scene}&surface=inline&theme=light`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => window.__preview?.ready === true, null, { timeout: 30000 }).catch(() => {});
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    const snap = await page.evaluate(specimen);
    snap.images.forEach((src) => images.add(src));
    const html = snap.html.replace(/__IMG\[(.+?)\]__/g, (_, src) => `__ASSET[${basename(new URL(src).pathname)}]__`);
    const height = Math.min(Math.max(Math.ceil(snap.height) + 48, 80), 1200);
    writeFileSync(join(DS, "components", c.name, "preview.html"),
      `<!-- @dsCard group="${c.group}" height=${height} subtitle="${c.subtitle || ""}" -->
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>${c.name} — preview</title></head>
<body class="bg-background font-sans text-foreground antialiased" style="margin: 0">
<div style="padding: 24px"><div style="position: relative">
${snap.html.includes("__IMG[") ? html : snap.html}
</div></div>
</body>
</html>
`);
    console.log(`✓ ${c.name} (${c.scene}) ${Math.round(snap.html.length / 1024)} KB`);
  }
} finally {
  await browser.close();
}
// Images a preview shows that are not already an asset: copied into Images.
for (const src of images) {
  const name = basename(new URL(src).pathname);
  if (assets.some((a) => a.name === name)) continue;
  mkdirSync(join(DS, "assets", "Images"), { recursive: true });
  const res = await fetch(src).catch(() => null);
  if (!res?.ok) continue;
  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(join(DS, "assets", "Images", name), buf);
  assets.push({ group: "Images", name, path: `assets/Images/${name}`, size: buf.length, type: MIME[extname(name)] });
}
writeFileSync(join(OUT, "design-system", "assets.json"), JSON.stringify(assets, null, 1));

// --- helpers ---------------------------------------------------------------------------------

// Runs in the frame: the specimen as static markup. Radix portals (an open
// menu, popover or tooltip) live at the end of <body>; each is moved into the
// specimen at the place it was drawn, so the preview shows it open.
function specimen() {
  const host = document.querySelector("[data-preview-content]");
  const box = host.getBoundingClientRect();
  const clone = host.cloneNode(true);
  const portals = [...document.body.children].filter((el) =>
    el !== host && !el.contains(host) && el.matches("[data-radix-popper-content-wrapper], [role='dialog'], [role='alertdialog'], [data-slot$='-portal'], div[data-state='open']"));
  let bottom = host.scrollHeight;
  for (const p of portals) {
    const r = p.getBoundingClientRect();
    const c = p.cloneNode(true);
    c.setAttribute("style", `${c.getAttribute("style") || ""}; position: absolute; left: ${Math.round(r.left - box.left)}px; top: ${Math.round(r.top - box.top)}px; transform: none; width: ${Math.round(r.width)}px`);
    clone.appendChild(c);
    bottom = Math.max(bottom, r.bottom - box.top);
  }
  clone.querySelectorAll("script, style, link, noscript, template").forEach((n) => n.remove());
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_COMMENT);
  const dead = [];
  while (walker.nextNode()) dead.push(walker.currentNode);
  dead.forEach((n) => n.remove());
  const images = [];
  clone.querySelectorAll("img").forEach((img) => {
    let url = new URL(img.getAttribute("src"), location.href);
    if (url.pathname === "/_next/image" && url.searchParams.get("url")) url = new URL(url.searchParams.get("url"), location.href);
    if (url.protocol === "data:") return;
    images.push(url.href);
    img.setAttribute("src", `__IMG[${url.href}]__`);
    for (const a of ["srcset", "sizes", "loading", "decoding", "fetchpriority", "data-nimg"]) img.removeAttribute(a);
  });
  clone.querySelectorAll("*").forEach((el) => {
    for (const a of [...el.attributes]) if (/^on/i.test(a.name)) el.removeAttribute(a.name);
  });
  clone.querySelectorAll("a[href]").forEach((a) => a.setAttribute("href", "#"));
  return { html: clone.innerHTML.trim(), height: bottom, images };
}

function readme(c, rows) {
  const lines = [`# ${c.name}`, "", c.summary, ""];
  for (const r of rows) {
    const end = (t) => (/[.!?)`]$/.test(t) ? t : `${t}.`);
    lines.push(`**${r.job}.** ${end(r.canonical)}`, "");
    if (r.retire && r.retire !== "—") lines.push(`*Retire on touch:* ${end(r.retire)}`, "");
  }
  if (c.notes) lines.push(c.notes, "");
  lines.push(`**In the code:** ${c.source.map((s) => `\`${s}\``).join(", ")}.${c.scene ? ` Live, every variant: \`/preview\` → \`${c.scene}\`.` : ""}`, "");
  if (c.scene) lines.push("*The preview is a static rendition: the component's own markup, captured from the app's `/preview`, styled by the app's stylesheet.*", "");
  return lines.join("\n");
}

function parseCanon(markdown) {
  const SECTION = "## Canon — one pattern per job";
  const start = markdown.indexOf(SECTION);
  if (start === -1) return [];
  const rest = markdown.slice(start + SECTION.length);
  const end = rest.indexOf("\n---");
  const rows = [];
  for (const line of (end === -1 ? rest : rest.slice(0, end)).split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|") || /^\|[\s|:-]+\|$/.test(t)) continue;
    const [job, canonical, retire] = t.slice(1, -1).split("|").map((s) => s.trim());
    if (job && job !== "Job") rows.push({ job, canonical, retire });
  }
  return rows;
}

function pointImagesAtUploads(blobs) {
  for (const name of readdirSync(join(DS, "components"))) {
    const f = join(DS, "components", name, "preview.html");
    if (!existsSync(f)) continue;
    const html = readFileSync(f, "utf8").replace(/__ASSET\[(.+?)\]__/g, (m, file) => (blobs[file] ? blobs[file] : m));
    writeFileSync(f, html);
  }
  console.log("previews point at the uploaded images");
}

function read(file) {
  return readFileSync(join(STYLES, file), "utf8");
}

// `--name: value;` pairs of the first block whose selector is exactly `sel`.
function declarations(css, sel) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const re = new RegExp(`(^|\\n)\\s*${sel.replace(".", "\\.")}\\s*\\{([^}]*)\\}`);
  const body = re.exec(clean)?.[2] || "";
  const out = {};
  for (const m of body.matchAll(/--([A-Za-z0-9-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

// onboarding.css carries its dark stones in a `.dark …` block of its own.
function darkOf(css) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const m = /\n\s*\.dark[^{]*\{([^}]*)\}/.exec(clean);
  const out = {};
  for (const d of (m?.[1] || "").matchAll(/--([A-Za-z0-9-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim();
  return out;
}

function isColor(v) {
  return /^(#|oklch\(|rgb|hsl)/.test(v) || /^var\(--orange/.test(v);
}

// tokens.json takes literal colours only: a var() fallback keeps its fallback.
function colorValue(v) {
  const fallback = /^var\(--[a-z-]+,\s*(.+)\)$/.exec(v);
  return (fallback ? fallback[1] : v).toLowerCase();
}

function gitHead() {
  try {
    const head = readFileSync(join(REPO, ".git/HEAD"), "utf8").trim();
    const ref = head.startsWith("ref: ") ? head.slice(5) : null;
    if (!ref) return head.slice(0, 7);
    const loose = join(REPO, ".git", ref);
    return existsSync(loose) ? readFileSync(loose, "utf8").trim().slice(0, 7) : null;
  } catch {
    return null;
  }
}

