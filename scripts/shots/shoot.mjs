#!/usr/bin/env node
// Product screenshots from the real app, fed one story.
//
//   npm --prefix app run dev                 # the app on :3003 (once)
//   node scripts/shots/shoot.mjs [id ...]    # all scenarios, or the named ones
//
// What it does: builds the story's agent streams and canned responses into a
// temp folder, starts the fixture-replaying mock backend on :8012 pointed at
// them (and at assets/ for the post covers), opens a headless Chromium at 2x
// with the app's backend calls rerouted to the mock, runs each scenario in
// scenarios.mjs, and composites the raw capture into a window or card frame
// on the brand backdrop. Output lands in docs/assets/readme/<id>.webp (OUT
// overrides).
//
// Playwright comes from site/ and sharp from app/, the two workspaces that
// already install them; nothing is added to the repo's dependencies.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const req = createRequire(import.meta.url);
const { chromium } = req(req.resolve("playwright", { paths: [join(REPO, "site")] }));
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));
const { SCENARIOS } = await import("./scenarios.mjs");
const fixtures = await import("./fixtures.mjs");
const { STORY } = await import("../../app/src/lib/__fixtures__/kestrel-story.mjs");

const APP = process.env.APP || "http://localhost:3003";
const MOCK_PORT = Number(process.env.MOCK_PORT || 8012);
const MOCK = `http://localhost:${MOCK_PORT}`;
const OUT = resolve(process.env.OUT || join(REPO, "docs/assets/readme"));
const SCALE = Number(process.env.SCALE || 2);
const only = process.argv.slice(2);
const wanted = SCENARIOS.filter((s) => !only.length || only.includes(s.id));
if (!wanted.length) { console.error("no such scenario; known:", SCENARIOS.map((s) => s.id).join(", ")); process.exit(2); }
mkdirSync(OUT, { recursive: true });

// --- story → mock backend inputs -------------------------------------------
const build = mkdtempSync(join(tmpdir(), "duct-shots-"));
writeFileSync(join(build, "insights-pause.json"), JSON.stringify(fixtures.insightsFrames()));
writeFileSync(join(build, "content-plan.json"), JSON.stringify(fixtures.contentFrames()));
writeFileSync(join(build, "audit-run.json"), JSON.stringify(fixtures.auditFrames()));
writeFileSync(join(build, "routes.json"), JSON.stringify(fixtures.routes()));

const mock = spawn(process.execPath, [join(REPO, "app/scripts/mock-agent-backend.mjs"), String(MOCK_PORT)], {
  env: { ...process.env, FIXTURES_DIR: build, ROUTES_FILE: join(build, "routes.json"), MEDIA_DIR: join(REPO, "scripts/shots/assets"), FRAME_MS: process.env.FRAME_MS || "40" },
  stdio: ["ignore", "ignore", "inherit"],
});
await waitFor(`${MOCK}/api/agents`, 15000);

