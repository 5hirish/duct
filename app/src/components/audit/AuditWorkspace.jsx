"use client";

import { useEffect, useRef, useState } from "react";
import AgentChat from "../workspace/AgentChat";
import AuditReport from "./AuditReport";
import AuditStepProgress from "./AuditStepProgress";
import SplitWorkspace from "../workspace/SplitWorkspace";
import { useAgentSession } from "../../hooks/useAgentSession";
import { Action, Row } from "../../lib/agentSession";
import { AuditEvent, STEP_LABELS } from "../../lib/auditEvents";
import { Phase } from "../../lib/agentPhase";
import { useAuditNav } from "../../lib/auditNavContext";

// Re-export so consumers can import Phase from AuditWorkspace if they prefer
export { Phase } from "../../lib/agentPhase";

const AGENT_TYPE = "audit_seo";

/**
 * The SEO audit workspace. The session lifecycle is `useAgentSession`; what is
 * audit's own is the report — its versions, the HTML streaming in before a
 * version lands, and the public lead-magnet banner.
 */
export default function AuditWorkspace({
  sessionId,
  auditParams,
  publicMode = false,
  onReportReady,
  leadToken = null,
  leadEmail = null,
}) {
  const { setIsAuditRunning } = useAuditNav();

  const [reportVersions, setReportVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [streamingHtml, setStreamingHtml] = useState("");

  const htmlBatchRef = useRef("");
  const htmlBatchTimer = useRef(null);
  const reportReceivedRef = useRef(false);
  const reportFiredRef = useRef(false); // onReportReady fires once

  const agent = useAgentSession({
    agentType: AGENT_TYPE,
    body: auditParams,
    // The page's own session key is unique per audit, so a reload of this
    // page reattaches to this audit's run.
    handleKey: `${AGENT_TYPE}:${sessionId}`,
    onEvent: handleEvent,
  });
  const { phase, dispatch } = agent;

  // Tell the nav bar whether to lock the back button
  useEffect(() => {
    setIsAuditRunning(phase === Phase.STARTING || phase === Phase.PIPELINE);
  }, [phase, setIsAuditRunning]);

  // Clear on unmount so the back button re-enables if the user navigates away
  useEffect(() => () => setIsAuditRunning(false), [setIsAuditRunning]);

  // Fire onReportReady once when the first complete report is available
  useEffect(() => {
    if (!onReportReady || reportFiredRef.current) return;
    if (phase !== Phase.READY || reportVersions.length === 0) return;
    const latest = reportVersions[reportVersions.length - 1];
    if (!latest?.report) return;
    reportFiredRef.current = true;
    onReportReady(latest.report);
  }, [onReportReady, phase, reportVersions]);

  // Browser notification permission — request once on mount
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  function upsertVersion(event) {
    setReportVersions((prev) =>
      [
        ...prev.filter((v) => v.version_id !== event.version_id),
        { version_id: event.version_id, label: event.label, report: event.payload },
      ].sort((a, b) => a.version_id - b.version_id),
    );
    setSelectedVersionId(event.version_id);
  }

  function handleEvent(event, { appendMessage }) {
    switch (event.event) {
      case AuditEvent.QUESTIONS_REQUIRED:
        if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
          new Notification("Duct — Your input is needed", {
            body: "The agent has a question before continuing the audit.",
            icon: "/favicon.ico",
          });
        }
        break;

      case AuditEvent.ARTIFACT_CHUNK:
      case AuditEvent.LEGACY_REPORT_CHUNK:
        htmlBatchRef.current += event.text;
        clearTimeout(htmlBatchTimer.current);
        htmlBatchTimer.current = setTimeout(() => setStreamingHtml(htmlBatchRef.current), 80);
        break;

      case AuditEvent.ARTIFACT_VERSION:
      case AuditEvent.LEGACY_REPORT_UPDATED:
        reportReceivedRef.current = true;
        // replay=True: a stored version re-emitted on resume — render it, but
        // skip the celebration meant for a fresh run.
        if (event.replay) {
          upsertVersion(event);
          break;
        }
        setStreamingHtml("");
        htmlBatchRef.current = "";
        clearTimeout(htmlBatchTimer.current);
        upsertVersion(event);
        if (event.version_id === 1) {
          appendMessage({
            role: Row.ASSISTANT,
            text: "✓ Your SEO report is ready! Review the score and findings in the panel on the right. Ask me anything about the results — I can explain findings, suggest fixes, or update the report.",
          });
        }
        break;

      case AuditEvent.PIPELINE_FINISHED:
        if (event.payload) {
          reportReceivedRef.current = true;
          setReportVersions((prev) =>
            prev.some((v) => v.version_id === 1)
              ? prev
              : [{ version_id: 1, label: "Initial audit", report: event.payload }, ...prev],
          );
          setSelectedVersionId(1);
        } else if (!reportReceivedRef.current) {
          // Pipeline completed but no report was ever produced.
          dispatch({ type: Action.FAILED, error: "AI synthesis finished but no report was generated." });
        }
        break;

      case AuditEvent.PIPELINE_FAILED:
        // A partial report exists: keep the panel, surface the error inline
        // rather than replacing everything with the failure state.
        if (reportReceivedRef.current) {
          dispatch({ type: Action.STOPPED, keepReady: true });
          appendMessage({
            role: Row.SEND_ERROR,
            text: event.error
              ? `Pipeline stopped early: ${event.error} — your partial report is still available above.`
              : "The pipeline ended unexpectedly. Your partial report is still available.",
            content: null,
          });
        }
        break;

      default:
        break;
    }
  }

  function handleRetry() {
    setReportVersions([]);
    setSelectedVersionId(null);
    setStreamingHtml("");
    htmlBatchRef.current = "";
    clearTimeout(htmlBatchTimer.current);
    reportReceivedRef.current = false;
    agent.retry();
  }

  function handleStop() {
    // During the pipeline: FAILED (no report yet); mid-chat with a report: READY.
    agent.stop({ keepReady: phase === Phase.CHATTING && reportVersions.length > 0 });
  }

  function handleSend(content) {
    agent.send(content, { context_version_id: selectedVersionId });
  }

  const showPublicCta = publicMode && phase === Phase.READY && reportVersions.length > 0;
  const rightStatus = reportVersions.length > 0 ? "ready" : phase === Phase.PIPELINE ? "busy" : "idle";

  const banner = showPublicCta ? (
    <div className="shrink-0 flex items-center justify-between gap-3 px-4 py-2.5 bg-orange-50 border-b border-orange-200 text-sm">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="font-semibold text-orange-900 leading-tight">Want the full picture?</span>
        <span className="text-orange-700 text-xs leading-tight">
          This is a quick scan. Sign up for a deeper audit with competitor analysis, keyword gaps, and a prioritized action plan.
        </span>
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
        <AgentChat
          title="Agent Chat"
          phase={phase}
          steps={agent.steps}
          todos={agent.todos}
          messages={agent.messages}
          pending={agent.pending}
          errorMsg={agent.error}
          errorCode={agent.errorCode}
          errorRetryable={agent.errorRetryable}
          retrying={agent.retrying}
          usage={agent.usage}
          compacting={agent.compacting}
          isAgentTyping={agent.isAgentTyping}
          isStreaming={phase === Phase.PIPELINE || (phase === Phase.CHATTING && agent.isAgentTyping)}
          reconnecting={agent.reconnecting}
          // Audit accepts a follow-up while the crawl runs (it is queued
          // server-side); only a pending card, a dropped link or a failure
          // closes the composer.
          inputDisabled={agent.inputDisabled}
          answerDisabled={!agent.attached}
          // Ambient state, per the memory UX rules: a session that is not being
          // remembered should say so while it runs, not only at the point the
          // switch was flipped.
          remembering={auditParams?.remember !== false}
          onAnswer={agent.answer}
          onSendMessage={handleSend}
          onRetrySend={handleSend}
          onRetry={handleRetry}
          onStop={handleStop}
          renderSteps={(steps) => <AuditStepProgress steps={steps} />}
          stepLabels={STEP_LABELS}
          questionsCopy={QUESTIONS_COPY}
          inputPlaceholder="Ask a follow-up question…"
          inputAriaLabel="Message the audit agent"
          inputAccept="image/*,.pdf"
          startingLabel="Starting audit…"
          failedTitle="Audit failed"
          retryLabel="↺ Retry audit"
          readyHint={
            reportVersions.length > 0 ? (
              <p className="text-sm text-center mt-6 px-2 py-3 rounded-lg bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
                ✓ Report ready — ask me anything about the findings.
              </p>
            ) : null
          }
        />
      }
      right={
        <AuditReport
          phase={phase}
          steps={agent.steps}
          versions={reportVersions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={setSelectedVersionId}
          streamingHtml={streamingHtml}
          errorMsg={agent.error}
          errorCode={agent.errorCode}
          errorRetryable={agent.errorRetryable}
          retrying={agent.retrying}
          usage={agent.usage}
          compacting={agent.compacting}
          onRetry={handleRetry}
          leadToken={leadToken}
          leadEmail={leadEmail}
        />
      }
    />
  );
}

const QUESTIONS_COPY = {
  title: "One moment — Duct has a quick question",
  hint: "Your answers sharpen the findings. Skip if you'd rather Duct decide.",
  submitLabel: "Continue audit →",
};
