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

const { PORT } = require("./port");
const ORIGIN = `http://localtest.me:${PORT}`;
// Google Tag Manager and GA4 were removed; nothing may fetch them again.
const GOOGLE_TAGS_PATTERN = /googletagmanager\.com|google-analytics\.com/;
// PostHog loads through the app's reverse proxy, never from posthog.com, so
// this is the one address its library can come from.
const POSTHOG_PATTERN = /app\.getduct\.ai\/ingest\//;

/** Records requests matching `pattern` and stops them leaving the machine. */
async function trap(page, pattern) {
  const hits = [];
  await page.route(pattern, (route) => {
    hits.push(route.request().url());
    return route.abort();
  });
  return hits;
}

const trapGoogleTags = (page) => trap(page, GOOGLE_TAGS_PATTERN);
const trapPosthog = (page) => trap(page, POSTHOG_PATTERN);

const banner = (page) => page.getByRole("dialog", { name: "Cookies, honestly" });

/** The stored decision, read the way a browser stores it. */
async function consentCookie(page) {
  const jar = await page.context().cookies();
  return jar.find((c) => c.name === "duct_consent") || null;
}

test("asks before loading anything, and declining loads nothing", async ({ page }) => {
  const posthog = await trapPosthog(page);
  await page.goto(`${ORIGIN}/`);

  await expect(banner(page)).toBeVisible();
  expect(posthog).toHaveLength(0);

  // Decline has to be the same kind of control as Accept, not a text link.
  const decline = page.getByRole("button", { name: "Decline" });
  const accept = page.getByRole("button", { name: "Accept" });
  await expect(decline).toBeVisible();
  await expect(accept).toBeVisible();

  await decline.click();
  await expect(banner(page)).toBeHidden();
  await page.waitForTimeout(3500); // outlast the idle-load fallback
  expect(posthog).toHaveLength(0);
  expect((await consentCookie(page))?.value).toBe("denied");
});

