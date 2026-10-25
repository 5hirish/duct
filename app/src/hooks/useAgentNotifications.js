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
import { msg } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { ErrorCode } from "../lib/agentEvents";
import { Phase } from "../lib/agentPhase";
import { notifyIfAway } from "../lib/notify";

const BUSY = new Set([Phase.PIPELINE, Phase.CHATTING]);

/** The notice a transition deserves — a tag and a fact, no words — or null.
 *  Exported for the tests. */
export function noticeFor(previous, next, { errorCode = "", pendingKind = "" } = {}) {
  if (previous === next) return null;
  if (next === Phase.QUESTIONS && BUSY.has(previous)) {
    return { tag: "input", connection: pendingKind === "connection" };
  }
  if (next === Phase.READY && BUSY.has(previous)) return { tag: "done" };
  if (next === Phase.FAILED && errorCode !== ErrorCode.CANCELLED) return { tag: "failed" };
  return null;
}

/** The words for a notice. The agent's name sits inside the sentence rather
 *  than glued in front of a fragment: "Insights is done" is one message a
 *  translator can reorder; `${name} ${"is done"}` is not. */
function noticeWords(i18n, name, notice) {
  switch (notice.tag) {
    case "input":
      return {
        title: i18n._(msg`${name} needs your input`),
        body: notice.connection
          ? i18n._(msg`A connection is needed before it can continue.`)
          : i18n._(msg`It has a question before it can continue.`),
      };
    case "done":
      return { title: i18n._(msg`${name} is done`), body: i18n._(msg`The reply is ready when you are.`) };
    default:
      return { title: i18n._(msg`${name} ran into a problem`), body: i18n._(msg`Open the tab to see what happened and what to do.`) };
  }
}

export function useAgentNotifications(state, name) {
  const { i18n } = useLingui();
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
    const { title, body } = noticeWords(i18n, name, notice);
    notifyIfAway({ title, body, tag: `${name}:${notice.tag}` });
    // i18n is stable for a mounted tree; the locale changes with a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.errorCode, state.pauses, name]);
}

export default useAgentNotifications;
