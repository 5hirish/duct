"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { CodeBlock, resolveCode } from "./CodeBlock";

/**
 * Compact markdown renderer for dense, secondary surfaces — the reasoning
 * bubble and step-detail panels (reference deconstruction, etc.). Small, muted
 * text with explicit per-element styling: the app has NO @tailwindcss/typography
 * plugin, so `prose` is a no-op and headings/lists/bold render as plain blobs
 * unless every element is styled directly. For the larger chat-reply markdown
 * style, see ChatBubble in ContentChat.
 */
export default function CompactMarkdown({ children }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      components={{
        h1: ({ children }) => <p className="text-xs font-bold text-foreground/80 mt-3 mb-1 first:mt-0">{children}</p>,
        h2: ({ children }) => <p className="text-xs font-semibold text-foreground/75 mt-2.5 mb-1 first:mt-0">{children}</p>,
        h3: ({ children }) => <p className="text-[11px] font-semibold text-foreground/70 mt-2 mb-0.5 uppercase tracking-wide first:mt-0">{children}</p>,
        h4: ({ children }) => <p className="text-[11px] font-medium text-foreground/65 mt-1.5 mb-0.5 first:mt-0">{children}</p>,
        p: ({ children }) => <p className="text-[11px] text-muted-foreground leading-relaxed my-2 first:mt-0 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-4 my-2 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 my-2 space-y-1">{children}</ol>,
        li: ({ children }) => <li className="text-[11px] text-muted-foreground leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground/75">{children}</strong>,
        em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
        code({ className, children }) {
          const { language, isBlock } = resolveCode(className, children);
          if (isBlock) return <CodeBlock language={language} compact>{children}</CodeBlock>;
          return <code className="bg-background/70 border border-border/60 text-foreground/80 px-1 py-0.5 rounded text-[10px] font-mono">{children}</code>;
        },
        a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-foreground/70 underline underline-offset-2 hover:text-foreground/90">{children}</a>,
        blockquote: ({ children }) => <blockquote className="border-l-2 border-border/60 pl-3 my-1.5 italic text-muted-foreground/70">{children}</blockquote>,
        hr: () => <hr className="border-border/40 my-2" />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
