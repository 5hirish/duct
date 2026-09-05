"use client";

import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks"; // honor single newlines as line breaks (LLMs use them)
import { CodeBlock, resolveCode } from "./CodeBlock";
import { healTail, splitSettled } from "../../lib/markdownStream";

// Explicit per-element styling — the app has NO @tailwindcss/typography plugin,
// so `prose` classes are no-ops and Tailwind's preflight strips heading sizes,
// list bullets and paragraph margins. Style every element directly so markdown
// renders, not blobs. Two maps: the assistant bubble at reading size, and the
// reasoning block a notch smaller and quieter.

const ASSISTANT_COMPONENTS = {
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
  code: ({ className, children }) => {
    const { language, isBlock } = resolveCode(className, children);
    if (isBlock) return <CodeBlock language={language}>{children}</CodeBlock>;
    return (
      <code className="bg-primary/10 text-primary dark:bg-primary/20 px-1.5 py-0.5 rounded text-[0.8em] font-mono before:content-none after:content-none">
        {children}
      </code>
    );
  },
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:no-underline">
      {children}
    </a>
  ),
  table: ({ children }) => <div className="overflow-x-auto my-3"><table className="border-collapse w-full text-sm">{children}</table></div>,
  th: ({ children }) => <th className="border border-border px-3 py-1.5 font-semibold text-left bg-muted/50">{children}</th>,
  td: ({ children }) => <td className="border border-border px-3 py-1.5">{children}</td>,
  blockquote: ({ children }) => <blockquote className="border-l-4 border-border pl-4 my-3 text-muted-foreground italic">{children}</blockquote>,
};

const THINKING_COMPONENTS = {
  h1: ({ children }) => <p className="text-xs font-bold text-foreground/80 mt-3 mb-1">{children}</p>,
  h2: ({ children }) => <p className="text-xs font-semibold text-foreground/75 mt-2.5 mb-1">{children}</p>,
  h3: ({ children }) => <p className="text-[11px] font-semibold text-foreground/70 mt-2 mb-0.5 uppercase tracking-wide">{children}</p>,
  h4: ({ children }) => <p className="text-[11px] font-medium text-foreground/65 mt-1.5 mb-0.5">{children}</p>,
  p: ({ children }) => <p className="text-[11px] text-muted-foreground leading-relaxed my-2">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-4 my-1.5 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-4 my-1.5 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="text-[11px] text-muted-foreground leading-relaxed">{children}</li>,
  code: ({ className, children }) => {
    const { language, isBlock } = resolveCode(className, children);
    if (isBlock) return <CodeBlock language={language} compact>{children}</CodeBlock>;
    return <code className="text-[10px] not-italic font-mono bg-background/70 border border-border/60 text-foreground/80 px-1 py-0.5 rounded">{children}</code>;
  },
  strong: ({ children }) => <strong className="font-semibold not-italic text-foreground/75">{children}</strong>,
  em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
  a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-foreground/70 underline underline-offset-2 not-italic hover:text-foreground/90">{children}</a>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-border/60 pl-3 my-1.5 italic text-muted-foreground/70">{children}</blockquote>,
  table: ({ children }) => <table className="border-collapse my-1.5 w-full text-[10px]">{children}</table>,
  th: ({ children }) => <th className="border border-border/60 px-2 py-0.5 font-semibold text-left not-italic bg-muted/20">{children}</th>,
  td: ({ children }) => <td className="border border-border/60 px-2 py-0.5">{children}</td>,
  hr: () => <hr className="border-border/40 my-2" />,
};

const PLUGINS = [remarkGfm, remarkBreaks];

// Memoised on its source: the settled part of a streaming reply is parsed
// once per closed block, not once per token.
const Settled = memo(function Settled({ source }) {
  return (
    <ReactMarkdown remarkPlugins={PLUGINS} components={ASSISTANT_COMPONENTS}>
      {source}
    </ReactMarkdown>
  );
});

/**
 * An assistant turn's markdown, at reading size.
 *
 * While `streaming`, the text is split at its last block boundary: what is
 * settled renders once and stays put, and only the tail re-renders per delta,
 * healed so an unfinished `**` or fence or table row reads as prose rather
 * than as markup mid-flight. That is what stops a table reflowing its columns
 * and a list renumbering as the reply grows. Once the turn ends the whole
 * reply is parsed in one go, so nothing the split got wrong survives it.
 */
export function AssistantMarkdown({ source, streaming = false }) {
  const parts = useMemo(() => (streaming ? splitSettled(source) : null), [source, streaming]);
  if (!parts) {
    return (
      <ReactMarkdown remarkPlugins={PLUGINS} components={ASSISTANT_COMPONENTS}>
        {source}
      </ReactMarkdown>
    );
  }
  return (
    <>
      {parts.settled && <Settled source={parts.settled} />}
      {parts.tail && (
        <ReactMarkdown remarkPlugins={PLUGINS} components={ASSISTANT_COMPONENTS}>
          {healTail(parts.tail)}
        </ReactMarkdown>
      )}
    </>
  );
}

/** Extended-thinking markdown: smaller, quieter, collapsible by the caller. */
export function ThinkingMarkdown({ source }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={THINKING_COMPONENTS}>
      {source}
    </ReactMarkdown>
  );
}
