#!/usr/bin/env node
// Lays a capture out as the Duct canvas: the folder the canvas is published
// from. Reads what capture.mjs wrote to OUT and writes OUT/canvas/project/:
//
//   canvas.json                 pages, boards, notes; merged into the live one
//   <id>.dc.html                "Core": the editable boards, a row per group
//   Built-<id>.dc.html          "As built": each screen at every size and theme
//   asbuilt/*.webp, img/*, duct-app.css   what those boards show and link
//
// The canvas serves duct-app.css but none of the pictures or fonts: assets.mjs
// runs next and moves them onto the canvas's asset store.
//
//   node design/tools/layout.mjs [--from live-canvas.json] [--ds <design system url> [--ds-version <v>]]
//
// --from keeps everything a person added on the canvas (notes, their own
// boards, moved frames are re-laid, though): only the boards and notes this
// tool owns are replaced. --ds records the design system the canvas uses, so
// its Theme menu reads Duct's tokens; --ds-version is the version its publish
// returned, which the canvas shows as the one its tokens were copied from.
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design"));
const PROJECT = join(OUT, "canvas", "project");
const args = process.argv.slice(2);
const opt = (k) => (args.includes(k) ? args[args.indexOf(k) + 1] : null);
const { SCREENS, VARIANTS } = await import("./screens.mjs");
const manifest = JSON.parse(readFileSync(join(OUT, "screens.json"), "utf8"));
const day = new Date(manifest.capturedAt || Date.now()).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const commit = manifest.commit ? ` (${manifest.commit})` : "";

rmSync(PROJECT, { recursive: true, force: true });
mkdirSync(join(PROJECT, "asbuilt"), { recursive: true });
mkdirSync(join(PROJECT, "img"), { recursive: true });

// --- canvas geometry (canvas px) -------------------------------------------------
const GAP_X = 80; // between frames in a row
const GAP_Y = 120; // between rows
const TITLE_ROOM = 300; // a row's title1 note sits this far above it
const BUILT_PER_ROW = 3;

const boards = {};
const order = [];
const notes = {};
const owned = new Set(); // board paths this tool writes, to replace on --from

// --- Core: the editable boards -------------------------------------------------------
const groups = [...new Set(SCREENS.map((s) => s.group))];
let y = 0;
let coreRight = 0;
for (const group of groups) {
  const row = SCREENS.filter((s) => s.group === group && manifest.screens[s.id]?.board);
  if (!row.length) continue;
  let x = 0;
  let tallest = 0;
  for (const s of row) {
    const b = manifest.screens[s.id].board;
    const path = `${s.id}.dc.html`;
    copyFileSync(join(OUT, "boards", path), join(PROJECT, path));
    boards[path] = {
      x, y, w: b.width, h: b.height,
      title: `${s.title}  (${s.route})`,
      page: "core", expand: "fill", is_interactive: true,
    };
    order.push(path);
    owned.add(path);
    x += b.width + GAP_X;
    tallest = Math.max(tallest, b.height);
  }
  notes[noteId("core", group)] = { x: 0, y: y - TITLE_ROOM, text: group, kind: "title1", maxW: x - GAP_X, page: "core" };
  coreRight = Math.max(coreRight, x);
  y += tallest + GAP_Y + TITLE_ROOM;
}
notes.coreWhat = {
  x: coreRight, y: 0, w: 520, fill: "blue", page: "core",
  text:
    "Editable boards: each is the app's own markup at 1440, light, captured from main" + commit + " on " + day +
    ", linking the app's own stylesheet, so a board reads as the same screen down to the pixel.\n\n" +
    "Press Play to click through: the sidebar moves between boards.\n\n" +
    "Design the next version here: duplicate a board beside the original and change it. Screens without a board, and every " +
    "other size and the dark theme, are on 'As built'.\n\nRefresh: design/README.md in the repo.",
};

// --- As built: pictures of every screen ------------------------------------------------
const shown = (v) => (v.width >= 640 ? 0.5 : 1); // desktop at half size (the file is full size), phone 1:1
const PHONE_MAX = 2400;
let by = 0;
let builtRight = 0;
let count = 0;
for (const group of groups) {
  const list = SCREENS.filter((s) => s.group === group && Object.keys(manifest.screens[s.id]?.shots || {}).length);
  if (!list.length) continue;
  notes[noteId("built", group)] = { x: 0, y: by - TITLE_ROOM, text: `As built · ${group}`, kind: "title1", page: "built" };
  let rowWidth = 0;
  for (let i = 0; i < list.length; i += BUILT_PER_ROW) {
    let x = 0;
    let tallest = 0;
    for (const s of list.slice(i, i + BUILT_PER_ROW)) {
      const { html, w, h } = builtBoard(s, manifest.screens[s.id]);
      const path = `Built-${s.id}.dc.html`;
      writeFileSync(join(PROJECT, path), html);
      boards[path] = { x, y: by, w, h, title: `As built · ${s.title}`, page: "built" };
      order.push(path);
      owned.add(path);
      x += w + GAP_X;
      tallest = Math.max(tallest, h);
      count += 1;
    }
    rowWidth = Math.max(rowWidth, x - GAP_X);
    by += tallest + GAP_Y;
  }
  notes[noteId("built", group)].maxW = rowWidth;
  builtRight = Math.max(builtRight, rowWidth + GAP_X);
  by += TITLE_ROOM;
}
notes.builtHow = {
  x: builtRight, y: 0, w: 520, fill: "blue", page: "built",
  text:
    `Ground truth: ${count} screens rendered from the real app on main${commit}, ${day}, against the README's story ` +
    "(Solo, a budgeting app, the week of 8–14 Sep 2026) with no live backend.\n\n" +
    VARIANTS.map((v) => `· ${v.label}`).join("\n") +
    "\n\nPictures, not boards. To change a screen, start from its board on 'Core', or capture one for it first.",
};

