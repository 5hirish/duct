"use client";

import { useEffect, useRef } from "react";
import AuditStepProgress from "./AuditStepProgress";
import AuditQuestions from "./AuditQuestions";
import AuditInput from "./AuditInput";
import AuditTodos from "./AuditTodos";

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

export default function AuditChat({
  messages,
  steps,
  todos,
  pendingQuestions,
  sessionId,
  onAnswerQuestions,
  onSendMessage,
  agentBusy,
  reportReady,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, steps, pendingQuestions]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-border/60 px-4 py-2 shrink-0">
        <span className="text-sm font-medium">Agent Chat</span>
        {agentBusy && (
          <span className="ml-2 text-xs text-muted-foreground animate-pulse">thinking…</span>
        )}
      </div>

      {/* Sticky todo tracker */}
      <AuditTodos todos={todos} />

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        {/* Step progress */}
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
        {pendingQuestions && pendingQuestions.length > 0 && (
          <AuditQuestions
            questions={pendingQuestions}
            onSubmit={onAnswerQuestions}
            disabled={agentBusy}
          />
        )}

        {reportReady && messages.length === 0 && (
          <p className="text-xs text-muted-foreground text-center mt-4">
            Report ready. Ask a follow-up question to dive deeper, modify findings,
            or upload a screenshot for context.
          </p>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <AuditInput
        onSend={onSendMessage}
        disabled={agentBusy || !!pendingQuestions}
      />
    </div>
  );
}
