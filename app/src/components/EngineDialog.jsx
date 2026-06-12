"use client";

import { useState, useEffect, useCallback } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ENGINES, DEFAULT_ENGINE, ENGINE_STORAGE_KEY, ENGINE_STATUS } from "@/lib/engines";
import { fetchEngineStatus } from "@/lib/api";

// ---------------------------------------------------------------------------
// Minimal Dialog primitives (radix-ui Dialog, not AlertDialog)
// ---------------------------------------------------------------------------

function DialogOverlay({ className, ...props }) {
  return (
    <DialogPrimitive.Overlay
      className={cn(
        "fixed inset-0 z-50 bg-foreground/15 backdrop-blur-[2px]",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  );
}

function DialogContent({ className, children, ...props }) {
  return (
    <DialogPrimitive.Portal>
      <DialogOverlay />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2",
          "rounded-3xl border border-border bg-card p-6 text-card-foreground shadow-lg ring-1 ring-foreground/5",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          className
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

// ---------------------------------------------------------------------------
// Status pill
// ---------------------------------------------------------------------------

const STATUS_PILL = {
  [ENGINE_STATUS.ACTIVE]: { label: "Active", className: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400" },
  [ENGINE_STATUS.NEEDS_AUTH]: { label: "Needs auth", className: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  [ENGINE_STATUS.INACTIVE]: { label: "Inactive", className: "bg-muted text-muted-foreground" },
};

function StatusPill({ status }) {
  const pill = STATUS_PILL[status];
  if (!pill) return null;
  return (
    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide", pill.className)}>
      {pill.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Authentication help (shown for needs_auth engines)
// ---------------------------------------------------------------------------

function AuthHelp({ detail }) {
  return (
    <div className="mt-1.5 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 text-xs text-muted-foreground">
      <p className="font-medium text-foreground">Authenticate Claude</p>
      <p className="mt-1">
        {detail ||
          "Set ANTHROPIC_API_KEY (from the Claude Console) for this engine."}
      </p>
      <ol className="mt-2 list-decimal space-y-1 pl-4">
        <li>
          Recommended: create a key in the{" "}
          <a
            href="https://platform.claude.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground underline underline-offset-2"
          >
            Claude Console
          </a>{" "}
          and set <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">ANTHROPIC_API_KEY</code>.
        </li>
        <li>
          Local / self-hosted: run{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">claude setup-token</code> and set{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">CLAUDE_CODE_OAUTH_TOKEN</code>.
        </li>
      </ol>
      <a
        href="https://code.claude.com/docs/en/authentication"
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-block text-foreground underline underline-offset-2"
      >
        Authentication docs →
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Engine row
// ---------------------------------------------------------------------------

function EngineRow({ engine, selected, status, disabled, onSelect, helpOpen, onToggleHelp }) {
  const statusKey = status?.status;
  const needsAuth = statusKey === ENGINE_STATUS.NEEDS_AUTH;

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && onSelect(engine.key)}
        className={cn(
          "flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-colors",
          selected
            ? "border-primary/40 bg-primary/8 text-foreground"
            : "border-border/60 bg-transparent text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground",
          disabled && "cursor-not-allowed opacity-55 hover:border-border/60 hover:bg-transparent"
        )}
      >
        {/* Radio indicator */}
        <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border border-current">
          {selected && <span className="size-2 rounded-full bg-primary" />}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wider",
                selected ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
              )}
            >
              {engine.badge}
            </span>
            <span className="text-sm font-medium text-foreground">{engine.label}</span>
            <span className="ml-auto">
              <StatusPill status={statusKey} />
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{engine.defaultModel} · {engine.description}</p>
        </div>
      </button>

      {needsAuth && (
        <div className="px-1">
          <button
            type="button"
            onClick={() => onToggleHelp(engine.key)}
            className="mt-1 text-xs font-medium text-amber-600 underline underline-offset-2 hover:text-amber-700 dark:text-amber-400"
          >
            {helpOpen ? "Hide setup" : "How to authenticate"}
          </button>
          {helpOpen && <AuthHelp detail={status?.detail} />}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EngineDialog
// ---------------------------------------------------------------------------

export default function EngineDialog({ children }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(DEFAULT_ENGINE);
  const [committed, setCommitted] = useState(DEFAULT_ENGINE);
  const [statuses, setStatuses] = useState({});
  const [helpFor, setHelpFor] = useState(null);

  // Read persisted engine on mount
  useEffect(() => {
    const stored = localStorage.getItem(ENGINE_STORAGE_KEY);
    if (stored) {
      setSelected(stored);
      setCommitted(stored);
    }
  }, []);

  // Treat an engine as selectable when active, or when its status is unknown
  // (status not yet loaded / backend unreachable) so the picker stays usable.
  const isActive = useCallback(
    (key) => {
      const s = statuses[key];
      return !s || s.status === ENGINE_STATUS.ACTIVE;
    },
    [statuses]
  );

  // Reset draft to committed when opening, and refresh engine availability.
  const handleOpenChange = useCallback((val) => {
    if (val) {
      setSelected(committed);
      setHelpFor(null);
      fetchEngineStatus().then(setStatuses);
    }
    setOpen(val);
  }, [committed]);

  function handleApply() {
    if (!isActive(selected)) return;
    localStorage.setItem(ENGINE_STORAGE_KEY, selected);
    setCommitted(selected);
    // Notify other components (generate page) listening for storage changes
    window.dispatchEvent(new StorageEvent("storage", {
      key: ENGINE_STORAGE_KEY,
      newValue: selected,
      storageArea: localStorage,
    }));
    setOpen(false);
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Trigger asChild>{children}</DialogPrimitive.Trigger>
      <DialogContent>
        <div className="mb-4 flex items-center justify-between">
          <DialogPrimitive.Title className="text-base font-semibold tracking-tight">Inference Engine</DialogPrimitive.Title>
          <DialogPrimitive.Close asChild>
            <button
              className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Close"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M1 1l12 12M13 1L1 13" />
              </svg>
            </button>
          </DialogPrimitive.Close>
        </div>

        <div className="flex flex-col gap-2">
          {ENGINES.map((engine) => (
            <EngineRow
              key={engine.key}
              engine={engine}
              selected={selected === engine.key}
              status={statuses[engine.key]}
              disabled={!isActive(engine.key)}
              onSelect={setSelected}
              helpOpen={helpFor === engine.key}
              onToggleHelp={(key) => setHelpFor((cur) => (cur === key ? null : key))}
            />
          ))}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <DialogPrimitive.Close asChild>
            <Button variant="outline" size="sm">Cancel</Button>
          </DialogPrimitive.Close>
          <Button size="sm" onClick={handleApply} disabled={selected === committed || !isActive(selected)}>
            Apply
          </Button>
        </div>
      </DialogContent>
    </DialogPrimitive.Root>
  );
}
