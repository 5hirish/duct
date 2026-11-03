#!/usr/bin/env node
/**
 * The page frame, measured in a real browser.
 *
 * `check:design` and `check-page-frame` read the source. This one renders
 * every framed screen, signed in against the fixture backend, at a phone, the
 * desktop app's default width and a laptop, and fails on what the 2026-11-02
 * UI audit found by looking:
 *
 *   - a page title that is not where every other page's title is, or not the
 *     same size (six left edges, three sizes and three weights, before);
 *   - a page wider than the window (Models was 56px wider than a phone);
 *   - a header status that wraps (one line of state on a desktop, two on a
 *     phone; it is not a paragraph);
 *   - cards in one row of a grid whose footers do not share a baseline (the
 *     "Not connected" lines stepped 17px across the Connections grid);
 *   - a title truncated to a few letters because its row crushed it rather
 *     than wrapping (a change set's title read "Ac" on a phone);
 *   - a wide column centred inside a left-aligned page, so the content starts
 *     somewhere other than under its title.
 *
 * It needs the app running (APP, default http://localhost:3003) and starts the
 * fixture backend itself (scripts/mock-agent-backend.mjs on MOCK_PORT, 8012),
 * with the story from scripts/shots so the screens have something on them.
 * Playwright comes from site/, which already installs it.
 *
 *   npm run dev                          # in app/, once
 *   npm run check:layout                 # every screen, three widths
 *   ROUTES=/connections npm run check:layout
 */
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const req = createRequire(import.meta.url);
// site/ installs Playwright for its own E2E tests; PLAYWRIGHT_FROM points at
// another install (a worktree without its own site/node_modules).
const { chromium } = req(req.resolve("playwright", { paths: [process.env.PLAYWRIGHT_FROM || join(REPO, "site")] }));
const fixtures = await import(join(REPO, "scripts/shots/fixtures.mjs"));
const { STORY } = await import(join(REPO, "app/src/lib/__fixtures__/solo-story.mjs"));

const APP = process.env.APP || "http://localhost:3003";
const API = process.env.API || "http://localhost:8002";
const MOCK_PORT = Number(process.env.MOCK_PORT || 8012);
const MOCK = `http://localhost:${MOCK_PORT}`;
const P = STORY.project.id;

const ROUTES = process.env.ROUTES
  ? process.env.ROUTES.split(",")
  : [
      "/insights/organic-growth", "/audit/seo", "/content", "/content?tab=brand", "/execute", "/connections",
      "/artifacts", "/activity", "/usage", "/projects", `/project/${P}`,
      "/settings/models", "/settings/profile", "/settings/agents",
    ];
const WIDTHS = [
  { width: 390, height: 844 },
  { width: 1100, height: 760 },
  { width: 1440, height: 900 },
];
const PX = 1; // sub-pixel rounding

const build = mkdtempSync(join(tmpdir(), "duct-layout-"));
writeFileSync(join(build, "insights-pause.json"), JSON.stringify(fixtures.insightsFrames()));
writeFileSync(join(build, "content-plan.json"), JSON.stringify(fixtures.contentFrames()));
writeFileSync(join(build, "audit-run.json"), JSON.stringify(fixtures.auditFrames()));
writeFileSync(join(build, "routes.json"), JSON.stringify(fixtures.routes()));
const mock = spawn(process.execPath, [join(REPO, "app/scripts/mock-agent-backend.mjs"), String(MOCK_PORT)], {
  env: { ...process.env, FIXTURES_DIR: build, ROUTES_FILE: join(build, "routes.json"), FRAME_MS: "20" },
  stdio: ["ignore", "ignore", "inherit"],
});

const failures = [];
const fail = (where, what) => failures.push(`${where}  ${what}`);

