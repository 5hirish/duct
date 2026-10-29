"use client";

import { lazy, Suspense, useState } from "react";
import { Trans } from "@lingui/react/macro";
import oneDark from "react-syntax-highlighter/dist/esm/styles/prism/one-dark";

// Loaded on the first code block, not with the chat pane: most replies have
// none, and the highlighter plus its grammars outweighs the rest of the pane.
const HighlightedCode = lazy(() => import("./HighlightedCode"));

// The theme's own box, so the plain fallback and the highlighted block are
// the same size and only the token colours arrive late.
const PRE_STYLE = oneDark['pre[class*="language-"]'];

/**
 * Syntax-highlighted code block with language label and copy button.
 * Used by every agent chat's ChatBubble and ThinkingBlock — audit and content
 * carried identical copies of this file before it moved here.
 */
export function CodeBlock({ language, children, compact = false }) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");
  const customStyle = {
    margin: 0,
    borderRadius: 0,
    fontSize: compact ? "10px" : "12px",
    lineHeight: compact ? "1.5" : "1.6",
    padding: compact ? "10px 12px" : "14px 16px",
  };

  function handleCopy() {
    navigator.clipboard.writeText(code).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-border/50">
      {/* Header bar: language + copy button */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#21252b] border-b border-white/5">
        <span className="text-2xs font-mono text-white/40 uppercase tracking-widest select-none">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-2xs font-medium text-white/40 hover:text-white/80 transition-colors select-none"
        >
          {copied ? <Trans>✓ copied</Trans> : <Trans>copy</Trans>}
        </button>
      </div>
      <Suspense
        fallback={
          <pre style={{ ...PRE_STYLE, ...customStyle, whiteSpace: "pre-wrap" }}>
            <code>{code}</code>
          </pre>
        }
      >
        <HighlightedCode language={language} code={code} style={oneDark} customStyle={customStyle} />
      </Suspense>
    </div>
  );
}

/**
 * Resolve inline vs block code from the className react-markdown injects.
 * Returns null for inline so the caller can render its own inline style.
 */
export function resolveCode(className, children) {
  const language = /language-(\w+)/.exec(className || "")?.[1];
  const isBlock = Boolean(language) || String(children).includes("\n");
  return { language, isBlock };
}
