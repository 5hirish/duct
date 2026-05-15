"use client";

import { useState } from "react";

const STATUS = {
  completed: {
    icon: "✓",
    cls: "text-green-500",
    textCls: "line-through text-muted-foreground",
  },
  in_progress: {
    icon: null, // rendered as CSS spinner below
    cls: "",
    textCls: "text-foreground font-medium",
  },
  pending: {
    icon: "○",
    cls: "text-muted-foreground/50",
    textCls: "text-muted-foreground",
  },
};

export default function AuditTodos({ todos }) {
  const [open, setOpen] = useState(true);

  if (!todos || todos.length === 0) return null;

  const completed = todos.filter(t => t.status === "completed").length;
  const inProgress = todos.filter(t => t.status === "in_progress").length;
  const total = todos.length;
  const pct = Math.round((completed / total) * 100);

  return (
    <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border/60">
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Progress
          </span>
          <span className="text-xs tabular-nums text-muted-foreground">
            {completed}/{total}
          </span>
          {inProgress > 0 && (
            <span className="text-xs text-blue-500 animate-pulse">
              working…
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Mini progress bar */}
          <div className="w-16 h-1 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-muted-foreground/60 text-xs">
            {open ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {/* Expandable list */}
      {open && (
        <div className="px-4 pb-3 space-y-1 max-h-48 overflow-y-auto">
          {todos.map((todo, i) => {
            const s = STATUS[todo.status] || STATUS.pending;
            const label =
              todo.status === "in_progress" && todo.activeForm
                ? todo.activeForm
                : todo.content;
            return (
              <div key={i} className="flex items-start gap-2 text-xs">
                {todo.status === "in_progress" ? (
                  <span className="inline-block size-2.5 shrink-0 mt-0.5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                ) : (
                  <span className={`shrink-0 mt-0.5 ${s.cls}`}>{s.icon}</span>
                )}
                <span className={s.textCls}>{label}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
