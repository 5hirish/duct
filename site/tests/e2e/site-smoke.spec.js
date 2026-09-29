const { test, expect } = require("@playwright/test");

const cleanRoutes = [
  "/for-product-intelligence",
  "/for-organic-growth",
  "/for-paid-ads",
  "/blog/",
];

// Content pages that must render but are not required to be linked from the
// home page's own nav (they live in the footer and the simple nav).
const contentRoutes = ["/about", "/open-source", "/doctrine", "/changelog/", "/tools/", "/tools/cpa-calculator"];

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
  expect(raw).toContain('"@type": "BlogPosting"');
  expect(raw).toContain('"@type": "BreadcrumbList"');
  expect(raw).toContain("Shirish Kadam");
  expect(raw).toMatch(/<h2 id="[a-z0-9-]+">/);
});

// The grid and its filter are generated from front matter; without the
// filter a reader looking for engineering posts scrolls past growth ones.
test("blog index filters posts by category and keeps it in the URL", async ({ page }) => {
  await page.goto("/blog/");
  const cards = page.locator(".blog-grid > li");
  const total = await cards.count();
  await page.locator('.blog-filter-chip[data-category="engineering"]').click();
  await expect(page).toHaveURL(/\?category=engineering$/);
  const visible = page.locator(".blog-grid > li:not([hidden])");
  expect(await visible.count()).toBeLessThan(total);
  for (const cat of await visible.evaluateAll((els) => els.map((e) => e.dataset.category))) {
    expect(cat).toBe("engineering");
  }
  await page.goto("/blog/?category=growth");
  await expect(page.locator('.blog-filter-chip[data-category="growth"]')).toHaveAttribute("aria-pressed", "true");
});

// A link post shares a post published elsewhere: its card leaves the site and
// says where it goes, and no copy of it is served here to compete with the original.
test("a link post's card goes to the original and has no page here", async ({ page, request }) => {
  await page.goto("/blog/");
  const card = page.locator('.blog-grid a.blog-card[href^="https://"]').first();
  await expect(card).toBeAttached();
  const href = await card.getAttribute("href");
  expect(new URL(href).hostname).not.toContain("getduct.ai");
  expect(await card.getAttribute("rel")).toContain("noopener");
  await expect(card.locator(".blog-card-meta")).toContainText("↗");
  const slug = new URL(await card.locator("img").getAttribute("src"), page.url()).pathname.match(/blog-(.+)\.jpg$/)[1];
  expect((await request.get(`/blog/${slug}`)).status()).toBe(404);
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

// The 404 page is the only page served from a URL it does not live at, so it is
// the only page whose asset paths must be root-absolute. A relative
// "assets/duct.css" resolves fine at /404.html and 404s everywhere else, which
// is how it shipped unstyled for every miss below the site root.
test("404 renders styled from a nested URL", async ({ page }) => {
  const broken = [];
  page.on("response", (res) => {
    if (res.status() >= 400 && !res.url().endsWith("/blog/no-such-page")) {
      broken.push(`${res.status()} ${res.url()}`);
    }
  });

  const response = await page.goto("/blog/no-such-page");
  expect(response && response.status()).toBe(404);
  expect(broken).toEqual([]);

  // Proves duct.css actually applied: the numeral is styled, not body text.
  const codeSize = await page
    .locator(".error-code")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(codeSize).toBeGreaterThan(60);

  // Shared nav and footer arrive via fetch, so they prove duct-partials.js loaded.
  await expect(page.locator("nav#nav")).toBeVisible();
  await expect(page.locator('a[href="/"]').first()).toBeVisible();
});

test("changelog lists releases with permanent anchors", async ({ page }) => {
  await page.goto("/changelog/");
  const releases = page.locator("article.cl-release");
  expect(await releases.count()).toBeGreaterThan(0);

  // The id is the permalink people share. An entry without one is a dead link,
  // and renaming one breaks every link already published.
  const id = await releases.first().getAttribute("id");
  expect(id).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await expect(page.locator(`article[id="${id}"] h2.cl-title`)).toContainText(/\S+/);

  const feed = await page.request.get("/changelog/feed.xml");
  expect(feed.ok()).toBeTruthy();
});
