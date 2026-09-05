/**
 * The agent session, as a pure reducer.
 *
 * Every agent workspace (content, audit, insights) moves through the same
 * lifecycle: a session opens, a run works, it may park on a question, a
 * connect offer or an account pick, it becomes a chat, turns fail or succeed,
 * the stream drops and comes back. Three components each carried their own
 * copy of that state machine — the content one was the most complete, the
 * insights one the least, and every gap between them was a bug somebody had
 * already fixed elsewhere.
 *
 * So the protocol half lives here, with no React in it: `reduce(state, action)`
 * over the shared `AgentEvent` vocabulary plus a handful of local actions
 * (the user sent, a send failed, the stream is reconnecting). The hook
 * (hooks/useAgentSession.js) owns the network and the effects; the workspace
 * owns only what is specific to its agent — the events this file returns
 * unchanged are its to handle.
 *
 * Being pure is what makes it testable against recorded streams: replay a
 * fixture of SSE frames and assert the phase sequence. See
 * lib/__tests__/agentSession.test.js.
 */

import { AgentEvent, ErrorCode, PAUSE_EVENTS } from "./agentEvents";
import { Phase } from "./agentPhase";
import { StepStatus } from "./agentSteps";

export const Action = Object.freeze({
  EVENT:          "event",          // an SSE frame
  HYDRATE:        "hydrate",        // stored transcript, before the live stream
  PAUSES:         "pauses",         // what the thread is parked on, from the state endpoint
  USER_SENT:      "user_sent",
  SEND_FAILED:    "send_failed",
  ANSWER_SENT:    "answer_sent",
  ANSWER_FAILED:  "answer_failed",
  APPEND_MESSAGE: "append_message", // an agent-specific row (an image bubble, say)
  STOPPED:        "stopped",
  RECONNECTING:   "reconnecting",
  FAILED:         "failed",
  RESET:          "reset",
});

export const initialAgentState = Object.freeze({
  phase: Phase.STARTING,
  steps: [],
  todos: [],
  messages: [],
  // Pauses the run is parked on, oldest first; `pauses[0]` is the card on
  // screen. More than one happens when two tools pause in the same turn.
  pauses: [],
  // The terminal error (FAILED phase). Per-turn failures are transcript rows.
  error: "",
  // Its ErrorCode, which picks the action offered (retry, open settings,
  // reconnect a connector, start fresh) — see `errorAction`.
  errorCode: "",
  errorRetryable: true,
  // A model call being retried: { attempt, max, code, until }. Status, not
  // failure; the next token clears it. `until` is when the next attempt goes
  // out, on this client's clock, so the status row can count down to it.
  retrying: null,
  // Tokens. `last` is the most recent model call on the thread the user is
  // talking to — its input size against `window` is how full the context is.
  // `total` sums every call seen this session (subagents included), which is
  // what the turn cost — in tokens and, for a priced model, in dollars. A
  // resumed thread gets both from the state route.
  usage: { last: null, total: { input: 0, output: 0, cached: 0, calls: 0, cost: 0 } },
  // The harness is summarising history to make room — shown in the status
  // row; the transcript gets a quiet note when it is done.
  compacting: false,
  // Text handed back to the composer: what was queued when the user stopped
  // the run. `key` changes per hand-back so the same text can be handed back
  // twice. pi's Escape does this; losing a typed message on Stop is worse
  // than losing the run.
  draft: null,
  reconnecting: false,
  isAgentTyping: false,
  // The opening run has finished at least once — after this a pause belongs
  // to a chat turn, not the pipeline, and answering it returns to CHATTING.
  opened: false,
  // On a resume the only turn is a one-line greeting whose extended thinking
  // narrates internal state; hidden until the user's first action.
  suppressThinking: false,
  // What PIPELINE_STARTED carried (channel, autonomy…), for the workspace.
  started: null,
});

// ---------------------------------------------------------------------------
// Message rows — the transcript shape AgentChat renders
// ---------------------------------------------------------------------------

export const Row = Object.freeze({
  USER:            "user",
  ASSISTANT:       "assistant",
  SEND_ERROR:      "send_error",
  ARTIFACT_CARD:   "artifact_card",
  CHANGE_SET_CARD: "change_set_card",
  MEMORY_NOTE:     "memory_note",
  MEMORY_RECALL:   "memory_recall",
  IMAGE:           "image",
  NOTICE:          "notice",  // a quiet centred line: "Context compacted"
});

