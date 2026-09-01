"use client";

import { Search } from "lucide-react";
import { formatShortcut } from "@/lib/shortcuts";
import { useCommands } from "./CommandRegistry";

/**
 * The visible way in.
 *
 * A ⌘K palette nobody knows about is a feature only its author uses, so the
 * shortcut gets a button that states it. Collapses to just the icon when there
 * is no room for the hint.
 */
export default function CommandPaletteTrigger({ className = "" }) {
  const { setOpen } = useCommands();

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-keyshortcuts="Meta+K Control+K"
      className={`inline-flex items-center gap-2 rounded-full border border-border/70 bg-muted/40 px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${className}`}
    >
      <Search className="size-3.5 shrink-0" aria-hidden />
      <span className="hidden @md:inline">Search</span>
      <kbd className="hidden rounded border border-border bg-background px-1 py-0.5 text-[10px] @md:inline">
        {formatShortcut("mod+k")}
      </kbd>
      <span className="sr-only">Open the command palette</span>
    </button>
  );
}
