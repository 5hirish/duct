"use client";

/**
 * useAgentSession — the one session lifecycle every agent workspace runs on.
 *
 * Owns the network half of an agent session so no workspace has to: create
 * the session (closing the orphan if the component was torn down first),
 * hydrate the stored transcript before the live stream, open the stream, run
 * the reconnect loop, resolve pauses by id, and put a reloaded tab back on the
 * run it was watching. State transitions go through the pure reducer in
 * lib/agentSession.js; this file only decides *when* to dispatch.
 *
 * What a reload does, in order: read the tab's handle for `handleKey`; if it
 * names a live session, reattach (the backend holds a run for a grace window
 * after its stream drops and buffers what it emitted meanwhile); if not,
 * create a session that resumes the conversation. Either way the transcript
 * is rehydrated first so the order is history, then live turns.
 *
 * What the caller owns: everything agent-specific. Events the reducer does
 * not handle (an artifact version, a plan payload, a slide render request)
 * reach `onEvent` — and so does every other event, after the reducer, so a
 * workspace can react to PIPELINE_STARTED's payload without re-parsing it.
 *
 *   const agent = useAgentSession({
 *     agentType: "insights",
 *     body: { project_id, prompt, conversation_id?, resume? },
 *     handleKey: `insights:${projectId}:${conversationId || prompt}`,
 *     notifyAs: "Insights",
 *     onEvent: (event, { appendMessage }) => { ... },
 *   });
 *
 * `notifyAs` turns phase transitions into system notifications while the tab
 * is not being looked at — done, needs input, failed — through
 * hooks/useAgentNotifications.js. A workspace never sends its own.
 *
 * `body` is the create payload; the effect reopens when it changes by value.
 * `handleKey` scopes the reload handle — make it specific to what the page
 * shows (a post id, a plan, a question) so a different page never resumes the
 * wrong run.
 */

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  closeAgentSession,
  createAgentSession,
  getAgentConversation,
  getAgentSessionState,
  getAgentThreadState,
  openAgentStream,
  sendAgentMessage,
} from "../lib/api";
import { AgentEvent } from "../lib/agentEvents";
import { mapEventsToMessages } from "../lib/agentHistory";
import { Phase } from "../lib/agentPhase";
import {
  Action,
  friendlyErrorMessage,
  initialAgentState,
  reduceAgentSession,
} from "../lib/agentSession";
import { clearSessionHandle, readSessionHandle, writeSessionHandle } from "../lib/agentSessionHandle";
import { consumeSseStream } from "../lib/sse";
import { useAgentNotifications } from "./useAgentNotifications";

