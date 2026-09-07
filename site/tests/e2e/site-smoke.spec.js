const { test, expect } = require("@playwright/test");

const cleanRoutes = [
  "/for-product-intelligence",
  "/for-organic-growth",
  "/for-paid-ads",
  "/blog/",
];

// Content pages that must render but are not required to be linked from the
// home page's own nav (they live in the footer and the simple nav).
const contentRoutes = ["/about", "/doctrine"];

const POST_PATH = "/blog/why-your-seo-metrics-arent-telling-you-the-full-story";

test("home page navigation uses clean links", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Duct/i);

  const badLinks = page.locator('a[href*=".html"]');
  await expect(badLinks).toHaveCount(0);

  for (const route of cleanRoutes) {
    const links = page.locator(`a[href="${route}"]`);
    const count = await links.count();
    let hasVisibleLink = false;

    for (let i = 0; i < count; i++) {
      if (await links.nth(i).isVisible()) {
        hasVisibleLink = true;
        break;
      }
    }

    expect(hasVisibleLink).toBeTruthy();
  }
});

test.describe("clean routes render", () => {
  for (const route of [...cleanRoutes, ...contentRoutes]) {
    test(`route ${route} loads`, async ({ page }) => {
      const response = await page.goto(route);
      expect(response && response.ok()).toBeTruthy();
      await expect(page.locator("body")).toBeVisible();
    });
  }
});

test("blog list navigates to a static post URL", async ({ page }) => {
  await page.goto("/blog/");
  const firstPostLink = page.locator('a[href^="/blog/"][href$="-story"]').first();
  await expect(firstPostLink).toBeVisible();
  const href = await firstPostLink.getAttribute("href");
  expect(href).not.toContain("?slug=");
  await firstPostLink.click();
  await expect(page).toHaveURL(/\/blog\/[a-z0-9-]+$/);
  await expect(page.locator("h1")).toContainText(/\S+/);
  expect(((await page.locator("#prose").innerText()) || "").length).toBeGreaterThan(2000);
});

// The regression this guards: posts used to render client-side, so a crawler
// without JavaScript received 49 characters and every post shared the canonical
// /blog/post. Assert against the raw bytes, not the rendered DOM.
test("post HTML carries the article without JavaScript", async ({ request }) => {
  const res = await request.get(POST_PATH);
  expect(res.ok()).toBeTruthy();
  const raw = await res.text();

  const text = raw
    .slice(raw.indexOf("<body"))
    .replace(/<(script|style|noscript)[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  expect(text.length).toBeGreaterThan(3000);

  expect(raw).toContain(`<link rel="canonical" href="https://getduct.ai${POST_PATH}"/>`);
  expect(raw).toMatch(/<meta name="description" content="[^"]{60,}"/);
  expect(raw).toContain('"@type": "Article"');
  expect(raw).toContain("Shirish Kadam");
  expect(raw).toContain("<h2>");
});

test("each post declares its own canonical", async ({ request }) => {
  const canonicals = [];
  for (const slug of ["why-your-seo-metrics-arent-telling-you-the-full-story",
                      "keyword-gap-analysis-without-a-spreadsheet"]) {
    const raw = await (await request.get(`/blog/${slug}`)).text();
    canonicals.push(raw.match(/<link rel="canonical" href="([^"]+)"/)[1]);
  }
  expect(new Set(canonicals).size).toBe(2);
});

test("legacy ?slug= links still reach the post", async ({ page }) => {
  await page.goto("/blog/post?slug=keyword-gap-analysis-without-a-spreadsheet");
  await expect(page).toHaveURL(/\/blog\/keyword-gap-analysis-without-a-spreadsheet$/);
  expect(((await page.locator("#prose").innerText()) || "").length).toBeGreaterThan(2000);
});

test("legacy link with a missing or unknown slug falls back to the index", async ({ page }) => {
  for (const url of ["/blog/post", "/blog/post?slug=nope-not-a-post"]) {
    await page.goto(url);
    await expect(page).toHaveURL(/\/blog\/$/);
  }
});
