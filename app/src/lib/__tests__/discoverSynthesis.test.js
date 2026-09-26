import { describe, expect, it } from "vitest";

import { engagement, hookOf, synthesize, TOP_HASHTAGS, WINNING_HOOKS } from "../discoverSynthesis.js";
import { formatPercent } from "../format.js";

function post(id, { plays = 10_000, acted = 500, slideshow = false, tags = [], text = `Hook ${id}` } = {}) {
  return {
    id,
    text,
    play_count: plays,
    digg_count: acted,
    comment_count: 0,
    share_count: 0,
    collect_count: 0,
    is_slideshow: slideshow,
    hashtags: tags,
    web_video_url: `https://www.tiktok.com/@kestrel/video/${id}`,
  };
}

describe("engagement", () => {
  it("is interactions per view, and zero without views", () => {
    expect(engagement({ play_count: 1000, digg_count: 30, comment_count: 5, share_count: 10, collect_count: 5 })).toBe(0.05);
    expect(engagement({ play_count: 0, digg_count: 30 })).toBe(0);
  });
});

describe("hookOf", () => {
  it("takes the first line that has words once hashtags are gone", () => {
    expect(hookOf("#fyp #faceshape\nStop contouring like this\nPart 2 tomorrow")).toBe("Stop contouring like this");
  });

  it("drops inline hashtags and clips a long line", () => {
    expect(hookOf("Round face? #faceshape Try this")).toBe("Round face? Try this");
    const long = hookOf("word ".repeat(40));
    expect(long.length).toBe(90);
    expect(long.endsWith("…")).toBe(true);
  });

  it("is empty for a caption that is only tags", () => {
    expect(hookOf("#fyp #viral")).toBe("");
  });
});

describe("synthesize", () => {
  it("returns null for no posts", () => {
    expect(synthesize([])).toBeNull();
    expect(synthesize(undefined)).toBeNull();
  });

  it("splits formats by share and median engagement", () => {
    const s = synthesize([
      post("a", { slideshow: true, acted: 800 }),
      post("b", { slideshow: true, acted: 600 }),
      post("c", { acted: 200 }),
      post("d", { acted: 400 }),
    ]);
    expect(s.total).toBe(4);
    expect(s.slideshow).toMatchObject({ count: 2, share: 0.5 });
    expect(s.slideshow.engagement).toBeCloseTo(0.07);
    expect(s.video).toMatchObject({ count: 2, share: 0.5 });
    expect(s.video.engagement).toBeCloseTo(0.03);
  });

  it("uses the median so one outlier cannot crown a format", () => {
    const s = synthesize([
      post("a", { slideshow: true, acted: 100 }),
      post("b", { slideshow: true, acted: 100 }),
      post("c", { slideshow: true, plays: 300, acted: 250 }), // 83% on 300 views
    ]);
    expect(s.slideshow.engagement).toBe(0.01);
  });

  it("ranks recurring tags, skipping the searched ones and the generic ones", () => {
    const s = synthesize(
      [
        post("a", { tags: ["faceshape", "fyp", "contour", "Blush"] }),
        post("b", { tags: ["faceshape", "#contour", "blush"] }),
        post("c", { tags: ["faceshape", "contour", "once"] }),
      ],
      { exclude: ["FaceShape"] },
    );
    expect(s.hashtags).toEqual([
      { tag: "contour", count: 3 },
      { tag: "blush", count: 2 },
    ]);
  });

  it("counts a tag once per post and caps the list", () => {
    const tags = Array.from({ length: TOP_HASHTAGS + 4 }, (_, i) => `tag${i}`);
    const s = synthesize([post("a", { tags: [...tags, "tag0"] }), post("b", { tags })]);
    expect(s.hashtags).toHaveLength(TOP_HASHTAGS);
    expect(s.hashtags[0]).toEqual({ tag: "tag0", count: 2 });
  });

  it("picks winning hooks only among posts with at least typical reach", () => {
    const s = synthesize([
      post("tiny", { plays: 200, acted: 150, text: "Tiny but loud" }), // 75%, too few views to count
      post("a", { plays: 50_000, acted: 5_000, text: "Best hook" }),
      post("b", { plays: 40_000, acted: 2_000, text: "Second hook" }),
      post("c", { plays: 30_000, acted: 900, text: "#fyp" }), // no words to show
      post("d", { plays: 20_000, acted: 100, text: "Weak hook" }),
    ]);
    expect(s.hooks.map((h) => h.text)).toEqual(["Best hook", "Second hook"]);
    expect(s.hooks.length).toBeLessThanOrEqual(WINNING_HOOKS);
    expect(s.hooks[0]).toMatchObject({ id: "a", engagement: 0.1, plays: 50_000, url: "https://www.tiktok.com/@kestrel/video/a" });
  });

  it("accepts hashtags in the actor's object shape too", () => {
    const s = synthesize([
      post("a", { tags: [{ name: "contour" }] }),
      post("b", { tags: [{ name: "contour" }] }),
    ]);
    expect(s.hashtags).toEqual([{ tag: "contour", count: 2 }]);
  });
});

describe("formatPercent", () => {
  it("formats a ratio in the reader's locale", () => {
    expect(formatPercent(0.062, { locale: "en" })).toBe("6.2%");
    // German puts a no-break space before the sign.
    expect(formatPercent(0.062, { locale: "de" }).replace(/\s/g, " ")).toBe("6,2 %");
    expect(formatPercent(Number.NaN, { locale: "en" })).toBe("0%");
  });
});
