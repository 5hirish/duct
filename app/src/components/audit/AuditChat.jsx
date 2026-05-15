"use client";

import { useEffect, useRef } from "react";
import AuditStepProgress from "./AuditStepProgress";
import AuditQuestions from "./AuditQuestions";
import AuditInput from "./AuditInput";
import AuditTodos from "./AuditTodos";
import { Phase } from "./AuditWorkspace";

function ChatBubble({ role, text, streaming }) {
  return (
    <div className={`flex ${role === "user" ? "justify-end" : "justify-start"} mb-2`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
          role === "user"
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">
          {text}
          {streaming && (
            <span className="inline-block w-0.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />
          )}
        </p>
      </div>
    </div>
  );
}

// Header status label per phase
const PHASE_STATUS = {
  [Phase.STARTING]:  { label: "Connecting…",      pulse: true  },
  [Phase.PIPELINE]:  { label: "Running pipeline…", pulse: true  },
  [Phase.QUESTIONS]: { label: "Waiting for you",   pulse: false },
  [Phase.READY]:     { label: "Ready",              pulse: false },
  [Phase.CHATTING]:  { label: "Thinking…",         pulse: true  },
  [Phase.FAILED]:    { label: "Failed",             pulse: false },
};

export default function AuditChat({
  phase,
  steps,
  todos,
  messages,
  pendingQuestions,
  hasReport,
  errorMsg,
  onAnswerQuestions,
  onSendMessage,
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

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-2 shrink-0">
        <span className="text-sm font-medium">Agent Chat</span>
        <span
          className={`text-xs ${isFailed ? "text-destructive" : "text-muted-foreground"} ${status.pulse ? "animate-pulse" : ""}`}
        >
          — {status.label}
        </span>
      </div>

      {/* Sticky todo tracker */}
      <AuditTodos todos={todos} />

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">

        {/* Starting: spinner before first step arrives */}
        {phase === Phase.STARTING && (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <span className="inline-block size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
            Starting audit…
          </div>
        )}

        {/* Step progress — always visible once steps arrive */}
        {steps.length > 0 && (
          <div className="mb-2">
            <AuditStepProgress steps={steps} />
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg, i) => (
          <ChatBubble key={i} role={msg.role} text={msg.text} streaming={msg.streaming} />
        ))}

        {/* Clarifying questions */}
        {phase === Phase.QUESTIONS && pendingQuestions?.length > 0 && (
          <AuditQuestions
            questions={pendingQuestions}
            onSubmit={onAnswerQuestions}
            disabled={false}
          />
        )}

        {/* Error */}
        {isFailed && (
          <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/8 p-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-destructive text-base leading-none">✕</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-destructive mb-1">Audit failed</p>
                <p className="text-xs text-muted-foreground break-words leading-relaxed">{errorMsg}</p>
              </div>
            </div>
            <button
              onClick={onRetry}
              className="mt-3 w-full rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
            >
              ↺ Retry audit
            </button>
          </div>
        )}

        {/* Ready hint */}
        {phase === Phase.READY && hasReport && messages.length === 0 && (
          <p className="text-xs text-muted-foreground text-center mt-4">
            Report ready. Ask a follow-up question to dive deeper, modify findings,
            or upload a screenshot for context.
          </p>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <AuditInput onSend={onSendMessage} disabled={inputDisabled} />
    </div>
  );
}
