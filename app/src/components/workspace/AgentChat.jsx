"use client";

/**
 * AgentChat — the left pane of every agent workspace.
 *
 * One transcript for three agents. It used to be two forks (AuditChat and
 * ContentChat) that had drifted a few hundred lines apart while rendering the
 * same thing, and a third, thinner one inside the insights workspace that had
 * none of the fixes the first two had accumulated. What differs per agent is
 * copy and a few slots; what is the same — phase header, todo strip, step
 * ladder, bubbles, thinking, the pause card, send errors, reconnecting,
 * failure, scroll behaviour, the composer — is here once.
 *
 * Feed it the state from `useAgentSession` and the actions it returns. The
 * message rows are the shapes lib/agentSession.js produces (see `Row`).
 *
 * Slots:
 *   renderSteps(steps)  — a richer step ladder (audit has per-step detail
 *                         panels); default is the plain StepProgress.
 *   headerExtra         — right-aligned header content.
 *   footer              — rendered between the transcript and the composer.
 *   readyHint           — shown once READY with an empty transcript.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Brain } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { Lightbox } from "@/components/ui/lightbox";
import ChangeSetCard from "@/components/execution/ChangeSetCard";
import { Phase } from "../../lib/agentPhase";
import { StepStatus } from "../../lib/agentSteps";
import { ErrorAction, Row, errorAction } from "../../lib/agentSession";
import { AssistantMarkdown, ThinkingMarkdown } from "./ChatMarkdown";
import ChatInput from "./ChatInput";
import ContextRing from "./ContextRing";
import { MemoryNote, MemoryRecall, RememberThis } from "./MemoryRows";
import PauseCard from "./PauseCard";
import StepProgress from "./StepProgress";
import Todos from "./Todos";

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/** A turn that failed, or a message that never got out. `content` is set only
 *  for the latter — it is what a retry resends. A failure whose code says a
 *  retry cannot help (a rejected key, a full context) gets no retry button;
 *  one whose code names where the fix lives gets the link there instead —
 *  the same action the terminal failure card offers, so a failure reads the
 *  same live and after a reload. */
function SendErrorBubble({ text, content, code = "", onRetry, retryable = true }) {
  const action = code ? errorAction(code) : ErrorAction.RETRY;
  const link = "block w-full text-xs text-right text-muted-foreground hover:text-foreground transition-colors pr-1";
  return (
    <div className="flex justify-end mb-2">
      <div className="max-w-[85%] space-y-1">
        <div className="rounded-2xl rounded-br-sm px-3 py-2 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
          <p className="text-xs font-medium mb-0.5">{content ? "Failed to send" : "That turn failed"}</p>
          <p className="text-xs text-destructive/80">{text}</p>
        </div>
        {action === ErrorAction.SETTINGS && <Link href="/settings/models" className={link}>Open model settings →</Link>}
        {action === ErrorAction.CONNECTIONS && <Link href="/connections" className={link}>Open connections →</Link>}
        {action === ErrorAction.RETRY && content && onRetry && retryable && (
          <button type="button" onClick={() => onRetry(content)} className={link}>
            ↺ Retry
          </button>
        )}
      </div>
    </div>
  );
}

