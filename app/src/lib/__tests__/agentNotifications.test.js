import { describe, expect, it } from "vitest";
import { Phase } from "../agentPhase";
import { noticeFor } from "../../hooks/useAgentNotifications";

describe("which phase transitions deserve a notification", () => {
  it("finishing a run, stopping on a card, and failing", () => {
    expect(noticeFor(Phase.PIPELINE, Phase.READY)).toMatchObject({ title: "is done" });
    expect(noticeFor(Phase.CHATTING, Phase.READY)).toMatchObject({ title: "is done" });
    expect(noticeFor(Phase.PIPELINE, Phase.QUESTIONS, { pendingKind: "questions" })).toMatchObject({ title: "needs your input" });
    expect(noticeFor(Phase.PIPELINE, Phase.QUESTIONS, { pendingKind: "connection" }).body).toMatch(/connection/);
    expect(noticeFor(Phase.PIPELINE, Phase.FAILED, { errorCode: "auth" })).toMatchObject({ title: "ran into a problem" });
  });

  it("not a stop the user asked for, a reload landing on a card, or no change", () => {
    expect(noticeFor(Phase.PIPELINE, Phase.FAILED, { errorCode: "cancelled" })).toBeNull();
    expect(noticeFor(Phase.STARTING, Phase.QUESTIONS)).toBeNull();
    expect(noticeFor(Phase.STARTING, Phase.READY)).toBeNull();
    expect(noticeFor(Phase.READY, Phase.READY)).toBeNull();
  });
});
