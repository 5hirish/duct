#!/usr/bin/env node
// Responsive variants of the product shots: `node scripts/build_media_variants.mjs`.
//
// scripts/shots captures at 2x, so a session shot is 3072px wide and ~250 KB.
// Every page served that file to every screen: a phone downloaded it to show
// it 340px wide. Each shot wider than a variant width gets a `-768` and a
// `-1536` copy here, and the pages list them in `srcset` so the browser picks
// by its own width and density (phone 2x → 768, 1x desktop → 1536, 2x
// desktop → the original). Run it after a reshoot; `--check` is what CI runs
// and fails when a variant is missing or older than its source.
import { createRequire } from "node:module";
import { readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("..", import.meta.url)));
const req = createRequire(import.meta.url);
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));
const MEDIA = join(REPO, "site/assets/media");
export const WIDTHS = [768, 1536];
// The poster belongs to the film, and the full-length audit report is only
// ever opened in the lightbox at its own size.
const SKIP = new Set(["demo-poster.webp", "audit-report-full.webp"]);
const VARIANT = /-(768|1536)\.webp$/;

export function sources() {
  return readdirSync(MEDIA).filter((f) => f.endsWith(".webp") && !VARIANT.test(f) && !SKIP.has(f)).sort();
}

export function variantsOf(name, width) {
  return WIDTHS.filter((w) => w < width).map((w) => ({ w, file: name.replace(/\.webp$/, `-${w}.webp`) }));
}

const check = process.argv.includes("--check");
let stale = [], written = 0;
for (const name of sources()) {
  const src = join(MEDIA, name);
  const { width } = await sharp(src).metadata();
  for (const { w, file } of variantsOf(name, width)) {
    const out = join(MEDIA, file);
    const fresh = existsSync(out) && statSync(out).mtimeMs >= statSync(src).mtimeMs;
    if (check) { if (!fresh) stale.push(file); continue; }
    if (fresh) continue;
    await sharp(src).resize({ width: w }).webp({ quality: 82, effort: 6 }).toFile(out);
    written++;
  }
}
if (check) {
  if (stale.length) { console.error(`stale or missing shot variants: ${stale.join(", ")}\nRun: node scripts/build_media_variants.mjs`); process.exit(1); }
  console.log("shot variants are up to date");
} else {
  console.log(`${written} variants written to site/assets/media`);
}
