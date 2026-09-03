#!/usr/bin/env node
/**
 * Render the social preview cards from template.html.
 *
 *   node scripts/social/render.mjs
 *
 * Writes two PNGs, because the two destinations want different sizes and
 * different pitches:
 *
 *   site/assets/og-image.png      1200x630  — the marketing site. 23 pages
 *                                 already point <meta og:image> at this path,
 *                                 and the file did not exist, so every share
 *                                 of getduct.ai rendered without a card.
 *   .github/social-preview.png    1280x640  — GitHub. Cannot be set from a file
 *                                 in the repo; upload it by hand at
 *                                 Settings -> Social preview. Kept in the repo
 *                                 so the next person does not have to redraw it.
 *
 * Uses the Playwright already installed for the site's smoke tests, so this
 * adds no dependency. Fonts are the system serif/sans the brand uses, so run
 * this on macOS to match what the site renders.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdir } from "node:fs/promises";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");

// Playwright is a devDependency of site/, installed for the smoke tests. ESM
// resolves from this file's directory rather than the cwd, so point it at that
// copy explicitly instead of requiring a second install at the repo root.
const require = createRequire(import.meta.url);
// require(), not import(): playwright is CommonJS, and a dynamic import of it
// hands back a namespace whose named exports are not always detected.
const { chromium } = require(
  require.resolve("playwright", { paths: [resolve(REPO, "site"), REPO] }),
);
const TEMPLATE = "file://" + resolve(HERE, "template.html");

const SOURCES = "Google Ads|GA4|Search Console|Mixpanel|Stripe";

const CARDS = [
  {
    out: "site/assets/og-image.png",
    width: 1200,
    height: 630,
    params: {
      w: 1200, h: 630, h1: 64, subsize: 25,
      headline: "The intelligence layer<br>your stack was <em>missing</em>.",
      sub: "Reads across your product and marketing tools and tells you what they mean together — as a decision brief, not another dashboard.",
      sources: SOURCES,
      tag: "getduct.ai",
    },
  },
  {
    out: ".github/social-preview.png",
    width: 1280,
    height: 640,
    params: {
      w: 1280, h: 640, h1: 60, subsize: 24,
      headline: "Open-source AI agent for<br>cross-tool <em>growth analytics</em>.",
      sub: "Ads, analytics, search and revenue — read together, then acted on with your approval. Self-hosted, or a local desktop app.",
      sources: SOURCES,
      tag: "MIT licensed",
    },
  },
];

const browser = await chromium.launch();
try {
  for (const card of CARDS) {
    const page = await browser.newPage({
      viewport: { width: card.width, height: card.height },
      deviceScaleFactor: 2, // retina; both destinations downscale, none upscale
    });
    const query = new URLSearchParams(card.params).toString();
    await page.goto(`${TEMPLATE}?${query}`, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);

    const out = resolve(REPO, card.out);
    await mkdir(dirname(out), { recursive: true });
    await page.locator("#card").screenshot({ path: out });
    await page.close();
    console.log(`wrote ${card.out}  (${card.width}x${card.height} @2x)`);
  }
} finally {
  await browser.close();
}
