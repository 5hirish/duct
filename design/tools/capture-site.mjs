#!/usr/bin/env node
// The marketing site, as the canvas needs it: each page as an editable board,
// its own markup linking its own stylesheet, the way capture.mjs does it for
// the app (the two share board.mjs). Writes to OUT (default
// $TMPDIR/duct-design-site):
//
//   boards/site-<id>.dc.html   the page at 1440, whole length (a PAGE board)
//   boards/duct-site.css       the site's stylesheet, url()s pointing at img/
//   boards/img/                every picture the pages and stylesheet use
//   site.json                  what was captured, for the canvas layout
//
//   python3 site/dev_server.py --port 8090      # the site, once
//   node design/tools/capture-site.mjs [id ...] # every page, or the named ones
//   node design/tools/capture-site.mjs --check  # each board beside its page
//
// COMPARE=http://localhost:8091 also captures that server's /connect-agent as
// site-connect-agent-main: another branch's copy of the page (a worktree of
// origin/main served on its own port), so two versions sit side by side.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { boardDocument, escapeHtml, serialize } from "./board.mjs";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const req = createRequire(import.meta.url);
const { chromium } = req(req.resolve("playwright", { paths: [process.env.PLAYWRIGHT_FROM || join(REPO, "site")] }));
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));

// CHROMIUM names a browser binary when the one the site's pinned Playwright
// expects is not installed (a sandbox with its own Chromium).
const LAUNCH = { headless: true, ...(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {}) };
const SITE = process.env.SITE || "http://localhost:8090";
const COMPARE = process.env.COMPARE || "";
const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design-site"));
const BOARDS = join(OUT, "boards");
const WIDTH = 1440;
const STYLESHEET = "duct-site.css";

// The pages a visitor lands on. Legal pages and the 404 are left out: they are
// text, and nothing about them is designed per page.
export const PAGES = [
  { id: "index", path: "/", title: "Home" },
  { id: "connect-agent", path: "/connect-agent", title: "Use Duct from your agent" },
  { id: "mcp", path: "/mcp", title: "Your MCP servers in Duct" },
  { id: "skills", path: "/skills", title: "Skills" },
  { id: "compare", path: "/compare", title: "Compare" },
  { id: "for-organic-growth", path: "/for-organic-growth", title: "For organic growth" },
  { id: "for-paid-ads", path: "/for-paid-ads", title: "For paid ads" },
  { id: "for-product-intelligence", path: "/for-product-intelligence", title: "For product intelligence" },
  { id: "seo-audit", path: "/seo-audit", title: "SEO audit" },
  { id: "download", path: "/download", title: "Download" },
  { id: "open-source", path: "/open-source", title: "Open source" },
  { id: "doctrine", path: "/doctrine", title: "Doctrine" },
  { id: "about", path: "/about", title: "About" },
  { id: "integrations", path: "/integrations/", title: "Integrations" },
  { id: "tools", path: "/tools/", title: "Free tools" },
  { id: "blog", path: "/blog/", title: "Blog" },
  { id: "changelog", path: "/changelog/", title: "Changelog" },
];
const compare = COMPARE ? [{ id: "connect-agent-main", path: "/connect-agent", title: "Use Duct from your agent (main)", base: COMPARE }] : [];

const args = process.argv.slice(2);
const checking = args.includes("--check");
const only = args.filter((a) => !a.startsWith("--"));
const wanted = [...PAGES, ...compare].filter((p) => !only.length || only.includes(p.id));
mkdirSync(join(BOARDS, "img"), { recursive: true });

// A link to another captured page goes to its board, so Play moves through
// the site the way its nav does. Every spelling the site uses for a page
// (extensionless, .html, a directory's index) lands on the same board.
const ROUTE_TO_BOARD = {};
for (const p of PAGES) {
  const file = `site-${p.id}.dc.html`;
  const bare = p.path.replace(/\/$/, "");
  for (const path of p.path === "/" ? ["/", "/index.html"] : [p.path, `${bare}.html`, `${bare}/`, `${bare}/index.html`]) {
    ROUTE_TO_BOARD[path] ??= file;
  }
}

const images = new Map(); // absolute url → file name under boards/img
// Stylesheet hrefs by the stylesheet file their boards link, in the order
// first seen: another branch's copy (COMPARE) links its own, since its CSS
// is that branch's and merging the two would restyle both.
const sheets = new Map();
const stylesheetFor = (base) => (base === SITE ? STYLESHEET : STYLESHEET.replace(/\.css$/, "-compare.css"));

