#!/usr/bin/env node
// The app, as the canvas needs it. Renders every screen against the story's
// fixture backend (the same one check:layout and the README shots use) and
// writes two things per screen:
//
//   asbuilt/<id>@<variant>.webp   a picture at each size and theme, for "As built"
//   boards/<id>.dc.html           the screen as an editable board (1440, light):
//                                 the app's own markup, linking the app's own
//                                 stylesheet, so it reads as the same screen
//
// plus boards/duct-app.css (that stylesheet), boards/img/ (every image the
// boards and the stylesheet use) and screens.json (what was shot, for
// layout.mjs, which lays it all out as the canvas).
//
//   npm --prefix app run dev                  # the app on :3003, once
//   node design/tools/capture.mjs [id ...]    # every screen, or the named ones
//
// OUT (default $TMPDIR/duct-design) is where it writes. Playwright comes from
// site/ and sharp from app/, as for scripts/shots.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const req = createRequire(import.meta.url);
const { chromium } = req(req.resolve("playwright", { paths: [process.env.PLAYWRIGHT_FROM || join(REPO, "site")] }));
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));
const fixtures = await import(join(REPO, "scripts/shots/fixtures.mjs"));
const { STORY, PLAN } = await import(join(REPO, "app/src/lib/__fixtures__/solo-story.mjs"));
const { SCREENS, VARIANTS } = await import("./screens.mjs");

const APP = process.env.APP || "http://localhost:3003";
const API = process.env.API || "http://localhost:8002";
const MOCK_PORT = Number(process.env.MOCK_PORT || 8012);
const MOCK = `http://localhost:${MOCK_PORT}`;
const OUT = resolve(process.env.OUT || join(tmpdir(), "duct-design"));
const STORY_NOW = new Date(`${STORY.week.end}T09:30:00+02:00`);
// A page longer than this is cut: the picture is for recognising the screen,
// and a 9000px strip shrinks to a sliver on the canvas.
const MAX_HEIGHT = { desktop: 2600, phone: 3600 };

const only = process.argv.slice(2);
const wanted = SCREENS.filter((s) => !only.length || only.includes(s.id));
if (!wanted.length) {
  console.error("no such screen; known:", SCREENS.map((s) => s.id).join(", "));
  process.exit(2);
}
for (const dir of ["asbuilt", "boards", "boards/img"]) mkdirSync(join(OUT, dir), { recursive: true });

// Where a link in a board goes: the board for that route, so Play moves
// between screens the way the sidebar does.
// The first screen on a path owns it: an overlay (the palette on Home, the
// feed sheet on Content Studio) shares its page's path and must not take
// the page's links. `link` names the concrete path for a route with an id.
const ROUTE_TO_BOARD = {};
for (const s of SCREENS.filter((x) => x.board !== false)) {
  const path = new URL(s.link ? s.link({ story: STORY, fixtures }) : s.route.replace(":id", STORY.project.id), APP).pathname;
  ROUTE_TO_BOARD[path] ??= `${s.id}.dc.html`;
}

const build = mkdtempSync(join(tmpdir(), "duct-capture-"));
writeFileSync(join(build, "insights-pause.json"), JSON.stringify(fixtures.insightsFrames()));
writeFileSync(join(build, "content-plan.json"), JSON.stringify(fixtures.contentFrames()));
writeFileSync(join(build, "audit-run.json"), JSON.stringify(fixtures.auditFrames()));
writeFileSync(join(build, "routes.json"), JSON.stringify(fixtures.routes()));
// A screen with `shot` gets <agent>@<shot>.json: the plan session is the
// content agent making a plan, where the default content stream drafts a post.
writeFileSync(join(build, "tiktok_studio@plan.json"), JSON.stringify(fixtures.planFrames()));
const mock = spawn(process.execPath, [join(REPO, "app/scripts/mock-agent-backend.mjs"), String(MOCK_PORT)], {
  env: {
    ...process.env,
    FIXTURES_DIR: build,
    ROUTES_FILE: join(build, "routes.json"),
    MEDIA_DIR: join(REPO, "scripts/shots/assets"),
    FRAME_MS: "20",
  },
  stdio: ["ignore", "ignore", "inherit"],
});

const manifestPath = join(OUT, "screens.json");
const manifest = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, "utf8")) : { screens: {} };
const sheets = new Map(); // stylesheet href → text, in the order first seen
const images = new Map(); // absolute url → file name under boards/img
let failed = 0;

