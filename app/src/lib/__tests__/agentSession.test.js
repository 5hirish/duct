import { describe, expect, it } from "vitest";
import { AgentEvent } from "../agentEvents";
import { Phase } from "../agentPhase";
import {
  Action,
  Row,
  friendlyErrorMessage,
  initialAgentState,
  reduceAgentSession,
  replayEvents,
} from "../agentSession";
import { StepStatus } from "../agentSteps";
import audit from "../__fixtures__/audit-run.json";
import content from "../__fixtures__/content-plan.json";
import insights from "../__fixtures__/insights-pause.json";

// A fixture is a recorded stream with two kinds of user action spliced in:
// {"__send__": text} is the user typing, {"__answer__": answers} is the user
// answering the card on screen. Replaying one through the reducer and noting
// the phase after every frame is the whole test — the sequence is the
// contract every workspace renders against.
function drive(frames, state = initialAgentState) {
  const phases = [];
  let s = state;
  for (const frame of frames) {
    if (frame.__send__ !== undefined) {
      s = reduceAgentSession(s, { type: Action.USER_SENT, text: frame.__send__ });
    } else if (frame.__answer__ !== undefined) {
      s = reduceAgentSession(s, { type: Action.ANSWER_SENT, pause: s.pauses[0] });
    } else {
      s = reduceAgentSession(s, { type: Action.EVENT, event: frame });
    }
    phases.push(s.phase);
  }
  return { state: s, phases };
}

const distinct = (phases) => phases.filter((p, i) => p !== phases[i - 1]);

describe("an insights run that pauses on a question", () => {
  const { state, phases } = drive(insights);

  it("moves starting → working → waiting → working → ready → chatting → ready", () => {
    expect(distinct(phases)).toEqual([
      Phase.PIPELINE,
      Phase.QUESTIONS,
      Phase.PIPELINE,
      Phase.READY,
      Phase.CHATTING,
      Phase.READY,
    ]);
  });

  it("keeps one card when the same pause is replayed", () => {
    const parked = drive(insights.slice(0, 11)).state;
    expect(parked.pauses).toHaveLength(1);
    expect(parked.pauses[0].interrupt_id).toBe("int_a1");
    expect(parked.phase).toBe(Phase.QUESTIONS);
  });

  it("does not let MESSAGE_STOP clear a pause that arrived just before it", () => {
    const afterStop = drive(insights.slice(0, 10)).state;
    expect(afterStop.phase).toBe(Phase.QUESTIONS);
    // The bubble with the sentence that introduced the question is closed.
    expect(afterStop.messages.at(-1)).toMatchObject({ role: Row.ASSISTANT, streaming: false });
  });

  it("carries PIPELINE_STARTED's payload for the workspace", () => {
    expect(state.started).toMatchObject({ autonomy: "ask", autonomy_configured: "assisted" });
  });

  it("puts the change set after the sentence that proposed it, and closes the bubble first", () => {
    const rows = state.messages.map((m) => m.role);
    const card = rows.indexOf(Row.CHANGE_SET_CARD);
    expect(card).toBeGreaterThan(0);
    expect(state.messages[card - 1]).toMatchObject({ role: Row.ASSISTANT, streaming: false });
    // The prose after the card is a new bubble, not appended to the old one.
    expect(state.messages[card + 1]).toMatchObject({ role: Row.ASSISTANT, text: " I proposed two changes above." });
  });

  it("collapses the per-pull steps onto one row that ends successful", () => {
    const collect = state.steps.filter((s) => s.step_id === "collect_source_data");
    expect(collect).toHaveLength(1);
    expect(collect[0].status).toBe(StepStatus.SUCCESS);
  });

  it("renders a recalled memory as a transcript row", () => {
    expect(state.messages[0]).toMatchObject({ role: Row.MEMORY_RECALL });
  });

  it("merges thinking onto the turn it belongs to", () => {
    const turn = state.messages.find((m) => m.role === Row.ASSISTANT && m.thinking);
    expect(turn.thinking).toBe("The user asked about CPA; I should confirm the goal first.");
  });
});