if (checking) await check();
else await captureAll();

// --- capture -----------------------------------------------------------------------

async function captureAll() {
  const manifestPath = join(OUT, "site.json");
  const manifest = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, "utf8")) : { pages: {} };
  const browser = await chromium.launch(LAUNCH);
  let failed = 0;
  try {
    for (const p of wanted) {
      const base = p.base || SITE;
      const context = await browser.newContext({ viewport: { width: WIDTH, height: 900 }, reducedMotion: "reduce", locale: "en-GB" });
      // Nothing leaves the machine: no analytics, no tag gateway, no fonts
      // (the site uses system fonts), only the server being captured.
      await context.route("**/*", (route) => {
        const u = new URL(route.request().url());
        return ["localhost", "127.0.0.1"].includes(u.hostname) || u.protocol === "data:" ? route.continue() : route.abort();
      });
      const page = await context.newPage();
      try {
        await page.goto(new URL(p.path, base).href, { waitUntil: "load" });
        await settle(page);
        const board = await capture(page, p, base);
        manifest.pages[p.id] = { id: p.id, title: p.title, path: p.path, base, board };
        console.log(`✓ ${p.id}  ${board.height}px`);
      } catch (err) {
        failed += 1;
        console.error(`✗ ${p.id}: ${err.message.split("\n")[0]}`);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  await writeStylesheet();
  await fetchImages();
  manifest.capturedAt = new Date().toISOString();
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 1));
  console.log(`${wanted.length} pages → ${OUT}${failed ? `, ${failed} failed` : ""}`);
  process.exit(failed ? 1 : 0);
}

async function settle(page) {
  // The nav and footer are partials duct-partials.js fetches; the page is not
  // the page until they are in.
  await page.waitForFunction(() => window.__DUCT_PARTIALS_READY === true, null, { timeout: 10000 }).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  // A section fades in when scrolled to; a board has no scroll, so every one
  // is in. Reduced motion already puts a scripted demo on its finished frame.
  await page.evaluate(() => document.querySelectorAll(".reveal").forEach((el) => el.classList.add("in")));
  // A lazy image below the fold never loads in a page nobody scrolls, so the
  // capture measured the page short and the check compared a board with its
  // picture against a page without it (/about, /connect-agent's sign-in).
  await page.evaluate(() => Promise.all([...document.querySelectorAll('img[loading="lazy"]')].map((img) => {
    img.loading = "eager";
    return img.complete ? null : new Promise((done) => { img.onload = img.onerror = done; setTimeout(done, 8000); });
  })));
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(1, 1).catch(() => {});
  await page.waitForTimeout(400);
}