const MAX_RECONNECT = 5;
function newClientId() {
  try {
    return crypto.randomUUID();
  } catch {
    return `m_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  }
}

const NOT_ATTACHED = "Still connecting to the session — try again in a moment.";

/** Jittered exponential backoff: ~1s, 2s, 4s, 8s, 15s (±50% jitter). */
function backoffDelay(attempt) {
  const base = Math.min(15000, 1000 * 2 ** (attempt - 1));
  return Math.round(base * (0.5 + Math.random() * 0.5));
}

function sleep(ms, signal) {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => { clearTimeout(t); resolve(); }, { once: true });
  });
}

export function useAgentSession({
  agentType,
  body,
  handleKey = "",
  enabled = true,
  hydrateThreadState = false,
  // The agent's name in a system notification ("Insights is done"). Omit it
  // and the session never notifies.
  notifyAs = "",
  onEvent,
}) {
  const [state, dispatch] = useReducer(reduceAgentSession, initialAgentState);
  useAgentNotifications(state, notifyAs);
  const [sessionId, setSessionId] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [attempt, setAttempt] = useState(0);        // retry re-runs the effect
  const [override, setOverride] = useState(null);   // start-fresh replaces the body

  const sessionIdRef = useRef(null);
  const conversationIdRef = useRef(null);
  const abortRef = useRef(null);
  // Latest props/state for callbacks created once per effect.
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const stateRef = useRef(state);
  stateRef.current = state;
  const bodyRef = useRef(body);
  bodyRef.current = body;

  const openBody = override || body;
  const bodyKey = JSON.stringify(openBody || null);

  const appendMessage = useCallback((message) => {
    dispatch({ type: Action.APPEND_MESSAGE, message });
  }, []);

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!enabled || !openBody) return undefined;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    // Per-effect-instance state (closures, not refs) so a StrictMode
    // double-mount never lets one instance clobber or leak the other's session.
    let cancelled = false;
    let adopted = null;      // the session this instance is attached to
    let reconnects = 0;
    // A real run failure — never auto-reconnect after it.
    let terminal = false;

    const dead = () => cancelled || ctrl.signal.aborted;

    function adopt(sid, cid) {
      adopted = sid;
      sessionIdRef.current = sid;
      setSessionId(sid);
      const next = cid || conversationIdRef.current || null;
      conversationIdRef.current = next;
      setConversationId(next);
      writeSessionHandle(handleKey, { sessionId: sid, conversationId: next });
    }

    function handleEvent(event) {
      // Any frame proves the stream is healthy — a drop later starts the
      // backoff from zero again.
      reconnects = 0;
      if (event.event === AgentEvent.PIPELINE_FAILED) {
        terminal = true;
        clearSessionHandle(handleKey);
      }
      // `at` is this client's clock at receipt: a retry countdown is anchored
      // to it, never to the server's clock.
      dispatch({ type: Action.EVENT, event, at: Date.now() });
      onEventRef.current?.(event, { appendMessage, sessionId: sessionIdRef.current, dispatch });
    }

    async function hydrate(cid) {
      // History first, so the order is stored turns then live ones. Non-fatal:
      // the server still resumes; the UI just lacks the transcript.
      try {
        const { events } = await getAgentConversation(agentType, cid);
        if (dead()) return;
        const messages = mapEventsToMessages(events);
        dispatch({ type: Action.HYDRATE, messages, suppressThinking: true });
      } catch {
        /* see above */
      }
      if (!hydrateThreadState) return;
      // The parked card, before any session exists to replay it.
      try {
        const thread = await getAgentThreadState(agentType, cid);
        if (dead()) return;
        if (thread?.pauses?.length || thread?.todos?.length) {
          dispatch({ type: Action.PAUSES, pauses: thread.pauses || [], todos: thread.todos || [], usage: thread.usage });
        }
      } catch {
        /* an agent without a durable thread, or offline — the stream will tell */
      }
    }

    async function create(extra) {
      const res = await createAgentSession(agentType, { ...openBody, ...extra });
      // Torn down before the stream opened (StrictMode remount / fast nav):
      // close the orphan so its worker is cancelled instead of racing the
      // surviving session.
      if (dead()) {
        closeAgentSession(agentType, res.session_id).catch(() => {});
        return null;
      }
      adopt(res.session_id, res.conversation_id);
      return openAgentStream(agentType, res.session_id, { signal: ctrl.signal });
    }

    // Re-open the stream of a session that already exists. The session id is
    // adopted the instant the stream is open — before anything else is
    // awaited — because a card restored from the thread state may already be
    // on screen, and an answer to it needs somewhere to go.
    async function reattach(sid, cid) {
      let stream;
      try {
        stream = await openAgentStream(agentType, sid, { signal: ctrl.signal });
      } catch {
        return null;  // past the grace window, or a different backend — create instead
      }
      if (dead()) return null;
      adopt(sid, cid);
      // The stream only carries what happens from now on. A card the run is
      // already parked on was delivered before the drop, so it is put back
      // from the session's state rather than waited for. Not awaited: the
      // stream must start draining now, and the card can land a beat later.
      getAgentSessionState(agentType, sid)
        .then((state) => {
          if (!dead() && state?.pending?.length) dispatch({ type: Action.PAUSES, pauses: state.pending });
        })
        .catch(() => { /* an older backend without the field — the next event will tell */ });
      return stream;
    }

    // After an unexpected drop: prefer the same live session so the in-flight
    // run continues gap-free; if it is gone, resume from the conversation.
    // Without a conversation there is nothing to resume into, and silently
    // re-running the whole pipeline is worse than saying the link was lost.
    async function reconnect() {
      if (sessionIdRef.current) {
        const stream = await reattach(sessionIdRef.current, conversationIdRef.current);
        if (stream) return stream;
      }
      if (dead() || !conversationIdRef.current) return null;
      return create({ conversation_id: conversationIdRef.current, resume: true });
    }

    async function start() {
      const handle = readSessionHandle(handleKey);
      const resumeCid = openBody.conversation_id || handle?.conversationId || null;
      if (resumeCid) await hydrate(resumeCid);
      if (dead()) return;

      let stream = null;
      if (handle?.sessionId) stream = await reattach(handle.sessionId, handle.conversationId);
      if (!stream && !dead()) {
        const resuming = Boolean(openBody.conversation_id) || Boolean(handle?.conversationId);
        const extra =
          !openBody.conversation_id && handle?.conversationId
            ? { conversation_id: handle.conversationId, resume: true }
            : {};
        // A brand-new thread opens with what was asked, the way the backend
        // records it — a transcript that starts with the answer reads wrong.
        if (!resuming && typeof openBody.prompt === "string" && openBody.prompt.trim()) {
          dispatch({ type: Action.HYDRATE, messages: [{ role: "user", text: openBody.prompt.trim() }] });
        }
        stream = await create(extra);
      }
      if (!stream || dead()) return;

      // Stream → reconnect loop. consumeSseStream returns on a server-side end
      // and throws on a network error; both are drops unless the run is truly
      // terminal or we have been torn down.
      while (true) {
        try {
          await consumeSseStream(stream, handleEvent, ctrl.signal);
        } catch {
          /* network drop → reconnect below */
        }
        if (dead() || terminal) return;

        reconnects += 1;
        if (reconnects > MAX_RECONNECT) {
          dispatch({ type: Action.FAILED, error: "We lost the connection and couldn't reconnect. Please retry." });
          return;
        }
        dispatch({ type: Action.RECONNECTING, value: true });
        await sleep(backoffDelay(reconnects), ctrl.signal);
        if (dead()) return;

        let next = null;
        try { next = await reconnect(); } catch { next = null; }
        if (dead()) return;
        if (!next) {
          if (!conversationIdRef.current) {
            dispatch({ type: Action.FAILED, error: "We lost the connection to this run. Please retry." });
            return;
          }
          continue;  // open failed → loop backs off again
        }
        stream = next;
        dispatch({ type: Action.RECONNECTING, value: false });
      }
    }

    start().catch((err) => {
      if (!dead()) dispatch({ type: Action.FAILED, error: friendlyErrorMessage(err?.message || "Stream error.") });
    });

    return () => {
      cancelled = true;
      ctrl.abort();
      const sid = sessionIdRef.current || adopted;
      if (sid) {
        closeAgentSession(agentType, sid).catch(() => {});
        if (sessionIdRef.current === sid) sessionIdRef.current = null;
      }
      // Only an instance that actually attached forgets the handle. A
      // StrictMode first mount is torn down before it attaches, and clearing
      // then would rob the second mount of the reload it was about to do.
      if (adopted) clearSessionHandle(handleKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType, bodyKey, enabled, attempt, handleKey, hydrateThreadState]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const send = useCallback(
    async (content, extra = {}) => {
      const text = typeof content === "string" ? content : "[image attached]";
      // The id is what lets USER_INPUT_CONSUMED release this row and no other.
      const clientId = newClientId();
      dispatch({ type: Action.USER_SENT, text, clientId });
      if (!sessionIdRef.current) {
        dispatch({ type: Action.SEND_FAILED, error: NOT_ATTACHED, content, clientId });
        return;
      }
      try {
        await sendAgentMessage(agentType, sessionIdRef.current, {
          type: "chat",
          content,
          client_message_id: clientId,
          ...extra,
        });
      } catch (err) {
        dispatch({ type: Action.SEND_FAILED, error: err?.message, content, clientId });
      }
    },
    [agentType],
  );

  const answer = useCallback(
    async (answers) => {
      const pause = stateRef.current.pauses[0];
      if (!pause) return;
      dispatch({ type: Action.ANSWER_SENT, pause });
      if (!sessionIdRef.current) {
        dispatch({ type: Action.ANSWER_FAILED, pause, error: NOT_ATTACHED });
        return;
      }
      try {
        await sendAgentMessage(agentType, sessionIdRef.current, {
          type: "answer",
          answers,
          ...(pause.interrupt_id ? { interrupt_id: pause.interrupt_id } : {}),
        });
      } catch (err) {
        // Put the card back so the user can try again — the session is fine.
        dispatch({ type: Action.ANSWER_FAILED, pause, error: err?.message });
      }
    },
    [agentType],
  );

  /** Stop the in-flight work. Stopping a chat turn returns to READY; stopping
   *  the opening run is a failure (there is nothing to be ready with) unless
   *  the caller says otherwise via `keepReady`. */
  const stop = useCallback(
    ({ keepReady } = {}) => {
      abortRef.current?.abort();
      if (sessionIdRef.current) closeAgentSession(agentType, sessionIdRef.current).catch(() => {});
      clearSessionHandle(handleKey);
      dispatch({ type: Action.STOPPED, keepReady: keepReady ?? stateRef.current.opened });
    },
    [agentType, handleKey],
  );

  /** Start the same request over from nothing. */
  const retry = useCallback(() => {
    clearSessionHandle(handleKey);
    setOverride(null);
    dispatch({ type: Action.RESET });
    setAttempt((n) => n + 1);
  }, [handleKey]);

  /** Abandon the conversation, keep whatever it produced, open a new one.
   *  `extra` lets the caller bind the new conversation (to the same post, say). */
  const startFresh = useCallback(
    (extra = {}) => {
      abortRef.current?.abort();
      if (sessionIdRef.current) closeAgentSession(agentType, sessionIdRef.current).catch(() => {});
      clearSessionHandle(handleKey);
      sessionIdRef.current = null;
      conversationIdRef.current = null;
      setSessionId(null);
      setConversationId(null);
      dispatch({ type: Action.RESET });
      setOverride({
        ...(bodyRef.current || {}),
        ...extra,
        conversation_id: undefined,
        resume: false,
        start_fresh: true,
      });
    },
    [agentType, handleKey],
  );

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  const { phase, isAgentTyping, reconnecting } = state;
  const isRunning = phase === Phase.STARTING || phase === Phase.PIPELINE;
  const pending = state.pauses[0] || null;

  return {
    ...state,
    pending,
    sessionId,
    conversationId,
    // A card can be on screen before the session is (restored from the
    // thread's state on open); until this is true it has nowhere to answer to.
    attached: Boolean(sessionId),
    isRunning,
    // The agent is producing tokens — drives the Stop button.
    isStreaming: isRunning || (phase === Phase.CHATTING && isAgentTyping),
    // The default input policy: open whenever there is a session to send to.
    // A message while the run works or a card waits is queued (the backend
    // steers it in at the next model call, or holds it for the next turn),
    // so the box only closes before the session exists, while the link is
    // down, or after a terminal failure.
    inputDisabled: phase === Phase.STARTING || phase === Phase.FAILED || reconnecting,
    send,
    answer,
    stop,
    retry,
    startFresh,
    appendMessage,
    dispatch,
  };
}

export default useAgentSession;
