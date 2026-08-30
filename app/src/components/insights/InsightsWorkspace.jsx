"use client";

/**
 * The insights session UI — one chat, no wizard.
 *
 * What it replaces: a six-step form (sources → Ads account → GA4 property →
 * GSC site → goal → review) that had to be completed before the agent ran at
 * all. Everything that form collected, the agent now discovers or asks for
 * mid-run, which is why this component's job is mostly *rendering a pause*:
 * a question, a connect offer, or an account choice, inline in the transcript.
 *
 * All three pauses resolve through the same endpoint (`type: "answer"`), so
 * `answerPending` is one function and the card decides the payload shape.
 *
 * Streaming is the shared `consumeSseStream`; the split shell, todo strip and
 * question card are the same components audit uses — the only genuinely new
 * pieces are the two cards beside this file.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import AuditQuestions from "@/components/audit/AuditQuestions";
import AuditTodos from "@/components/audit/AuditTodos";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import {
  createAgentSession,
  openAgentStream,
  sendAgentMessage,
} from "../../lib/api";
import { consumeSseStream } from "../../lib/sse";
import { InsightsEvent } from "../../lib/insightsEvents";
import AccountSelect from "./AccountSelect";
import ConnectionRequest from "./ConnectionRequest";

const AGENT_TYPE = "insights";

export default function InsightsWorkspace({ projectId, initialPrompt = "" }) {
  const [turns, setTurns] = useState([]);        // [{role, text}] — completed turns
  const [streaming, setStreaming] = useState(""); // the assistant turn in flight
  const [todos, setTodos] = useState([]);
  const [pending, setPending] = useState(null);   // the pause we are showing, if any
  const [status, setStatus] = useState("idle");   // idle | running | ready | failed
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [memories, setMemories] = useState([]);

  const sessionRef = useRef(null);
  const abortRef = useRef(null);
  // The streamed text also lives in a ref: the SSE callback is created once and
  // would otherwise close over a stale `streaming` on every chunk.
  const bufferRef = useRef("");

  const onEvent = useCallback((event) => {
    switch (event.event) {
      case InsightsEvent.AGENT_MESSAGE_CHUNK:
        bufferRef.current += event.text || "";
        setStreaming(bufferRef.current);
        break;
      case InsightsEvent.MESSAGE_STOP: {
        const text = bufferRef.current.trim();
        bufferRef.current = "";
        setStreaming("");
        if (text) setTurns((prev) => [...prev, { role: "assistant", text }]);
        break;
      }
      case InsightsEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;
      case InsightsEvent.MEMORY_RECALLED:
        setMemories(event.memories || []);
        break;
      // The three pauses. Each carries what its card needs to render; the
      // `kind` is what tells this component which card that is.
      case InsightsEvent.QUESTIONS_REQUIRED:
        setPending({ kind: "questions", questions: event.questions || [] });
        break;
      case InsightsEvent.CONNECTION_REQUIRED:
        setPending({ kind: "connection", ...event });
        break;
      case InsightsEvent.ACCOUNT_SELECTION_REQUIRED:
        setPending({ kind: "account", ...event });
        break;
      case InsightsEvent.PIPELINE_FINISHED:
        setStatus("ready");
        break;
      case InsightsEvent.PIPELINE_FAILED:
        setStatus("failed");
        setError(event.error || "The session failed.");
        break;
      case InsightsEvent.STEP_FAILED:
        // A single bad turn — the session is still alive and the user can retry.
        setError(event.error || "That turn failed.");
        break;
      default:
        break;
    }
  }, []);

  const start = useCallback(
    async (prompt) => {
      setStatus("running");
      setError("");
      try {
        const { session_id: sessionId } = await createAgentSession(AGENT_TYPE, {
          project_id: projectId || null,
          prompt,
        });
        sessionRef.current = sessionId;
        const controller = new AbortController();
        abortRef.current = controller;
        const body = await openAgentStream(AGENT_TYPE, sessionId, {
          signal: controller.signal,
        });
        await consumeSseStream(body, onEvent, controller.signal);
      } catch (err) {
        setStatus("failed");
        setError(err?.message || "Could not start the session.");
      }
    },
    [projectId, onEvent]
  );

  useEffect(() => {
    if (sessionRef.current) return;      // StrictMode double-mount guard
    start(initialPrompt);
    return () => abortRef.current?.abort();
  }, [start, initialPrompt]);

  /** Resolve whatever the session is parked on. One endpoint, three shapes. */
  async function answerPending(answers) {
    const sessionId = sessionRef.current;
    if (!sessionId) return;
    setPending(null);
    try {
      await sendAgentMessage(AGENT_TYPE, sessionId, { type: "answer", answers });
    } catch (err) {
      setError(err?.message || "Could not send that answer.");
    }
  }

  async function send() {
    const text = draft.trim();
    const sessionId = sessionRef.current;
    if (!text || !sessionId) return;
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", text }]);
    try {
      await sendAgentMessage(AGENT_TYPE, sessionId, { type: "chat", content: text });
    } catch (err) {
      setError(err?.message || "Could not send that message.");
    }
  }

  const chat = (
    <div className="flex h-full min-h-0 flex-col">
      <AuditTodos todos={todos} />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {memories.length > 0 && (
          <p className="text-[11px] text-muted-foreground">
            Recalled {memories.length} thing{memories.length === 1 ? "" : "s"} Duct already
            knew about this project.
          </p>
        )}

        {turns.map((turn, i) => (
          <Turn key={i} role={turn.role} text={turn.text} />
        ))}
        {streaming && <Turn role="assistant" text={streaming} />}

        {pending?.kind === "questions" && (
          <AuditQuestions questions={pending.questions} onSubmit={answerPending} />
        )}
        {pending?.kind === "connection" && (
          <ConnectionRequest request={pending} onAnswer={answerPending} />
        )}
        {pending?.kind === "account" && (
          <AccountSelect request={pending} onAnswer={answerPending} />
        )}

        {error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-end gap-2 border-t border-border/60 p-3">
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask about your growth data…"
          className="min-h-[2.5rem] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <Button size="sm" onClick={send} disabled={!draft.trim() || status === "running"}>
          Send
        </Button>
      </div>
    </div>
  );

  // The right pane is the artifact viewport. Insights does not produce one yet
  // — that is the markdown artifact contract, still to come — so it says so
  // rather than showing an empty frame that looks broken.
  const viewport = (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <p className="max-w-xs text-xs text-muted-foreground">
        Briefs will appear here once Duct can pull your data. For now the
        conversation is on the left.
      </p>
    </div>
  );

  return (
    <SplitWorkspace
      left={chat}
      right={viewport}
      storageKey="insights_split_w"
      leftLabel="Chat"
      rightLabel="Brief"
      rightStatus={status === "running" ? "busy" : "idle"}
    />
  );
}

function Turn({ role, text }) {
  const isUser = role === "user";
  return (
    <div className={isUser ? "flex justify-end" : ""}>
      <div
        className={`whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
          isUser ? "max-w-[85%] bg-primary/10" : "text-foreground"
        }`}
      >
        {text}
      </div>
    </div>
  );
}
