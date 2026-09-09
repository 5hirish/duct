const { test, expect } = require("@playwright/test");

/**
 * The consent gate in assets/duct.js.
 *
 * Everything here runs against `localtest.me`, a public wildcard that resolves
 * to 127.0.0.1, because the loader deliberately does nothing on localhost — a
 * tag firing against a developer measures nothing and asks a question no one
 * needs answered. Reaching the same server under a real hostname is the only
 * way to exercise the path a visitor takes.
 *
 * `/cdn-cgi/trace` does not exist on the static server, so the region lookup
 * fails, and a failed lookup is required to mean "ask" — that is the assertion
 * underneath most of these, not an artefact of the fixture.
 */

const ORIGIN = "http://localtest.me:4317";
const GTM_PATTERN = /googletagmanager\.com/;

/** Records GTM requests and stops them leaving the machine. */
async function trapGtm(page) {
  const hits = [];
  await page.route(GTM_PATTERN, (route) => {
    hits.push(route.request().url());
    return route.abort();
  });
  return hits;
}

const banner = (page) => page.getByRole("dialog", { name: "Cookies, honestly" });

/** The stored decision, read the way a browser stores it. */
async function consentCookie(page) {
  const jar = await page.context().cookies();
  return jar.find((c) => c.name === "duct_consent") || null;
}

test("asks before loading anything, and declining loads nothing", async ({ page }) => {
  const gtm = await trapGtm(page);
  await page.goto(`${ORIGIN}/`);

  await expect(banner(page)).toBeVisible();
  expect(gtm).toHaveLength(0);

  // Decline has to be the same kind of control as Accept, not a text link.
  const decline = page.getByRole("button", { name: "Decline" });
  const accept = page.getByRole("button", { name: "Accept" });
  await expect(decline).toBeVisible();
  await expect(accept).toBeVisible();

  await decline.click();
  await expect(banner(page)).toBeHidden();
  await page.waitForTimeout(3500); // outlast the idle-load fallback
  expect(gtm).toHaveLength(0);
  expect((await consentCookie(page))?.value).toBe("denied");
});

test("a decline survives the next page load", async ({ page }) => {
  const gtm = await trapGtm(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Decline" }).click();

  await page.goto(`${ORIGIN}/about`);
  await expect(banner(page)).toBeHidden();
  await page.waitForTimeout(3500);
  expect(gtm).toHaveLength(0);
});

test("accepting loads the container", async ({ page }) => {
  const gtm = await trapGtm(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Accept" }).click();

  await expect(banner(page)).toBeHidden();
  await expect.poll(() => gtm.length).toBeGreaterThan(0);
  expect(gtm[0]).toContain("GTM-PKL589SW");
  expect((await consentCookie(page))?.value).toBe("granted");
});

test("consent defaults are denied before any decision", async ({ page }) => {
  await trapGtm(page);
  await page.goto(`${ORIGIN}/`);
  await expect(banner(page)).toBeVisible();

  // Consent Mode reads the arguments objects queued on dataLayer. If the
  // default is missing or granted, a tag loading later is unrestricted.
  const defaults = await page.evaluate(() =>
    (window.dataLayer || [])
      .map((entry) => Array.from(entry || []))
      .filter((args) => args[0] === "consent" && args[1] === "default")
      .map((args) => args[2]),
  );
  expect(defaults).toHaveLength(1);
  expect(defaults[0].analytics_storage).toBe("denied");
  expect(defaults[0].ad_storage).toBe("denied");
});

test("the footer link reopens the choice after it was made", async ({ page }) => {
  await trapGtm(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Decline" }).click();
  await expect(banner(page)).toBeHidden();

  await page.getByRole("link", { name: "Cookie settings" }).click();
  await expect(banner(page)).toBeVisible();
});

test("the decision is stored where both surfaces can read it", async ({ page }) => {
  await trapGtm(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Accept" }).click();

  // Scoped to the registrable domain, not the exact host. In production that is
  // `.getduct.ai`, so answering on the marketing site also answers for
  // app.getduct.ai and for the desktop shell, which loads app.getduct.ai.
  // localStorage would be per-origin and ask the same person three times.
  const cookie = await consentCookie(page);
  expect(cookie?.domain).toBe(".localtest.me");
  expect(cookie?.path).toBe("/");

  // And it outlives the tab, or the question returns on every visit.
  expect(cookie?.expires).toBeGreaterThan(Date.now() / 1000 + 60 * 60 * 24 * 150);
});
