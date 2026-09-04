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
import { Brain } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { Lightbox } from "@/components/ui/lightbox";
import ChangeSetCard from "@/components/execution/ChangeSetCard";
import { Phase } from "../../lib/agentPhase";
import { Row } from "../../lib/agentSession";
import { AssistantMarkdown, ThinkingMarkdown } from "./ChatMarkdown";
import ChatInput from "./ChatInput";
import { MemoryNote, MemoryRecall, RememberThis } from "./MemoryRows";
import PauseCard from "./PauseCard";
import StepProgress from "./StepProgress";
import Todos from "./Todos";

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

function SendErrorBubble({ text, content, onRetry }) {
  return (
    <div className="flex justify-end mb-2">
      <div className="max-w-[85%] space-y-1">
        <div className="rounded-2xl rounded-br-sm px-3 py-2 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
          <p className="text-xs font-medium mb-0.5">Failed to send</p>
          <p className="text-xs text-destructive/80">{text}</p>
        </div>
        {content && onRetry && (
          <button
            type="button"
            onClick={() => onRetry(content)}
            className="w-full text-xs text-right text-muted-foreground hover:text-foreground transition-colors pr-1"
          >
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

function ChatBubble({ role, text, thinking, streaming, remember }) {
  if (role === Row.USER) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[82%]">
          <div className="rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed bg-primary text-primary-foreground">
            <p className="whitespace-pre-wrap break-words">{text}</p>
          </div>
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
            <AssistantMarkdown source={text} />
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
      return <SendErrorBubble text={msg.text} content={msg.content} onRetry={onRetrySend} />;
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
    default:
      return <ChatBubble role={msg.role} text={msg.text} thinking={msg.thinking} streaming={msg.streaming} remember={remember} />;
  }
}

// ---------------------------------------------------------------------------
// Header status
// ---------------------------------------------------------------------------

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
          } ${status.pulse && !waiting ? "animate-pulse" : ""}`}
        >
          — {reconnecting && !isFailed ? "Reconnecting…" : status.label}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {headerExtra}
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
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-3 w-full rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
                >
                  {retryLabel}
                </button>
              )}
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
        placeholder={inputPlaceholder}
        ariaLabel={inputAriaLabel}
        accept={inputAccept}
      />
    </div>
  );
}