async function capture(page, p, base) {
  // An icon is a <use> into the site's sprite (/assets/icons.svg), a file the
  // canvas cannot serve. Each becomes the symbol's own shapes, inline, which
  // is what an icon on a board is.
  await page.evaluate(async () => {
    const uses = [...document.querySelectorAll("svg use")].filter((u) => /icons\.svg#/.test(u.getAttribute("href") || u.getAttribute("xlink:href") || ""));
    if (!uses.length) return;
    const sprites = {};
    for (const use of uses) {
      const ref = new URL(use.getAttribute("href") || use.getAttribute("xlink:href"), location.href);
      const key = ref.origin + ref.pathname;
      if (!sprites[key]) {
        const text = await fetch(key).then((r) => r.text()).catch(() => "");
        sprites[key] = new DOMParser().parseFromString(text, "image/svg+xml");
      }
      const symbol = sprites[key].getElementById(ref.hash.slice(1));
      const svg = use.closest("svg");
      if (!symbol || !svg) continue;
      if (!svg.getAttribute("viewBox") && symbol.getAttribute("viewBox")) svg.setAttribute("viewBox", symbol.getAttribute("viewBox"));
      for (const a of ["fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin"]) {
        if (symbol.getAttribute(a) && !svg.getAttribute(a)) svg.setAttribute(a, symbol.getAttribute(a));
      }
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      for (const child of symbol.childNodes) g.appendChild(document.importNode(child, true));
      use.replaceWith(g);
    }
  });

  // A page that shows one state at a time keys it on <body> (the SEO audit's
  // data-lm-state), and the board's root stands in for <html> and <body>:
  // with only their classes carried, every state's section showed at once.
  const rootData = await page.evaluate(() => {
    const out = {};
    for (const el of [document.documentElement, document.body]) {
      for (const a of el.attributes) if (a.name.startsWith("data-")) out[a.name] = a.value;
    }
    return out;
  });
  // An image with a srcset keeps its smallest file in src; serialize() drops
  // the srcset, so pin src to the file the browser chose at 1440 or a hero
  // shot comes out a blurred 768px copy stretched to fit.
  await page.evaluate(() => document.querySelectorAll("img").forEach((img) => {
    if (img.currentSrc && img.currentSrc !== img.src) img.setAttribute("src", img.currentSrc);
  }));
  // Video, canvases and frames cannot be board markup: each becomes a picture
  // of itself in place, as in capture.mjs (the home page's hero is a video).
  const swaps = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll("iframe, canvas, video").forEach((el, i) => {
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return;
      el.setAttribute("data-cap-shot", String(i));
      out.push(i);
    });
    return out;
  });
  const shots = {};
  for (const i of swaps) {
    const name = `site-${p.id}-frame-${i}.png`;
    const ok = await page.locator(`[data-cap-shot="${i}"]`).screenshot({ path: join(BOARDS, "img", name) }).then(() => true, () => false);
    if (ok) shots[i] = name;
  }
  const snap = await page.evaluate(serialize, { routeToBoard: ROUTE_TO_BOARD, shots });
  const stylesheet = stylesheetFor(base);
  if (!sheets.has(stylesheet)) sheets.set(stylesheet, new Set());
  for (const href of snap.sheets) sheets.get(stylesheet).add(href);
  const html = snap.html.replace(/__IMG\[(.+?)\]__/g, (_, url) => `img/${imageName(url)}`);
  const file = `site-${p.id}.dc.html`;
  const height = Math.max(snap.height, 900);
  const doc = boardDocument({
    title: `Duct site · ${p.title}`,
    rootClass: `${snap.htmlClass} ${snap.bodyClass}`.trim(),
    html,
    width: WIDTH,
    height,
    stylesheet,
    // A page's own <style> stays with its board: the site writes most of a
    // page's layout there, and in the shared sheet it would reach every page.
    inline: snap.inline.map((text) => rewriteCss(text, new URL(p.path, base).href)).join("\n"),
  });
  const attrs = Object.entries(rootData).filter(([k]) => /^data-[a-z0-9-]+$/.test(k))
    .map(([k, v]) => ` ${k}="${escapeHtml(v)}"`).join("");
  writeFileSync(join(BOARDS, file), attrs ? doc.replace(/(<x-dc>[\s\S]*?<\/helmet>\s*<div class="[^"]*")/, `$1${attrs}`) : doc);
  return { file, width: WIDTH, height, stylesheet, bytes: Buffer.byteLength(doc) };
}

async function writeStylesheet() {
  for (const [file, hrefs] of sheets) {
    const parts = [];
    for (const href of hrefs) {
      const text = await fetch(href).then((r) => (r.ok ? r.text() : "")).catch(() => "");
      if (text) parts.push(`/* ${new URL(href).pathname} */\n${rewriteCss(text, href)}`);
    }
    if (!parts.length) continue;
    writeFileSync(join(BOARDS, file),
      `/* Duct site stylesheet, captured from ${new URL([...hrefs][0]).origin} by design/tools/capture-site.mjs on ${new Date().toISOString().slice(0, 10)}.\n   Regenerate it; never edit it here. */\n${parts.join("\n")}`);
  }
}

function rewriteCss(text, base) {
  return text.replace(/url\((['"]?)([^'")]+)\1\)/g, (m, q, u) => {
    if (u.startsWith("data:") || u.startsWith("#")) return m;
    const abs = new URL(u, base).href;
    if (!/\.(png|jpe?g|gif|webp|svg|avif|woff2?|ttf|otf)(\?|$)/i.test(abs)) return m;
    return `url("img/${imageName(abs)}")`;
  });
}

function imageName(url) {
  if (images.has(url)) return images.get(url);
  const u = new URL(url);
  let name = basename(u.pathname).replace(/[^A-Za-z0-9._-]/g, "-") || "image";
  const taken = new Set(images.values());
  for (let n = 2; taken.has(name); n += 1) name = name.replace(/(\.[^.]+)?$/, `-${n}$1`);
  images.set(url, name);
  return name;
}

async function fetchImages() {
  for (const [url, name] of images) {
    const res = await fetch(url).catch(() => null);
    if (!res?.ok) {
      console.error(`  missing image ${url}`);
      continue;
    }
    writeFileSync(join(BOARDS, "img", name), Buffer.from(await res.arrayBuffer()));
  }
}

// --- check -------------------------------------------------------------------------

// Each board rendered as a browser renders its markup (not through the
// canvas's runtime), beside the page it came from at the same width, with a
// difference image. Prints the mean difference; read the picture.
async function check() {
  const manifest = JSON.parse(readFileSync(join(OUT, "site.json"), "utf8"));
  const dir = join(OUT, "check");
  mkdirSync(dir, { recursive: true });
  const TYPES = { ".css": "text/css", ".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif" };
  const browser = await chromium.launch(LAUNCH);
  try {
    for (const p of wanted) {
      const entry = manifest.pages[p.id];
      if (!entry) continue;
      const src = readFileSync(join(BOARDS, entry.board.file), "utf8");
      const helmet = /<helmet>([\s\S]*?)<\/helmet>/.exec(src)?.[1] || "";
      const body = /<\/helmet>([\s\S]*?)<\/x-dc>/.exec(src)?.[1] || "";
      const doc = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="${entry.board.stylesheet || STYLESHEET}">${helmet}</head><body>${body}</body></html>`;
      const shotOf = async (url, fulfil) => {
        const context = await browser.newContext({ viewport: { width: WIDTH, height: 900 }, reducedMotion: "reduce" });
        await context.route("**/*", (route) => {
          const u = new URL(route.request().url());
          if (fulfil && u.hostname === "board.local") {
            if (u.pathname === "/") return route.fulfill({ body: doc, contentType: "text/html" });
            const f = join(BOARDS, decodeURIComponent(u.pathname));
            if (!existsSync(f)) return route.fulfill({ status: 404, body: "" });
            return route.fulfill({ body: readFileSync(f), contentType: TYPES[extname(f).toLowerCase()] || "application/octet-stream" });
          }
          return ["localhost", "127.0.0.1"].includes(u.hostname) && !fulfil ? route.continue() : route.abort();
        });
        const page = await context.newPage();
        await page.goto(url, { waitUntil: "load" });
        if (!fulfil) await settle(page);
        await page.evaluate(() => document.fonts.ready);
        // Long enough for a page's CSS entrance animation (a hero that fades
        // up on load) to finish on the board as it has on the page.
        await page.waitForTimeout(1500);
        const png = await page.screenshot({ fullPage: true });
        await context.close();
        return png;
      };
      const board = await shotOf("http://board.local/", true);
      const real = await shotOf(new URL(entry.path, entry.base).href, false);
      const [mb, mr] = [await sharp(board).metadata(), await sharp(real).metadata()];
      const h = Math.min(mb.height, mr.height);
      const a = await sharp(board).extract({ left: 0, top: 0, width: WIDTH, height: h }).removeAlpha().raw().toBuffer();
      const b = await sharp(real).extract({ left: 0, top: 0, width: WIDTH, height: h }).removeAlpha().raw().toBuffer();
      const diff = Buffer.alloc(a.length);
      let sum = 0;
      for (let i = 0; i < a.length; i += 1) {
        const d = Math.abs(a[i] - b[i]);
        sum += d;
        diff[i] = Math.min(255, d * 3);
      }
      const mean = sum / a.length;
      const scale = 0.25;
      const side = async (buf, raw) => sharp(buf, raw ? { raw: { width: WIDTH, height: h, channels: 3 } } : undefined)
        .extract({ left: 0, top: 0, width: WIDTH, height: h }).resize(Math.round(WIDTH * scale)).png().toBuffer();
      const tiles = [await side(real), await side(board), await side(diff, true)];
      const th = Math.round(h * scale);
      await sharp({ create: { width: Math.round(WIDTH * scale) * 3 + 40, height: th, channels: 3, background: "#fff" } })
        .composite(tiles.map((input, i) => ({ input, left: i * (Math.round(WIDTH * scale) + 20), top: 0 })))
        .png().toFile(join(dir, `${p.id}.compare.png`));
      const heights = mb.height === mr.height ? `${h}px` : `board ${mb.height}px, page ${mr.height}px`;
      console.log(`${mean < 3 ? "✓" : "✗"} ${p.id}: mean difference ${mean.toFixed(2)}  (${heights})`);
    }
  } finally {
    await browser.close();
  }
}