/** The assistant bubble tokens are flowing into, if one is open. */
function streamingTail(messages) {
  const last = messages[messages.length - 1];
  return last?.role === Row.ASSISTANT && last.streaming ? last : null;
}

/** Close an open streaming bubble so the next row lands after it, not inside it. */
function closeStreaming(messages) {
  const last = messages[messages.length - 1];
  if (!last?.streaming) return messages;
  return [...messages.slice(0, -1), { ...last, streaming: false }];
}

function appendToTail(messages, patch) {
  const tail = streamingTail(messages);
  if (tail) return [...messages.slice(0, -1), { ...tail, ...patch(tail) }];
  return [...messages, { role: Row.ASSISTANT, text: "", streaming: true, ...patch({ text: "", thinking: "" }) }];
}

/** Drop a trailing send-error row: a fresh send supersedes it. */
function withoutTrailingSendError(messages) {
  const last = messages[messages.length - 1];
  return last?.role === Row.SEND_ERROR ? messages.slice(0, -1) : messages;
}

/** Drop the "queued" mark from the user row with this client id (or from
 *  every queued row when the event names none). */
function releaseQueued(messages, clientId) {
  if (!messages.some((m) => m.role === Row.USER && m.queued)) return messages;
  return messages.map((m) =>
    m.role === Row.USER && m.queued && (!clientId || m.clientId === clientId) ? { ...m, queued: false } : m,
  );
}

