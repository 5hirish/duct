import { describe, expect, it } from "vitest";
import { Standing, channelRows, hasStrategy, planDisplayName, plainWords } from "../planStrategy.js";

const day = (post_type, ...platforms) => ({ post_type, platforms });
const many = (n, d) => Array.from({ length: n }, () => d);

const DAYS = [
  ...many(10, day("video", "tiktok", "instagram")),
  ...many(4, day("slideshow", "tiktok")),
  ...many(2, day("image", "tiktok")),
  ...many(3, day("image", "instagram")),
  ...many(5, day("text", "linkedin")),
];

const MIX = {
  goal: "intent",
  channels: [
    { channel: "tiktok", last_days: 12, standing: Standing.LEADS, scaling: "video", testing: ["image", "video"] },
    { channel: "instagram", last_days: 6, standing: Standing.UNTESTED, scaling: "", testing: [] },
    { channel: "linkedin", last_days: 6, standing: Standing.TRAILS, scaling: "text", testing: [] },
  ],
};

describe("channelRows", () => {
  it("gives each channel its own bets, counted from the days on it", () => {
    const rows = channelRows({ exploit: "video", explore: "image", mix: MIX }, DAYS);
    expect(rows.map((r) => [r.channel, r.posts])).toEqual([["tiktok", 16], ["instagram", 13], ["linkedin", 5]]);
    const [tiktok, instagram, linkedin] = rows;
    // The scaled type is never also "tried", and the split moved by the days made for it.
    expect(tiktok).toMatchObject({ scaling: "video", testing: ["image"], standing: Standing.LEADS, change: 4 });
    // History says nothing yet: no bets, the mix it is trying instead.
    expect(instagram).toMatchObject({ scaling: "", testing: [], change: -3 });
    expect(instagram.types).toEqual([{ type: "video", count: 10 }, { type: "image", count: 3 }]);
    // One type is no choice, so a text channel leans on nothing.
    expect(linkedin).toMatchObject({ scaling: "", testing: [], change: -1, standing: Standing.TRAILS });
  });

  it("claims only types the plan makes on that channel", () => {
    const mix = { channels: [{ channel: "tiktok", last_days: null, scaling: "image", testing: ["slideshow"] }] };
    const [row] = channelRows({ mix }, [day("video", "tiktok"), day("slideshow", "tiktok")]);
    expect(row).toMatchObject({ scaling: "", testing: ["slideshow"], change: null });
  });

  it("puts a plan made before the mix on its busiest channel only", () => {
    const rows = channelRows({ exploit: "video", explore: "image" }, DAYS);
    expect(rows[0]).toMatchObject({ channel: "tiktok", scaling: "video", testing: ["image"], standing: null });
    expect(rows[1]).toMatchObject({ channel: "instagram", scaling: "", testing: [] });
  });

  it("skips days with no platform, as the channel chips do", () => {
    expect(channelRows({}, [{ post_type: "video" }, null])).toEqual([]);
  });
});

describe("hasStrategy", () => {
  it("counts the stored mix as a strategy", () => {
    expect(hasStrategy({})).toBe(false);
    expect(hasStrategy({ mix: MIX })).toBe(true);
    expect(hasStrategy({ review_notes: "TikTok gets four more days." })).toBe(true);
  });
});

describe("plainWords", () => {
  it("reads data names as words and leaves prose alone", () => {
    expect(plainWords("transformation_reveal hooks beat question_open_loop at 6.5%"))
      .toBe("transformation reveal hooks beat question open loop at 6.5%");
    expect(plainWords("Tue, Thu · 19:00")).toBe("Tue, Thu · 19:00");
  });
});

describe("planDisplayName", () => {
  it("drops a bracketed date range the line below already says", () => {
    expect(planDisplayName("November 2026 plan (Nov 8 - Nov 30)")).toBe("November 2026 plan");
    expect(planDisplayName("Launch plan (beta)")).toBe("Launch plan (beta)");
    expect(planDisplayName("(Nov 8 - Nov 30)")).toBe("(Nov 8 - Nov 30)");
    expect(planDisplayName(undefined)).toBe("");
  });
});
