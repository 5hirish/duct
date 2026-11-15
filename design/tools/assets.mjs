#!/usr/bin/env node
// Moves the canvas's pictures and fonts onto its asset store. The canvas
// serves a board's .css, .js and .json beside it and nothing else: an image
// or a font named by its path never loads (the runtime logs "not serving N
// file(s)"), and on 2026-11-15 every As built picture, logo, framed document
// and font face was a broken image for exactly that reason. A board names
// each one by the /_blob/<id> url its upload returned instead.
//
// Runs after layout.mjs, on OUT/canvas/project/:
//
//   node design/tools/assets.mjs plan [--map <assets.json>]   stage what needs uploading, 25 to a batch
//   node design/tools/assets.mjs record <upload result>       add one upload's urls to the map
//   node design/tools/assets.mjs apply                         point boards and stylesheet at them, drop the files
//
// Between plan and apply, Claude uploads each batch with the Artifact tool
// (publish, url, asset: true, file_paths) and saves its result to a file for
// `record`. --map is the canvas's own project/assets.json from the last
// refresh: a file whose bytes have not changed keeps its url, so a logo or a
// font is uploaded once, not once per refresh.
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join, relative, resolve } from "node:path";

const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design"));
const CANVAS = join(OUT, "canvas");
const PROJECT = join(CANVAS, "project");
const STAGE = join(CANVAS, "upload");
const MAP_FILE = join(CANVAS, "assets.json");
const BATCH = 25; // the most files one asset upload takes
const SERVED = /\.(dc\.html|css|m?js|jsx|tsx|json)$/i; // what the canvas serves from project/
const BLOB = /^\/_blob\/[0-9a-f]{32}$/;

const [cmd, ...rest] = process.argv.slice(2);
const opt = (k) => (rest.includes(k) ? rest[rest.indexOf(k) + 1] : null);
const commands = { plan, record, apply };
if (!commands[cmd]) {
  console.error("usage: assets.mjs plan [--map <assets.json>] | record <upload result> | apply");
  process.exit(2);
}
commands[cmd]();

// --- plan: stage every file the store does not hold yet ----------------------------
function plan() {
  const map = loadMap(MAP_FILE);
  const previous = opt("--map");
  if (previous) Object.assign(map, loadMap(previous));
  rmSync(STAGE, { recursive: true, force: true });
  mkdirSync(STAGE, { recursive: true });
  const pending = [];
  for (const file of unserved()) {
    const sha = hashOf(file);
    if (map[sha]) continue;
    // Staged as <sha12>-<name>.<ext>: the hash prefix is how `record` finds
    // the file in an upload's result, and the store wants an extension to
    // know the type (Google's favicon arrives named just "favicons").
    const name = `${sha.slice(0, 12)}-${relative(PROJECT, file).replace(/[/\\]/g, "-")}`;
    const staged = join(STAGE, extname(name) ? name : `${name}.${sniff(file)}`);
    copyFileSync(file, staged);
    pending.push(staged);
  }
  writeMap(MAP_FILE, map);
  const batches = [];
  for (let i = 0; i < pending.length; i += BATCH) batches.push(pending.slice(i, i + BATCH));
  writeFileSync(join(STAGE, "batches.json"), JSON.stringify(batches, null, 1));
  console.log(`${unserved().length} pictures and fonts, ${pending.length} to upload in ${batches.length} batch(es) → ${join(STAGE, "batches.json")}`);
}

