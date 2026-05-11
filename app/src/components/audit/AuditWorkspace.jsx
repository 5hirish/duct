"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AuditChat from "./AuditChat";
import AuditReport from "./AuditReport";
import {
  closeAuditSession,
  sendAuditChat,
  startAuditStream,
  submitAuditAnswers,
} from "../../lib/api";
import { AuditEvent, AuditStep } from "../../lib/auditEvents";

function parseSseDataFrame(frame) {
  const dataLines = frame
    .split("\n")
    .filter(l => l.startsWith("data: "))
    .map(l => l.slice(6));
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

export default function AuditWorkspace({ sessionId, auditParams }) {
  const [leftWidth, setLeftWidth] = useState(() => {
    if (typeof window !== "undefined") {
      return Number(localStorage.getItem("audit_split_w") || INITIAL_SPLIT);
    }
    return INITIAL_SPLIT;
  });

  const [steps, setSteps] = useState([]);
  const [todos, setTodos] = useState([]);
  const [messages, setMessages] = useState([]);
  const [reportVersions, setReportVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [pendingQuestions, setPendingQuestions] = useState(null);
  const [agentBusy, setAgentBusy] = useState(true);
  const [reportReady, setReportReady] = useState(false);
  const [error, setError] = useState("");

  const abortRef = useRef(null);
  const dragging = useRef(false);
  const containerRef = useRef(null);

  // Actual backend session ID (returned from SSE response header)
  const backendSessionIdRef = useRef(null);

  // Start the SSE stream on mount
  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    async function start() {
      try {
        const { sessionId: sid, body } = await startAuditStream(auditParams, {
          signal: ctrl.signal,
        });
        backendSessionIdRef.current = sid || sessionId;

        await consumeSseStream(body, handleEvent, ctrl.signal);
      } catch (err) {
        if (!ctrl.signal.aborted) {
          setError(err.message || "Stream error");
          setAgentBusy(false);
        }
      }
    }

    start();
    return () => {
      ctrl.abort();
      if (backendSessionIdRef.current) {
        closeAuditSession(backendSessionIdRef.current).catch(() => {});
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleEvent(event) {
    switch (event.event) {
      case AuditEvent.STEP_STARTED:
        setSteps(prev => {
          const existing = prev.find(s => s.step_id === event.step_id);
          if (existing) return prev.map(s => s.step_id === event.step_id ? { ...s, status: "running" } : s);
          return [...prev, { step_id: event.step_id, label: event.label, status: "running", payload: null }];
        });
        break;

      case AuditEvent.STEP_FINISHED:
        setSteps(prev =>
          prev.map(s =>
            s.step_id === event.step_id
              ? { ...s, status: event.status || "success", payload: event.payload || null }
              : s
          )
        );
        break;

      case AuditEvent.QUESTIONS_REQUIRED:
        setPendingQuestions(event.questions);
        setAgentBusy(false);
        break;

      case AuditEvent.REPORT_UPDATED:
        setReportVersions(prev => {
          const updated = [
            ...prev.filter(v => v.version_id !== event.version_id),
            { version_id: event.version_id, label: event.label, report: event.payload },
          ].sort((a, b) => a.version_id - b.version_id);
          return updated;
        });
        setSelectedVersionId(event.version_id);
        break;

      case AuditEvent.PIPELINE_FINISHED:
        setReportReady(true);
        setAgentBusy(false);
        if (event.payload) {
          setReportVersions(prev => {
            const v1 = { version_id: 1, label: "Initial audit", report: event.payload };
            const exists = prev.some(v => v.version_id === 1);
            return exists ? prev : [v1, ...prev.filter(v => v.version_id !== 1)];
          });
          setSelectedVersionId(1);
        }
        break;

      case AuditEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;

      case AuditEvent.AGENT_MESSAGE_CHUNK:
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && last.streaming) {
            return [...prev.slice(0, -1), { ...last, text: last.text + event.text }];
          }
          return [...prev, { role: "assistant", text: event.text, streaming: true }];
        });
        break;

      case AuditEvent.MESSAGE_STOP:
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last && last.streaming) {
            return [...prev.slice(0, -1), { ...last, streaming: false }];
          }
          return prev;
        });
        setAgentBusy(false);
        break;

      case AuditEvent.AGENT_MESSAGE:
        setMessages(prev => [...prev, { role: "assistant", text: event.text }]);
        setAgentBusy(false);
        break;

      case AuditEvent.PIPELINE_FAILED:
        setError(event.error || "Audit failed.");
        setAgentBusy(false);
        break;

      default:
        break;
    }
  }

  function activeSid() {
    return backendSessionIdRef.current || sessionId;
  }

  async function handleAnswerQuestions(answers) {
    setPendingQuestions(null);
    setAgentBusy(true);
    try {
      await submitAuditAnswers(activeSid(), answers);
    } catch (err) {
      setError(err.message);
      setAgentBusy(false);
    }
  }

  async function handleSendMessage(content) {
    const text = typeof content === "string" ? content : "[image attached]";
    setMessages(prev => [...prev, { role: "user", text }]);
    setAgentBusy(true);
    try {
      await sendAuditChat(activeSid(), content, selectedVersionId);
    } catch (err) {
      setError(err.message);
      setAgentBusy(false);
    }
  }

  // Draggable divider
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

  return (
    <div
      ref={containerRef}
      className="flex h-full w-full overflow-hidden"
      style={{ height: "calc(100vh - var(--header-h, 56px))" }}
    >
      {/* Left — Chat */}
      <div
        className="flex flex-col overflow-hidden border-r border-border/60"
        style={{ width: `${leftWidth}%`, minWidth: "280px" }}
      >
        {error && (
          <div className="bg-destructive/10 text-destructive text-xs px-4 py-2 border-b border-destructive/20">
            {error}
          </div>
        )}
        <AuditChat
          messages={messages}
          steps={steps}
          todos={todos}
          pendingQuestions={pendingQuestions}
          sessionId={sessionId}
          onAnswerQuestions={handleAnswerQuestions}
          onSendMessage={handleSendMessage}
          agentBusy={agentBusy}
          reportReady={reportReady}
        />
      </div>

      {/* Draggable divider */}
      <div
        onMouseDown={onMouseDownDivider}
        className="w-1 shrink-0 cursor-col-resize bg-border/40 hover:bg-primary/30 transition-colors select-none"
        title="Drag to resize"
      />

      {/* Right — Report */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-[280px]">
        <AuditReport
          versions={reportVersions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={setSelectedVersionId}
        />
      </div>
    </div>
  );
}
