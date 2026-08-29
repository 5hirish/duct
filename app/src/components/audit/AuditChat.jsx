"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";  // honor single newlines as line breaks (LLMs use them)
import AuditStepProgress from "./AuditStepProgress";
import AuditQuestions from "./AuditQuestions";
import AuditInput from "./AuditInput";
import AuditTodos from "./AuditTodos";
import { Brain } from "lucide-react";
import { Phase } from "./auditPhase";
import { CodeBlock, resolveCode } from "./CodeBlock";
import {
  approveChangeSet,
  applyChangeSet,
  rejectChangeSet,
  rollbackChangeSet,
} from "@/lib/executionApi";
import { createMemory } from "@/lib/memoryApi";
import { getActiveProject } from "@/lib/projects";

/** The quiet "Remembered: …" line under a turn that wrote project memory.
 * Deliberately understated — memory should feel like a side effect the user can
 * see and undo, not an announcement. Each entry links to its timeline row. */
function MemoryNote({ memories }) {
  const projectId = getActiveProject()?.id;
  if (!memories?.length) return null;
  return (
    <div className="my-1.5 flex flex-wrap items-center gap-1.5 px-1 text-xs text-muted-foreground">
      <Brain size={13} aria-hidden="true" />
      <span>Remembered:</span>
      {memories.map((m, i) => (
        <span key={m.id || i}>
          {projectId ? (
            <a
              href={`/project/${projectId}/memory?q=${encodeURIComponent(m.title || "")}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              {m.title}
            </a>
          ) : (
            m.title
          )}
          {i < memories.length - 1 ? "," : ""}
        </span>
      ))}
    </div>
  );
}

/** "Recalled N memories" — what this turn was primed with, listed on demand so
 * an answer can always be traced back to the facts behind it. */
function MemoryRecall({ memoryIds }) {
  const projectId = getActiveProject()?.id;
  if (!memoryIds?.length) return null;
  return (
    <details className="my-1.5 px-1 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none hover:text-foreground">
        <Brain size={13} className="mr-1 inline-block align-[-2px]" aria-hidden="true" />
        Recalled {memoryIds.length} {memoryIds.length === 1 ? "memory" : "memories"}
      </summary>
      <p className="mt-1 flex flex-wrap gap-1.5 font-mono text-[11px]">
        {memoryIds.map((id) => (
          <span key={id} className="rounded bg-muted/60 px-1.5 py-0.5">{id}</span>
        ))}
      </p>
      {projectId && (
        <a
          href={`/project/${projectId}/memory`}
          className="mt-1 inline-block underline underline-offset-2 hover:text-foreground"
        >
          Open the project timeline
        </a>
      )}
    </details>
  );
}

/** Compact chip for an artifact the agent just created/revised — opens the
 * artifact viewer. Industry "card-in-stream" convention. */
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

/** API change-set response → SSE-card shape, preserving per-change flags the
 * API rows don't carry (destructive comes only from the SSE card). */
function apiToCard(cs, prevCard) {
  const prevById = Object.fromEntries((prevCard?.changes || []).map((c) => [c.id, c]));
  return {
    change_set_id: cs.id,
    connector_type: cs.connector_type,
    account_id: cs.account_id,
    account_name: cs.account_name,
    title: cs.title,
    context: cs.context,
    status: cs.status,
    source: cs.source ?? prevCard?.source ?? "agent",
    applied_by: cs.applied_by ?? "",
    auto_apply_eligible: cs.auto_apply_eligible ?? prevCard?.auto_apply_eligible ?? false,
    changes: (cs.changes || []).map((c) => ({
      id: c.id,
      op_type: c.op_type,
      summary: c.summary || "",
      status: c.status || "",
      diff: c.preview?.diff || "",
      warnings: c.preview?.warnings || [],
      guardrail_violations: c.guardrail_violations || [],
      preview_error: c.preview?.error || "",
      destructive: prevById[c.id]?.destructive ?? false,
    })),
  };
}

const CHANGE_SET_STATUS_STYLES = {
  proposed: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  applied: "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-400",
  rejected: "bg-muted text-muted-foreground",
  rolled_back: "bg-muted text-muted-foreground",
};

/** Inline review card for a staged change set the agent proposed. Reversible
 * clean sets may arrive already auto-applied (assisted autonomy); everything
 * else waits here for Approve & apply. Destructive changes are flagged. */
function ChangeSetCard({ changeSet: initial }) {
  const [cs, setCs] = useState(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // A later SSE upsert (e.g. rollback via agent tool) replaces the card data.
  useEffect(() => setCs(initial), [initial]);

  if (!cs) return null;
  const autoApplied = cs.applied_by === "auto";
  const canReview = cs.status === "proposed";
  const canRollback = ["applied", "partial"].includes(cs.status);
  const hasDestructive = (cs.changes || []).some((c) => c.destructive);

  const run = async (label, fn) => {
    setBusy(label);
    setError("");
    try {
      const result = await fn();
      setCs((prev) => apiToCard(result, prev));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  };

  const onApprove = () =>
    run("approve", async () => {
      await approveChangeSet(cs.change_set_id);
      return applyChangeSet(cs.change_set_id, cs.connector_type);
    });
  const onReject = () => run("reject", () => rejectChangeSet(cs.change_set_id));
  const onRollback = () =>
    run("rollback", () => rollbackChangeSet(cs.change_set_id, cs.connector_type));

  return (
    <div className="my-2 rounded-lg border border-input bg-muted/20 max-w-md overflow-hidden">
      <div className="px-3 py-2 border-b border-border/60 flex items-start gap-2">
        <span aria-hidden="true" className="text-base leading-tight">⚡</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">{cs.title}</p>
          <p className="text-xs text-muted-foreground truncate">
            {cs.connector_type}
            {cs.account_name ? ` · ${cs.account_name}` : cs.account_id ? ` · ${cs.account_id}` : ""}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            CHANGE_SET_STATUS_STYLES[cs.status] || "bg-muted text-muted-foreground"
          }`}
        >
          {autoApplied && cs.status === "applied" ? "auto-applied" : cs.status.replace("_", " ")}
        </span>
      </div>

      {cs.context && (
        <p className="px-3 pt-2 text-xs text-muted-foreground leading-relaxed">{cs.context}</p>
      )}

      <ul className="px-3 py-2 space-y-1.5">
        {(cs.changes || []).map((c) => (
          <li key={c.id} className="text-xs leading-snug">
            <span className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">
                {c.status === "applied" ? "✓" : c.status === "blocked" || c.preview_error ? "✕" : c.status === "rolled_back" ? "↺" : "•"}
              </span>
              <span className="min-w-0">
                <span className="text-foreground/90">{c.diff || c.summary || c.op_type}</span>
                {c.destructive && (
                  <span className="ml-1.5 rounded bg-red-100 dark:bg-red-950/50 px-1 py-px text-[10px] font-medium text-red-700 dark:text-red-400">
                    destructive
                  </span>
                )}
                {(c.warnings || []).map((w, j) => (
                  <span key={j} className="block text-amber-700 dark:text-amber-400">⚠ {w}</span>
                ))}
                {(c.guardrail_violations || []).map((v, j) => (
                  <span key={j} className="block text-red-700 dark:text-red-400">⛔ {v}</span>
                ))}
                {c.preview_error && (
                  <span className="block text-red-700 dark:text-red-400">Preview failed: {c.preview_error}</span>
                )}
              </span>
            </span>
          </li>
        ))}
      </ul>

      {error && (
        <p className="px-3 pb-1 text-xs text-destructive break-words">{error}</p>
      )}

      {(canReview || canRollback) && (
        <div className="px-3 pb-2.5 flex items-center gap-2">
          {canReview && (
            <>
              <button
                onClick={onApprove}
                disabled={!!busy}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                  hasDestructive
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-primary text-primary-foreground hover:bg-primary/90"
                }`}
              >
                {busy === "approve" ? "Applying…" : hasDestructive ? "Approve & apply (destructive)" : "Approve & apply"}
              </button>
              <button
                onClick={onReject}
                disabled={!!busy}
                className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/60 transition-colors disabled:opacity-50"
              >
                {busy === "reject" ? "Rejecting…" : "Reject"}
              </button>
            </>
          )}
          {canRollback && (
            <button
              onClick={onRollback}
              disabled={!!busy}
              className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/60 transition-colors disabled:opacity-50"
            >
              {busy === "rollback" ? "Rolling back…" : "↺ Roll back"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

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
        {text && !streaming && <RememberThis text={text} />}
      </div>
    </div>
  );
}

/** "Remember this" under a finished agent turn — or under a selection inside it.
 *
 * The agent decides what to remember on its own; this is the other half, where
 * the user overrules that judgement. What it writes is a user statement, so it
 * lands confirmed rather than as a proposal awaiting its own approval. */
function RememberThis({ text }) {
  const [state, setState] = useState("idle"); // idle | saving | saved | error
  const projectId = getActiveProject()?.id;
  if (!projectId) return null;

  async function save() {
    // A selection inside this turn beats the whole turn — the user pointing at
    // one sentence is a much better title than 400 words of analysis.
    const selected = String(window.getSelection?.() || "").trim();
    const title = (selected || text).replace(/\s+/g, " ").trim().slice(0, 200);
    if (!title) return;
    setState("saving");
    try {
      await createMemory({
        projectId,
        kind: "conclusion",
        title,
        source_refs: [{ source: "user", from: "chat" }],
      });
      setState("saved");
    } catch {
      setState("error");
    }
  }

  return (
    <button
      type="button"
      onClick={save}
      disabled={state === "saving" || state === "saved"}
      className="mt-1 ml-1 text-[11px] text-muted-foreground hover:text-foreground disabled:hover:text-muted-foreground"
    >
      {state === "saved" ? (
        <a href={`/project/${projectId}/memory`} className="underline underline-offset-2">
          Remembered — open the timeline
        </a>
      ) : state === "error" ? (
        "Could not remember that"
      ) : state === "saving" ? (
        "Remembering…"
      ) : (
        "+ Remember this"
      )}
    </button>
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
          ) : msg.role === "artifact_card" ? (
            <ArtifactCard key={i} artifact={msg.artifact} />
          ) : msg.role === "change_set_card" ? (
            <ChangeSetCard key={msg.changeSet?.change_set_id || i} changeSet={msg.changeSet} />
          ) : msg.role === "memory_note" ? (
            <MemoryNote key={i} memories={msg.memories} />
          ) : msg.role === "memory_recall" ? (
            <MemoryRecall key={i} memoryIds={msg.memoryIds} />
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