// --- record: read an upload's result back into the map --------------------------------
function record() {
  const file = rest[0];
  if (!file || !existsSync(file)) {
    console.error("record needs the saved text of an asset upload's result");
    process.exit(2);
  }
  const staged = Object.fromEntries(readdirSync(STAGE).filter((f) => /^[0-9a-f]{12}-/.test(f)).map((f) => [f.slice(0, 12), f]));
  const map = loadMap(MAP_FILE);
  let added = 0;
  // One line per file: its staged name and the url the store gave it. A
  // session transcript (.jsonl) holds the same result with its newlines
  // escaped, so it can be read directly instead of retyping 200 ids.
  // The canvas's asset listing (list, scope "assets") works too: each of its
  // lines carries the stored file's own sha256. An SVG is sanitised on upload,
  // so its stored hash differs from ours and it is simply uploaded again.
  for (const line of readFileSync(file, "utf8").replace(/\\n/g, "\n").split(/\r?\n/)) {
    const id = /\/_blob\/([0-9a-f]{32})/.exec(line)?.[1];
    if (!id) continue;
    const sha = /sha256 ([0-9a-f]{64})/.exec(line)?.[1];
    const key = /(?:^|[\s/"'(])([0-9a-f]{12})-/.exec(line)?.[1];
    if (sha) map[sha] = `/_blob/${id}`;
    else if (key && staged[key]) map[hashOf(join(STAGE, staged[key]))] = `/_blob/${id}`;
    else continue;
    added += 1;
  }
  writeMap(MAP_FILE, map);
  console.log(`recorded ${added} url(s); ${Object.keys(map).length} in the map`);
}

// --- apply: rewrite every reference, then prove none is left ---------------------------
function apply() {
  const map = loadMap(MAP_FILE);
  const urlOf = new Map();
  const missing = [];
  for (const file of unserved()) {
    const url = map[hashOf(file)];
    if (url) urlOf.set(relative(PROJECT, file).split("\\").join("/"), url);
    else missing.push(relative(PROJECT, file));
  }
  if (missing.length) {
    console.error(`${missing.length} file(s) have no uploaded url; run plan, upload, record:\n  ${missing.join("\n  ")}`);
    process.exit(1);
  }

  let rewritten = 0;
  const leftovers = [];
  for (const file of textFiles()) {
    const before = readFileSync(file, "utf8");
    const after = before.replace(/(["'(])(?:\.\/)?((?:img|asbuilt)\/[^"')\s]+)/g, (m, q, path) => {
      const url = urlOf.get(path);
      if (!url) return m;
      rewritten += 1;
      return q + url;
    });
    if (after !== before) writeFileSync(file, after);
    leftovers.push(...references(after).filter((ref) => !loads(ref)).map((ref) => `${relative(PROJECT, file)}: ${ref}`));
  }
  if (leftovers.length) {
    console.error(`${leftovers.length} reference(s) the canvas cannot load:\n  ${[...new Set(leftovers)].slice(0, 40).join("\n  ")}`);
    process.exit(1);
  }

  const removed = [...urlOf.keys()].map((p) => `project/${p}`);
  for (const dir of ["img", "asbuilt"]) rmSync(join(PROJECT, dir), { recursive: true, force: true });
  // The map ships with the canvas, so the next refresh can reuse its urls.
  writeMap(join(PROJECT, "assets.json"), map);
  writeFileSync(join(CANVAS, "removed.json"), JSON.stringify(removed, null, 1));
  console.log(`${rewritten} reference(s) now point at the asset store; ${removed.length} file(s) left the folder (publish them as null: ${join(CANVAS, "removed.json")})`);
}

// --- helpers --------------------------------------------------------------------------

function walk(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

// project/ds/ is the design system's own copy: its install writes it, not us.
function unserved() {
  return walk(PROJECT).filter((p) => !SERVED.test(p) && !relative(PROJECT, p).startsWith("ds"));
}

function textFiles() {
  return walk(PROJECT).filter((p) => /\.(dc\.html|css)$/.test(p) && !relative(PROJECT, p).startsWith("ds"));
}

// Every src, href and url() a board or stylesheet names.
function references(text) {
  const refs = [];
  for (const m of text.matchAll(/\s(?:src|href)="([^"]*)"/g)) refs.push(m[1]);
  for (const m of text.matchAll(/url\((['"]?)([^'")]+)\1\)/g)) refs.push(m[2]);
  return refs;
}

function loads(ref) {
  if (!ref || ref.startsWith("#") || ref.startsWith("data:") || BLOB.test(ref)) return true;
  if (/^[a-z][a-z0-9+.-]*:/i.test(ref)) return true; // a link out (https:, the desktop app's own scheme), not a file
  if (ref === "./support.js") return true;
  const path = ref.replace(/^\.\//, "").split(/[?#]/)[0];
  return SERVED.test(path) && existsSync(join(PROJECT, path));
}

function hashOf(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function sniff(file) {
  const b = readFileSync(file).subarray(0, 12);
  if (b[0] === 0x89 && b[1] === 0x50) return "png";
  if (b[0] === 0xff && b[1] === 0xd8) return "jpg";
  if (b.toString("ascii", 0, 3) === "GIF") return "gif";
  if (b.toString("ascii", 8, 12) === "WEBP") return "webp";
  if (b.toString("ascii", 0, 4) === "wOF2") return "woff2";
  if (b.toString("ascii", 0, 4) === "wOFF") return "woff";
  if (/<svg|<\?xml/.test(readFileSync(file, "utf8").slice(0, 200))) return "svg";
  return "bin";
}

function loadMap(file) {
  if (!existsSync(file)) return {};
  const raw = JSON.parse(readFileSync(file, "utf8"));
  // Only well-formed pairs: a map read from the live canvas is other people's data.
  return Object.fromEntries(Object.entries(raw).filter(([k, v]) => /^[0-9a-f]{64}$/.test(k) && BLOB.test(v)));
}

function writeMap(file, map) {
  writeFileSync(file, JSON.stringify(map, null, 1));
}