// --- browser ----------------------------------------------------------------
const browser = await chromium.launch({ headless: true });
let failed = 0;
try {
  for (const sc of wanted) {
    const t0 = Date.now();
    const context = await browser.newContext({
      viewport: sc.viewport, deviceScaleFactor: SCALE, colorScheme: sc.theme || "light", locale: "en-GB", timezoneId: "Europe/Madrid",
    });
    await context.route(/^http:\/\/localhost:8002\//, (route) =>
      route.continue({ url: route.request().url().replace("http://localhost:8002", MOCK) }));
    if (sc.shell) await context.addInitScript(shellStub, sc.shell);
    const page = await context.newPage();
    page.setDefaultTimeout(60000);
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
    try {
      if (sc.kind === "page") await signIn(page);
      if (sc.kind === "scene") {
        await page.goto(`${APP}/preview/frame?scene=${sc.scene}&surface=inline&theme=${sc.theme || "light"}`);
        await page.waitForFunction(() => window.__preview?.ready === true);
        await page.evaluate(() => document.fonts.ready);
      }
      const target = await sc.run({ page, app: APP, story: STORY });
      await page.evaluate(() => document.fonts.ready);
      // The dev server's issues badge is not part of the product.
      await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
      const raw = target?.clip ? await page.screenshot({ type: "png", clip: target.clip })
        : target?.element ? await target.element.screenshot({ type: "png" })
        : target ? await target.screenshot({ type: "png" }) : await page.screenshot({ type: "png" });
      // WebP at 90: a sixth of the PNG for the photo-heavy frames, and text
      // at 2x stays crisp. GitHub and the site both render it.
      const out = join(OUT, `${sc.id}.webp`);
      await (await frame(raw, sc.frame || "window", target?.radius)).webp({ quality: 90 }).toFile(out);
      console.log(`✓ ${sc.id}  ${Math.round((Date.now() - t0) / 100) / 10}s  ${errors.length ? `(${errors.length} page errors)` : ""}`);
    } catch (err) {
      failed += 1;
      console.error(`✗ ${sc.id}: ${err.message.split("\n")[0]}`);
      await page.screenshot({ path: join(OUT, `${sc.id}.failed.png`) }).catch(() => {});
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
  mock.kill();
}
process.exit(failed ? 1 : 0);

// --- helpers ----------------------------------------------------------------
async function signIn(page) {
  await page.goto(`${APP}/`);
  await page.evaluate(({ user, project }) => {
    const b64 = (o) => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/=+$/, "");
    const token = `${b64({ alg: "none" })}.${b64({ sub: user.email, name: user.name, email: user.email, exp: Math.floor(Date.now() / 1000) + 86400 })}.sig`;
    localStorage.setItem("duct_auth_token", token);
    localStorage.setItem("duct_projects", JSON.stringify([{ id: project.id, name: project.name, profile: { company: { name: project.name } } }]));
    localStorage.setItem("duct_active_project_id", project.id);
    sessionStorage.clear();
  }, { user: STORY.user, project: STORY.project });
}

// Runs in the page before any of its scripts: the shell the app would find
// in the desktop build, answering the commands the scenario lists.
function shellStub(answers) {
  window.__TAURI__ = {
    core: {
      invoke: async (cmd) => {
        if (cmd in answers) return answers[cmd];
        throw new Error(`shots: shell stub has no answer for ${cmd}`);
      },
    },
  };
}

async function waitFor(url, ms) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try { await fetch(url); return; } catch { await new Promise((r) => setTimeout(r, 200)); }
  }
  throw new Error(`mock backend did not answer at ${url}`);
}

// A window (title bar with three dots) or a bare card (rounded, shadowed),
// on a soft brand gradient with generous padding. All sizes in output
// pixels, so the frame scales with the capture's density.
async function frame(raw, kind, ownRadius) {
  const img = sharp(raw);
  const { width: w, height: h } = await img.metadata();
  const pad = 48 * SCALE, radius = (ownRadius || 12) * SCALE, bar = kind === "window" ? 30 * SCALE : 0;
  const W = w + pad * 2, H = h + bar + pad * 2;
  const x = pad, y = pad;
  const dot = (cx, fill) => `<circle cx="${cx}" cy="${y + bar / 2}" r="${5 * SCALE}" fill="${fill}"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
    <defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#fff1e8"/><stop offset="0.55" stop-color="#f7f4f0"/><stop offset="1" stop-color="#e9ecf5"/>
      </linearGradient>
      <filter id="shadow" x="-10%" y="-10%" width="120%" height="125%">
        <feDropShadow dx="0" dy="${10 * SCALE}" stdDeviation="${14 * SCALE}" flood-color="#0d0f1a" flood-opacity="0.18"/>
      </filter>
    </defs>
    <rect width="${W}" height="${H}" fill="url(#bg)"/>
    <rect x="${x}" y="${y}" width="${w}" height="${h + bar}" rx="${radius}" fill="#ffffff" filter="url(#shadow)"/>
    ${bar ? `<path d="M${x},${y + radius} a${radius},${radius} 0 0 1 ${radius},-${radius} h${w - radius * 2} a${radius},${radius} 0 0 1 ${radius},${radius} v${bar - radius} h-${w} z" fill="#f3f3f1"/>
      <line x1="${x}" y1="${y + bar}" x2="${x + w}" y2="${y + bar}" stroke="#e3e3df" stroke-width="${SCALE}"/>
      ${dot(x + 16 * SCALE, "#ff5f57")}${dot(x + 32 * SCALE, "#febc2e")}${dot(x + 48 * SCALE, "#28c840")}` : ""}
  </svg>`;
  // Round the capture's corners (the bottom ones always; the top ones only
  // for a bare card, since a window's title bar covers them).
  const mask = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
    <rect x="0" y="${bar ? -radius : 0}" width="${w}" height="${h + (bar ? radius : 0)}" rx="${radius}" fill="#fff"/></svg>`);
  const rounded = await img.composite([{ input: mask, blend: "dest-in" }]).png().toBuffer();
  return sharp(Buffer.from(svg)).composite([{ input: rounded, left: x, top: y + bar }]);
}
