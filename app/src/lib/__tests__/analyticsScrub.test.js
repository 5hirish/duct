import { afterEach, describe, expect, it, vi } from "vitest";

import { beforeSend, scrubPath, scrubUrl } from "../analytics/scrub.js";

// What must never leave the browser in an event: an OAuth code, an invitation
// token, a shared audit's id. Each is a credential that works for whoever
// holds the URL.
describe("scrub", () => {
  it("drops query strings and fragments", () => {
    expect(scrubUrl("https://app.getduct.ai/?auth_code=abc#x")).toBe("https://app.getduct.ai/");
    expect(scrubPath("/start?url=example.com")).toBe("/start");
  });

  it("replaces credentials that live in a path", () => {
    expect(scrubPath("/invite/s3cr3t")).toBe("/invite/[token]");
    expect(scrubUrl("https://app.getduct.ai/open/audit/9f1c/report")).toBe(
      "https://app.getduct.ai/open/audit/[token]/report",
    );
    expect(scrubPath("/insights/session")).toBe("/insights/session");
  });

  it("cleans every URL and path property, including person properties", () => {
    const event = beforeSend({
      event: "$pageview",
      properties: {
        $current_url: "https://app.getduct.ai/invite/abc?x=1",
        $referrer: "https://getduct.ai/?utm_source=x",
        $pathname: "/invite/abc",
        utm_source: "x",
      },
      $set_once: { $initial_current_url: "https://app.getduct.ai/?auth_code=1" },
    });
    expect(event.properties).toEqual({
      $current_url: "https://app.getduct.ai/invite/[token]",
      $referrer: "https://getduct.ai/",
      $pathname: "/invite/[token]",
      utm_source: "x",
    });
    expect(event.$set_once.$initial_current_url).toBe("https://app.getduct.ai/");
  });
});

// Several providers run as one; the consent flow never learns how many.
describe("provider selection", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  async function load(env) {
    for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value);
    vi.resetModules();
    return (await import("../analytics/index.js")).analytics;
  }

  it("measures nothing when nothing is configured", async () => {
    const analytics = await load({ NEXT_PUBLIC_POSTHOG_KEY: "", NEXT_PUBLIC_ANALYTICS_PROVIDER: "" });
    expect(analytics.id).toBe("none");
  });

  it("runs PostHog when its key is set", async () => {
    const analytics = await load({ NEXT_PUBLIC_POSTHOG_KEY: "phc_x", NEXT_PUBLIC_ANALYTICS_PROVIDER: "" });
    expect(analytics.id).toBe("posthog");
  });

  it("honours an explicit list", async () => {
    const analytics = await load({ NEXT_PUBLIC_POSTHOG_KEY: "phc_x", NEXT_PUBLIC_ANALYTICS_PROVIDER: "none" });
    expect(analytics.id).toBe("none");
  });
});
