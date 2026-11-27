// Drives the three agent workspaces in a headless browser against the
// fixture-replaying mock, and screenshots each state. The checkpoints it
// visits are asserted, not just logged, so a broken pause card or a reattach
// that loses its card fails loudly (exit 1).
//
//   npm run mock:agents                       # terminal 1, on :8012
//   npm run dev                               # terminal 2, on :3003 (its backend calls are rerouted below)
//   node scripts/smoke-agent-workspaces.mjs   # terminal 3; screenshots land in ./smoke-shots
//
// Playwright comes from site/ (the only workspace that installs it); the
// browser needs `npx --prefix ../site playwright install chromium` once.
//
// Runs in CI (app.yml, the app-layout job) against the production build. It
// was kept out on the fear of SSE flake; what that cost was a composer stuck
// on "Connecting…" after every reload and follow-up pictures that never
// reached the agent, both invisible to the reducer tests, which replay events
// and so never see a reload that receives none. A flake here is a bug to fix
// in the mock's timing, not a reason to take the journey out again.
import { chromium } from "../../site/node_modules/playwright/index.mjs";
import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";

const APP = process.env.APP || "http://localhost:3003";
const MOCK = process.env.MOCK || "http://localhost:8012";
const OUT = process.env.OUT || "./smoke-shots";
mkdirSync(OUT, { recursive: true });
const errors = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1360, height: 860 } });
// Every call the app makes to its backend goes to the mock instead, so the
// real backend on 8002 is never touched by a smoke run.
await context.route(/^http:\/\/localhost:8002\//, (route) =>
  route.continue({ url: route.request().url().replace("http://localhost:8002", MOCK) }),
);
const page = await context.newPage();
page.setDefaultTimeout(90000);
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
page.on("pageerror", (e) => errors.push("PAGEERROR " + String(e).slice(0, 300)));
page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.request().method()} ${r.url()}`); });

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("shot", name);
}
async function status() {
  return page.locator('[role="status"]').first().innerText().catch(() => "?");
}

await page.goto(`${APP}/`);
await page.evaluate(() => {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/=+$/, "");
  const token = `${b64({ alg: "none" })}.${b64({ sub: "smoke@example.com", name: "Smoke Tester", exp: Math.floor(Date.now() / 1000) + 86400 })}.sig`;
  localStorage.setItem("duct_auth_token", token);
  localStorage.setItem("duct_projects", JSON.stringify([{ id: "p1", name: "Demo project", profile: { company: { name: "Demo" } } }]));
  localStorage.setItem("duct_active_project_id", "p1");
  sessionStorage.clear();
});

let ok = true;
try {
// ---------------------------------------------------------------- insights
await page.goto(`${APP}/insights/session?q=${encodeURIComponent("why did CPA jump?")}&project=p1`);
await page.getByText("Which goal matters most?", { exact: true }).waitFor({ timeout: 30000 });
console.log("insights: pause on screen; status:", await status());
await shot("insights-1-pause");

// Reload mid-pause: the tab's handle reattaches to the same session and the
// card is put back from the session's state.
await page.reload();
await page.getByText("Which goal matters most?", { exact: true }).waitFor({ timeout: 30000 });
console.log("insights: after reload, card back; status:", await status());
await shot("insights-2-reload-reattached");

await page.getByRole("radio", { name: "Signups", exact: true }).click();
await page.getByRole("button", { name: /Continue/ }).click();

// Type the moment the turn resumes, while it is still streaming: the box
// stays open, the row shows as queued, and the mock hands the message over
// at its next wait point. (Typing any later races the mock's frame pace.)
await page.getByLabel("Message the insights agent").fill("and what about mobile?");
await page.keyboard.press("Enter");
await page.getByText("↳ Queued").waitFor({ timeout: 5000 });
console.log("insights: follow-up queued mid-turn; status:", await status());
await shot("insights-3-queued");

await page.getByText("I proposed two changes above.").waitFor({ timeout: 30000 });
await page.getByText("Mobile CPA is flat.").waitFor({ timeout: 30000 });
await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 15000 });
if (await page.getByText("↳ Queued").count()) throw new Error("queued mark was not released");
if (!(await page.getByText(/^Compacted ·/).count())) throw new Error("no compaction note in the transcript");
console.log("insights: brief, change set, queued follow-up answered; status:", await status());
await shot("insights-4-ready");

await page.setViewportSize({ width: 390, height: 800 });
await page.waitForTimeout(400);
await shot("insights-5-mobile");
await page.setViewportSize({ width: 1360, height: 860 });

// ---------------------------------------------------------------- content
await page.goto(`${APP}/content/sessions/new`);
await page.getByText("Here is your plan.").waitFor({ timeout: 30000 });
await page.waitForTimeout(600);
console.log("content: plan ready; status:", await status());
await shot("content-1-plan-ready");
await page.getByLabel("Message the content agent").fill("make day 3 about pricing");
await page.keyboard.press("Enter");
await page.getByText("day 3 is now pricing").waitFor({ timeout: 30000 });
await shot("content-2-followup");

// Reload once the reply has finished. The stream replays only what the rows
// do not hold, so a finished run sends nothing at all; the page must still
// leave "Connecting…" (it once sat there for good, box locked).
await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 15000 });
await page.waitForTimeout(500);  // the last frames are on the client, not still in the mock
await page.reload();
await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 15000 });
if (await page.getByLabel("Message the content agent").isDisabled()) throw new Error("composer still locked after reload");
console.log("content: reload of an idle run is ready; status:", await status());
await shot("content-3-reload-idle");

// A picture dropped on the composer is a tile, and the message that carries
// it reaches the agent with the picture in it. Each layer had its own test
// while follow-up pictures were silently dropped for eleven weeks; this
// asserts on what was posted, not on what the page drew.
const composer = page.locator("[data-composer]").first();
const drop = await page.evaluateHandle(() => {
  const d = new DataTransfer();
  const png = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="), (c) => c.charCodeAt(0));
  d.items.add(new File([png], "slide-3.png", { type: "image/png" }));
  return d;
});
await composer.dispatchEvent("dragenter", { dataTransfer: drop });
await composer.dispatchEvent("drop", { dataTransfer: drop });
await composer.locator('img[alt="slide-3.png"]').waitFor({ timeout: 5000 });
await page.getByLabel("Message the content agent").fill("does slide 3 fit?");
await Promise.all([
  page.waitForResponse((r) => r.url().endsWith("/messages") && r.request().method() === "POST"),
  page.keyboard.press("Enter"),
]);
const posted = await (await fetch(`${MOCK}/__mock/messages`)).json();
const last = posted.at(-1);
const blocks = Array.isArray(last?.content) ? last.content : [];
if (!blocks.some((b) => b.type === "image" && (b.source?.data || b.base64))) {
  throw new Error(`the dropped picture was not in the message: ${JSON.stringify(last).slice(0, 200)}`);
}
console.log("content: dropped picture posted with the message");
await shot("content-4-picture-sent");

// ---------------------------------------------------------------- audit
const auditId = randomUUID();
await page.evaluate((id) => {
  sessionStorage.setItem(`audit_session_${id}`, JSON.stringify({ url: "https://getduct.ai", project_id: "p1", report_mode: "template" }));
}, auditId);
await page.goto(`${APP}/audit/seo/${auditId}`);
await page.getByText("Your report is on the right").waitFor({ timeout: 30000 });
await page.waitForTimeout(600);
console.log("audit: report ready; status:", await status());
await shot("audit-1-ready");
await page.getByLabel("Message the audit agent").fill("why is the score 61?");
await page.keyboard.press("Enter");
await page.getByText("Try rephrasing").waitFor({ timeout: 30000 });
await shot("audit-2-turn-failed");
await page.getByLabel("Message the audit agent").fill("explain the title finding");
await page.keyboard.press("Enter");
await page.getByText("truncated in results").waitFor({ timeout: 30000 });
await shot("audit-3-recovered");

} catch (err) {
  ok = false;
  console.log("FAILED:", String(err).split("\n")[0]);
  await shot("failure");
}

// A console error, a page error, or a 4xx/5xx from any call along the way is
// a real failure even when every `waitFor` above was satisfied — the flow can
// render the right text and still have thrown on the way there.
if (errors.length) {
  ok = false;
  console.log("console/page/http errors:", errors);
} else {
  console.log("console errors: none");
}

await browser.close();
process.exit(ok ? 0 : 1);