try {
  await waitFor(`${MOCK}/api/agents`, 15000);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const screen of wanted) {
      const entry = { id: screen.id, title: screen.title, group: screen.group, route: screen.route, shots: {} };
      for (const variant of VARIANTS) {
        if (screen.variants && !screen.variants.includes(variant.id)) continue;
        const t0 = Date.now();
        const context = await browser.newContext({
          viewport: { width: variant.width, height: variant.height },
          deviceScaleFactor: variant.scale,
          colorScheme: variant.theme,
          locale: "en-GB",
          timezoneId: "Europe/Madrid",
        });
        // Nothing leaves the machine: the backend is the story's mock, and
        // analytics (the /ingest rewrite included) and the sign-in bot check
        // are refused, so a capture neither reports to the product's own
        // analytics nor draws a challenge most visitors never see.
        await context.route("**/*", (route) => {
          const url = route.request().url();
          if (url.startsWith(`${API}/`)) {
            const headers = screen.shot ? { ...route.request().headers(), "x-duct-shot": screen.shot } : undefined;
            return route.continue({ url: url.replace(API, MOCK), headers });
          }
          const u = new URL(url);
          if (u.pathname.startsWith("/ingest")) return route.abort();
          if (["localhost", "127.0.0.1"].includes(u.hostname) || u.protocol === "data:") return route.continue();
          return route.abort();
        });
        // The story's week, so the desk reads as that Monday rather than as
        // two months of silence.
        await context.clock.setFixedTime(STORY_NOW);
        await context.addCookies([{ name: "duct_consent", value: "rejected", url: APP }]);
        const page = await context.newPage();
        page.setDefaultTimeout(45000);
        try {
          if (!screen.signedOut) await signIn(page);
          await screen.open({ page, app: APP, story: STORY, plan: PLAN, variant, fixtures });
          await settle(page);
          const file = `${screen.id}@${variant.id}.webp`;
          const kind = variant.width < 640 ? "phone" : "desktop";
          const size = await shoot(page, join(OUT, "asbuilt", file), screen.workspace ? variant.height : MAX_HEIGHT[kind], variant);
          entry.shots[variant.id] = { file, ...size, theme: variant.theme, label: variant.label };
          rmSync(join(OUT, "asbuilt", `${screen.id}@${variant.id}.failed.png`), { force: true });
          if (variant.board && screen.board !== false) {
            entry.board = await capture(page, screen);
          }
          console.log(`✓ ${screen.id} @${variant.id}  ${Math.round((Date.now() - t0) / 100) / 10}s`);
        } catch (err) {
          failed += 1;
          console.error(`✗ ${screen.id} @${variant.id}: ${err.message.split("\n")[0]}`);
          await page.screenshot({ path: join(OUT, "asbuilt", `${screen.id}@${variant.id}.failed.png`) }).catch(() => {});
        } finally {
          await context.close();
        }
      }
      manifest.screens[screen.id] = entry;
    }
  } finally {
    await browser.close();
  }
  await writeStylesheet();
  await fetchImages();
  manifest.app = APP;
  manifest.capturedAt = new Date().toISOString();
  manifest.commit = gitHead();
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 1));
} finally {
  mock.kill();
}
console.log(`${wanted.length} screens → ${OUT}${failed ? `, ${failed} shot(s) failed` : ""}`);
process.exit(failed ? 1 : 0);

// --- shooting ------------------------------------------------------------------

