#!/usr/bin/env node
// Render every .card in an HTML file to PNG, and optionally all of them to one
// PDF (a LinkedIn document post). Hand-drawn cards instead of image-model
// output, because generated text is misspelt often enough to cost a re-roll
// per card.
//
//   node .agents/skills/build-in-public/render.mjs <cards.html> <out-prefix> [--pdf]
//
// Writes <out-prefix>-1.png, -2.png … and <out-prefix>.pdf. Uses the
// Playwright that site/ already installs, so it adds no dependency.
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = resolve(fileURLToPath(new URL("../../..", import.meta.url)));
const req = createRequire(import.meta.url);

const [input, prefix] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const wantPdf = process.argv.includes("--pdf");
if (!input || !prefix) {
  console.error("usage: render.mjs <cards.html> <out-prefix> [--pdf]");
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = req(req.resolve("playwright", { paths: [join(REPO, "site")] })));
} catch {
  console.error("Playwright not found: run `make setup` (it installs site/'s dev dependencies).");
  process.exit(1);
}

mkdirSync(dirname(resolve(prefix)), { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(resolve(input)).href);
  const cards = await page.$$(".card");
  if (!cards.length) throw new Error(`no .card elements in ${input}`);

  for (const [i, card] of cards.entries()) {
    const out = `${prefix}-${i + 1}.png`;
    await card.screenshot({ path: out });
    console.log(out);
  }

  if (wantPdf) {
    // A PDF page per card, sized to the first card: LinkedIn shows every page
    // at the first page's ratio, so a mixed deck would letterbox.
    const { width, height } = await cards[0].boundingBox();
    await page.addStyleTag({
      content: `@page { size: ${width}px ${height}px; margin: 0 }
                body { margin: 0 } .card { break-after: page }`,
    });
    const out = `${prefix}.pdf`;
    await page.pdf({ path: out, width: `${width}px`, height: `${height}px`, printBackground: true });
    console.log(out);
  }
} finally {
  await browser.close();
}