describe("a content plan run", () => {
  const { state, phases } = drive(content);

  it("goes working → ready → chatting → ready", () => {
    expect(distinct(phases)).toEqual([Phase.PIPELINE, Phase.READY, Phase.CHATTING, Phase.READY]);
  });

  it("finishes every step by the time the run is ready", () => {
    expect(state.steps.every((s) => s.status === StepStatus.SUCCESS)).toBe(true);
    expect(state.steps.map((s) => s.step_id)).toEqual([
      "load_project",
      "enriching",
      "dispatch_subagent:research_pillar",
    ]);
  });

  it("leaves the agent-specific payloads to the workspace", () => {
    // The reducer knows nothing about plans or posts; it must not swallow them
    // into the transcript either.
    expect(state.messages.some((m) => m.payload)).toBe(false);
  });

  it("clears typing on the first token of a reply", () => {
    const sent = drive(content.slice(0, 14)).state;
    expect(sent.isAgentTyping).toBe(true);
    const replied = drive(content.slice(0, 15)).state;
    expect(replied.isAgentTyping).toBe(false);
    expect(replied.messages.at(-1)).toMatchObject({ role: Row.ASSISTANT, streaming: true });
  });
});

describe("an audit run", () => {
  const { state, phases } = drive(audit);

  it("goes working → ready → chatting → ready → chatting → ready", () => {
    expect(distinct(phases)).toEqual([
      Phase.PIPELINE,
      Phase.READY,
      Phase.CHATTING,
      Phase.READY,
      Phase.CHATTING,
      Phase.READY,
    ]);
  });

  it("keeps a step's payload when a later STEP_STARTED carries none", () => {
    const crawl = state.steps.find((s) => s.step_id === "crawl_pages");
    expect(crawl.payload).toEqual({ done: 1, total: 9 });
  });

  it("turns a turn failure into a transcript row, not the failed phase", () => {
    const afterFailure = drive(audit.slice(0, 15)).state;
    expect(afterFailure.messages.at(-1)).toMatchObject({ role: Row.SEND_ERROR, text: expect.stringMatching(/rephrasing/) });
    expect(afterFailure.phase).toBe(Phase.READY);
    expect(afterFailure.error).toBe("");
    // The next message the user sends supersedes the failure row.
    expect(state.messages.some((m) => m.role === Row.SEND_ERROR)).toBe(false);
  });

  it("merges several memory writes into one line", () => {
    const notes = state.messages.filter((m) => m.role === Row.MEMORY_NOTE);
    expect(notes).toHaveLength(1);
    expect(notes[0].memories.map((m) => m.title)).toEqual(["Homepage title is 71 chars", "Blog has no sitemap"]);
  });

  it("renders a complete AGENT_MESSAGE as its own bubble", () => {
    expect(state.messages.at(-1)).toEqual({
      role: Row.ASSISTANT,
      text: "The title runs past 60 characters and gets truncated in results.",
    });
  });
});

describe("answering a pause", () => {
  const pause = { event: AgentEvent.QUESTIONS_REQUIRED, questions: [], interrupt_id: "i1" };
  const parked = replayEvents([{ event: AgentEvent.PIPELINE_STARTED }, pause]);

  it("returns to the pipeline when the run has not opened yet", () => {
    const s = reduceAgentSession(parked, { type: Action.ANSWER_SENT, pause });
    expect(s.phase).toBe(Phase.PIPELINE);
    expect(s.pauses).toEqual([]);
    expect(s.isAgentTyping).toBe(false);
  });

  it("returns to a chat turn once the run has opened", () => {
    const opened = replayEvents([{ event: AgentEvent.PIPELINE_FINISHED }, pause], parked);
    const s = reduceAgentSession(opened, { type: Action.ANSWER_SENT, pause });
    expect(s.phase).toBe(Phase.CHATTING);
    expect(s.isAgentTyping).toBe(true);
  });

  it("shows the next card when two pauses are pending", () => {
    const second = { event: AgentEvent.ACCOUNT_SELECTION_REQUIRED, candidates: [], interrupt_id: "i2" };
    const two = replayEvents([second], parked);
    expect(two.pauses).toHaveLength(2);
    const s = reduceAgentSession(two, { type: Action.ANSWER_SENT, pause });
    expect(s.pauses).toEqual([second]);
    expect(s.phase).toBe(Phase.QUESTIONS);
  });

  it("puts the card back when the answer could not be sent", () => {
    const sent = reduceAgentSession(parked, { type: Action.ANSWER_SENT, pause });
    const s = reduceAgentSession(sent, { type: Action.ANSWER_FAILED, pause, error: "offline" });
    expect(s.pauses).toEqual([pause]);
    expect(s.phase).toBe(Phase.QUESTIONS);
    expect(s.messages.at(-1)).toMatchObject({ role: Row.SEND_ERROR });
  });

  it("stays waiting if PIPELINE_FINISHED lands while a card is up", () => {
    const s = replayEvents([{ event: AgentEvent.PIPELINE_FINISHED }], parked);
    expect(s.phase).toBe(Phase.QUESTIONS);
    expect(s.opened).toBe(true);
  });

  it("treats pauses without ids as one per kind", () => {
    const a = { event: AgentEvent.CONNECTION_REQUIRED, connector_id: "ga4" };
    const b = { event: AgentEvent.CONNECTION_REQUIRED, connector_id: "ga4" };
    expect(replayEvents([a, b], parked).pauses).toHaveLength(2); // the id'd one plus one connection
  });
});

