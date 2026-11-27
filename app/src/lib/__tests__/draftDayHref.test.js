import { describe, expect, it } from "vitest";
import { draftDayHref } from "../../components/content/PlanBoard.jsx";

// A day that already holds a post opens that post. Drafting it again started
// a second session on the saved draft, away from the conversation it came from.
describe("draftDayHref", () => {
  it("opens the post a day already holds", () => {
    const plan = { id: "plan-1", days: [{ post_id: "post-9", platforms: ["tiktok"] }] };
    expect(draftDayHref(plan, 0)).toBe("/content/posts/post-9");
  });

  it("starts a draft for a day with none", () => {
    const plan = { id: "plan-1", days: [{ platforms: ["linkedin"] }] };
    expect(draftDayHref(plan, 0)).toBe("/content/posts/new?plan_id=plan-1&day=0&channel=linkedin");
  });
});
