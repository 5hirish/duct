"use client";

import { useState, useEffect } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";
import {
  AGENT_TYPES,
  DEFAULT_AGENT_TYPE,
  AGENT_TYPE_STORAGE_KEY,
} from "@/lib/engines";

// ---------------------------------------------------------------------------
// Left-side drawer using Dialog primitive
// ---------------------------------------------------------------------------

function DrawerOverlay({ className, ...props }) {
  return (
    <DialogPrimitive.Overlay
      className={cn(
        "fixed inset-0 z-40 bg-foreground/10 backdrop-blur-[1px]",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  );
}

function DrawerContent({ className, children, ...props }) {
  return (
    <DialogPrimitive.Portal>
      <DrawerOverlay />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-0 top-0 z-40 h-full w-64 border-r border-border bg-card shadow-xl",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
          "duration-200 ease-out",
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
// Agent type card
// ---------------------------------------------------------------------------

function AgentTypeRow({ agent, active }) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-2xl px-3 py-2.5 transition-colors",
        active
          ? "bg-primary/10 text-foreground"
          : agent.available
          ? "text-muted-foreground hover:bg-muted/50 hover:text-foreground cursor-pointer"
          : "opacity-40 cursor-not-allowed"
      )}
    >
      <span className="mt-0.5 text-base leading-none">{agent.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-medium", active && "text-primary")}>{agent.label}</span>
          {!agent.available && (
            <span className="rounded-full bg-muted px-1.5 py-px text-[10px] text-muted-foreground">
              Soon
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground leading-snug">{agent.description}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AgentDrawer
// ---------------------------------------------------------------------------

export default function AgentDrawer({ children }) {
  const [open, setOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(DEFAULT_AGENT_TYPE);

  useEffect(() => {
    const stored = localStorage.getItem(AGENT_TYPE_STORAGE_KEY);
    if (stored) setActiveAgent(stored);
  }, []);

  function handleSelectAgent(key) {
    const agent = AGENT_TYPES.find((a) => a.key === key);
    if (!agent?.available) return;
    localStorage.setItem(AGENT_TYPE_STORAGE_KEY, key);
    setActiveAgent(key);
    setOpen(false);
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>{children}</DialogPrimitive.Trigger>
      <DrawerContent aria-label="Agent selector">
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold tracking-tight">Agents</span>
            <DialogPrimitive.Close asChild>
              <button
                className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Close"
              >
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M1 1l12 12M13 1L1 13" />
                </svg>
              </button>
            </DialogPrimitive.Close>
          </div>

          {/* Agent list */}
          <div className="flex-1 overflow-y-auto px-2 py-3">
            <div className="flex flex-col gap-0.5">
              {AGENT_TYPES.map((agent) => (
                <div
                  key={agent.key}
                  onClick={() => handleSelectAgent(agent.key)}
                >
                  <AgentTypeRow agent={agent} active={activeAgent === agent.key} />
                </div>
              ))}
            </div>
          </div>

          {/* Handoff mode — reserved, coming soon */}
          <div className="border-t border-border px-4 py-3">
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-widest text-muted-foreground/60">
              Handoff Mode
            </p>
            <div
              className="flex items-center gap-2 opacity-40"
              title="Human-in-the-loop agent handoffs — coming soon"
            >
              <button
                disabled
                className="rounded-full border border-border bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
              >
                Manual
              </button>
              <button
                disabled
                className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
              >
                Auto
              </button>
            </div>
            <p className="mt-1 text-[10px] text-muted-foreground/50">
              Cross-agent invocations — coming soon
            </p>
          </div>
        </div>
      </DrawerContent>
    </DialogPrimitive.Root>
  );
}
