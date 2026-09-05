"use client";

/**
 * Phase transitions → system notifications, for a tab nobody is looking at.
 *
 * Three moments matter, and they are the ones OpenCode notifies on: the
 * agent finished ("Done"), it stopped to ask ("Needs your input"), it failed.
 * They are read off the session reducer's phase, so every workspace gets them
 * by naming itself (`notifyAs`) and none has to remember to send one — the
 * audit page used to be the only one that did, from inside its own event
 * handler, and only for questions.
 *
 * A stop the user asked for is not news, and neither is a failure while the
 * page is on screen; lib/notify.js drops anything while the window is focused.
 */

import { useEffect, useRef } from "react";
import { ErrorCode } from "../lib/agentEvents";
import { Phase } from "../lib/agentPhase";
import { notifyIfAway } from "../lib/notify";

const BUSY = new Set([Phase.PIPELINE, Phase.CHATTING]);

/** The notice a transition deserves, or null. Exported for the tests. */
export function noticeFor(previous, next, { errorCode = "", pendingKind = "" } = {}) {
  if (previous === next) return null;
  if (next === Phase.QUESTIONS && BUSY.has(previous)) {
    return {
      title: "needs your input",
      body: pendingKind === "connection" ? "A connection is needed before it can continue." : "It has a question before it can continue.",
      tag: "input",
    };
  }
  if (next === Phase.READY && BUSY.has(previous)) {
    return { title: "is done", body: "The reply is ready when you are.", tag: "done" };
  }
  if (next === Phase.FAILED && errorCode !== ErrorCode.CANCELLED) {
    return { title: "ran into a problem", body: "Open the tab to see what happened and what to do.", tag: "failed" };
  }
  return null;
}

export function useAgentNotifications(state, name) {
  const previous = useRef(state.phase);
  useEffect(() => {
    const was = previous.current;
    previous.current = state.phase;
    if (!name) return;
    const notice = noticeFor(was, state.phase, {
      errorCode: state.errorCode,
      pendingKind: state.pauses[0]?.event?.replace(/_required$/, "") || "",
    });
    if (!notice) return;
    notifyIfAway({ title: `${name} ${notice.title}`, body: notice.body, tag: `${name}:${notice.tag}` });
  }, [state.phase, state.errorCode, state.pauses, name]);
}

export default useAgentNotifications;
