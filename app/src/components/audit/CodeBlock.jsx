"use client";

import { useState } from "react";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/cjs/styles/prism";
import js from "react-syntax-highlighter/dist/cjs/languages/prism/javascript";
import markup from "react-syntax-highlighter/dist/cjs/languages/prism/markup";
import json from "react-syntax-highlighter/dist/cjs/languages/prism/json";
import css from "react-syntax-highlighter/dist/cjs/languages/prism/css";
import bash from "react-syntax-highlighter/dist/cjs/languages/prism/bash";
import python from "react-syntax-highlighter/dist/cjs/languages/prism/python";
import typescript from "react-syntax-highlighter/dist/cjs/languages/prism/typescript";

SyntaxHighlighter.registerLanguage("javascript", js);
SyntaxHighlighter.registerLanguage("js", js);
SyntaxHighlighter.registerLanguage("jsx", js);
SyntaxHighlighter.registerLanguage("html", markup);
SyntaxHighlighter.registerLanguage("xml", markup);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("sh", bash);
SyntaxHighlighter.registerLanguage("shell", bash);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("py", python);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("ts", typescript);

/**
 * Syntax-highlighted code block with language label and copy button.
 * Used by both ChatBubble and ThinkingBlock.
 */
export function CodeBlock({ language, children, compact = false }) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");

  function handleCopy() {
    navigator.clipboard.writeText(code).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-border/50">
      {/* Header bar: language + copy button */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#21252b] border-b border-white/5">
        <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest select-none">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-[10px] font-medium text-white/40 hover:text-white/80 transition-colors select-none"
        >
          {copied ? "✓ copied" : "copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: compact ? "10px" : "12px",
          lineHeight: compact ? "1.5" : "1.6",
          padding: compact ? "10px 12px" : "14px 16px",
        }}
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
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
