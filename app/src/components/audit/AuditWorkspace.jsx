"use client";

import { useEffect, useRef, useState } from "react";
import AuditChat from "./AuditChat";
import AuditReport from "./AuditReport";
import {
  closeAgentSession,
  createAgentSession,
  openAgentStream,
  sendAgentMessage,
} from "../../lib/api";
import { AuditEvent } from "../../lib/auditEvents";

// ---------------------------------------------------------------------------
// Phase enum — single source of truth for what the UI shows
// ---------------------------------------------------------------------------
export const Phase = {
  STARTING:  "starting",   // connecting, before first SSE event
  PIPELINE:  "pipeline",   // steps running
  QUESTIONS: "questions",  // agent waiting for user answers
  READY:     "ready",      // report done, chat open
  CHATTING:  "chatting",   // user sent a message, waiting for reply
  FAILED:    "failed",     // fatal error — show retry
};

// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------

function parseSseDataFrame(frame) {
  const dataLines = frame
    .split("\n")
    .filter((l) => l.startsWith("data: "))
    .map((l) => l.slice(6));
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

async function consumeSseStream(body, onEvent, signal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        const event = parseSseDataFrame(frame);
        if (event) onEvent(event);
      }
    }
  } catch (err) {
    if (!signal?.aborted) throw err;
  } finally {
    reader.releaseLock();
  }
}

const INITIAL_SPLIT = 50;

// ---------------------------------------------------------------------------
// AuditWorkspace
// ---------------------------------------------------------------------------