function upsertBy(rows, match, row) {
  const at = rows.findIndex(match);
  if (at === -1) return [...rows, row];
  const next = [...rows];
  next[at] = row;
  return next;
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function stepStarted(steps, event) {
  const existing = steps.find((s) => s.step_id === event.step_id);
  if (existing) {
    return steps.map((s) =>
      s.step_id === event.step_id
        ? {
            ...s,
            status: StepStatus.RUNNING,
            label: event.label || s.label,
            summary: event.summary ?? s.summary,
            // A payload-less STEP_STARTED keeps the existing payload (audit
            // sends live "N/9 categories" progress this way).
            payload: event.payload ?? s.payload,
          }
        : s,
    );
  }
  return [
    ...steps,
    {
      step_id: event.step_id,
      label: event.label || event.step_id,
      status: StepStatus.RUNNING,
      summary: event.summary || "",
      payload: event.payload ?? null,
    },
  ];
}

function stepFinished(steps, event, status) {
  return steps.map((s) =>
    s.step_id === event.step_id
      ? {
          ...s,
          status,
          summary: event.summary || event.error || s.summary,
          payload: event.payload ?? s.payload,
        }
      : s,
  );
}

function finishRunningSteps(steps) {
  return steps.map((s) => (s.status === StepStatus.RUNNING ? { ...s, status: StepStatus.SUCCESS } : s));
}

// ---------------------------------------------------------------------------
// Pauses
// ---------------------------------------------------------------------------

/** Two frames for one pause (a replay after reconnect, the same interrupt
 *  re-raised) must not stack two cards. With an interrupt id that is exact;
 *  without one (the in-process bridge) one pause per event kind is the rule. */
function samePause(a, b) {
  if (a.interrupt_id || b.interrupt_id) return a.interrupt_id === b.interrupt_id;
  return a.event === b.event;
}

function addPause(pauses, pause) {
  return upsertBy(pauses, (p) => samePause(p, pause), pause);
}

// ---------------------------------------------------------------------------
// Usage
// ---------------------------------------------------------------------------

function usageCall(event) {
  return {
    input: event.input_tokens || 0,
    output: event.output_tokens || 0,
    cached: event.cache_read_tokens || 0,
    window: event.context_window || 0,
    model: event.model || "",
    // null for a model the backend has no price for; the tooltip then shows
    // tokens without a dollar figure rather than a made-up one.
    cost: typeof event.cost_usd === "number" ? event.cost_usd : null,
  };
}

function addUsage(usage, event) {
  const call = usageCall(event);
  const t = usage.total;
  return {
    // A subagent's call fills its own context, not the thread's.
    last: event.scope && event.scope !== "thread" ? usage.last : call,
    total: {
      input: t.input + call.input,
      output: t.output + call.output,
      cached: t.cached + call.cached,
      calls: t.calls + 1,
      cost: (t.cost || 0) + (call.cost || 0),
    },
  };
}

/** The state route's shape → the reducer's: last call + running total. */
function usageFromThread(thread) {
  if (!thread) return null;
  const window = thread.context_window || 0;
  const last = thread.last
    ? {
        input: thread.last.input_tokens || 0,
        output: thread.last.output_tokens || 0,
        cached: thread.last.cache_read_tokens || 0,
        window,
        model: thread.model || "",
        cost: typeof thread.last.cost_usd === "number" ? thread.last.cost_usd : null,
      }
    : null;
  const t = thread.total || {};
  return {
    last,
    total: {
      input: t.input_tokens || 0,
      output: t.output_tokens || 0,
      cached: t.cache_read_tokens || 0,
      calls: t.calls || 0,
      cost: typeof t.cost_usd === "number" ? t.cost_usd : 0,
    },
  };
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function reduceEvent(state, event, at = 0) {
  switch (event.event) {
    case AgentEvent.TOKEN_USAGE:
      return { ...state, usage: addUsage(state.usage, event) };

    case AgentEvent.CONTEXT_COMPACTING:
      return { ...state, compacting: true };

    case AgentEvent.CONTEXT_COMPACTED:
      // The gauge's last reading is of the context that was just replaced;
      // nothing true can be shown until the next call reports its size.
      return {
        ...state,
        compacting: false,
        usage: state.usage.last ? { ...state.usage, last: { ...state.usage.last, stale: true } } : state.usage,
        messages: [
          ...closeStreaming(state.messages),
          { role: Row.NOTICE, text: "Context compacted — older history summarised to make room." },
        ],
      };

    case AgentEvent.USER_INPUT_CONSUMED:
      // The model has the message now: the "queued" mark comes off its row.
      return { ...state, messages: releaseQueued(state.messages, event.client_message_id) };

    case AgentEvent.PIPELINE_STARTED:
      return {
        ...state,
        started: event,
        // Leave "Starting…" the instant the backend responds, before any step
        // arrives, so the working state shows immediately.
        phase: state.phase === Phase.STARTING ? Phase.PIPELINE : state.phase,
      };

    case AgentEvent.STEP_STARTED:
      return {
        ...state,
        steps: stepStarted(state.steps, event),
        phase: state.opened ? state.phase : Phase.PIPELINE,
      };

    case AgentEvent.STEP_FINISHED:
      return { ...state, steps: stepFinished(state.steps, event, event.status || StepStatus.SUCCESS) };

    case AgentEvent.STEP_FAILED:
      // With a step id it is a stage that failed; without one it is a whole
      // turn (a provider error mid-chat). The session is alive either way,
      // so the failure is a row in the transcript, not the FAILED phase.
      if (event.step_id) return { ...state, steps: stepFinished(state.steps, event, StepStatus.ERROR) };
      return {
        ...state,
        isAgentTyping: false,
        retrying: null,
        phase: state.phase === Phase.CHATTING ? Phase.READY : state.phase,
        messages: [
          ...closeStreaming(state.messages),
          {
            role: Row.SEND_ERROR,
            text: friendlyErrorMessage(event.error || "That turn failed. Try again.", event.code),
            content: null,
            code: event.code || "",
            retryable: event.retryable ?? true,
          },
        ],
      };

    case AgentEvent.THINKING_CHUNK:
      if (state.suppressThinking || !event.text) return state;
      return {
        ...state,
        retrying: null,
        messages: appendToTail(state.messages, (t) => ({ thinking: (t.thinking || "") + event.text })),
      };

    case AgentEvent.AGENT_MESSAGE_CHUNK:
      if (!event.text) return state;
      return {
        ...state,
        isAgentTyping: false,
        retrying: null,
        messages: appendToTail(state.messages, (t) => ({ text: (t.text || "") + event.text })),
      };

    case AgentEvent.MODEL_RETRYING:
      // The provider is having a moment and the harness is waiting it out.
      // Shown in the status row, never as a failure: the turn is still alive.
      // `retry_in` is a duration; anchoring it to the clock the event arrived
      // on (not the server's) is what keeps the countdown honest.
      return {
        ...state,
        retrying: {
          attempt: event.attempt || 1,
          max: event.max_attempts || event.attempt || 1,
          code: event.code || "",
          until: typeof event.retry_in === "number" ? at + event.retry_in * 1000 : null,
        },
      };

    case AgentEvent.AGENT_MESSAGE:
      return {
        ...state,
        isAgentTyping: false,
        phase: state.phase === Phase.CHATTING ? Phase.READY : state.phase,
        messages: [...closeStreaming(state.messages), { role: Row.ASSISTANT, text: event.text || "" }],
      };

    case AgentEvent.MESSAGE_STOP:
      return {
        ...state,
        isAgentTyping: false,
        retrying: null,
        messages: closeStreaming(state.messages),
        // Only a chat turn ends here. The opening run ends on PIPELINE_FINISHED,
        // and a pause that arrived just before this stays a pause.
        phase: state.phase === Phase.CHATTING ? Phase.READY : state.phase,
      };

    case AgentEvent.TODO_UPDATE:
      return { ...state, todos: event.todos || [] };

    case AgentEvent.QUESTIONS_REQUIRED:
    case AgentEvent.CONNECTION_REQUIRED:
    case AgentEvent.ACCOUNT_SELECTION_REQUIRED:
      return {
        ...state,
        isAgentTyping: false,
        retrying: null,
        pauses: addPause(state.pauses, event),
        phase: Phase.QUESTIONS,
        messages: closeStreaming(state.messages),
      };

    case AgentEvent.PIPELINE_FINISHED:
      return {
        ...state,
        opened: true,
        steps: finishRunningSteps(state.steps),
        isAgentTyping: false,
        retrying: null,
        messages: closeStreaming(state.messages),
        phase: state.pauses.length ? Phase.QUESTIONS : Phase.READY,
      };

    case AgentEvent.PIPELINE_FAILED:
      return {
        ...state,
        isAgentTyping: false,
        reconnecting: false,
        retrying: null,
        error: friendlyErrorMessage(event.error, event.code),
        errorCode: event.code || "",
        errorRetryable: event.retryable ?? true,
        phase: Phase.FAILED,
        messages: closeStreaming(state.messages),
      };

    case AgentEvent.ARTIFACT_UPDATED:
      return { ...state, messages: [...state.messages, { role: Row.ARTIFACT_CARD, artifact: event.artifact }] };

    case AgentEvent.MEMORY_WRITTEN: {
      if (!event.memory) return state;
      // Several writes in one turn collapse into one quiet line.
      const last = state.messages[state.messages.length - 1];
      if (last?.role === Row.MEMORY_NOTE) {
        return {
          ...state,
          messages: [...state.messages.slice(0, -1), { ...last, memories: [...last.memories, event.memory] }],
        };
      }
      return { ...state, messages: [...state.messages, { role: Row.MEMORY_NOTE, memories: [event.memory] }] };
    }

    case AgentEvent.MEMORY_RECALLED:
      if (!event.memories?.length) return state;
      return { ...state, messages: [...state.messages, { role: Row.MEMORY_RECALL, memories: event.memories }] };

    case AgentEvent.EXECUTION_PROPOSED: {
      const card = event.change_set;
      if (!card?.change_set_id) return state;
      // The card lands mid-turn, after the sentence that introduced it: close
      // the streaming bubble first so the two read in the order they were
      // written. Upsert by id — the same set arrives again on a state change,
      // and two cards for one change set is a way to approve something twice.
      return {
        ...state,
        messages: upsertBy(
          closeStreaming(state.messages),
          (m) => m.role === Row.CHANGE_SET_CARD && m.changeSet?.change_set_id === card.change_set_id,
          { role: Row.CHANGE_SET_CARD, changeSet: card },
        ),
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// The reducer
// ---------------------------------------------------------------------------

export function reduceAgentSession(state, action) {
  switch (action.type) {
    case Action.EVENT:
      return reduceEvent(state, action.event, action.at || 0);

    case Action.HYDRATE:
      return {
        ...state,
        messages: action.messages || [],
        suppressThinking: action.suppressThinking ?? state.suppressThinking,
      };

    case Action.PAUSES: {
      const pauses = (action.pauses || []).reduce(addPause, state.pauses);
      return {
        ...state,
        pauses,
        todos: action.todos?.length ? action.todos : state.todos,
        usage: usageFromThread(action.usage) || state.usage,
        phase: pauses.length ? Phase.QUESTIONS : state.phase,
      };
    }

    case Action.USER_SENT: {
      // Sent while the agent is busy — working, thinking, or parked on a
      // card — the message is queued, not refused: the row carries a mark
      // until USER_INPUT_CONSUMED says the model has it, and the phase does
      // not move (a queued note is not a new turn). From READY it is a turn.
      const busy = state.phase === Phase.PIPELINE || state.phase === Phase.CHATTING || state.phase === Phase.QUESTIONS;
      const row = { role: Row.USER, text: action.text, clientId: action.clientId || "", queued: busy };
      return {
        ...state,
        suppressThinking: false,
        isAgentTyping: busy ? state.isAgentTyping : true,
        phase: busy ? state.phase : Phase.CHATTING,
        messages: [...withoutTrailingSendError(state.messages), row],
      };
    }

    case Action.SEND_FAILED:
      return {
        ...state,
        isAgentTyping: false,
        phase: state.phase === Phase.CHATTING ? Phase.READY : state.phase,
        messages: [
          ...releaseQueued(state.messages, action.clientId),
          { role: Row.SEND_ERROR, text: action.error || "Failed to send message.", content: action.content ?? null },
        ],
      };

    case Action.ANSWER_SENT: {
      const pauses = state.pauses.filter((p) => !samePause(p, action.pause));
      return {
        ...state,
        pauses,
        // More cards to answer, or the run resumes: as the pipeline if it has
        // not opened yet, as a chat turn if it has.
        phase: pauses.length ? Phase.QUESTIONS : state.opened ? Phase.CHATTING : Phase.PIPELINE,
        isAgentTyping: !pauses.length && state.opened,
      };
    }

    case Action.ANSWER_FAILED:
      return {
        ...state,
        isAgentTyping: false,
        pauses: [action.pause, ...state.pauses.filter((p) => !samePause(p, action.pause))],
        phase: Phase.QUESTIONS,
        messages: [
          ...state.messages,
          { role: Row.SEND_ERROR, text: `Failed to submit: ${action.error || "network error"}.`, content: null },
        ],
      };

    case Action.APPEND_MESSAGE:
      return { ...state, messages: [...closeStreaming(state.messages), action.message] };

    case Action.STOPPED: {
      // A message still marked queued never reached the model: it comes out
      // of the transcript and back into the composer, not into the void.
      const queued = state.messages.filter((m) => m.role === Row.USER && m.queued);
      const kept = queued.length ? state.messages.filter((m) => !(m.role === Row.USER && m.queued)) : state.messages;
      const draft = queued.length
        ? { text: queued.map((m) => m.text).filter(Boolean).join("\n\n"), key: (state.draft?.key || 0) + 1 }
        : state.draft;
      return {
        ...state,
        isAgentTyping: false,
        messages: closeStreaming(kept),
        draft,
        retrying: null,
        phase: action.keepReady ? Phase.READY : Phase.FAILED,
        error: action.keepReady ? state.error : "Stopped.",
        errorCode: action.keepReady ? state.errorCode : ErrorCode.CANCELLED,
        errorRetryable: true,
      };
    }

    case Action.RECONNECTING:
      return { ...state, reconnecting: action.value, isAgentTyping: action.value ? false : state.isAgentTyping };

    case Action.FAILED:
      return {
        ...state,
        reconnecting: false,
        isAgentTyping: false,
        retrying: null,
        error: action.error,
        errorCode: action.code || "",
        errorRetryable: true,
        phase: Phase.FAILED,
      };

    case Action.RESET:
      return { ...initialAgentState, suppressThinking: action.suppressThinking || false };

    default:
      return state;
  }
}

/** Convenience for tests and callers replaying a recorded stream. */
export function replayEvents(events, state = initialAgentState, at = 0) {
  return events.reduce((s, event) => reduceAgentSession(s, { type: Action.EVENT, event, at }), state);
}

export function isPauseEvent(event) {
  return PAUSE_EVENTS.includes(event?.event);
}

// ---------------------------------------------------------------------------
// Friendly errors — the code picks the copy; the text is a fallback
// ---------------------------------------------------------------------------

/** What the user can do about a failure — decides the button under it. */
export const ErrorAction = Object.freeze({
  RETRY:       "retry",        // try the same thing again
  SETTINGS:    "settings",     // the model or key is the problem
  CONNECTIONS: "connections",  // a connector needs attention
  FRESH:       "fresh",        // this conversation cannot continue; a new one can
  NONE:        "none",
});

const ERROR_COPY = Object.freeze({
  [ErrorCode.RATE_LIMITED]:        { text: "The model provider is rate limiting us. Wait a minute, then try again.", action: ErrorAction.RETRY },
  [ErrorCode.OVERLOADED]:          { text: "The model provider is overloaded right now. Try again in a moment.", action: ErrorAction.RETRY },
  [ErrorCode.UPSTREAM_ERROR]:      { text: "The model provider returned an error. Try again.", action: ErrorAction.RETRY },
  [ErrorCode.TIMEOUT]:             { text: "The model took too long to answer. Try again.", action: ErrorAction.RETRY },
  [ErrorCode.NETWORK]:             { text: "Couldn't reach the model provider. Check your connection and try again.", action: ErrorAction.RETRY },
  [ErrorCode.AUTH]:                { text: "The model provider rejected the API key. Check it under Settings → Models.", action: ErrorAction.SETTINGS },
  [ErrorCode.PERMISSION]:          { text: "This API key isn't allowed to use that model. Pick another under Settings → Models.", action: ErrorAction.SETTINGS },
  [ErrorCode.MODEL_NOT_FOUND]:     { text: "That model isn't available on this provider. Pick another under Settings → Models.", action: ErrorAction.SETTINGS },
  [ErrorCode.CONTEXT_WINDOW]:      { text: "This conversation no longer fits the model's context, even after summarising it. Start fresh, or pick a model with a bigger window.", action: ErrorAction.FRESH },
  [ErrorCode.BAD_REQUEST]:         { text: "The model provider rejected the request. Try rephrasing.", action: ErrorAction.NONE },
  [ErrorCode.CONNECTOR_EXPIRED]:   { text: "A connected account needs reconnecting before the agent can read it.", action: ErrorAction.CONNECTIONS },
  [ErrorCode.CONNECTOR_FORBIDDEN]: { text: "A connected account doesn't have access to that data. Check its permissions under Connections.", action: ErrorAction.CONNECTIONS },
  [ErrorCode.CANCELLED]:           { text: "Stopped.", action: ErrorAction.RETRY },
  [ErrorCode.UNKNOWN]:             { text: "Something went wrong. Try again.", action: ErrorAction.RETRY },
});

/** The action a failure with this code deserves. No code means the old
 *  behaviour: offer a retry. */
export function errorAction(code) {
  return ERROR_COPY[code]?.action || ErrorAction.RETRY;
}

/**
 * Translate a failure into something a user can act on. With an `ErrorCode`
 * the copy comes from the table above and the text is ignored — that is what
 * makes it stable across providers. Without one, the raw text is pattern
 * matched (the backend before typed codes, a stream error from the browser),
 * and never passes through anything that looks like a traceback or a status
 * code.
 */
export function friendlyErrorMessage(raw, code = "") {
  const known = ERROR_COPY[code];
  if (known) return known.text;
  const msg = String(raw || "").trim();
  if (!msg) return "Something went wrong. Please try again.";

  // Configuration gaps
  if (/ANTHROPIC_API_KEY/i.test(msg)) return "The assistant isn't connected. Ask your admin to finish setup.";
  if (/GEMINI_API_KEY/i.test(msg)) return "Image generation isn't connected yet. Ask your admin to finish setup.";
  if (/uploads.*disabled/i.test(msg)) return "Image uploads aren't enabled in this environment.";
  if (/POSTBRIDGE|post.?bridge.*connect/i.test(msg)) return "Publishing isn't connected. Ask your admin to set it up.";

  // Common transient classes
  if (/rate limit|429/i.test(msg)) return "We're hitting a rate limit — wait a minute and try again.";
  if (/timeout|timed.?out/i.test(msg)) return "That took longer than expected. Try again.";
  if (/network|connection|fetch failed|ECONNREFUSED/i.test(msg)) return "Couldn't reach the server. Check your internet and try again.";

  // Validation
  if (/validation|invalid|missing/i.test(msg) && msg.length < 200) return "Some input wasn't valid — please review and try again.";

  // Don't leak status codes / file paths / stack traces.
  if (/^\d{3}\b/.test(msg) || /Traceback|line \d+/i.test(msg)) return "Something went wrong on our end. Please try again in a moment.";

  // Reasonably short, doesn't look technical → pass through.
  if (msg.length < 200 && !/^\w+Error:/.test(msg)) return msg;

  return "Something went wrong. Please try again.";
}
