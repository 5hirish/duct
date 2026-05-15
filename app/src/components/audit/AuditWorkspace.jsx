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
import { AuditEvent, AuditStep } from "../../lib/auditEvents";
import { Phase } from "./auditPhase";
import { useAuditNav } from "../../lib/auditNavContext";

// Re-export so consumers can import Phase from AuditWorkspace if they prefer
export { Phase } from "./auditPhase";

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
  const { setIsAuditRunning } = useAuditNav();

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

  // Tell the nav bar whether to lock the back button
  useEffect(() => {
    const running = phase === Phase.STARTING || phase === Phase.PIPELINE;
    setIsAuditRunning(running);
  }, [phase, setIsAuditRunning]);

  // Clear on unmount so the back button re-enables if the user navigates away
  useEffect(() => {
    return () => setIsAuditRunning(false);
  }, [setIsAuditRunning]);

  // ---------------------------------------------------------------------------
  // Browser notification permission — request once on mount
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

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

      // Thinking tokens from extended-thinking — accumulate into the current streaming bubble
      case AuditEvent.THINKING_CHUNK:
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, thinking: (last.thinking || "") + event.text }];
          return [...prev, { role: "assistant", text: "", thinking: event.text, streaming: true }];
        });
        break;

      // Fix 2 — browser notification + header pulse when agent needs input
      case AuditEvent.QUESTIONS_REQUIRED:
        setPendingQuestions(event.questions);
        setPhase(Phase.QUESTIONS);
        if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
          new Notification("Duct — Your input is needed", {
            body: "The agent has a question before continuing the audit.",
            icon: "/favicon.ico",
          });
        }
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
        // Close the last streaming bubble (if still open) + celebrate on initial report
        setMessages((prev) => {
          const withStreaming = prev[prev.length - 1]?.streaming
            ? [...prev.slice(0, -1), { ...prev[prev.length - 1], streaming: false }]
            : prev;
          if (event.version_id === 1) {
            return [...withStreaming, {
              role: "assistant",
              text: "✓ Your SEO report is ready! Review the score and findings in the panel on the right. Ask me anything about the results — I can explain findings, suggest fixes, or update the report.",
            }];
          }
          return withStreaming;
        });
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
        if (reportReceivedRef.current) {
          // Partial report exists — surface error inline, keep report panel intact
          setMessages((prev) => [
            ...prev,
            {
              role: "send_error",
              text: event.error
                ? `Pipeline stopped early: ${event.error} — your partial report is still available above.`
                : "The pipeline ended unexpectedly. Your partial report is still available.",
              content: null,
            },
          ]);
          setPhase(Phase.READY);
        } else {
          setPhase(Phase.FAILED);
        }
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
      // Restore questions so the user can retry — don't kill the session
      setMessages((prev) => [
        ...prev,
        { role: "send_error", text: `Failed to submit answers: ${err.message || "network error"}. Please try again.`, content: null },
      ]);
      setPendingQuestions(answers); // restore so the form reappears
      setPhase(Phase.QUESTIONS);
    }
  }

  async function handleSendMessage(content) {
    const text = typeof content === "string" ? content : "[image attached]";
    // Remove any previous inline send error before adding the new user message
    setMessages((prev) => {
      const cleaned = prev[prev.length - 1]?.role === "send_error" ? prev.slice(0, -1) : prev;
      return [...cleaned, { role: "user", text }];
    });
    setPhase(Phase.CHATTING);
    try {
      await sendAgentMessage(agentTypeRef.current, backendSessionIdRef.current, {
        type: "chat",
        content,
        context_version_id: selectedVersionId,
      });
    } catch (err) {
      // Inline error — keep the report and chat intact, just flag the failed send
      setMessages((prev) => [
        ...prev,
        { role: "send_error", text: err.message || "Failed to send message.", content },
      ]);
      setPhase(Phase.READY);
    }
  }

  function handleRetrySend(content) {
    handleSendMessage(content);
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
          onRetrySend={handleRetrySend}
          onRetry={handleRetry}
        />
      </div>

      <div
        onMouseDown={onMouseDownDivider}
        title="Drag to resize"
        className="w-3 shrink-0 cursor-col-resize select-none flex items-center justify-center group"
      >
        <div className="w-px h-full bg-border/60 group-hover:bg-primary/30 transition-colors" />
        <div className="absolute flex flex-col gap-[3px] opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          {[0,1,2,3,4].map((i) => (
            <span key={i} className="block w-[3px] h-[3px] rounded-full bg-muted-foreground/50" />
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden min-w-[280px]">
        <AuditReport
          phase={phase}
          steps={steps}
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
