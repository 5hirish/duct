#!/usr/bin/env node
/**
 * Render the repository's social preview from template.html.
 *
 *   node scripts/social/render.mjs
 *
 * Writes .github/social-preview.png, 1280x640. GitHub cannot read it from the
 * repo; upload it by hand at Settings -> General -> Social preview. It is kept
 * here so the next person redraws it from source instead of from scratch.
 *
 * Captured at 2x and downscaled, so the type is antialiased like a retina
 * screenshot but the file stays at the size GitHub asks for and under its
 * 1 MB limit (the template's grain makes a 2x PNG larger than that).
 *
 * Playwright comes from site/ (the smoke tests) and sharp from app/, like
 * scripts/build_og_images.mjs, so this adds no dependency. The fonts are the
 * system Georgia and SF the brand uses, so run it on macOS.
 */

import { createRequire } from "node:module";
import { statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const require = createRequire(import.meta.url);
// require(), not import(): playwright is CommonJS, and a dynamic import of it
// hands back a namespace whose named exports are not always detected.
const { chromium } = require(require.resolve("playwright", { paths: [resolve(REPO, "site"), REPO] }));
const sharp = require(require.resolve("sharp", { paths: [resolve(REPO, "app"), REPO] }));

const W = 1280, H = 640, LIMIT = 1024 * 1024;
const OUT = resolve(REPO, ".github/social-preview.png");

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(pathToFileURL(resolve(HERE, "template.html")).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  const shot = await page.screenshot({ type: "png" });
  await sharp(shot).resize(W, H, { kernel: "lanczos3" }).png({ compressionLevel: 9 }).toFile(OUT);
  const size = statSync(OUT).size;
  if (size > LIMIT) throw new Error(`${OUT} is ${size} bytes; GitHub takes at most ${LIMIT}`);
  console.log(`wrote .github/social-preview.png  (${W}x${H}, ${Math.round(size / 1024)} KB)`);
} finally {
  await browser.close();
}
