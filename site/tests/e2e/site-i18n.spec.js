const { test, expect } = require("@playwright/test");

// The translated trees are generated (scripts/build_site_i18n.py) from the
// English pages. These guard the plumbing a generator cannot check by diffing
// its own output: that the pages are reachable at their clean URLs, that the
// browser is told which language it is reading, that every page links to its
// alternates in both directions, and that the switcher lands on the same page
// in the other language rather than on the home page.

const LOCALES = ["es", "pt-br", "de", "ja"];

for (const locale of LOCALES) {
  test(`/${locale}/ renders in its language with alternates`, async ({ page }) => {
    const response = await page.goto(`/${locale}/`);
    expect(response && response.ok()).toBeTruthy();
    await expect(page.locator("html")).toHaveAttribute("lang", /^(es|pt-BR|de|ja)$/);
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
    expect(canonical).toBe(`https://getduct.ai/${locale}/`);
    const alternates = page.locator('link[rel="alternate"][hreflang]');
    expect(await alternates.count()).toBe(2 + LOCALES.length);
    await expect(page.locator('link[rel="alternate"][hreflang="x-default"]')).toHaveAttribute("href", "https://getduct.ai/");
  });
}

test("the English page links to every translation", async ({ request }) => {
  const res = await request.get("/about");
  expect(res.ok()).toBeTruthy();
  const raw = await res.text();
  for (const locale of LOCALES) {
    expect(raw).toContain(`href="https://getduct.ai/${locale}/about"`);
  }
});

test("a translated page loads its translated partials and assets", async ({ page }) => {
  const missing = [];
  page.on("response", (r) => {
    if (r.status() >= 400) missing.push(`${r.status()} ${r.url()}`);
  });
  await page.goto("/es/about");
  await page.waitForFunction(() => window.__DUCT_PARTIALS_READY === true);
  expect(missing).toEqual([]);
  // The nav came from /es/partials/, so its language select is set to Spanish.
  await expect(page.locator("select[data-duct-lang]").first()).toHaveValue("es");
});

test("the switcher keeps the page and changes the language", async ({ page }) => {
  await page.goto("/es/tools/cpa-calculator");
  await page.waitForFunction(() => window.__DUCT_PARTIALS_READY === true);
  // The bar's select is hidden with .nav-links on a phone; the drawer carries
  // a copy, so open the drawer there and use whichever select is visible.
  const visibleSelect = async () => {
    if (!(await page.locator("select[data-duct-lang]").first().isVisible())) {
      await page.locator(".nav-toggle").click();
    }
    return page.locator("select[data-duct-lang]:visible").first();
  };
  await (await visibleSelect()).selectOption("de");
  await expect(page).toHaveURL(/\/de\/tools\/cpa-calculator$/);
  await page.waitForFunction(() => window.__DUCT_PARTIALS_READY === true);
  await (await visibleSelect()).selectOption("en");
  await expect(page).toHaveURL(/\/tools\/cpa-calculator$/);
});

test("on an English-only page the switcher goes to the language's home", async ({ page }) => {
  // Blog posts and the changelog are not translated and carry no hreflang
  // alternates; /es/blog/… does not exist, so the switch must land somewhere
  // that does.
  // Posts are pre-rendered with their partials inline, so there is no
  // partials-ready event here; the rewritten footer link is the ready signal.
  await page.goto("/blog/keyword-gap-analysis-without-a-spreadsheet");
  await expect(page.locator('link[rel="alternate"][hreflang]')).toHaveCount(0);
  await expect(page.locator('a[data-duct-lang-link="de"]')).toHaveAttribute("href", "/de/");
  if (!(await page.locator("select[data-duct-lang]").first().isVisible())) {
    await page.locator(".nav-toggle").click();
  }
  await page.locator("select[data-duct-lang]:visible").first().selectOption("es");
  await expect(page).toHaveURL(/\/es\/$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
});

test("translated pages carry the JavaScript strings", async ({ page }) => {
  await page.goto("/de/");
  const dict = await page.evaluate(() => window.DUCT_I18N || null);
  expect(dict).not.toBeNull();
  expect(Object.keys(dict).length).toBeGreaterThan(5);
});