test("a decline survives the next page load", async ({ page }) => {
  const posthog = await trapPosthog(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Decline" }).click();

  await page.goto(`${ORIGIN}/about`);
  await expect(banner(page)).toBeHidden();
  await page.waitForTimeout(3500);
  expect(posthog).toHaveLength(0);
});

test("accepting loads PostHog and nothing from Google", async ({ page }) => {
  const google = await trapGoogleTags(page);
  const posthog = await trapPosthog(page);
  await page.goto(`${ORIGIN}/`);
  // Nothing before the answer, PostHog included: it rides the same gate.
  await expect(banner(page)).toBeVisible();
  expect(posthog).toHaveLength(0);
  await page.getByRole("button", { name: "Accept" }).click();

  await expect(banner(page)).toBeHidden();
  await expect.poll(() => posthog.length).toBeGreaterThan(0);
  expect(posthog[0]).toBe("https://app.getduct.ai/ingest/static/array.js");
  expect((await consentCookie(page))?.value).toBe("granted");
  expect(google).toHaveLength(0);
});

test("PostHog starts with inputs masked, queries stripped and queued events", async ({ page }) => {
  // A stand-in for array.js that records how it was started, so the promises
  // the privacy policy makes are checked against the config that carries them.
  await page.route(POSTHOG_PATTERN, (route) =>
    route.fulfill({
      contentType: "application/javascript",
      // The loader asks for it crossorigin, as PostHog's own snippet does;
      // PostHog's asset host answers with the same header.
      headers: { "Access-Control-Allow-Origin": "*" },
      body: `window.posthog = {
        captured: [], registered: {},
        init: function (token, config) { this.token = token; this.config = config; config.loaded(this); },
        register: function (props) { Object.assign(this.registered, props); },
        has_opted_out_capturing: function () { return false; },
        capture: function (event, props) { this.captured.push([event, props]); }
      };`,
    }),
  );
  await page.goto(`${ORIGIN}/`);
  // Tracked before the answer: held, not sent, until PostHog is allowed.
  await page.evaluate(() => window.ductTrack("download_started", { os: "macos" }));
  await page.getByRole("button", { name: "Accept" }).click();
  await page.waitForFunction(() => window.posthog && window.posthog.config);

  const seen = await page.evaluate(() => {
    const ph = window.posthog;
    const event = ph.config.before_send({
      properties: {
        $current_url: "https://getduct.ai/blog/?category=growth&email=a@b.co#faq",
        $referrer: "https://news.example.org/item?id=1",
        utm_source: "newsletter",
      },
      $set_once: { $initial_current_url: "https://getduct.ai/?gclid=abc" },
    });
    return {
      config: ph.config,
      event,
      registered: ph.registered,
      captured: ph.captured,
    };
  });
  expect(seen.config.session_recording.maskAllInputs).toBe(true);
  expect(seen.config.enable_recording_console_log).toBe(false);
  expect(seen.config.cross_subdomain_cookie).toBe(true);
  expect(seen.config.person_profiles).toBe("identified_only");
  expect(seen.event.properties.$current_url).toBe("https://getduct.ai/blog/");
  expect(seen.event.properties.$referrer).toBe("https://news.example.org/item");
  expect(seen.event.properties.utm_source).toBe("newsletter");
  expect(seen.event.$set_once.$initial_current_url).toBe("https://getduct.ai/");
  expect(seen.registered).toMatchObject({ surface: "site", locale: "en" });
  expect(["mac", "windows", "linux", "other"]).toContain(seen.registered.platform);
  expect(seen.captured).toEqual([["download_started", { os: "macos" }]]);
});

test("declining after accepting clears PostHog's cookies and storage", async ({ page }) => {
  await trapPosthog(page);
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Accept" }).click();
  await expect(banner(page)).toBeHidden();

  // What PostHog would have written: its cookie on the registrable domain (so
  // app.getduct.ai shares it) and on the host, and its localStorage copy.
  await page.context().addCookies([
    { name: "ph_phc_test_posthog", value: "x", domain: ".localtest.me", path: "/" },
    { name: "ph_phc_test_host", value: "x", domain: "localtest.me", path: "/" },
  ]);
  await page.evaluate(() => {
    localStorage.setItem("ph_phc_test_posthog", "{}");
    localStorage.setItem("duct_site_lang", "en");
  });

  await page.getByRole("link", { name: "Cookie settings" }).click();
  await Promise.all([
    page.waitForEvent("load"), // a withdrawal reloads the page
    page.getByRole("button", { name: "Decline" }).click(),
  ]);

  const jar = await page.context().cookies();
  expect(jar.filter((c) => c.name.startsWith("ph_"))).toEqual([]);
  expect((await consentCookie(page))?.value).toBe("denied");
  const stored = await page.evaluate(() => Object.keys(localStorage));
  expect(stored.filter((k) => k.startsWith("ph_"))).toEqual([]);
  // Only PostHog's keys go; the site's own preferences stay.
  expect(stored).toContain("duct_site_lang");
});


test("the footer link reopens the choice after it was made", async ({ page }) => {
  await page.goto(`${ORIGIN}/`);
  await page.getByRole("button", { name: "Decline" }).click();
  await expect(banner(page)).toBeHidden();

  await page.getByRole("link", { name: "Cookie settings" }).click();
  await expect(banner(page)).toBeVisible();
});

test("the decision is stored where both surfaces can read it", async ({ page }) => {
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

test("cookies Google Analytics left behind are deleted on the next visit", async ({ page }) => {
  // Set on the registrable domain, as GA4 and the Conversion Linker set them.
  await page.context().addCookies([
    { name: "_ga", value: "GA1.1.1.1", domain: ".localtest.me", path: "/" },
    { name: "_ga_SXH5LYVTJ8", value: "GS1.1.1", domain: ".localtest.me", path: "/" },
    { name: "_gcl_au", value: "1.1.1", domain: ".localtest.me", path: "/" },
  ]);
  await page.goto(`${ORIGIN}/`);
  await expect(banner(page)).toBeVisible();

  const names = (await page.context().cookies()).map((c) => c.name);
  expect(names.filter((name) => /^_g(a|cl)/.test(name))).toEqual([]);
});