for (const f of readdirSync(join(OUT, "asbuilt"))) if (f.endsWith(".webp")) copyFileSync(join(OUT, "asbuilt", f), join(PROJECT, "asbuilt", f));
for (const f of readdirSync(join(OUT, "boards/img"))) copyFileSync(join(OUT, "boards/img", f), join(PROJECT, "img", f));
copyFileSync(join(OUT, "boards", "duct-app.css"), join(PROJECT, "duct-app.css"));

// --- canvas.json, merged into the live one ------------------------------------------------
const from = opt("--from");
const live = from && existsSync(from) ? JSON.parse(readFileSync(from, "utf8")) : null;
const canvas = live || {
  v: 3,
  createdOnFiles: { v: 1, at: new Date().toISOString().replace(/\.\d+Z$/, "Z") },
  title: "Duct Prototype",
  notes: {},
  designSystems: [],
};
canvas.launch = { view: "canvas", page: "core" };
const pages = [
  { id: "core", name: "Core · editable boards" },
  { id: "built", name: "As built · every screen" },
];
canvas.pages = [...pages, ...(canvas.pages || []).filter((p) => !pages.some((q) => q.id === p.id))];
const keptBoards = Object.fromEntries(Object.entries(canvas.boards || {}).filter(([p, b]) => !isOwned(p, b)));
canvas.boards = { ...boards, ...keptBoards };
canvas.order = [...order, ...(canvas.order || []).filter((p) => keptBoards[p])];
const keptNotes = Object.fromEntries(Object.entries(canvas.notes || {}).filter(([id]) => !/^(core|built)[A-Z]|^core-|^built-/.test(id)));
canvas.notes = { ...keptNotes, ...notes };
const ds = opt("--ds");
if (ds) {
  canvas.designSystems = (canvas.designSystems || []).filter((d) => d.namespace !== "duct");
  canvas.designSystems.push({ title: "Duct Design System", namespace: "duct", artifact: ds, version: opt("--ds-version"), copiedAt: new Date().toISOString() });
}
writeFileSync(join(PROJECT, "canvas.json"), JSON.stringify(canvas, null, 1));
console.log(`canvas: ${order.length} boards (${Object.keys(boards).length - count} editable, ${count} as built) → ${PROJECT}`);

// --- helpers --------------------------------------------------------------------------

function isOwned(path, b) {
  if (owned.has(path)) return true;
  // A screen dropped from screens.mjs leaves its old board behind otherwise.
  return /^Built-/.test(path) || (b?.page === "core" && SCREENS.some((s) => `${s.id}.dc.html` === path));
}

function noteId(page, group) {
  return `${page}-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function builtBoard(screen, entry) {
  const PAD = 48;
  const GAP = 40;
  const figures = VARIANTS.filter((v) => entry.shots[v.id]).map((v) => {
    const shot = entry.shots[v.id];
    const k = shown(v);
    const w = Math.round(shot.width * k);
    const h = Math.min(Math.round(shot.height * k), PHONE_MAX);
    return { v, shot, w, h };
  });
  const width = PAD * 2 + figures.reduce((a, f) => a + f.w, 0) + GAP * (figures.length - 1);
  const tallest = Math.max(...figures.map((f) => f.h));
  const height = PAD * 2 + 110 + tallest + 64;
  const route = screen.route;
  const fig = (f) => `<figure style="margin: 0; width: ${f.w}px; display: flex; flex-direction: column; gap: 10px">
<img src="asbuilt/${f.shot.file}" alt="As built: ${esc(screen.title)}, ${esc(f.v.label)}" style="width: ${f.w}px; height: ${f.h}px; display: block; object-fit: cover; object-position: top; border-radius: ${f.v.width < 640 ? 28 : 10}px; box-shadow: 0 0 0 1px rgba(40,30,20,0.14), 0 12px 32px rgba(40,30,20,0.10)">
<figcaption style="font-size: 17px; line-height: 1.3; color: #3b342c"><span style="font-weight: 600">${esc(f.v.label)}</span>${f.shot.cut ? `<br><span style="font-size: 13px; color: #6f665c">cut at ${f.shot.height}px; the page runs on</span>` : ""}</figcaption>
</figure>`;
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>As built: ${esc(screen.title)}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400..700&amp;display=swap" rel="stylesheet">
<style>
body{margin:0}
</style>
</helmet>
<div style="width: ${width}px; height: ${height}px; box-sizing: border-box; padding: ${PAD}px; background: #f6f3ee; font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif; color: #29241f; display: flex; flex-direction: column; gap: 0">
<header style="height: 110px; display: flex; flex-direction: column; gap: 6px">
<h1 style="margin: 0; font-size: 44px; font-weight: 700; letter-spacing: -0.02em">${esc(screen.title)}</h1>
<p style="margin: 0; font-size: 18px; color: #6f665c">As built · ${esc(route)} · rendered from the app on main${esc(commit)}, ${esc(day)}</p>
</header>
<div style="display: flex; flex-direction: row; gap: ${GAP}px; align-items: flex-start">
${figures.map(fig).join("\n")}
</div>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":${width},"height":${height}}}'>
class Component extends DCLogic {
renderVals() { return {}; }
}
</script>
</body>
</html>
`;
  return { html, w: width, h: height };
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}
