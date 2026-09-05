"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Rich, readable markdown renderer for content-format spec docs.
 *
 * Unlike the compact chat renderer (workspace/ChatMarkdown), this is tuned for
 * long-form reading: full-size headings, GFM tables with proper borders,
 * code blocks, and blockquote call-outs. Used by the format detail view
 * and the live editor preview.
 */
export default function MarkdownSpec({ children, className = "" }) {
  return (
    <div className={`markdown-spec text-sm leading-relaxed text-foreground/90 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-semibold tracking-tight text-foreground mt-8 mb-3 first:mt-0 pb-2 border-b border-border/60">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold text-foreground mt-7 mb-2 flex items-center gap-2">
              <span className="h-3.5 w-1 rounded-full bg-primary/70" />
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-foreground/90 mt-5 mb-1.5">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mt-4 mb-1">{children}</h4>
          ),
          p: ({ children }) => <p className="my-2.5 text-foreground/80">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-5 my-2.5 space-y-1 marker:text-muted-foreground/50">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 my-2.5 space-y-1 marker:text-muted-foreground/50">{children}</ol>,
          li: ({ children }) => <li className="text-foreground/80 leading-relaxed">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          em: ({ children }) => <em className="text-foreground/70">{children}</em>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">
              {children}
            </a>
          ),
          hr: () => <hr className="my-6 border-border/50" />,
          blockquote: ({ children }) => (
            <blockquote className="my-3 rounded-r-md border-l-2 border-primary/50 bg-muted/40 px-4 py-2 text-foreground/75 [&>p]:my-1">
              {children}
            </blockquote>
          ),
          code: ({ inline, className, children }) => {
            const isBlock = inline === false || /\n/.test(String(children));
            if (isBlock) {
              return (
                <code className="block whitespace-pre-wrap break-words font-mono text-xs text-foreground/85">
                  {children}
                </code>
              );
            }
            return (
              <code className="font-mono text-[0.8em] bg-muted border border-border/60 text-foreground/85 px-1.5 py-0.5 rounded">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="my-3 overflow-x-auto rounded-lg border border-border/60 bg-muted/50 p-3.5">{children}</pre>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg border border-border/60">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-muted/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-border/60 px-3 py-2 text-left font-semibold text-foreground/90 align-top">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/40 px-3 py-2 text-foreground/75 align-top [&:not(:last-child)]:border-r [&:not(:last-child)]:border-border/30">
              {children}
            </td>
          ),
        }}
      >
        {children || ""}
      </ReactMarkdown>
    </div>
  );
}
