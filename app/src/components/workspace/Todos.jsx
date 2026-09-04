"use client";

import { useState } from "react";
import { Spinner } from "@/components/ui/spinner";

const STATUS = {
  completed:   { icon: "✓", cls: "text-green-500",           textCls: "line-through text-muted-foreground" },
  in_progress: { icon: null, cls: "",                        textCls: "text-foreground font-medium" },
  pending:     { icon: "○", cls: "text-muted-foreground/50", textCls: "text-muted-foreground" },
};

/**
 * Sticky progress strip above the transcript — the agent's own plan, from
 * TodoWrite. Hidden until the agent has written one. The shape rendered is
 * exactly what both harnesses emit ({content, status, activeForm?}); no
 * mapping layer should creep in between.
 */
export default function Todos({ todos }) {
  const [open, setOpen] = useState(true);

  if (!todos || todos.length === 0) return null;

  const completed = todos.filter((t) => t.status === "completed").length;
  const inProgress = todos.filter((t) => t.status === "in_progress").length;
  const total = todos.length;
  const pct = Math.round((completed / total) * 100);

  return (
    <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border/60">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Progress</span>
          <span className="text-xs tabular-nums text-muted-foreground">{completed}/{total}</span>
          {inProgress > 0 && <span className="text-xs text-blue-500 animate-pulse">working…</span>}
        </div>
        <div className="flex items-center gap-2">
          <div className="w-16 h-1 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-muted-foreground/60 text-xs" aria-hidden="true">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-3 space-y-1 max-h-48 overflow-y-auto">
          {todos.map((todo, i) => {
            const s = STATUS[todo.status] || STATUS.pending;
            const label = todo.status === "in_progress" && todo.activeForm ? todo.activeForm : todo.content;
            return (
              <div key={i} className="flex items-start gap-2 text-xs">
                {todo.status === "in_progress" ? (
                  <Spinner className="mt-0.5 size-2.5 text-blue-500" />
                ) : (
                  <span className={`shrink-0 mt-0.5 ${s.cls}`} aria-hidden="true">{s.icon}</span>
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