try {
  await waitFor(`${MOCK}/api/agents`, 15000);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const viewport of WIDTHS) {
      const context = await browser.newContext({ viewport, colorScheme: "dark", locale: "en-GB" });
      await context.route(new RegExp(`^${API.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/`), (route) =>
        route.continue({ url: route.request().url().replace(API, MOCK) }));
      await context.addCookies([{ name: "duct_consent", value: "rejected", url: APP }]);
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      await signIn(page);

      const titles = [];
      for (const route of ROUTES) {
        const where = `${route} @${viewport.width}`;
        await page.goto(`${APP}${route}`, { waitUntil: "domcontentloaded" });
        await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
        await page.waitForSelector('[data-slot="page-header"] h1', { timeout: 20000 }).catch(() => {});
        await page.waitForTimeout(400);
        const m = await page.evaluate(measure);
        if (m.h1Count !== 1) fail(where, `${m.h1Count} visible <h1>, expected 1`);
        if (!m.header) {
          fail(where, "no PageHeader");
          continue;
        }
        if (Math.abs(m.header.left - m.page.left) > PX) {
          fail(where, `title starts at ${m.header.left}px, its page at ${m.page.left}px`);
        }
        titles.push({ route, ...m.header });
        if (m.overflow > PX) fail(where, `page is ${m.overflow}px wider than the window`);
        // One line of state on a desktop; a phone may take two.
        const maxLines = viewport.width < 640 ? 2 : 1;
        if (m.statusLines > maxLines) fail(where, `header status wraps to ${m.statusLines} lines`);
        for (const row of m.misalignedRows) {
          fail(where, `card footers in one grid row differ by ${row}px`);
        }
        for (const block of m.centred) {
          fail(where, `a ${block}px column is centred inside a left-aligned page — it moves the content's left edge off the title's`);
        }
        for (const text of m.squeezed) {
          fail(where, `"${text.text}" is cut to ${text.width}px — the layout should wrap, not crush it`);
        }
      }

      // Same left edge and same size for every page title at this width.
      const plain = titles.filter((t) => t.size !== "hero");
      const lefts = new Set(titles.map((t) => Math.round(t.left)));
      if (lefts.size > 1) {
        fail(`@${viewport.width}`, `page titles start at ${[...lefts].join(", ")}px — one edge expected`);
      }
      const sizes = new Set(plain.map((t) => t.fontSize));
      if (sizes.size > 1) fail(`@${viewport.width}`, `page titles at ${[...sizes].join(", ")} — one size expected`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
} finally {
  mock.kill();
}

if (failures.length) {
  console.error(`✗ ${failures.length} layout failure(s):`);
  for (const f of failures) console.error(`    ${f}`);
  console.error(
    "\n  Each one is a rule in app/DESIGN.md (\"The page frame\"). Fix the screen, not the check:" +
      "\n  titles come from PageHeader, grids from TileGrid, cards from ui/card with a CardFooter."
  );
  process.exit(1);
}
console.log(`layout OK — ${ROUTES.length} screens × ${WIDTHS.length} widths`);

// Runs in the page.
function measure() {
  const main = document.querySelector("#main-content") || document.body;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
  };
  const h1s = [...main.querySelectorAll("h1")].filter(visible);
  const headerEl = main.querySelector('[data-slot="page-header"]');
  const pageEl = main.querySelector('[data-slot="page"]');
  let header = null;
  let statusLines = 0;
  if (headerEl && pageEl) {
    const h1 = headerEl.querySelector("h1");
    header = {
      left: Math.round(h1.getBoundingClientRect().left * 10) / 10,
      fontSize: getComputedStyle(h1).fontSize,
      size: headerEl.dataset.size,
    };
    const status = headerEl.querySelector('[data-slot="page-status"]');
    if (status) {
      const lh = parseFloat(getComputedStyle(status).lineHeight) || 20;
      // line-clamp hides the overflow, so ask for the height it wanted.
      status.style.webkitLineClamp = "unset";
      status.style.display = "block";
      statusLines = Math.round(status.scrollHeight / lh);
      status.style.webkitLineClamp = "";
      status.style.display = "";
    }
  }
  const misalignedRows = [];
  for (const grid of main.querySelectorAll('[data-slot="tile-grid"]')) {
    const rows = new Map();
    for (const cell of grid.children) {
      if (!visible(cell)) continue;
      const top = Math.round(cell.getBoundingClientRect().top);
      if (!rows.has(top)) rows.set(top, []);
      rows.get(top).push(cell);
    }
    for (const cells of rows.values()) {
      const feet = cells
        .map((c) => c.matches('[data-slot="card"]') ? c.querySelector(':scope > [data-slot="card-footer"]') : null)
        .filter(Boolean)
        .map((f) => f.getBoundingClientRect().bottom);
      if (feet.length < 2) continue;
      const spread = Math.round(Math.max(...feet) - Math.min(...feet));
      if (spread > 1) misalignedRows.push(spread);
    }
  }
  // Truncation is for a long name in a column that has room for most of it;
  // a title ellipsised to a few letters means the row needed to wrap.
  const squeezed = [...main.querySelectorAll(".truncate, .line-clamp-1, .line-clamp-2")]
    .filter((el) => visible(el) && el.textContent.trim().length > 6)
    .filter((el) => el.clientWidth < 72 && el.scrollWidth > el.clientWidth + 1)
    .slice(0, 5)
    .map((el) => ({ text: el.textContent.trim().slice(0, 30), width: Math.round(el.clientWidth) }));
  // A wide block centred with auto margins inside a framed page: its left
  // edge leaves the title's, which is the misalignment the Brand tab had at
  // wide windows (a max-w-4xl form under left-aligned tabs).
  const pageBox = pageEl?.getBoundingClientRect();
  const centred = pageEl
    ? [...pageEl.querySelectorAll("*")]
        .filter((el) => visible(el))
        .filter((el) => {
          const cs = getComputedStyle(el);
          const l = parseFloat(cs.marginLeft);
          const r = parseFloat(cs.marginRight);
          const w = el.getBoundingClientRect().width;
          if (!(l > 24 && Math.abs(l - r) < 2 && w > 400 && w < pageBox.width - 48)) return false;
          for (let a = el.parentElement; a && a !== pageEl; a = a.parentElement) {
            if (getComputedStyle(a).textAlign === "center") return false;
          }
          return true;
        })
        .slice(0, 3)
        .map((el) => Math.round(el.getBoundingClientRect().width))
    : [];
  return {
    centred,
    squeezed,
    h1Count: h1s.length,
    header,
    page: pageEl ? { left: Math.round(pageEl.getBoundingClientRect().left * 10) / 10 } : null,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    statusLines,
    misalignedRows,
  };
}

async function signIn(page) {
  await page.goto(`${APP}/`);
  await page.evaluate(({ user, project }) => {
    const b64 = (o) => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/=+$/, "");
    const token = `${b64({ alg: "none" })}.${b64({ sub: user.email, name: user.name, email: user.email, exp: Math.floor(Date.now() / 1000) + 86400 })}.sig`;
    localStorage.setItem("duct_auth_token", token);
    localStorage.setItem("duct_projects", JSON.stringify([{ id: project.id, name: project.name, profile: { company: { name: project.name } } }]));
    localStorage.setItem("duct_active_project_id", project.id);
  }, { user: STORY.user, project: STORY.project });
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