async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  // Skeletons give way to content, and Reveal fades it in over 200ms.
  await page.waitForFunction(() => !document.querySelector('[data-slot="skeleton"]'), null, { timeout: 8000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  // The dev server's issues badge is not part of the product.
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
  await page.waitForTimeout(700);
}

async function shoot(page, out, maxHeight, variant) {
  const full = await page.evaluate(() => document.documentElement.scrollHeight);
  const height = Math.min(Math.max(full, variant.height), maxHeight);
  const raw = await page.screenshot({
    type: "png",
    fullPage: height > variant.height,
    clip: { x: 0, y: 0, width: variant.width, height },
  });
  await sharp(raw).webp({ quality: 82 }).toFile(out);
  return { width: variant.width, height, cut: full > height };
}

// --- the board -------------------------------------------------------------------

async function capture(page, screen) {
  // Frames, canvases and video cannot be board markup: each becomes a picture
  // of itself, in place, at its size.
  const swaps = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll("iframe, canvas, video").forEach((el, i) => {
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return;
      el.setAttribute("data-cap-shot", String(i));
      out.push({ i, w: Math.round(r.width), h: Math.round(r.height) });
    });
    return out;
  });
  // Each picture's file name travels into serialize() as an argument, never
  // through the page's DOM: a src built from an attribute is page text turned
  // into a URL, which CodeQL rightly refuses (js/xss-through-dom).
  const shots = {};
  for (const s of swaps) {
    const name = `${screen.id}-frame-${s.i}.png`;
    const shot = await page.locator(`[data-cap-shot="${s.i}"]`).screenshot({ path: join(OUT, "boards/img", name) }).then(() => true, () => false);
    if (shot) shots[s.i] = name;
  }

  const snap = await page.evaluate(serialize, { routeToBoard: ROUTE_TO_BOARD, shots });
  for (const href of snap.sheets) if (!sheets.has(href)) sheets.set(href, null);
  let html = snap.html;
  html = html.replace(/__IMG\[(.+?)\]__/g, (_, url) => `img/${imageName(url)}`);

  const width = 1440;
  const height = Math.max(snap.height, 900);
  const doc = boardDocument({
    title: `Duct · ${screen.title}`,
    rootClass: `${snap.htmlClass} ${snap.bodyClass}`.trim(),
    html,
    width,
    height: screen.workspace ? 900 : height,
    workspace: screen.workspace,
    // A <style> a page renders is that page's, not the app's: the audit
    // report's sets body { line-height: 1.65 } while it is on screen, and in
    // the shared sheet it moved every line on every board.
    inline: snap.inline.map((text) => rewriteCss(text, APP)).join("\n"),
  });
  writeFileSync(join(OUT, "boards", `${screen.id}.dc.html`), doc);
  return { file: `${screen.id}.dc.html`, width, height: screen.workspace ? 900 : height, bytes: Buffer.byteLength(doc) };
}

