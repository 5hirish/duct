"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";  // honor single newlines as line breaks (LLMs use them)
import ContentInput from "./ContentInput";
import ContentQuestions from "./ContentQuestions";
import ContentStepProgress from "./ContentStepProgress";
import ContentTodos from "./ContentTodos";
import { Phase } from "./contentPhase";
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

// We deliberately do NOT surface the model's raw chain-of-thought. It's a private
// scratchpad that inevitably contains internals (sub-agent + tool names, asset
// UUIDs, JSON, slide ids like "slide-06", field names) — no prompt rule cleans it
// reliably, and this is a non-technical creator tool. While the model is reasoning
// (thinking streaming, no reply text yet) we show a calm "Thinking…" affordance;
// the polished reply + the step chips convey everything the user needs.
function ThinkingBlock({ thinking, streaming }) {
  if (!thinking || !streaming) return null;
  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
      <span className="flex gap-1">
        {[0, 150, 300].map((d) => (
          <span
            key={d}
            className="inline-block size-1 rounded-full bg-muted-foreground/60 animate-bounce"
            style={{ animationDelay: `${d}ms` }}
          />
        ))}
      </span>
      <span>Thinking…</span>
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
                h1: ({ children }) => <h1 className="text-lg font-bold text-foreground mt-4 mb-2 first:mt-0">{children}</h1>,
                h2: ({ children }) => <h2 className="text-base font-bold text-foreground mt-4 mb-1.5 first:mt-0">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-semibold text-foreground mt-3 mb-1 first:mt-0">{children}</h3>,
                h4: ({ children }) => <h4 className="text-sm font-semibold text-foreground/90 mt-2.5 mb-1 first:mt-0">{children}</h4>,
                p: ({ children }) => <p className="my-2.5 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-5 my-2.5 space-y-1 marker:text-muted-foreground/70 [&_ul]:my-1 [&_ol]:my-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-5 my-2.5 space-y-1 marker:text-muted-foreground/70 [&_ul]:my-1 [&_ol]:my-1">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed pl-0.5">{children}</li>,
                strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                em: ({ children }) => <em className="italic">{children}</em>,
                hr: () => <hr className="border-border my-4" />,
                code({ className, children }) {
                  const { language, isBlock } = resolveCode(className, children);
                  if (isBlock) return <CodeBlock language={language}>{children}</CodeBlock>;
                  return (
                    <code className="bg-primary/10 text-primary dark:bg-primary/20 px-1.5 py-0.5 rounded text-[0.8em] font-mono before:content-none after:content-none">
                      {children}
                    </code>
                  );
                },
                a({ href, children }) {
                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:no-underline">
                      {children}
                    </a>
                  );
                },
                table: ({ children }) => <div className="overflow-x-auto my-3"><table className="border-collapse w-full text-sm">{children}</table></div>,
                th: ({ children }) => <th className="border border-border px-3 py-1.5 font-semibold text-left bg-muted/50">{children}</th>,
                td: ({ children }) => <td className="border border-border px-3 py-1.5">{children}</td>,
                blockquote: ({ children }) => <blockquote className="border-l-4 border-border pl-4 my-3 text-muted-foreground italic">{children}</blockquote>,
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

// A generated-image bubble in the transcript. Shows the inline data URI for an
// instant thumbnail; clicking opens a full-screen lightbox at the full-res URL.
function ChatImageBubble({ image, fullUrl, caption }) {
  const [open, setOpen] = useState(false);
  const thumb = image || fullUrl;   // inline data: URI first (instant paint)
  const full = fullUrl || image;    // full-res target for the lightbox
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
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
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-black/80 p-6"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={full} alt={caption || "Generated image"} className="max-h-full max-w-full rounded-lg object-contain shadow-2xl" />
        </div>
      )}
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
  update_plan: "Content Planner",
};

export default function ContentChat({
  mode,
  phase,
  steps,
  todos,
  messages,
  pendingQuestions,
  errorMsg,
  isAgentTyping,
  isStreaming,
  reconnecting,
  onAnswerQuestions,
  onSendMessage,
  onRetrySend,
  onRetry,
  onStop,
  onStartFresh,
  canStartFresh,
  mobilePostBar,
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

  // Instant auto-scroll only when already near the bottom (don't hijack manual reading).
  useEffect(() => {
    if (isAtBottom.current) scrollToLatest();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, steps, isAgentTyping, pendingQuestions]);

  // Show "New message" button only when a new message appears and user has scrolled up.
  useEffect(() => {
    if (messages.length > prevMsgLen.current) {
      prevMsgLen.current = messages.length;
      if (!isAtBottom.current) setShowScrollBtn(true);
    }
  }, [messages.length]);

  const status = PHASE_STATUS[phase] ?? PHASE_STATUS[Phase.STARTING];
  const isFailed = phase === Phase.FAILED;
  // Input enabled during READY + CHATTING (post-artifact chat), disabled during
  // pipeline / questions / failed, and while we're reconnecting a dropped stream.
  const inputDisabled = phase === Phase.STARTING || phase === Phase.PIPELINE || phase === Phase.QUESTIONS || isFailed || reconnecting;
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
        {onStartFresh && canStartFresh && (
          <button
            type="button"
            onClick={onStartFresh}
            title="Abandon this conversation and start a new one (the post/plan is kept)"
            className="ml-auto rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            ↺ Start fresh
          </button>
        )}
      </div>

      <ContentTodos todos={todos} />

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
            ) : msg.image ? (
              <ChatImageBubble key={i} image={msg.image} fullUrl={msg.fullUrl} caption={msg.caption} />
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

          {isAgentTyping && <TypingIndicator />}

          {phase === Phase.QUESTIONS && pendingQuestions?.length > 0 && (
            <ContentQuestions questions={pendingQuestions} onSubmit={onAnswerQuestions} disabled={false} />
          )}

          {reconnecting && !isFailed && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-600 dark:text-amber-400">
              <span className="inline-block size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
              Connection dropped — reconnecting…
            </div>
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
      </div>

      {/* Mobile pane bar — opens the right-side viewport as a bottom sheet on small screens */}
      {mobilePostBar}

      <ContentInput
        onSend={onSendMessage}
        disabled={inputDisabled}
        isStreaming={isStreaming}
        onStop={onStop}
      />
    </div>
  );
}