function ThinkingBlock({ thinking, streaming }) {
  const [expanded, setExpanded] = useState(false);
  if (!thinking) return null;
  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        aria-expanded={expanded}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="font-mono" aria-hidden="true">{expanded ? "▾" : "▸"}</span>
        <span>{expanded ? "Hide" : "Show"} reasoning{streaming ? "…" : ""}</span>
      </button>
      {expanded && (
        <div className="mt-1.5 rounded-lg px-3.5 py-3 bg-muted/40 border border-border/40">
          <ThinkingMarkdown source={thinking} />
          {streaming && <span className="inline-block w-0.5 h-3 bg-muted-foreground/60 ml-0.5 animate-pulse align-middle" />}
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-2">
      <div className="rounded-2xl rounded-bl-sm px-4 py-3 bg-muted text-foreground">
        <span className="flex gap-1 items-center">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="inline-block w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

function ChatBubble({ role, text, thinking, streaming, remember, queued = false }) {
  if (role === Row.USER) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[82%]">
          <div
            className={`rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed bg-primary text-primary-foreground ${
              queued ? "opacity-70" : ""
            }`}
          >
            <p className="whitespace-pre-wrap break-words">{text}</p>
          </div>
          {queued && (
            <p className="mt-1 pr-1 text-right text-[11px] text-muted-foreground" title="Sent while the agent was busy; it reads this at its next step.">
              ↳ Queued · picked up at the next step
            </p>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start mb-4">
      <div className="w-full space-y-1">
        <ThinkingBlock thinking={thinking} streaming={streaming && !text} />
        {text && (
          <div className="rounded-2xl rounded-bl-sm px-4 py-3 text-sm bg-muted text-foreground max-w-none">
            <AssistantMarkdown source={text} streaming={streaming} />
            {streaming && <span className="inline-block w-0.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />}
          </div>
        )}
        {text && !streaming && remember && <RememberThis text={text} />}
      </div>
    </div>
  );
}

/** A generated image in the transcript: the inline data URI for an instant
 * thumbnail, the full-res URL in a lightbox on click. */
function ImageBubble({ image, fullUrl, caption }) {
  const [open, setOpen] = useState(false);
  const thumb = image || fullUrl;
  const full = fullUrl || image;
  if (!thumb) return null;
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[82%] space-y-1">
        <button
          type="button"
          onClick={() => setOpen(true)}
          title="View full screen"
          className="block overflow-hidden rounded-2xl rounded-bl-sm border border-border/60 bg-muted/40 transition-opacity hover:opacity-95"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={thumb} alt={caption || "Generated image"} loading="lazy" className="block w-44 max-w-full object-cover" />
        </button>
        {caption && <p className="pl-1 text-[11px] text-muted-foreground">{caption}</p>}
      </div>
      <Lightbox open={open} onOpenChange={setOpen} src={full} alt={caption || "Generated image"} />
    </div>
  );
}

/** Compact chip for an artifact the agent just created or revised — opens the
 * artifact viewer. The "card-in-stream" convention. */
function ArtifactCard({ artifact }) {
  if (!artifact) return null;
  return (
    <a
      href={`/artifacts/${artifact.artifact_id}`}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-2.5 my-1.5 px-3 py-2 rounded-lg border border-input bg-muted/30 hover:bg-muted/60 transition-colors max-w-md no-underline"
    >
      <span aria-hidden="true" className="text-base">📄</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium truncate">{artifact.title || artifact.slug}</span>
        <span className="block text-xs text-muted-foreground truncate">
          {artifact.kind} · v{artifact.version}
          {artifact.label ? ` — ${artifact.label}` : ""}
        </span>
      </span>
    </a>
  );
}

function TranscriptRow({ msg, onRetrySend, remember }) {
  switch (msg.role) {
    case Row.SEND_ERROR:
      return <SendErrorBubble text={msg.text} content={msg.content} code={msg.code} onRetry={onRetrySend} retryable={msg.retryable} />;
    case Row.IMAGE:
      return <ImageBubble image={msg.image} fullUrl={msg.fullUrl} caption={msg.caption} />;
    case Row.ARTIFACT_CARD:
      return <ArtifactCard artifact={msg.artifact} />;
    case Row.CHANGE_SET_CARD:
      return <ChangeSetCard changeSet={msg.changeSet} />;
    case Row.MEMORY_NOTE:
      return <MemoryNote memories={msg.memories} />;
    case Row.MEMORY_RECALL:
      return <MemoryRecall memories={msg.memories} />;
    case Row.NOTICE:
      return <NoticeRow text={msg.text} />;
    default:
      return (
        <ChatBubble
          role={msg.role}
          text={msg.text}
          thinking={msg.thinking}
          streaming={msg.streaming}
          remember={remember}
          queued={Boolean(msg.queued)}
        />
      );
  }
}

/** The one thing worth offering under a terminal failure, decided by its
 *  ErrorCode: a retry only when a retry can work, otherwise the place the fix
 *  lives. A failure with no code is treated as retryable, which is what every
 *  failure was before codes existed. */
function FailedAction({ action, retryable, onRetry, retryLabel, onStartFresh }) {
  const button = "mt-3 w-full rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors text-center";
  switch (action) {
    case ErrorAction.SETTINGS:
      return <Link href="/settings/models" className={button}>Open model settings</Link>;
    case ErrorAction.CONNECTIONS:
      return <Link href="/connections" className={button}>Open connections</Link>;
    case ErrorAction.FRESH:
      if (onStartFresh) return <button type="button" onClick={onStartFresh} className={button}>Start a fresh conversation</button>;
      return null;
    case ErrorAction.NONE:
      return null;
    default:
      if (!onRetry || !retryable) return null;
      return <button type="button" onClick={onRetry} className={button}>{retryLabel}</button>;
  }
}

// ---------------------------------------------------------------------------
// Header status
// ---------------------------------------------------------------------------

/** Seconds since `active` last became true; 0 while it is false. A clock in
 *  the status row is what tells a user a four-minute run is alive. */
function useElapsed(active) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    setSeconds(0);
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return seconds;
}

export function formatElapsed(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${String(s).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${String(m % 60).padStart(2, "0")}m`;
}

/** A quiet centred line in the transcript — "Context compacted". */
function NoticeRow({ text }) {
  return (
    <p className="my-3 text-center text-[11px] text-muted-foreground" role="note">
      {text}
    </p>
  );
}

const PHASE_STATUS = {
  [Phase.STARTING]:  { label: "Connecting…",     pulse: true },
  [Phase.PIPELINE]:  { label: "Working…",        pulse: true },
  [Phase.QUESTIONS]: { label: "Waiting for you", pulse: false },
  [Phase.READY]:     { label: "Ready",           pulse: false },
  [Phase.CHATTING]:  { label: "Thinking…",       pulse: true },
  [Phase.FAILED]:    { label: "Failed",          pulse: false },
};

// ---------------------------------------------------------------------------
// The pane
// ---------------------------------------------------------------------------

export default function AgentChat({
  title = "Agent Chat",
  phase,
  steps = [],
  todos = [],
  messages = [],
  pending = null,
  errorMsg = "",
  // The failure's ErrorCode and whether a retry can help (lib/agentEvents.js).
  errorCode = "",
  errorRetryable = true,
  // A model call being waited out: { attempt, max }. Shown in the status row.
  retrying = null,
  draft = null,
  // Tokens (lib/agentSession.js `usage`): the ring in the header, the figures
  // in its tooltip. Null until the first model call has been billed.
  usage = null,
  // History is being summarised to make room — the status row says so.
  compacting = false,
  isAgentTyping = false,
  isStreaming = false,
  reconnecting = false,
  inputDisabled = false,
  // The pause card can be on screen before the session it answers to exists
  // (restored from the thread's state on open); keep its buttons off until then.
  answerDisabled = false,
  remembering = true,
  onAnswer,
  onSendMessage,
  onRetrySend,
  onRetry,
  onStop,
  onStartFresh,
  canStartFresh = false,
  renderSteps,
  stepLabels,
  questionsCopy,
  inputPlaceholder,
  inputAriaLabel,
  inputAccept,
  startingLabel = "Starting session…",
  failedTitle = "Session failed",
  retryLabel = "↺ Retry",
  readyHint = null,
  headerExtra = null,
  footer = null,
}) {
  const scrollRef = useRef(null);
  const isAtBottom = useRef(true);
  const prevMsgLen = useRef(0);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    isAtBottom.current = atBottom;
    if (atBottom) setShowScrollBtn(false);
  }

  function scrollToLatest() {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    setShowScrollBtn(false);
  }

  // Instant auto-scroll only when already near the bottom (don't hijack manual reading).
  useEffect(() => {
    if (isAtBottom.current) scrollToLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, steps, isAgentTyping, pending]);

  // "New message" only when a new row appears while the user has scrolled up.
  // Token updates don't change messages.length, so they don't trigger it.
  useEffect(() => {
    if (messages.length > prevMsgLen.current) {
      prevMsgLen.current = messages.length;
      if (!isAtBottom.current) setShowScrollBtn(true);
    }
  }, [messages.length]);

  const status = PHASE_STATUS[phase] ?? PHASE_STATUS[Phase.STARTING];
  const isFailed = phase === Phase.FAILED;
  const waiting = phase === Phase.QUESTIONS && Boolean(pending);
  const working = phase === Phase.PIPELINE || phase === Phase.CHATTING;
  const elapsed = useElapsed(working);
  // What it is doing right now, most specific first. Codex titles this row
  // with the model's own words; we have the step it is in, which is enough.
  const runningStep = steps.find((s) => s.status === StepStatus.RUNNING && !s.step_id?.includes(":"));
  // The countdown re-reads the clock on every tick of the elapsed timer, so it
  // needs no timer of its own. `until` is on this client's clock (the reducer
  // anchors the backend's duration at receipt), so skew cannot show "in -3s".
  const retryIn = retrying?.until ? Math.max(0, Math.ceil((retrying.until - Date.now()) / 1000)) : 0;
  const activity = retrying
    ? `Reconnecting to the model (${retrying.attempt}/${retrying.max})${retryIn > 0 ? ` · retry in ${retryIn}s` : ""}`
    : compacting
      ? "Compacting context"
      : runningStep?.label || "";
  const statusLabel = reconnecting && !isFailed
    ? "Reconnecting…"
    : working
      ? [status.label.replace(/…$/, ""), formatElapsed(elapsed), activity].filter(Boolean).join(" · ")
      : status.label;
  const contextUsed = usage?.last?.window ? (usage.last.input + usage.last.output) / usage.last.window : 0;
  // The box stays open while the agent works: say where a message goes.
  const placeholder = inputPlaceholder
    || (working ? "Add a thought — it goes in at the next step"
      : waiting ? "Answer above, or leave a note for after"
        : undefined);

  return (
    <div className="flex flex-col h-full">
      <div
        className={`flex items-center gap-2 border-b px-4 py-2 shrink-0 transition-colors ${
          waiting ? "border-amber-400/70 bg-amber-50/60 dark:bg-amber-950/20" : "border-border/60"
        }`}
      >
        <span className="text-sm font-medium">{title}</span>
        {waiting && (
          <span className="relative flex size-2" aria-hidden="true">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full size-2 bg-amber-500" />
          </span>
        )}
        {/* role="status" so a screen reader hears the agent change state —
            "Working…", "Waiting for you", "Ready", "Failed". This is the only
            live region in the agent shell on purpose: announcing the streaming
            tokens themselves, or the rotating subtitle in PipelineProgress,
            would talk over the user continuously. State changes are the signal;
            the prose is already readable on demand. */}
        <span
          role="status"
          aria-live="polite"
          className={`text-xs ${
            waiting ? "text-amber-600 dark:text-amber-400 font-medium" : isFailed ? "text-destructive" : "text-muted-foreground"
          } ${status.pulse && !waiting && !working ? "animate-pulse" : ""}`}
        >
          — {statusLabel}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {headerExtra}
          {usage?.last && <ContextRing used={contextUsed} details={usage} />}
          {!remembering && (
            <span
              className="inline-flex items-center gap-1 text-xs text-muted-foreground"
              title="Nothing from project memory is read into this session, and nothing it concludes is written back."
            >
              <Brain size={12} aria-hidden="true" />
              Not remembering
            </span>
          )}
          {onStartFresh && canStartFresh && (
            <button
              type="button"
              onClick={onStartFresh}
              title="Abandon this conversation and start a new one (what it produced is kept)"
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              ↺ Start fresh
            </button>
          )}
        </span>
      </div>

      <Todos todos={todos} />

      <div className="flex-1 relative min-h-0">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="absolute inset-0 overflow-y-auto px-4 py-4
            [&::-webkit-scrollbar]:w-[3px]
            [&::-webkit-scrollbar-thumb]:rounded-full
            [&::-webkit-scrollbar-thumb]:bg-border/60
            [&::-webkit-scrollbar-track]:bg-transparent"
        >
          {phase === Phase.STARTING && (
            <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
              <Spinner className="size-3" />
              {startingLabel}
            </div>
          )}

          {steps.length > 0 && (
            <div className="mb-2">{renderSteps ? renderSteps(steps) : <StepProgress steps={steps} labels={stepLabels} />}</div>
          )}

          {messages.map((msg, i) => (
            <TranscriptRow
              key={msg.role === Row.CHANGE_SET_CARD ? msg.changeSet?.change_set_id || i : i}
              msg={msg}
              onRetrySend={onRetrySend}
              remember={remembering}
            />
          ))}

          {isAgentTyping && <TypingIndicator />}

          {waiting && <PauseCard pause={pending} onAnswer={onAnswer} disabled={answerDisabled} questionsCopy={questionsCopy} />}

          {reconnecting && !isFailed && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-600 dark:text-amber-400">
              <Spinner className="size-3" />
              Connection dropped — reconnecting…
            </div>
          )}

          {isFailed && (
            <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/8 p-4">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 text-destructive text-base leading-none" aria-hidden="true">✕</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-destructive mb-1">{failedTitle}</p>
                  <p className="text-xs text-muted-foreground break-words leading-relaxed">{errorMsg}</p>
                </div>
              </div>
              <FailedAction
                action={errorAction(errorCode)}
                retryable={errorRetryable}
                onRetry={onRetry}
                retryLabel={retryLabel}
                onStartFresh={onStartFresh}
              />
            </div>
          )}

          {phase === Phase.READY && messages.length === 0 && readyHint}
        </div>

        {showScrollBtn && (
          <div className="absolute bottom-3 inset-x-0 flex justify-center z-10 pointer-events-none">
            <button
              type="button"
              onClick={scrollToLatest}
              className="pointer-events-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 transition-all"
            >
              ↓ New message
            </button>
          </div>
        )}
      </div>

      {footer}

      <ChatInput
        onSend={onSendMessage}
        disabled={inputDisabled}
        isStreaming={isStreaming}
        onStop={onStop}
        draft={draft}
        placeholder={placeholder}
        ariaLabel={inputAriaLabel}
        accept={inputAccept}
      />
    </div>
  );
}
