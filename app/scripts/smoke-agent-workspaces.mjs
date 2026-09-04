// Drives the three agent workspaces in a headless browser against the
// fixture-replaying mock, and screenshots each state. Not a CI gate — the
// reducer tests are that — but the cheapest way to *look* at a change to the
// agent shell before calling it done, which app/AGENTS.md asks for.
//
//   npm run mock:agents                       # terminal 1, on :8012
//   npm run dev                               # terminal 2, on :3003 (its backend calls are rerouted below)
//   node scripts/smoke-agent-workspaces.mjs   # terminal 3; screenshots land in ./smoke-shots
//
// Playwright comes from site/ (the only workspace that installs it); the
// browser needs `npx --prefix ../site playwright install chromium` once.
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

await page.getByRole("button", { name: "Signups", exact: true }).click();
await page.getByRole("button", { name: /Continue/ }).click();
await page.getByText("I proposed two changes above.").waitFor({ timeout: 30000 });
await page.locator('[role="status"]', { hasText: "Ready" }).first().waitFor({ timeout: 15000 });
console.log("insights: brief + change set; status:", await status());
await shot("insights-3-ready");

await page.getByLabel("Message the insights agent").fill("and what about mobile?");
await page.keyboard.press("Enter");
await page.getByText("Mobile CPA is flat.").waitFor({ timeout: 30000 });
console.log("insights: follow-up answered; status:", await status());
await shot("insights-4-followup");

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

// ---------------------------------------------------------------- audit
const auditId = randomUUID();
await page.evaluate((id) => {
  sessionStorage.setItem(`audit_session_${id}`, JSON.stringify({ url: "https://getduct.ai", project_id: "p1", report_mode: "template" }));
}, auditId);
await page.goto(`${APP}/audit/seo/${auditId}`);
await page.getByText("Your SEO report is ready").waitFor({ timeout: 30000 });
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
  console.log("FAILED:", String(err).split("\n")[0]);
  await shot("failure");
}
console.log("console errors:", errors.length ? errors : "none");
await browser.close();
