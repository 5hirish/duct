#!/usr/bin/env node
// Turn a generated hero image into the two WebP files a post's front matter
// points at: site/blog/assets/<slug>/hero.webp at 1320px wide (2x the 652px
// text measure) and hero-768.webp beside it, which the generator adds to the
// srcset. Exists so every post is encoded the same way; before it, the budget
// (hero under 300 KB, variant under 120 KB) was a sentence in the skill that
// each author met differently. Mosaic tiles are high-frequency detail, so the
// quality knobs below are the lowest that keep the tesserae crisp.
//
//   node scripts/build_blog_hero.mjs <generated image> <slug>
//
// Also renders an SVG figure at page size so it can be looked at before commit:
//
//   node scripts/build_blog_hero.mjs --render <figure.svg> <out.png>

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, statSync } from "node:fs";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const req = createRequire(import.meta.url);
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));

const HERO_WIDTH = 1320;
const VARIANT_WIDTH = 768;
const FIGURE_WIDTH = 652;
const HERO_BUDGET = 300 * 1024;
const VARIANT_BUDGET = 120 * 1024;

const kb = (p) => `${Math.round(statSync(p).size / 1024)} KB`;

async function hero(src, slug) {
  const dir = join(REPO, "site/blog/assets", slug);
  mkdirSync(dir, { recursive: true });
  const base = sharp(src).rotate();
  const { width, height } = await base.metadata();
  const ratio = width / height;
  if (Math.abs(ratio - 16 / 9) > 0.02) {
    console.warn(`warning: source is ${width}x${height} (${ratio.toFixed(2)}), not 16:9; it will be center-cropped`);
  }
  const full = join(dir, "hero.webp");
  const small = join(dir, "hero-768.webp");
  await base.clone().resize(HERO_WIDTH, Math.round(HERO_WIDTH * 9 / 16), { fit: "cover" }).webp({ quality: 74, effort: 6 }).toFile(full);
  await base.clone().resize(VARIANT_WIDTH, Math.round(VARIANT_WIDTH * 9 / 16), { fit: "cover" }).webp({ quality: 72, effort: 6 }).toFile(small);
  for (const [p, budget] of [[full, HERO_BUDGET], [small, VARIANT_BUDGET]]) {
    const over = statSync(p).size > budget ? "  OVER BUDGET" : "";
    console.log(`${p}  ${kb(p)}${over}`);
  }
}

async function render(svg, out) {
  await sharp(svg, { density: 144 }).resize(FIGURE_WIDTH).png().toFile(out);
  console.log(`${out}  ${kb(out)}`);
}

const args = process.argv.slice(2);
if (args[0] === "--render" && args.length === 3) await render(args[1], args[2]);
else if (args.length === 2) await hero(args[0], args[1]);
else {
  console.error("usage: build_blog_hero.mjs <image> <slug>  |  --render <figure.svg> <out.png>");
  process.exit(2);
}
