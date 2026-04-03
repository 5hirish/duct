const { test, expect } = require("@playwright/test");

const cleanRoutes = [
  "/for-product-intelligence",
  "/for-organic-growth",
  "/for-paid-ads",
  "/blog",
];

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
  for (const route of cleanRoutes) {
    test(`route ${route} loads`, async ({ page }) => {
      const response = await page.goto(route);
      expect(response && response.ok()).toBeTruthy();
      await expect(page.locator("body")).toBeVisible();
    });
  }
});

test("blog list navigates to post with slug", async ({ page }) => {
  await page.goto("/blog");
  const firstPostLink = page.locator('a[href^="/blog/post?slug="]').first();
  await expect(firstPostLink).toBeVisible();
  const href = await firstPostLink.getAttribute("href");
  expect(href).toMatch(/^\/blog\/post\?slug=/);
  await page.goto(href);
  await expect(page).toHaveURL(/\/blog\/post\?slug=/);
  await expect(page.locator("#article-title")).toContainText(/\S+/);
  await expect(page.locator("#prose")).toContainText(/.+/);
});

test("blog post renders valid slug content", async ({ page }) => {
  await page.goto(
    "/blog/post?slug=why-your-seo-metrics-arent-telling-you-the-full-story"
  );
  await expect(page.locator("#article-title")).toContainText(
    "Why Your SEO Metrics Aren't Telling You the Full Story"
  );
  await expect(page.locator("#prose")).not.toContainText("No article specified.");
  await expect(page.locator("#prose")).not.toContainText("Article not found");
});

test("blog post missing slug shows fallback", async ({ page }) => {
  await page.goto("/blog/post");
  await expect(page.locator("#prose")).toContainText("No article specified.");
});

test("blog post invalid slug shows not found fallback", async ({ page }) => {
  await page.goto("/blog/post?slug=does-not-exist");
  await expect(page.locator("#article-title")).toContainText("Article not found");
});
