const { test, expect } = require("@playwright/test");

// The integrations pages are generated from the backend (scripts/build_integrations.py);
// its --check already proves they match the code. What only a browser can prove is that
// the hub's links land on real pages and that the facts are in the HTML a crawler reads.

test("the hub links every connector page, and each one renders", async ({ page, request }) => {
  await page.goto("/integrations/");
  await expect(page.locator("h1")).toContainText(/tools/i);
  expect(await page.locator(".ig-card").count()).toBeGreaterThanOrEqual(12);

  const hrefs = await page.locator("a.ig-card.is-link").evaluateAll((els) => els.map((a) => a.getAttribute("href")));
  expect(hrefs.length).toBeGreaterThanOrEqual(4);
  for (const href of hrefs) {
    const res = await request.get(href);
    expect(res.ok(), href).toBeTruthy();
    expect(await res.text()).toContain('class="ig-lockup"');
  }
});

// A crawler without JavaScript must still read what Duct can change and the FAQ it quotes.
test("a connector page carries its changes and FAQ without JavaScript", async ({ request }) => {
  const raw = await (await request.get("/integrations/google-ads")).text();
  expect(raw).toContain('<link rel="canonical" href="https://getduct.ai/integrations/google-ads"/>');
  expect(raw).toContain("Set campaign daily budget");
  expect(raw).toContain('"@type":"FAQPage"');
  expect(raw).toContain('"@type":"BreadcrumbList"');

  const readOnly = await (await request.get("/integrations/chatgpt-ads")).text();
  expect(readOnly).toContain('class="ig-readonly-big">Nothing.');
});

test("the site nav reaches the hub", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('a[href="/integrations/"]').first()).toBeAttached();
});