export default function AuditWorkspace({ sessionId, auditParams }) {
  const [leftWidth, setLeftWidth] = useState(() => {
    if (typeof window !== "undefined") {
      return Number(localStorage.getItem("audit_split_w") || INITIAL_SPLIT);
    }
    return INITIAL_SPLIT;
  });

  // Core state
  const [phase, setPhase]                     = useState(Phase.STARTING);
  const [steps, setSteps]                     = useState([]);
  const [todos, setTodos]                     = useState([]);
  const [messages, setMessages]               = useState([]);
  const [reportVersions, setReportVersions]   = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [pendingQuestions, setPendingQuestions] = useState(null);
  const [errorMsg, setErrorMsg]               = useState("");
  const [retryCount, setRetryCount]           = useState(0);

  // Refs that need to be readable inside async closures without stale values
  const abortRef            = useRef(null);
  const pipelineEndedRef    = useRef(false); // set by PIPELINE_FINISHED or PIPELINE_FAILED
  const reportReceivedRef   = useRef(false); // set when any report data arrives
  const backendSessionIdRef = useRef(null);
  const agentTypeRef        = useRef("audit_seo");
  const dragging            = useRef(false);
  const containerRef        = useRef(null);

  // ---------------------------------------------------------------------------
  // Retry
  // ---------------------------------------------------------------------------

  function handleRetry() {
    setPhase(Phase.STARTING);
    setSteps([]);
    setTodos([]);
    setMessages([]);
    setReportVersions([]);
    setSelectedVersionId(null);
    setPendingQuestions(null);
    setErrorMsg("");
    pipelineEndedRef.current  = false;
    reportReceivedRef.current = false;
    setRetryCount((c) => c + 1);
  }

  // ---------------------------------------------------------------------------
  // SSE stream lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current          = ctrl;
    pipelineEndedRef.current  = false;
    reportReceivedRef.current = false;

    async function start() {
      try {
        const { session_id, agent_type } = await createAgentSession("audit_seo", auditParams);
        backendSessionIdRef.current = session_id;
        agentTypeRef.current        = agent_type;

        const body = await openAgentStream(agent_type, session_id, { signal: ctrl.signal });
        await consumeSseStream(body, handleEvent, ctrl.signal);

        // Stream closed without a terminal event → backend crashed silently
        if (!ctrl.signal.aborted && !pipelineEndedRef.current) {
          setErrorMsg("Backend closed the stream unexpectedly.");
          setPhase(Phase.FAILED);
        }
      } catch (err) {
        if (!ctrl.signal.aborted) {
          setErrorMsg(err.message || "Stream error.");
          setPhase(Phase.FAILED);
        }
      }
    }

    start();
    return () => {
      ctrl.abort();
      if (backendSessionIdRef.current) {
        closeAgentSession(agentTypeRef.current, backendSessionIdRef.current).catch(() => {});
      }
    };
  }, [retryCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Event handler — maps every SSE event to a phase transition + data update
  // ---------------------------------------------------------------------------

  function handleEvent(event) {
    switch (event.event) {

      case AuditEvent.STEP_STARTED:
        setPhase(Phase.PIPELINE);
        setSteps((prev) => {
          const existing = prev.find((s) => s.step_id === event.step_id);
          if (existing)
            return prev.map((s) =>
              s.step_id === event.step_id ? { ...s, status: "running" } : s
            );
          return [...prev, { step_id: event.step_id, label: event.label, status: "running", payload: null }];
        });
        break;

      case AuditEvent.STEP_FINISHED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: event.status || "success", payload: event.payload || null }
              : s
          )
        );
        break;

      case AuditEvent.QUESTIONS_REQUIRED:
        setPendingQuestions(event.questions);
        setPhase(Phase.QUESTIONS);
        break;

      case AuditEvent.REPORT_UPDATED:
        reportReceivedRef.current = true;
        setReportVersions((prev) => {
          const updated = [
            ...prev.filter((v) => v.version_id !== event.version_id),
            { version_id: event.version_id, label: event.label, report: event.payload },
          ].sort((a, b) => a.version_id - b.version_id);
          return updated;
        });
        setSelectedVersionId(event.version_id);
        break;

      case AuditEvent.PIPELINE_FINISHED:
        pipelineEndedRef.current = true;
        if (event.payload) {
          reportReceivedRef.current = true;
          setReportVersions((prev) => {
            const v1 = { version_id: 1, label: "Initial audit", report: event.payload };
            return prev.some((v) => v.version_id === 1)
              ? prev
              : [v1, ...prev.filter((v) => v.version_id !== 1)];
          });
          setSelectedVersionId(1);
          setPhase(Phase.READY);
        } else if (reportReceivedRef.current) {
          // Report already arrived via REPORT_UPDATED
          setPhase(Phase.READY);
        } else {
          // Pipeline completed but no report was ever produced
          setErrorMsg("AI synthesis finished but no report was generated.");
          setPhase(Phase.FAILED);
        }
        break;

      case AuditEvent.PIPELINE_FAILED:
        pipelineEndedRef.current = true;
        setErrorMsg(event.error || "Audit pipeline failed.");
        setPhase(Phase.FAILED);
        break;

      case AuditEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;

      case AuditEvent.AGENT_MESSAGE_CHUNK:
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, text: last.text + event.text }];
          return [...prev, { role: "assistant", text: event.text, streaming: true }];
        });
        break;

      case AuditEvent.MESSAGE_STOP:
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
          return prev;
        });
        setPhase(Phase.READY);
        break;

      case AuditEvent.AGENT_MESSAGE:
        setMessages((prev) => [...prev, { role: "assistant", text: event.text }]);
        setPhase(Phase.READY);
        break;

      default:
        break;
    }
  }

  // ---------------------------------------------------------------------------
  // User actions
  // ---------------------------------------------------------------------------

  async function handleAnswerQuestions(answers) {
    setPendingQuestions(null);
    setPhase(Phase.PIPELINE);
    try {
      await sendAgentMessage(agentTypeRef.current, backendSessionIdRef.current, {
        type: "answer",
        answers,
      });
    } catch (err) {
      setErrorMsg(err.message);
      setPhase(Phase.FAILED);
    }
  }

  async function handleSendMessage(content) {
    const text = typeof content === "string" ? content : "[image attached]";
    setMessages((prev) => [...prev, { role: "user", text }]);
    setPhase(Phase.CHATTING);
    try {
      await sendAgentMessage(agentTypeRef.current, backendSessionIdRef.current, {
        type: "chat",
        content,
        context_version_id: selectedVersionId,
      });
    } catch (err) {
      setErrorMsg(err.message);
      setPhase(Phase.FAILED);
    }
  }

  // ---------------------------------------------------------------------------
  // Drag divider
  // ---------------------------------------------------------------------------

  function onMouseDownDivider(e) {
    e.preventDefault();
    dragging.current = true;
    function onMove(ev) {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.min(80, Math.max(20, ((ev.clientX - rect.left) / rect.width) * 100));
      setLeftWidth(pct);
      localStorage.setItem("audit_split_w", String(pct));
    }
    function onUp() {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      <div
        className="flex flex-col overflow-hidden border-r border-border/60"
        style={{ width: `${leftWidth}%`, minWidth: "280px" }}
      >
        <AuditChat
          phase={phase}
          steps={steps}
          todos={todos}
          messages={messages}
          pendingQuestions={pendingQuestions}
          hasReport={reportVersions.length > 0}
          errorMsg={errorMsg}
          onAnswerQuestions={handleAnswerQuestions}
          onSendMessage={handleSendMessage}
          onRetry={handleRetry}
        />
      </div>

      <div
        onMouseDown={onMouseDownDivider}
        className="w-1 shrink-0 cursor-col-resize bg-border/40 hover:bg-primary/30 transition-colors select-none"
        title="Drag to resize"
      />

      <div className="flex-1 flex flex-col overflow-hidden min-w-[280px]">
        <AuditReport
          phase={phase}
          versions={reportVersions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={setSelectedVersionId}
          errorMsg={errorMsg}
          onRetry={handleRetry}
        />
      </div>
    </div>
  );
}