// Runs in the page: the body as board markup. Everything the canvas cannot
// hold goes (scripts, the dev overlay, comments), every image and link is
// marked for the rewrite in Node, and text that would read as a {{hole}} is
// broken with a zero-width space.
function serialize({ routeToBoard, shots }) {
  const sheets = [...document.querySelectorAll('link[rel="stylesheet"]')].map((l) => l.href);
  const inline = [...document.querySelectorAll("style")].map((s) => s.textContent).filter((t) => t && t.length < 200000);
  // A pane scrolled to the answer stays there: a board has no scroll position.
  // A pane at its end (a transcript, almost always) is pinned to its end, so
  // it still shows the latest turn when the board is narrower and the
  // transcript taller; any other pane is lifted by what was scrolled past,
  // which holds only at the width it was captured at.
  document.querySelectorAll("body *").forEach((el) => {
    if (el.scrollTop <= 0 || !el.firstElementChild) return;
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
    el.setAttribute("data-cap-scroll", atEnd ? "end" : String(Math.round(el.scrollTop)));
  });
  const root = document.body.cloneNode(true);
  const addStyle = (el, css) => el.setAttribute("style", `${el.getAttribute("style") || ""}; ${css}`.replace(/^; /, ""));
  root.querySelectorAll("[data-cap-scroll]").forEach((el) => {
    const at = el.getAttribute("data-cap-scroll");
    if (at === "end") addStyle(el, "display: flex; flex-direction: column; justify-content: flex-end");
    else addStyle(el.firstElementChild, `margin-top: -${at}px`);
    el.removeAttribute("data-cap-scroll");
  });
  root.querySelectorAll("script, style, link, noscript, template, nextjs-portal, next-route-announcer, #__next-route-announcer__")
    .forEach((n) => n.remove());
  const comments = document.createTreeWalker(root, NodeFilter.SHOW_COMMENT);
  const dead = [];
  while (comments.nextNode()) dead.push(comments.currentNode);
  dead.forEach((n) => n.remove());

  root.querySelectorAll("[data-cap-shot]").forEach((el) => {
    // The attribute only says which frame this was; its picture's name is
    // capture()'s, and a frame whose screenshot failed is left out.
    const i = el.getAttribute("data-cap-shot");
    const name = Object.hasOwn(shots, i) ? shots[i] : null;
    if (!name) return el.remove();
    // The picture takes the frame's layout box, not its painted one: a
    // thumbnail is a full-size frame scaled down by a transform, and the
    // picture inherits that transform with the frame's class and style, so
    // sizing it to the painted box scaled it down twice.
    const live = document.querySelector(`[data-cap-shot="${CSS.escape(i)}"]`);
    const w = live?.offsetWidth ?? 0;
    const h = live?.offsetHeight ?? 0;
    const scaled = live && getComputedStyle(live).transform !== "none";
    const img = document.createElement("img");
    img.setAttribute("src", `img/${name}`);
    img.setAttribute("alt", el.getAttribute("title") || "");
    if (el.getAttribute("class")) img.setAttribute("class", el.getAttribute("class"));
    const own = el.getAttribute("style") ? `${el.getAttribute("style").replace(/;?\s*$/, "")}; ` : "";
    img.setAttribute("style", `${own}display: block; width: ${w}px; height: ${h}px;${scaled ? "" : " max-width: 100%;"} object-fit: cover; object-position: left top`);
    el.replaceWith(img);
  });

  // React builds a <p> around block content (a <details>, a <pre>) as the DOM
  // allows, but an HTML parser closes the <p> at the first block and the board
  // comes out restructured. A <div> renders the same under the app's reset.
  root.querySelectorAll("p").forEach((p) => {
    if (!p.querySelector("div, details, pre, ul, ol, table, section, figure, form, blockquote, hr, h1, h2, h3, h4, h5, h6")) return;
    const div = document.createElement("div");
    for (const a of p.attributes) div.setAttribute(a.name, a.value);
    div.append(...p.childNodes);
    p.replaceWith(div);
  });

  root.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src");
    if (!src || src.startsWith("img/") || src.startsWith("data:")) return;
    let url = new URL(src, location.href);
    // next/image's optimiser: the original is in its `url` parameter.
    if (url.pathname === "/_next/image" && url.searchParams.get("url")) url = new URL(url.searchParams.get("url"), location.href);
    img.setAttribute("src", `__IMG[${url.href}]__`);
    for (const a of ["srcset", "sizes", "loading", "decoding", "fetchpriority", "data-nimg"]) img.removeAttribute(a);
  });
  root.querySelectorAll("[style*='url(']").forEach((el) => {
    el.setAttribute("style", el.getAttribute("style").replace(/url\((['"]?)([^'")]+)\1\)/g, (m, q, u) =>
      u.startsWith("data:") ? m : `url("__IMG[${new URL(u, location.href).href}]__")`));
  });

  root.querySelectorAll("a[href]").forEach((a) => {
    const u = new URL(a.getAttribute("href"), location.href);
    if (u.origin !== location.origin) return;
    if (u.pathname === location.pathname && u.hash) return;
    a.setAttribute("href", routeToBoard[u.pathname] || "#");
  });
  root.querySelectorAll("form").forEach((f) => f.removeAttribute("action"));
  // An empty boolean attribute is false to React; say it out loud.
  for (const name of ["disabled", "checked", "selected", "readonly", "required", "hidden", "open", "multiple", "autofocus", "novalidate", "inert"]) {
    root.querySelectorAll(`[${name}]`).forEach((el) => {
      if (el.getAttribute(name) === "") el.setAttribute(name, name);
    });
  }
  root.querySelectorAll("*").forEach((el) => {
    for (const a of [...el.attributes]) if (/^on/i.test(a.name)) el.removeAttribute(a.name);
  });
  const texts = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (texts.nextNode()) {
    const t = texts.currentNode;
    if (t.data.includes("{{") || t.data.includes("}}")) t.data = t.data.replace(/\{\{/g, "{​{").replace(/\}\}/g, "}​}");
  }
  return {
    html: root.innerHTML,
    htmlClass: document.documentElement.className,
    bodyClass: document.body.className,
    height: document.documentElement.scrollHeight,
    sheets,
    inline,
  };
}

function boardDocument({ title, rootClass, html, width, height, workspace, inline = "" }) {
  const props = JSON.stringify({ $preview: { width, height } });
  // A workspace fills its window and scrolls inside; a framed page grows with
  // its content, so the board's root takes the page's own height.
  const rootStyle = workspace ? "height: 100vh; overflow: hidden" : "min-height: 100vh";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<script src="./support.js"></script>
<link rel="stylesheet" href="duct-app.css">
</head>
<body>
<x-dc>
<helmet>
<style>
body{margin:0}
${inline.replace(/<\/style/gi, "<\\/style")}
</style>
</helmet>
<div class="${escapeHtml(rootClass)}" style="${rootStyle}">
${html.trim()}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='${props}'>
class Component extends DCLogic {
renderVals() { return {}; }
}
</script>
</body>
</html>
`;
}

// --- the stylesheet and images ------------------------------------------------------

// Each route loads its own chunks, so the boards' stylesheet is the union of
// every run's: a run over two screens adds to it rather than replacing it with
// those two screens' share. Parts are kept by name in boards/css/ and listed,
// in the order first seen, in screens.json.
async function writeStylesheet() {
  mkdirSync(join(OUT, "boards/css"), { recursive: true });
  manifest.css = manifest.css || [];
  const keep = (name, text) => {
    writeFileSync(join(OUT, "boards/css", name), text);
    if (!manifest.css.includes(name)) manifest.css.push(name);
  };
  for (const href of sheets.keys()) {
    const text = await fetch(href).then((r) => (r.ok ? r.text() : "")).catch(() => "");
    if (text) keep(decodeURIComponent(new URL(href).pathname.split("/").pop()).replace(/[^A-Za-z0-9._-]/g, "_"), rewriteCss(text, href));
  }
  // Inline parts from runs before inline styles moved into their boards.
  manifest.css = manifest.css.filter((name) => !name.startsWith("inline-"));
  const parts = manifest.css.filter((name) => existsSync(join(OUT, "boards/css", name)))
    .map((name) => `/* ${name} */\n${readFileSync(join(OUT, "boards/css", name), "utf8")}`);
  if (!parts.length) return;
  writeFileSync(join(OUT, "boards", "duct-app.css"),
    `/* Duct app stylesheet, captured from the app by design/tools/capture.mjs on ${new Date().toISOString().slice(0, 10)}.\n   Regenerate it; never edit it here. */\n${parts.join("\n")}`);
}


function rewriteCss(text, base) {
  // The boards use next/font's own files, copied beside the images: Google's
  // build of DM Sans has other vertical metrics, which moved every line a
  // pixel or two and, at phone width, whole sections. The dev overlay's own
  // faces (/__nextjs_font/) are not the product's and are dropped.
  let css = text.replace(/@font-face\s*\{[^}]*\/__nextjs_font\/[^}]*\}/g, "");
  css = css.replace(/url\((['"]?)([^'")]+)\1\)/g, (m, q, u) => {
    if (u.startsWith("data:") || u.startsWith("#")) return m;
    const abs = new URL(u, base).href;
    if (!/\.(png|jpe?g|gif|webp|svg|avif|woff2?|ttf|otf)(\?|$)/i.test(abs)) return m;
    return `url("img/${imageName(abs)}")`;
  });
  return css;
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
    // Google's favicon service answers an unknown site with 404 and its
    // default globe, which is what the app shows, so an image body counts.
    if (!res?.ok && !res?.headers.get("content-type")?.startsWith("image/")) {
      console.error(`  missing image ${url}`);
      continue;
    }
    writeFileSync(join(OUT, "boards/img", name), Buffer.from(await res.arrayBuffer()));
  }
}

// --- helpers -----------------------------------------------------------------------

async function signIn(page) {
  await page.goto(`${APP}/`);
  await page.evaluate(({ user, project }) => {
    const b64 = (o) => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/=+$/, "");
    const token = `${b64({ alg: "none" })}.${b64({ sub: user.email, name: user.name, email: user.email, exp: Math.floor(Date.now() / 1000) + 86400 })}.sig`;
    localStorage.setItem("duct_auth_token", token);
    localStorage.setItem("duct_projects", JSON.stringify([project]));
    localStorage.setItem("duct_active_project_id", project.id);
    sessionStorage.clear();
  }, { user: STORY.user, project: fixtures.project() });
}

async function waitFor(url, ms) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try {
      await fetch(url);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  throw new Error(`fixture backend did not answer at ${url}`);
}

function gitHead() {
  try {
    const head = readFileSync(join(REPO, ".git/HEAD"), "utf8").trim();
    if (!head.startsWith("ref: ")) return head.slice(0, 7);
    const ref = head.slice(5);
    const loose = join(REPO, ".git", ref);
    if (existsSync(loose)) return readFileSync(loose, "utf8").trim().slice(0, 7);
    const packed = readFileSync(join(REPO, ".git/packed-refs"), "utf8").split("\n").find((l) => l.endsWith(` ${ref}`));
    return packed ? packed.slice(0, 7) : null;
  } catch {
    return null;
  }
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
