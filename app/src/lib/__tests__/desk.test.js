import { describe, expect, it } from "vitest";
import { IN_PROGRESS, NEEDS_YOU, buildDesk, conversationCard, routeConversation } from "../desk";

describe("threads on the desk", () => {
  const conv = (run_status, extra = {}) => ({ id: run_status, status: "active", title: "t", run_status, ...extra });

  it("a parked or failed thread needs its owner; a working or idle one is in progress", () => {
    expect(routeConversation(conv("paused"))).toBe(NEEDS_YOU);
    expect(routeConversation(conv("failed"))).toBe(NEEDS_YOU);
    expect(routeConversation(conv("running"))).toBe(IN_PROGRESS);
    expect(routeConversation(conv("idle"))).toBe(IN_PROGRESS);
    expect(routeConversation({ status: "archived", run_status: "paused" })).toBeNull();
  });

  it("the card says why", () => {
    expect(conversationCard(conv("paused"))).toEqual({ code: "waiting", tone: "attention", error: "" });
    // The backend's own reason travels with the code, so the card can show it
    // in place of the generic sentence.
    expect(conversationCard(conv("failed", { run_error: { error: "The model provider rejected the API key." } }))).toEqual({
      code: "failed", tone: "attention", error: "The model provider rejected the API key.",
    });
    expect(conversationCard(conv("failed")).error).toBe("");
    expect(conversationCard(conv("running")).code).toBe("working");
  });

  it("a thread waiting on the user outranks a pinned open one", () => {
    const desk = buildDesk({ conversations: [conv("idle", { pinned: true }), conv("paused")] });
    expect(desk.needsYou.map((c) => c.conversationId)).toEqual(["paused"]);
    expect(desk.inProgress.map((c) => c.conversationId)).toEqual(["idle"]);
  });

  it("a thread with no title says so by code, not by an English fallback", () => {
    const desk = buildDesk({ conversations: [conv("idle", { title: "" })] });
    expect(desk.inProgress[0]).toMatchObject({ title: "", titleCode: "untitled_thread", detailCode: "resume" });
    expect(buildDesk({ conversations: [conv("idle")] }).inProgress[0].titleCode).toBe("");
  });
});
