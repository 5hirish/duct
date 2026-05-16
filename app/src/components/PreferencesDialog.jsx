"use client";

import { useState, useEffect } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  PREFS_DEFAULTS,
  ROLE_OPTIONS,
  loadPreferences,
  savePreferences,
} from "@/lib/userPreferences";

// ---------------------------------------------------------------------------
// Shared Dialog primitives (mirrors EngineDialog pattern)
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
          "fixed left-1/2 top-1/2 z-50 w-full max-w-xl -translate-x-1/2 -translate-y-1/2",
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
// Option card — used for communication style and detail level
// ---------------------------------------------------------------------------

function OptionCard({ value, selected, onSelect, label, description }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(value)}
      className={cn(
        "flex-1 rounded-xl border p-3 text-left transition-all",
        selected
          ? "border-primary bg-primary/8 ring-1 ring-primary/30"
          : "border-border hover:border-border/80 hover:bg-muted/40"
      )}
    >
      <span className="block text-sm font-medium leading-snug">{label}</span>
      <span className="block text-[11px] text-muted-foreground mt-0.5 leading-relaxed">{description}</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// PreferencesDialog
// ---------------------------------------------------------------------------

export default function PreferencesDialog({ children }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(PREFS_DEFAULTS);
  const [committed, setCommitted] = useState(PREFS_DEFAULTS);

  // Load from localStorage when dialog opens
  useEffect(() => {
    if (open) {
      const prefs = loadPreferences();
      setDraft(prefs);
      setCommitted(prefs);
    }
  }, [open]);

  const changed =
    draft.role !== committed.role ||
    draft.communication_style !== committed.communication_style ||
    draft.report_depth !== committed.report_depth ||
    draft.primary_outcome !== committed.primary_outcome;

  function handleApply() {
    savePreferences(draft);
    setCommitted(draft);
    setOpen(false);
  }

  function set(key, value) {
    setDraft(prev => ({ ...prev, [key]: value }));
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>{children}</DialogPrimitive.Trigger>

      <DialogContent>
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <DialogPrimitive.Title className="text-base font-semibold">
              Your Profile
            </DialogPrimitive.Title>
            <p className="text-xs text-muted-foreground mt-0.5">
              Duct uses this to personalise how results are communicated to you.
            </p>
          </div>
          <DialogPrimitive.Close className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors -mr-1 -mt-1">
            <span className="sr-only">Close</span>
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
            </svg>
          </DialogPrimitive.Close>
        </div>

        <div className="space-y-5">
          {/* Role */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              Role
            </label>
            <select
              value={draft.role}
              onChange={e => set("role", e.target.value)}
              className="w-full rounded-lg border border-input bg-background pl-3 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {ROLE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Communication style */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              Communication style
            </label>
            <div className="flex gap-2">
              <OptionCard
                value="executive"
                selected={draft.communication_style === "executive"}
                onSelect={v => set("communication_style", v)}
                label="Executive"
                description="Strategic summaries, business impact, dollar amounts"
              />
              <OptionCard
                value="practitioner"
                selected={draft.communication_style === "practitioner"}
                onSelect={v => set("communication_style", v)}
                label="Practitioner"
                description="Actionable, signal-driven specifics"
              />
              <OptionCard
                value="technical"
                selected={draft.communication_style === "technical"}
                onSelect={v => set("communication_style", v)}
                label="Technical"
                description="Deep detail, developer-friendly"
              />
            </div>
          </div>

          {/* Report depth */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              Level of detail
            </label>
            <div className="flex gap-2">
              <OptionCard
                value="summary"
                selected={draft.report_depth === "summary"}
                onSelect={v => set("report_depth", v)}
                label="Summary"
                description="Key points only"
              />
              <OptionCard
                value="balanced"
                selected={draft.report_depth === "balanced"}
                onSelect={v => set("report_depth", v)}
                label="Balanced"
                description="Full context + actions"
              />
              <OptionCard
                value="detailed"
                selected={draft.report_depth === "detailed"}
                onSelect={v => set("report_depth", v)}
                label="Detailed"
                description="All evidence & data"
              />
            </div>
          </div>

          {/* Primary outcome */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              What matters most? <span className="normal-case font-normal">(optional)</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: "revenue",    label: "Revenue & Growth" },
                { value: "efficiency", label: "Efficiency & Speed" },
                { value: "risk",       label: "Risk & Compliance" },
                { value: "quality",    label: "Quality & Standards" },
              ].map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("primary_outcome", draft.primary_outcome === opt.value ? "" : opt.value)}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm text-left transition-colors",
                    draft.primary_outcome === opt.value
                      ? "border-primary bg-primary/8 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground hover:border-border/80"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-border/60">
          <button
            type="button"
            onClick={() => setDraft(PREFS_DEFAULTS)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Reset to defaults
          </button>
          <div className="flex items-center gap-2">
            <DialogPrimitive.Close asChild>
              <Button variant="outline" size="sm">Cancel</Button>
            </DialogPrimitive.Close>
            <Button size="sm" onClick={handleApply} disabled={!changed}>
              Apply
            </Button>
          </div>
        </div>
      </DialogContent>
    </DialogPrimitive.Root>
  );
}
