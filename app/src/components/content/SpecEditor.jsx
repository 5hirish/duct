"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

// The visual editor is the one heavy dependency in Content Studio (MDXEditor
// and Lexical, about half a megabyte gzipped). It loads only when a format
// editor opens, never with the page, and never on the server: Lexical needs
// a document to mount into.
const SpecEditorInner = dynamic(() => import("./SpecEditorInner"), {
  ssr: false,
  loading: () => (
    <div className="rounded-md border border-border/70 bg-background p-3">
      <Skeleton className="mb-3 h-8 w-full" />
      <Skeleton className="mb-2 h-4 w-2/3" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  ),
});

/**
 * A spec document editor that needs no Markdown: headings, lists, tables,
 * quotes and links from a toolbar, Markdown kept underneath so the agent
 * reads what it always read. `value` is the Markdown string; `onChange`
 * receives the new one. A document the visual editor cannot represent falls
 * back to a plain text box rather than losing a line of it.
 */
export default function SpecEditor({ value, onChange, placeholder, className = "" }) {
  return (
    <SpecEditorInner
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className={className}
    />
  );
}
