"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";  // honor single newlines as line breaks (LLMs use them)
import AuditStepProgress from "./AuditStepProgress";
import AuditQuestions from "./AuditQuestions";
import AuditInput from "./AuditInput";
import AuditTodos from "./AuditTodos";
import { Phase } from "./auditPhase";
import { CodeBlock, resolveCode } from "./CodeBlock";

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
    <div className="mb-2">
      <button
        onClick={() => setExpanded((x) => !x)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="font-mono">{expanded ? "▾" : "▸"}</span>
        <span>{expanded ? "Hide" : "Show"} reasoning{streaming ? "…" : ""}</span>
      </button>
      {expanded && (
        <div className="mt-1.5 rounded-lg px-3.5 py-3 bg-muted/40 border border-border/40">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkBreaks]}
            components={{
              // Headings: not italic, real weight/color so sections are scannable
              h1: ({children}) => <p className="text-xs font-bold text-foreground/80 mt-3 mb-1">{children}</p>,
              h2: ({children}) => <p className="text-xs font-semibold text-foreground/75 mt-2.5 mb-1">{children}</p>,
              h3: ({children}) => <p className="text-[11px] font-semibold text-foreground/70 mt-2 mb-0.5 uppercase tracking-wide">{children}</p>,
              h4: ({children}) => <p className="text-[11px] font-medium text-foreground/65 mt-1.5 mb-0.5">{children}</p>,
              // Body: plain (NOT italic) + muted, with breathing room between paragraphs
              p:  ({children}) => <p className="text-[11px] text-muted-foreground leading-relaxed my-2">{children}</p>,
              // Lists: proper vertical rhythm
              ul: ({children}) => <ul className="list-disc pl-4 my-2 space-y-1">{children}</ul>,
              ol: ({children}) => <ol className="list-decimal pl-4 my-2 space-y-1">{children}</ol>,
              li: ({children}) => <li className="text-[11px] text-muted-foreground leading-relaxed">{children}</li>,
              // Code: inline vs fenced block
              code: ({className, children}) => {
                const { language, isBlock } = resolveCode(className, children);
                if (isBlock) return <CodeBlock language={language} compact>{children}</CodeBlock>;
                return <code className="text-[10px] not-italic font-mono bg-background/70 border border-border/60 text-foreground/80 px-1 py-0.5 rounded">{children}</code>;
              },
              strong: ({children}) => <strong className="font-semibold not-italic text-foreground/75">{children}</strong>,
              em: ({children}) => <em className="italic text-muted-foreground">{children}</em>,
              // Links: open in new tab
              a: ({href, children}) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-foreground/70 underline underline-offset-2 not-italic hover:text-foreground/90">{children}</a>,
              // Blockquote
              blockquote: ({children}) => <blockquote className="border-l-2 border-border/60 pl-3 my-1.5 italic text-muted-foreground/70">{children}</blockquote>,
              // Tables
              table: ({children}) => <table className="border-collapse my-1.5 w-full text-[10px]">{children}</table>,
              th: ({children}) => <th className="border border-border/60 px-2 py-0.5 font-semibold text-left not-italic bg-muted/20">{children}</th>,
              td: ({children}) => <td className="border border-border/60 px-2 py-0.5">{children}</td>,
              hr: () => <hr className="border-border/40 my-2" />,
            }}
          >
            {thinking}
          </ReactMarkdown>
          {streaming && (
            <span className="inline-block w-0.5 h-3 bg-muted-foreground/60 ml-0.5 animate-pulse align-middle" />
          )}
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

function ChatBubble({ role, text, thinking, streaming }) {
  if (role === "user") {
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
            {/* Explicit per-element styling — the app has NO @tailwindcss/typography
                plugin, so `prose` classes are no-ops and Tailwind's preflight strips
                heading sizes, list bullets and paragraph margins. Style every element
                directly (same approach as ThinkingBlock) so markdown renders, not blobs. */}
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkBreaks]}
              components={{
                // Headings
                h1: ({ children }) => <h1 className="text-lg font-bold text-foreground mt-4 mb-2 first:mt-0">{children}</h1>,
                h2: ({ children }) => <h2 className="text-base font-bold text-foreground mt-4 mb-1.5 first:mt-0">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-semibold text-foreground mt-3 mb-1 first:mt-0">{children}</h3>,
                h4: ({ children }) => <h4 className="text-sm font-semibold text-foreground/90 mt-2.5 mb-1 first:mt-0">{children}</h4>,
                // Paragraph
                p: ({ children }) => <p className="my-2.5 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
                // Lists — restore bullets/numbers (preflight removes list-style)
                ul: ({ children }) => <ul className="list-disc pl-5 my-2.5 space-y-1 marker:text-muted-foreground/70 [&_ul]:my-1 [&_ol]:my-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-5 my-2.5 space-y-1 marker:text-muted-foreground/70 [&_ul]:my-1 [&_ol]:my-1">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed pl-0.5">{children}</li>,
                strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                em: ({ children }) => <em className="italic">{children}</em>,
                hr: () => <hr className="border-border my-4" />,
                // Inline vs fenced code block
                code({ className, children }) {
                  const { language, isBlock } = resolveCode(className, children);
                  if (isBlock) return <CodeBlock language={language}>{children}</CodeBlock>;
                  return (
                    <code className="bg-primary/10 text-primary dark:bg-primary/20 px-1.5 py-0.5 rounded text-[0.8em] font-mono before:content-none after:content-none">
                      {children}
                    </code>
                  );
                },
                // Links: new tab + security
                a({ href, children }) {
                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer"
                       className="text-primary underline underline-offset-2 hover:no-underline">
                      {children}
                    </a>
                  );
                },
                // Tables
                table({ children }) { return <div className="overflow-x-auto my-3"><table className="border-collapse w-full text-sm">{children}</table></div>; },
                th({ children }) { return <th className="border border-border px-3 py-1.5 font-semibold text-left bg-muted/50">{children}</th>; },
                td({ children }) { return <td className="border border-border px-3 py-1.5">{children}</td>; },
                // Blockquote
                blockquote({ children }) {
                  return <blockquote className="border-l-4 border-border pl-4 my-3 text-muted-foreground italic">{children}</blockquote>;
                },
              }}
            >
              {text}
            </ReactMarkdown>
            {streaming && (
              <span className="inline-block w-0.5 h-3.5 bg-current ml-0.5 animate-pulse align-middle" />
            )}
          </div>
        )}
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
  isAgentTyping,
  isStreaming,
  onAnswerQuestions,
  onSendMessage,
  onRetrySend,
  onRetry,
  onStop,
}) {
  const scrollRef    = useRef(null);
  const bottomRef    = useRef(null);
  const isAtBottom   = useRef(true);
  const prevMsgLen   = useRef(0);
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

  // Instant auto-scroll only when already near the bottom (don't hijack manual reading)
  useEffect(() => {
    if (isAtBottom.current) scrollToLatest();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, steps, isAgentTyping, pendingQuestions]);

  // Show "New message" button only when a new message appears and user has scrolled up
  // (thinking chunk updates don't add to messages.length, so this ignores them)
  useEffect(() => {
    if (messages.length > prevMsgLen.current) {
      prevMsgLen.current = messages.length;
      if (!isAtBottom.current) setShowScrollBtn(true);
    }
  }, [messages.length]);

  const status = PHASE_STATUS[phase] ?? PHASE_STATUS[Phase.STARTING];
  const isFailed = phase === Phase.FAILED;
  // Allow typing during CHATTING (post-report chat), disabled only during pipeline + questions + failed
  const inputDisabled = phase === Phase.QUESTIONS || isFailed;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`flex items-center gap-2 border-b px-4 py-2 shrink-0 transition-colors ${
        phase === Phase.QUESTIONS
          ? "border-amber-400/70 bg-amber-50/60 dark:bg-amber-950/20"
          : "border-border/60"
      }`}>
        <span className="text-sm font-medium">Agent Chat</span>
        {/* Fix 2 — pulsing attention dot when agent is waiting for user input */}
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

      {/* Sticky todo tracker */}
      <AuditTodos todos={todos} />

      {/* Scrollable content + floating new-message button */}
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
        {messages.map((msg, i) =>
          msg.role === "send_error" ? (
            <SendErrorBubble key={i} text={msg.text} content={msg.content} onRetry={onRetrySend} />
          ) : (
            <ChatBubble key={i} role={msg.role} text={msg.text} thinking={msg.thinking} streaming={msg.streaming} />
          )
        )}

        {/* Typing indicator — shown after sending a message while waiting for first chunk */}
        {isAgentTyping && <TypingIndicator />}

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

        {/* Ready hint — only shown if no messages yet (e.g. report arrived without synthesis chunks) */}
        {phase === Phase.READY && hasReport && messages.length === 0 && (
          <p className="text-sm text-center mt-6 px-2 py-3 rounded-lg bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
            ✓ Report ready — ask me anything about the findings.
          </p>
        )}

          <div ref={bottomRef} />
        </div>{/* end scroll container */}

        {/* Floating "New message" indicator — only appears when user has scrolled up */}
        {showScrollBtn && (
          <div className="absolute bottom-3 inset-x-0 flex justify-center z-10 pointer-events-none">
            <button
              onClick={scrollToLatest}
              className="pointer-events-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 transition-all"
            >
              ↓ New message
            </button>
          </div>
        )}
      </div>{/* end relative wrapper */}

      {/* Input */}
      <AuditInput
        onSend={onSendMessage}
        disabled={inputDisabled}
        isStreaming={isStreaming}
        onStop={onStop}
      />
    </div>
  );
}
