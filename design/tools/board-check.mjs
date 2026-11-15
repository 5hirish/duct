#!/usr/bin/env node
// Is this board the app? Renders a board's markup with the stylesheet it
// links and lays it beside the app's own picture of the same screen, with a
// difference image between them (bright = different).
//
//   node design/tools/board-check.mjs [id ...]   # every board in OUT, or the named ones
//   node design/tools/board-check.mjs --size 390 # the same boards at another size
//
// --size takes a variant id from screens.mjs (1440, 1440-dark, 1100, 390). A
// board is captured once, at 1440 light; rendering it at another width and
// theme and comparing with the app's own picture there is what proves it
// reflows the way the app does, rather than only matching where it was shot.
//
// A framed document (a brief, a slide, a thumbnail) is a picture on the board,
// fixed at its 1440 size, while the app reflows the frame's content: those
// regions are left out of the number and drawn grey in the difference image,
// so a failure means the board's own markup is off.
//
// Writes <OUT>/check/<id>[@size].compare.png and prints the mean difference. Read the
// picture; the number is a guide (a caret, a clock or a font still loading
// never reach 0). This renders the markup as a browser does, not through the
// canvas's own runtime, so it proves the capture, not the canvas.
import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { VARIANTS } from "./screens.mjs";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const req = createRequire(import.meta.url);
const { chromium } = req(req.resolve("playwright", { paths: [process.env.PLAYWRIGHT_FROM || join(REPO, "site")] }));
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));

const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design"));
const BOARDS = join(OUT, "boards");
const TYPES = { ".css": "text/css", ".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf" };
const args = process.argv.slice(2);
const sizeAt = args.indexOf("--size");
const sizeId = sizeAt >= 0 ? args.splice(sizeAt, 2)[1] : "1440";
const variant = VARIANTS.find((v) => v.id === sizeId);
if (!variant) throw new Error(`--size ${sizeId}: not one of ${VARIANTS.map((v) => v.id).join(", ")}`);
const suffix = variant.id === "1440" ? "" : `@${variant.id}`;
const only = args;
const ids = readdirSync(BOARDS).filter((f) => f.endsWith(".dc.html")).map((f) => f.replace(/\.dc\.html$/, ""))
  .filter((id) => !only.length || only.includes(id));
mkdirSync(join(OUT, "check"), { recursive: true });

const browser = await chromium.launch({ headless: true });
let worst = 0;
try {
  for (const id of ids) {
    const src = readFileSync(join(BOARDS, `${id}.dc.html`), "utf8");
    const helmet = /<helmet>([\s\S]*?)<\/helmet>/.exec(src)?.[1] || "";
    let body = /<\/helmet>([\s\S]*?)<\/x-dc>/.exec(src)?.[1] || "";
    // The theme is a class on the board's root, as it is on the app's <html>.
    if (variant.theme === "dark") body = body.replace(/^(\s*<div class="[^"]*)\blight\b/, "$1dark");
    const { height } = JSON.parse(/data-props='([^']*)'/.exec(src)[1]).$preview;
    const width = variant.width;
    const doc = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="duct-app.css">${helmet}</head><body>${body}</body></html>`;

    const context = await browser.newContext({
      viewport: { width, height: variant.id === "1440" ? Math.min(height, variant.height) : variant.height },
      deviceScaleFactor: variant.scale,
    });
    await context.route("**/*", (route) => {
      const u = new URL(route.request().url());
      if (u.hostname === "board.local") {
        if (u.pathname === "/") return route.fulfill({ body: doc, contentType: "text/html" });
        const f = join(BOARDS, decodeURIComponent(u.pathname));
        if (!existsSync(f)) return route.fulfill({ status: 404, body: "" });
        return route.fulfill({ body: readFileSync(f), contentType: TYPES[extname(f).toLowerCase()] || "application/octet-stream" });
      }
      if (/fonts\.(googleapis|gstatic)\.com$/.test(u.hostname)) return route.continue();
      return route.abort();
    });
    const page = await context.newPage();
    await page.goto("http://board.local/", { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    // At its own size the board is as tall as the page it was cut from; at
    // another width the page reflows to a height of its own.
    const tall = variant.id === "1440" ? height : await page.evaluate(() => document.documentElement.scrollHeight);
    const boardPng = await page.screenshot({ fullPage: true, clip: { x: 0, y: 0, width, height: tall } });
    // capture.mjs names a frame's picture <id>-frame-<n>.png.
    const pictures = await page.evaluate(() => [...document.querySelectorAll('img[src*="-frame-"]')]
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.height > 0)
      .map((r) => ({ x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height })));
    await context.close();

    const ref = join(OUT, "asbuilt", `${id}@${variant.id}.webp`);
    if (!existsSync(ref)) {
      console.log(`? ${id}: no As built picture to compare with`);
      continue;
    }
    const px = width * variant.scale;
    const [mb, mr] = [await sharp(boardPng).metadata(), await sharp(ref).metadata()];
    const h = Math.min(mb.height, mr.height);
    const a = await sharp(boardPng).extract({ left: 0, top: 0, width: px, height: h }).removeAlpha().raw().toBuffer();
    const b = await sharp(ref).extract({ left: 0, top: 0, width: px, height: h }).removeAlpha().raw().toBuffer();
    const diff = Buffer.alloc(a.length);
    const scale = variant.scale;
    const exempt = (x, y) => pictures.some((r) => x >= r.x * scale && x < (r.x + r.w) * scale && y >= r.y * scale && y < (r.y + r.h) * scale);
    let sum = 0;
    let counted = 0;
    for (let i = 0; i < a.length; i += 3) {
      const px = (i / 3) % (width * scale);
      const py = Math.floor(i / 3 / (width * scale));
      if (pictures.length && exempt(px, py)) {
        diff[i] = diff[i + 1] = diff[i + 2] = 128;
        continue;
      }
      for (let c = 0; c < 3; c += 1) {
        const d = Math.abs(a[i + c] - b[i + c]);
        diff[i + c] = Math.min(255, d * 4);
        sum += d;
      }
      counted += 3;
    }
    const mean = counted ? sum / counted : 0;
    worst = Math.max(worst, mean);
    const raw = { raw: { width: px, height: h, channels: 3 } };
    const gap = 24;
    // sharp composites after it resizes, so the strip is built whole first.
    const strip = await sharp({ create: { width: px * 3 + gap * 2, height: h, channels: 3, background: "#808080" } })
      .composite([
        { input: await sharp(a, raw).png().toBuffer(), left: 0, top: 0 },
        { input: await sharp(b, raw).png().toBuffer(), left: px + gap, top: 0 },
        { input: await sharp(diff, raw).png().toBuffer(), left: (px + gap) * 2, top: 0 },
      ])
      .png()
      .toBuffer();
    await sharp(strip).resize({ width: Math.min(2400, px * 3 + gap * 2) }).png().toFile(join(OUT, "check", `${id}${suffix}.compare.png`));
    const tallNote = Math.abs(mb.height - mr.height) > 8 * variant.scale ? `  (board ${mb.height / variant.scale}px tall, app ${mr.height / variant.scale}px)` : "";
    const pictureNote = pictures.length ? `  (${pictures.length} framed ${pictures.length === 1 ? "picture" : "pictures"} left out)` : "";
    console.log(`${mean < 3 ? "✓" : "✗"} ${id}${suffix}  mean difference ${mean.toFixed(2)}${tallNote}${pictureNote}`);
  }
} finally {
  await browser.close();
}
process.exit(worst < 3 ? 0 : 1);
