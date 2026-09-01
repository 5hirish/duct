"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { formatShortcut, useShortcut } from "@/lib/shortcuts";
import { useCommands } from "./CommandRegistry";

/**
 * ⌘K palette — the keyboard route to anything the app can currently do.
 *
 * Deliberately built on the shared Dialog (portal, focus trap, Escape, scroll
 * lock) and on a plain filtered list rather than pulling in a combobox
 * library: the whole interaction is a text field, a list, and four keys.
 *
 * Matching is subsequence-based, so "cst" finds "Content Studio" — the thing
 * people actually expect from a palette — and scored so that a prefix match on
 * the label beats an incidental hit inside a keyword.
 */

/** Subsequence match with a score; null when it doesn't match at all. */
function score(query, command) {
  if (!query) return 0;
  const q = query.toLowerCase();
  const label = command.label.toLowerCase();

  if (label.startsWith(q)) return 100;
  if (label.includes(q)) return 80;

  const haystack = [label, command.group || "", ...(command.keywords || [])]
    .join(" ")
    .toLowerCase();
  if (haystack.includes(q)) return 60;

  // Subsequence: every character of the query, in order, anywhere in the label.
  let i = 0;
  for (const ch of label) {
    if (ch === q[i]) i += 1;
    if (i === q.length) return 40;
  }
  return null;
}

export default function CommandPalette() {
  const { commands, open, setOpen } = useCommands();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef(null);

  useShortcut("mod+k", () => setOpen((o) => !o), { allowInInput: true });

  const results = useMemo(() => {
    const scored = commands
      .map((command) => ({ command, s: score(query, command) }))
      .filter((r) => r.s !== null)
      .sort((a, b) => b.s - a.s);
    return scored.map((r) => r.command);
  }, [commands, query]);

  // Grouped for display, but the keyboard walks the flat list — so the index
  // the arrows move through and the item highlighted are always the same thing.
  const groups = useMemo(() => {
    const byGroup = new Map();
    results.forEach((command, index) => {
      const key = command.group || "Actions";
      if (!byGroup.has(key)) byGroup.set(key, []);
      byGroup.get(key).push({ command, index });
    });
    return [...byGroup.entries()];
  }, [results]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
    }
  }, [open]);

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(results.length - 1, 0)));
  }, [results.length]);

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function runCommand(command) {
    setOpen(false);
    // After the dialog has released focus, so a command that focuses something
    // is not immediately undone by the focus trap restoring.
    requestAnimationFrame(() => command.run());
  }

  function onKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((a) => (results.length ? (a + 1) % results.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((a) => (results.length ? (a - 1 + results.length) % results.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const command = results[active];
      if (command) runCommand(command);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        showCloseButton={false}
        className="top-[15%] max-w-xl translate-y-0 gap-0 overflow-hidden p-0"
        aria-label="Command palette"
      >
        <DialogTitle className="sr-only">Command palette</DialogTitle>

        <div className="flex items-center gap-2 border-b border-border/60 px-4">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search commands…"
            aria-label="Search commands"
            aria-activedescendant={results[active] ? `command-${results[active].id}` : undefined}
            className="w-full bg-transparent py-3.5 text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>

        <div ref={listRef} role="listbox" aria-label="Commands" className="max-h-80 overflow-y-auto py-1.5">
          {results.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
              No commands match “{query}”.
            </p>
          )}

          {groups.map(([groupName, entries]) => (
            <div key={groupName} className="px-1.5 pb-1">
              <p className="px-2.5 pt-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {groupName}
              </p>
              {entries.map(({ command, index }) => {
                const Icon = command.icon;
                const isActive = index === active;
                return (
                  <button
                    key={command.id}
                    id={`command-${command.id}`}
                    data-index={index}
                    role="option"
                    aria-selected={isActive}
                    type="button"
                    onMouseMove={() => setActive(index)}
                    onClick={() => runCommand(command)}
                    className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors ${
                      isActive ? "bg-accent text-accent-foreground" : "text-foreground"
                    }`}
                  >
                    {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
                    <span className="flex-1 truncate">{command.label}</span>
                    {command.shortcut ? (
                      <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {formatShortcut(command.shortcut)}
                      </kbd>
                    ) : null}
                    {isActive ? (
                      <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                    ) : null}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
          <span>↑↓ to move · ↵ to run · esc to close</span>
          <span>{results.length} command{results.length === 1 ? "" : "s"}</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
