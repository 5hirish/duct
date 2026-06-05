"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronUp, FileText, X } from "lucide-react";
import ContentChat from "./ContentChat";
import { Phase } from "./contentPhase";
import {
  answerContentQuestions,
  closeContentSession,
  consumeSseStream,
  openPlanStream,
  openPostStream,
  sendContentChat,
} from "../../lib/contentApi";
import { ContentEvent } from "../../lib/contentEvents";

const INITIAL_SPLIT = 50;

/**
 * Universal split-pane workspace for the content agent.
 *
 * Props:
 *   - mode: 'plan_month' | 'draft_post'
 *   - context: { projectId } | { projectId, planId, dayIndex, topic, pillar, postId }
 *   - renderViewport: ({ payload, mode, sessionId }) => ReactNode
 *     Called every render with the latest plan/post payload from the agent.
 */
export default function ContentWorkspace({ mode, context, renderViewport }) {
  const [leftWidth, setLeftWidth] = useState(() => {
    if (typeof window !== "undefined") {
      return Number(localStorage.getItem("content_split_w") || INITIAL_SPLIT);
    }
    return INITIAL_SPLIT;
  });

  const [phase,    setPhase]    = useState(Phase.STARTING);
  const [steps,    setSteps]    = useState([]);
  const [todos,    setTodos]    = useState([]);
  const [messages, setMessages] = useState([]);
  const [pendingQuestions, setPendingQuestions] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [payload, setPayload]   = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [channelNote, setChannelNote] = useState(null);
  const [isAgentTyping, setIsAgentTyping] = useState(false);
  const [mobilePaneOpen, setMobilePaneOpen] = useState(false);

  const abortRef = useRef(null);
  const pipelineEndedRef = useRef(false);
  const sessionIdRef     = useRef(null);
  const dragging         = useRef(false);
  const containerRef     = useRef(null);

  // ---------------------------------------------------------------------------
  // Retry
  // ---------------------------------------------------------------------------

  function handleRetry() {
    setPhase(Phase.STARTING);
    setSteps([]);
    setTodos([]);
    setMessages([]);
    setPendingQuestions(null);
    setErrorMsg("");
    setPayload(null);
    setSessionId(null);
    setIsAgentTyping(false);
    pipelineEndedRef.current = false;
    setRetryCount((c) => c + 1);
  }

  // ---------------------------------------------------------------------------
  // SSE lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    pipelineEndedRef.current = false;

    async function start() {
      try {
        const opener = mode === "plan_month" ? openPlanStream : openPostStream;
        const { body, sessionId: sid } = await opener(context, { signal: ctrl.signal });
        sessionIdRef.current = sid;
        setSessionId(sid);

        await consumeSseStream(body, handleEvent, ctrl.signal);

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
      if (sessionIdRef.current) {
        closeContentSession(sessionIdRef.current).catch(() => {});
        sessionIdRef.current = null;
      }
    };
  }, [retryCount, mode, JSON.stringify(context)]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // SSE event handler
  // ---------------------------------------------------------------------------

  function handleEvent(event) {
    // PIPELINE_STARTED carries the resolved channel; note when we fell back.
    if (event.channel) {
      setChannelNote(
        event.channel_supported === false
          ? `Using the TikTok playbook — no dedicated ${event.channel_label || event.channel} agent yet.`
          : null,
      );
    }
    switch (event.event) {

      case ContentEvent.STEP_STARTED:
        setPhase(Phase.PIPELINE);
        setSteps((prev) => {
          const existing = prev.find((s) => s.step_id === event.step_id);
          if (existing) {
            return prev.map((s) =>
              s.step_id === event.step_id
                ? { ...s, status: "running", label: event.label || s.label, summary: event.summary }
                : s,
            );
          }
          return [
            ...prev,
            {
              step_id: event.step_id,
              label: event.label || event.step_id,
              status: "running",
              summary: event.summary || "",
            },
          ];
        });
        break;

      case ContentEvent.STEP_FINISHED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: event.status || "success", summary: event.summary || s.summary }
              : s,
          ),
        );
        break;

      case ContentEvent.STEP_FAILED:
        setSteps((prev) =>
          prev.map((s) =>
            s.step_id === event.step_id
              ? { ...s, status: "failed", summary: event.error || s.summary }
              : s,
          ),
        );
        break;

      case ContentEvent.THINKING_CHUNK:
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, thinking: (last.thinking || "") + event.text }];
          return [...prev, { role: "assistant", text: "", thinking: event.text, streaming: true }];
        });
        break;

      case ContentEvent.QUESTIONS_REQUIRED:
        setPendingQuestions(event.questions);
        setPhase(Phase.QUESTIONS);
        if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
          new Notification("Duct — Your input is needed", {
            body: "The content agent has a question before continuing.",
            icon: "/favicon.ico",
          });
        }
        break;

      case ContentEvent.REPORT_CHUNK:
        // Stream tokens are accumulated inside <duct_report>; we don't render
        // them live in MVP (the close-tag PLAN_GENERATED / POST_DRAFT_UPDATED
        // gives us the structured payload). Future: render to a "streaming
        // preview" indicator.
        break;

      case ContentEvent.PLAN_GENERATED:
        setPayload({ type: "plan", ...event.payload });
        break;

      case ContentEvent.POST_DRAFT_UPDATED:
        setPayload({ type: "post", ...event.payload });
        break;

      case ContentEvent.PIPELINE_FINISHED:
        pipelineEndedRef.current = true;
        setPhase(Phase.READY);
        break;

      case ContentEvent.PIPELINE_FAILED:
        pipelineEndedRef.current = true;
        setErrorMsg(friendlyErrorMessage(event.error));
        setPhase(Phase.FAILED);
        break;

      case ContentEvent.TODO_UPDATE:
        setTodos(event.todos || []);
        break;

      case ContentEvent.AGENT_MESSAGE_CHUNK:
        setIsAgentTyping(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming)
            return [...prev.slice(0, -1), { ...last, text: last.text + event.text }];
          return [...prev, { role: "assistant", text: event.text, streaming: true }];
        });
        break;

      case ContentEvent.MESSAGE_STOP:
        setIsAgentTyping(false);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
          return prev;
        });
        setPhase((prev) => (prev === Phase.CHATTING ? Phase.READY : prev));
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
      await answerContentQuestions(sessionIdRef.current, answers);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "send_error",
          text: `Failed to submit answers: ${err.message || "network error"}.`,
          content: null,
        },
      ]);
      setPendingQuestions(answers);
      setPhase(Phase.QUESTIONS);
    }
  }

  async function handleSendMessage(content) {
    const text = typeof content === "string" ? content : "[image attached]";
    setMessages((prev) => {
      const cleaned = prev[prev.length - 1]?.role === "send_error" ? prev.slice(0, -1) : prev;
      return [...cleaned, { role: "user", text }];
    });
    setPhase(Phase.CHATTING);
    setIsAgentTyping(true);
    try {
      await sendContentChat(sessionIdRef.current, content);
    } catch (err) {
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
    if (sessionIdRef.current) {
      closeContentSession(sessionIdRef.current).catch(() => {});
    }
    setIsAgentTyping(false);
    setPhase((prev) =>
      prev === Phase.CHATTING && payload ? Phase.READY : Phase.FAILED,
    );
  }

  // ---------------------------------------------------------------------------
  // Friendly error mapping — hide stack traces / status codes from users.
  // ---------------------------------------------------------------------------

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
      localStorage.setItem("content_split_w", String(pct));
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

  const hasPayload = Boolean(payload);
  const isRunning  = phase === Phase.STARTING || phase === Phase.PIPELINE;
  // True whenever the agent is actively producing tokens — drives ContentInput
  // Stop button + textarea disabling. Distinct from inputDisabled (which is
  // phase-based) so the user can stop in-flight chat without falling into a
  // FAILED state.
  const isStreaming = isRunning || (phase === Phase.CHATTING && isAgentTyping);

  // Always-visible mobile bar above the input — opens the right pane as a
  // bottom sheet. Shows "Generating…" while running, "Ready" once a payload
  // arrives.
  const paneLabel = mode === "plan_month" ? "30-day plan" : "Post draft";
  const mobilePostBar = (
    <button
      onClick={() => setMobilePaneOpen(true)}
      className="md:hidden w-full flex items-center gap-3 px-4 py-3 bg-card border-t border-border/60 hover:bg-muted/50 active:bg-muted transition-colors text-left"
    >
      {hasPayload ? (
        <>
          <div className="size-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <FileText size={16} className="text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold truncate">{paneLabel} ready</p>
            <p className="text-xs text-muted-foreground">Tap to view + edit</p>
          </div>
          <ChevronUp size={16} className="text-muted-foreground shrink-0" />
        </>
      ) : (
        <>
          <div className="size-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
            {isRunning ? (
              <span className="size-4 rounded-full border-2 border-border border-t-primary animate-spin" aria-hidden="true" />
            ) : (
              <FileText size={16} className="text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-muted-foreground truncate">
              {isRunning ? `Generating ${paneLabel.toLowerCase()}…` : paneLabel}
            </p>
            <p className="text-xs text-muted-foreground">
              {isRunning ? "Agent is working" : "Tap to view"}
            </p>
          </div>
          <ChevronUp size={16} className="text-muted-foreground/40 shrink-0" />
        </>
      )}
    </button>
  );

  const viewportEl = (
    <div className="flex h-full flex-col overflow-hidden">
      {channelNote && (
        <div className="shrink-0 border-b border-amber-400/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-600 dark:text-amber-400">
          {channelNote}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-hidden">
        {renderViewport
          ? renderViewport({ payload, mode, sessionId, phase })
          : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No viewport configured.
              </div>
            )}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <div
        ref={containerRef}
        className="flex flex-1 min-h-0 w-full overflow-hidden"
        style={{ "--split": `${leftWidth}%` }}
      >
        {/* Chat panel — full-width on mobile, split on md+ */}
        <div className="flex flex-col overflow-hidden border-r border-border/60 w-full md:w-[var(--split)] md:min-w-[280px]">
          <ContentChat
            mode={mode}
            phase={phase}
            steps={steps}
            todos={todos}
            messages={messages}
            pendingQuestions={pendingQuestions}
            errorMsg={errorMsg}
            isAgentTyping={isAgentTyping}
            isStreaming={isStreaming}
            onAnswerQuestions={handleAnswerQuestions}
            onSendMessage={handleSendMessage}
            onRetrySend={handleRetrySend}
            onRetry={handleRetry}
            onStop={handleStop}
            mobilePostBar={mobilePostBar}
          />
        </div>

        {/* Divider — desktop only */}
        <div
          onMouseDown={onMouseDownDivider}
          title="Drag to resize"
          className="hidden md:flex w-3 shrink-0 cursor-col-resize select-none items-center justify-center group"
        >
          <div className="w-px h-full bg-border/60 group-hover:bg-primary/30 transition-colors" />
        </div>

        {/* Viewport panel — desktop only */}
        <div className="hidden md:flex flex-1 flex-col overflow-hidden min-w-[280px]">
          {viewportEl}
        </div>
      </div>

      {/* Mobile bottom sheet — full-screen viewport */}
      {mobilePaneOpen && (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-background md:hidden"
          style={{ animation: "slideUp 0.25s ease-out", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
        >
          <div
            className="shrink-0 flex items-center justify-between px-4 border-b border-border/60"
            style={{ paddingTop: "max(12px, env(safe-area-inset-top, 12px))", paddingBottom: "12px" }}
          >
            <span className="font-semibold text-sm">{paneLabel}</span>
            <button
              onClick={() => setMobilePaneOpen(false)}
              className="flex items-center justify-center size-11 rounded-md hover:bg-muted transition-colors"
              aria-label={`Close ${paneLabel.toLowerCase()}`}
            >
              <X size={18} />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {viewportEl}
          </div>
        </div>
      )}
    </div>
  );
}


/**
 * Translate raw backend errors into actionable user-facing messages.
 * Hides stack traces, status codes, and internal terminology. Falls back
 * to a generic message when the input doesn't pattern-match.
 */
function friendlyErrorMessage(raw) {
  const msg = String(raw || "").trim();
  if (!msg) return "Something went wrong. Please try again.";

  // Configuration gaps
  if (/ANTHROPIC_API_KEY/i.test(msg)) {
    return "The assistant isn't connected. Ask your admin to finish setup.";
  }
  if (/GEMINI_API_KEY/i.test(msg)) {
    return "Image generation isn't connected yet. Ask your admin to finish setup.";
  }
  if (/uploads.*disabled/i.test(msg)) {
    return "Image uploads aren't enabled in this environment.";
  }
  if (/POSTBRIDGE|post.?bridge.*connect/i.test(msg)) {
    return "Publishing isn't connected. Ask your admin to set it up.";
  }

  // Common transient classes
  if (/rate limit|429/i.test(msg)) {
    return "We're hitting a rate limit — wait a minute and try again.";
  }
  if (/timeout|timed.?out/i.test(msg)) {
    return "That took longer than expected. Try again.";
  }
  if (/network|connection|fetch failed|ECONNREFUSED/i.test(msg)) {
    return "Couldn't reach the server. Check your internet and try again.";
  }

  // Validation
  if (/validation|invalid|missing/i.test(msg) && msg.length < 200) {
    return "Some input wasn't valid — please review and try again.";
  }

  // Don't leak status codes / file paths / stack traces.
  if (/^\d{3}\b/.test(msg) || /Traceback|line \d+/i.test(msg)) {
    return "Something went wrong on our end. Please try again in a moment.";
  }

  // Reasonably short, doesn't look technical → pass through.
  if (msg.length < 200 && !/^\w+Error:/.test(msg)) return msg;

  return "Something went wrong. Please try again.";
}
