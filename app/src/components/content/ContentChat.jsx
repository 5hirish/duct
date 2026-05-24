"use client";

import { useEffect, useRef, useState } from "react";
import ContentInput from "./ContentInput";
import ContentQuestions from "./ContentQuestions";
import ContentStepProgress from "./ContentStepProgress";
import ContentTodos from "./ContentTodos";
import { Phase } from "./contentPhase";

function SendErrorBubble({ text, content, onRetry }) {
  return (
    <div className="flex justify-end mb-2">
      <div className="max-w-[85%] space-y-1">
        <div className="rounded-2xl rounded-br-sm px-3 py-2 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
          <p className="text-xs font-medium mb-0.5">Failed to send</p>
          <p className="text-xs text-destructive/80">{text}</p>
        </div>
        {content && (
          <button
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
    <div className="mb-1">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="font-mono">{expanded ? "▾" : "▸"}</span>
        <span>{expanded ? "Hide" : "Show"} reasoning{streaming ? "…" : ""}</span>
      </button>
      {expanded && (
        <div className="mt-1 rounded-lg px-3 py-2 text-xs text-muted-foreground bg-muted/40 border border-border/40 italic whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
          {thinking}
          {streaming && (
            <span className="inline-block w-0.5 h-3 bg-current ml-0.5 animate-pulse align-middle" />
          )}
        </div>
      )}
    </div>
  );
}

function ChatBubble({ role, text, thinking, streaming }) {
  return (
    <div className={`flex ${role === "user" ? "justify-end" : "justify-start"} mb-2`}>
      <div className={`max-w-[85%] ${role !== "user" ? "space-y-0.5" : ""}`}>
        {role !== "user" && <ThinkingBlock thinking={thinking} streaming={streaming && !text} />}
        {(text || role === "user") && (
          <div
            className={`rounded-2xl px-3 py-2 text-sm leading-relaxed ${
              role === "user"
                ? "bg-primary text-primary-foreground rounded-br-sm"
                : "bg-muted text-foreground rounded-bl-sm"
            }`}
          >
            <p className="whitespace-pre-wrap break-words">
              {text}
              {streaming && text && (
                <span className="inline-block w-0.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />
              )}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

const PHASE_STATUS = {
  [Phase.STARTING]:  { label: "Connecting…",       pulse: true  },
  [Phase.PIPELINE]:  { label: "Working…",          pulse: true  },
  [Phase.QUESTIONS]: { label: "Waiting for you",   pulse: false },
  [Phase.READY]:     { label: "Ready",             pulse: false },
  [Phase.CHATTING]:  { label: "Thinking…",         pulse: true  },
  [Phase.FAILED]:    { label: "Failed",            pulse: false },
};

const MODE_LABELS = {
  plan_month: "Generating 30-day plan",
  draft_post: "Drafting post",
};

export default function ContentChat({
  mode,
  phase,
  steps,
  todos,
  messages,
  pendingQuestions,
  errorMsg,
  onAnswerQuestions,
  onSendMessage,
  onRetrySend,
  onRetry,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, steps, pendingQuestions]);

  const status = PHASE_STATUS[phase] ?? PHASE_STATUS[Phase.STARTING];
  const isBusy = phase === Phase.STARTING || phase === Phase.PIPELINE || phase === Phase.CHATTING;
  const isFailed = phase === Phase.FAILED;
  const inputDisabled = isBusy || phase === Phase.QUESTIONS || isFailed;
  const modeLabel = MODE_LABELS[mode] || "Content agent";

  return (
    <div className="flex flex-col h-full">
      <div
        className={`flex items-center gap-2 border-b px-4 py-2 shrink-0 transition-colors ${
          phase === Phase.QUESTIONS
            ? "border-amber-400/70 bg-amber-50/60 dark:bg-amber-950/20"
            : "border-border/60"
        }`}
      >
        <span className="text-sm font-medium">{modeLabel}</span>
        {phase === Phase.QUESTIONS && (
          <span className="relative flex size-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full size-2 bg-amber-500" />
          </span>
        )}
        <span
          className={`text-xs ${
            phase === Phase.QUESTIONS
              ? "text-amber-600 dark:text-amber-400 font-medium"
              : isFailed
              ? "text-destructive"
              : "text-muted-foreground"
          } ${status.pulse && phase !== Phase.QUESTIONS ? "animate-pulse" : ""}`}
        >
          — {status.label}
        </span>
      </div>

      <ContentTodos todos={todos} />

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        {phase === Phase.STARTING && (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <span className="inline-block size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
            Starting session…
          </div>
        )}

        {steps.length > 0 && (
          <div className="mb-2">
            <ContentStepProgress steps={steps} />
          </div>
        )}

        {messages.map((msg, i) =>
          msg.role === "send_error" ? (
            <SendErrorBubble key={i} text={msg.text} content={msg.content} onRetry={onRetrySend} />
          ) : (
            <ChatBubble
              key={i}
              role={msg.role}
              text={msg.text}
              thinking={msg.thinking}
              streaming={msg.streaming}
            />
          ),
        )}

        {phase === Phase.QUESTIONS && pendingQuestions?.length > 0 && (
          <ContentQuestions questions={pendingQuestions} onSubmit={onAnswerQuestions} disabled={false} />
        )}

        {isFailed && (
          <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/8 p-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-destructive text-base leading-none">✕</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-destructive mb-1">Session failed</p>
                <p className="text-xs text-muted-foreground break-words leading-relaxed">{errorMsg}</p>
              </div>
            </div>
            <button
              onClick={onRetry}
              className="mt-3 w-full rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
            >
              ↺ Retry
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ContentInput onSend={onSendMessage} disabled={inputDisabled} />
    </div>
  );
}