describe("the state endpoint's pauses", () => {
  it("park the session before any stream event arrives", () => {
    const s = reduceAgentSession(initialAgentState, {
      type: Action.PAUSES,
      pauses: [{ event: AgentEvent.QUESTIONS_REQUIRED, questions: [], interrupt_id: "x" }],
      todos: [{ content: "Pull", status: "completed" }],
    });
    expect(s.phase).toBe(Phase.QUESTIONS);
    expect(s.todos).toHaveLength(1);
  });
});

describe("sending", () => {
  it("drops a previous send error and opens a chat turn", () => {
    const s0 = reduceAgentSession(initialAgentState, { type: Action.SEND_FAILED, error: "x", content: "hi" });
    const s = reduceAgentSession(s0, { type: Action.USER_SENT, text: "hi again" });
    expect(s.messages).toEqual([{ role: Row.USER, text: "hi again" }]);
    expect(s.phase).toBe(Phase.CHATTING);
    expect(s.suppressThinking).toBe(false);
  });

  it("hides thinking on a resumed thread until the user acts", () => {
    const s0 = reduceAgentSession(initialAgentState, { type: Action.HYDRATE, messages: [], suppressThinking: true });
    const s1 = reduceAgentSession(s0, { type: Action.EVENT, event: { event: AgentEvent.THINKING_CHUNK, text: "hmm" } });
    expect(s1.messages).toEqual([]);
    const s2 = reduceAgentSession(s1, { type: Action.USER_SENT, text: "go" });
    const s3 = reduceAgentSession(s2, { type: Action.EVENT, event: { event: AgentEvent.THINKING_CHUNK, text: "hmm" } });
    expect(s3.messages.at(-1)).toMatchObject({ thinking: "hmm" });
  });
});

describe("failure and reconnect", () => {
  it("maps a raw backend error to something a user can act on", () => {
    const s = replayEvents([{ event: AgentEvent.PIPELINE_FAILED, error: "RuntimeError: ANTHROPIC_API_KEY missing" }]);
    expect(s.phase).toBe(Phase.FAILED);
    expect(s.error).toBe("The assistant isn't connected. Ask your admin to finish setup.");
  });

  it("stops typing while reconnecting", () => {
    const typing = reduceAgentSession(initialAgentState, { type: Action.USER_SENT, text: "x" });
    const s = reduceAgentSession(typing, { type: Action.RECONNECTING, value: true });
    expect(s.reconnecting).toBe(true);
    expect(s.isAgentTyping).toBe(false);
  });

  it("stop keeps a chat ready but fails an opening run", () => {
    expect(reduceAgentSession(initialAgentState, { type: Action.STOPPED, keepReady: false }).phase).toBe(Phase.FAILED);
    expect(reduceAgentSession(initialAgentState, { type: Action.STOPPED, keepReady: true }).phase).toBe(Phase.READY);
  });
});

describe("friendlyErrorMessage", () => {
  it.each([
    ["", "Something went wrong. Please try again."],
    ["429 Too Many Requests", "We're hitting a rate limit — wait a minute and try again."],
    ["Read timed out", "That took longer than expected. Try again."],
    ["Traceback (most recent call last): line 12", "Something went wrong on our end. Please try again in a moment."],
    ["That turn failed. Try rephrasing.", "That turn failed. Try rephrasing."],
  ])("%s", (raw, expected) => {
    expect(friendlyErrorMessage(raw)).toBe(expected);
  });
});
