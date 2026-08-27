"use client";

import { useEffect, useRef, useState } from "react";
import AuditChat from "./AuditChat";
import AuditReport from "./AuditReport";
import SplitWorkspace from "../workspace/SplitWorkspace";
import {
  closeAgentSession,
  createAgentSession,
  getAgentConversation,
  openAgentStream,
  sendAgentMessage,
} from "../../lib/api";
import { mapEventsToMessages } from "../../lib/agentHistory";
import { AuditEvent, AuditStep } from "../../lib/auditEvents";
import { StepStatus } from "../../lib/agentSteps";
import { Phase } from "./auditPhase";
import { useAuditNav } from "../../lib/auditNavContext";
import { consumeSseStream } from "@/lib/sse";

// Re-export so consumers can import Phase from AuditWorkspace if they prefer
export { Phase } from "./auditPhase";

// ---------------------------------------------------------------------------
// AuditWorkspace
// ---------------------------------------------------------------------------

export default function AuditWorkspace({ sessionId, auditParams, publicMode = false, onReportReady, leadToken = null, leadEmail = null }) {
  const { setIsAuditRunning } = useAuditNav();

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
  const [streamingHtml, setStreamingHtml]     = useState("");
  const [isAgentTyping, setIsAgentTyping]     = useState(false);

  // Refs that need to be readable inside async closures without stale values
  const abortRef            = useRef(null);
  const pipelineEndedRef    = useRef(false); // set by PIPELINE_FINISHED or PIPELINE_FAILED
  const reportReceivedRef   = useRef(false); // set when any report data arrives
  const backendSessionIdRef = useRef(null);
  const agentTypeRef        = useRef("audit_seo");
  const htmlBatchRef        = useRef("");
  const htmlBatchTimer      = useRef(null);
  const reportFiredRef      = useRef(false); // prevents onReportReady firing more than once

  // Tell the nav bar whether to lock the back button
  useEffect(() => {
    const running = phase === Phase.STARTING || phase === Phase.PIPELINE;
    setIsAuditRunning(running);
  }, [phase, setIsAuditRunning]);

  // Fire onReportReady once when the first complete report is available
  useEffect(() => {
    if (!onReportReady || reportFiredRef.current) return;
    if (phase !== Phase.READY || reportVersions.length === 0) return;
    const latest = reportVersions[reportVersions.length - 1];
    if (!latest?.report) return;
    reportFiredRef.current = true;
    onReportReady(latest.report);
  }, [onReportReady, phase, reportVersions]);

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
    setStreamingHtml("");
    htmlBatchRef.current = "";
    clearTimeout(htmlBatchTimer.current);
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
    // Per-effect-instance state (closures) so a StrictMode double-mount can't
    // leak an orphaned audit session that races the survivor on the CLI dir.
    let cancelled = false;
    let localSid  = null;

    async function start() {
      try {
        // Resume: seed the chat with persisted history before the live stream
        // attaches, so the user sees their prior conversation instantly.
        if (auditParams.resume && auditParams.conversation_id) {
          try {
            const conv = await getAgentConversation("audit_seo", auditParams.conversation_id);
            if (!cancelled) setMessages(mapEventsToMessages(conv.events));
          } catch {
            /* history unavailable — the session still resumes server-side */
          }
        }
        const { session_id, agent_type } = await createAgentSession("audit_seo", auditParams);
        localSid = session_id;
        // Torn down before the stream opened (StrictMode remount / fast nav):
        // close the orphan so its worker is cancelled instead of running a full
        // duplicate audit that contends with the survivor on ~/.claude.
        if (cancelled) {
          closeAgentSession(agent_type, session_id).catch(() => {});
          return;
        }
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
      cancelled = true;
      ctrl.abort();
      const sid = backendSessionIdRef.current || localSid;
      if (sid) {
        closeAgentSession(agentTypeRef.current, sid).catch(() => {});
        if (backendSessionIdRef.current === sid) backendSessionIdRef.current = null;
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
              // merge payload when present (e.g. live "N/9 categories" progress);
              // a payload-less STEP_STARTED keeps the existing payload.
              s.step_id === event.step_id ? { ...s, status: StepStatus.RUNNING, payload: event.payload ?? s.payload } : s
            );
          return [...prev, { step_id: event.step_id, label: event.label, status: StepStatus.RUNNING, payload: event.payload ?? null }];
        });
        break;

      case AuditEvent.STEP_FINISHED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: event.status || StepStatus.SUCCESS, payload: event.payload || null }
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

      case AuditEvent.REPORT_CHUNK:
        htmlBatchRef.current += event.text;
        clearTimeout(htmlBatchTimer.current);
        htmlBatchTimer.current = setTimeout(() => {
          setStreamingHtml(htmlBatchRef.current);
        }, 80);
        break;

      case AuditEvent.REPORT_UPDATED:
        // replay=True: a stored version re-emitted on resume — render it, but
        // skip the celebration bubble and step-clearing meant for fresh runs.
        if (event.replay) {
          reportReceivedRef.current = true;
          setReportVersions((prev) => [
            ...prev.filter((v) => v.version_id !== event.version_id),
            { version_id: event.version_id, label: event.label, report: event.payload },
          ].sort((a, b) => a.version_id - b.version_id));
          setSelectedVersionId(event.version_id);
          break;
        }
        setStreamingHtml("");
        htmlBatchRef.current = "";
        clearTimeout(htmlBatchTimer.current);
        reportReceivedRef.current = true;
        // The report is ready → synthesis (and any earlier still-"running" step)
        // is done. run_synthesis stays open for follow-up chat, so its backend
        // STEP_FINISHED won't arrive until the session closes — clear the loaders
        // now instead of leaving them spinning behind a finished report.
        setSteps((prev) => prev.map((s) => (s.status === StepStatus.RUNNING ? { ...s, status: StepStatus.SUCCESS } : s)));
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
        setSteps((prev) => prev.map((s) => (s.status === StepStatus.RUNNING ? { ...s, status: StepStatus.SUCCESS } : s)));
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

      // A durable artifact was created/revised by a tool — render a compact
      // card in the chat that opens the artifact viewer.
      case AuditEvent.ARTIFACT_UPDATED:
        setMessages((prev) => [...prev, { role: "artifact_card", artifact: event.artifact }]);
        break;

      // The agent proposed (or updated) a staged change set — inline review
      // card. Emitted again on state changes (auto-applied, rolled back), so
      // upsert by change_set_id instead of appending duplicates.
      case AuditEvent.EXECUTION_PROPOSED: {
        const incoming = event.change_set;
        if (!incoming?.change_set_id) break;
        setMessages((prev) => {
          const idx = prev.findIndex(
            (m) => m.role === "change_set_card" && m.changeSet?.change_set_id === incoming.change_set_id
          );
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = { ...next[idx], changeSet: incoming };
            return next;
          }
          return [...prev, { role: "change_set_card", changeSet: incoming }];
        });
        break;
      }

      case AuditEvent.AGENT_MESSAGE_CHUNK:
        setIsAgentTyping(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, text: last.text + event.text }];
          return [...prev, { role: "assistant", text: event.text, streaming: true }];
        });
        break;

      case AuditEvent.MESSAGE_STOP:
        setIsAgentTyping(false);
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
    setIsAgentTyping(true);
    try {
      await sendAgentMessage(agentTypeRef.current, backendSessionIdRef.current, {
        type: "chat",
        content,
        context_version_id: selectedVersionId,
      });
    } catch (err) {
      // Inline error — keep the report and chat intact, just flag the failed send
      setIsAgentTyping(false);
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

  function handleStop() {
    abortRef.current?.abort();
    if (backendSessionIdRef.current) {
      closeAgentSession(agentTypeRef.current, backendSessionIdRef.current).catch(() => {});
    }
    setIsAgentTyping(false);
    // During pipeline: go to FAILED (no report yet); during chatting: stay READY if we have a report
    setPhase((prev) =>
      prev === Phase.CHATTING && reportVersions.length > 0 ? Phase.READY : Phase.FAILED
    );
  }

  // ---------------------------------------------------------------------------
  // Render — split shell is shared (../workspace/SplitWorkspace).
  // ---------------------------------------------------------------------------

  const showPublicCta = publicMode && phase === Phase.READY && reportVersions.length > 0;
  const rightStatus = reportVersions.length > 0 ? "ready" : phase === Phase.PIPELINE ? "busy" : "idle";

  const banner = showPublicCta ? (
    <div className="shrink-0 flex items-center justify-between gap-3 px-4 py-2.5 bg-orange-50 border-b border-orange-200 text-sm">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="font-semibold text-orange-900 leading-tight">Want the full picture?</span>
        <span className="text-orange-700 text-xs leading-tight">This is a quick scan. Sign up for a deeper audit with competitor analysis, keyword gaps, and a prioritized action plan.</span>
      </div>
      <a
        href="/"
        className="shrink-0 inline-flex items-center gap-1 rounded-md bg-orange-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-orange-700 transition-colors"
      >
        Get the full audit →
      </a>
    </div>
  ) : null;

  return (
    <SplitWorkspace
      storageKey="audit_split_w"
      rightLabel="Report"
      rightStatus={rightStatus}
      banner={banner}
      left={
        <AuditChat
          phase={phase}
          steps={steps}
          todos={todos}
          messages={messages}
          pendingQuestions={pendingQuestions}
          hasReport={reportVersions.length > 0}
          errorMsg={errorMsg}
          isAgentTyping={isAgentTyping}
          isStreaming={phase === Phase.PIPELINE || (phase === Phase.CHATTING && isAgentTyping)}
          onAnswerQuestions={handleAnswerQuestions}
          onSendMessage={handleSendMessage}
          onRetrySend={handleRetrySend}
          onRetry={handleRetry}
          onStop={handleStop}
        />
      }
      right={
        <AuditReport
          phase={phase}
          steps={steps}
          versions={reportVersions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={setSelectedVersionId}
          streamingHtml={streamingHtml}
          errorMsg={errorMsg}
          onRetry={handleRetry}
          leadToken={leadToken}
          leadEmail={leadEmail}
        />
      }
    />
  );
}
