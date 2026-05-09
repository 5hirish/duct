"use client";

import { useState, useEffect, useCallback } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ENGINES, DEFAULT_ENGINE, ENGINE_STORAGE_KEY, getEngine } from "@/lib/engines";

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
// Engine row
// ---------------------------------------------------------------------------

function EngineRow({ engine, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(engine.key)}
      className={cn(
        "flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-colors",
        selected
          ? "border-primary/40 bg-primary/8 text-foreground"
          : "border-border/60 bg-transparent text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground"
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
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{engine.defaultModel} · {engine.description}</p>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// EngineDialog
// ---------------------------------------------------------------------------

export default function EngineDialog({ children }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(DEFAULT_ENGINE);
  const [committed, setCommitted] = useState(DEFAULT_ENGINE);

  // Read persisted engine on mount
  useEffect(() => {
    const stored = localStorage.getItem(ENGINE_STORAGE_KEY);
    if (stored) {
      setSelected(stored);
      setCommitted(stored);
    }
  }, []);

  // Reset draft to committed when opening
  const handleOpenChange = useCallback((val) => {
    if (val) setSelected(committed);
    setOpen(val);
  }, [committed]);

  function handleApply() {
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
          <h2 className="text-base font-semibold tracking-tight">Inference Engine</h2>
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
              onSelect={setSelected}
            />
          ))}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <DialogPrimitive.Close asChild>
            <Button variant="outline" size="sm">Cancel</Button>
          </DialogPrimitive.Close>
          <Button size="sm" onClick={handleApply} disabled={selected === committed}>
            Apply
          </Button>
        </div>
      </DialogContent>
    </DialogPrimitive.Root>
  );
}
