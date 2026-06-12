"use client";

import { useRef, useState } from "react";
import { MessageSquare, PanelRight } from "lucide-react";

/**
 * SplitWorkspace — the shared chat-left / viewport-right shell for every agent
 * UI (content, audit, …). It owns ONLY layout + responsiveness so those fixes
 * live in one place:
 *   - desktop (md+): a draggable divider + split ratio, persisted per `storageKey`
 *   - mobile (<md): a pure CSS-driven pane TOGGLE — one pane at a time, switched
 *     by a built-in segmented control. No overlay/sheet, no portals, no extra
 *     mounts; `right` renders exactly once and is shown/hidden via classes.
 *
 * Everything agent-specific (streaming, chat, the viewport) stays in the
 * caller — just pass `left` / `right` as plain nodes. No render-props, no
 * triggers to wire: the responsive behavior is fully self-contained here.
 *
 * Props:
 *   - left, right: ReactNode — the two panes
 *   - banner?: ReactNode — optional full-width bar above the split
 *   - storageKey: string — localStorage key for the split ratio
 *   - initialSplit?: number — default left width % (clamped 20–80)
 *   - leftLabel?, rightLabel?: string — mobile toggle labels
 *   - rightStatus?: "idle" | "busy" | "ready" — badges the right tab when the
 *     user is on the left pane (a dot when the viewport has something to see)
 */
export default function SplitWorkspace({
  left,
  right,
  banner = null,
  storageKey = "split_w",
  initialSplit = 50,
  leftLabel = "Chat",
  rightLabel = "Preview",
  rightStatus = "idle",
}) {
  const [leftWidth, setLeftWidth] = useState(() => {
    if (typeof window !== "undefined") {
      const v = Number(localStorage.getItem(storageKey) || initialSplit);
      return Number.isFinite(v) ? Math.min(80, Math.max(20, v)) : initialSplit;
    }
    return initialSplit;
  });
  const [mobilePane, setMobilePane] = useState("left"); // "left" | "right"
  const dragging = useRef(false);
  const containerRef = useRef(null);

  function onMouseDownDivider(e) {
    e.preventDefault();
    dragging.current = true;
    function onMove(ev) {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = Math.min(80, Math.max(20, ((ev.clientX - rect.left) / rect.width) * 100));
      setLeftWidth(pct);
      try { localStorage.setItem(storageKey, String(pct)); } catch { /* ignore */ }
    }
    function onUp() {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      {banner}

      {/* Mobile pane toggle — desktop shows both panes so this is hidden there */}
      <div className="flex shrink-0 items-center gap-1 border-b border-border/60 bg-card p-1.5 md:hidden">
        <PaneTab active={mobilePane === "left"} onClick={() => setMobilePane("left")} icon={MessageSquare} label={leftLabel} />
        <PaneTab active={mobilePane === "right"} onClick={() => setMobilePane("right")} icon={PanelRight} label={rightLabel} status={rightStatus} />
      </div>

      <div
        ref={containerRef}
        className="flex min-h-0 w-full flex-1 overflow-hidden"
        style={{ "--split": `${leftWidth}%` }}
      >
        {/* Left pane — toggled on mobile, split on md+ */}
        <div className={`${mobilePane === "left" ? "flex" : "hidden"} w-full flex-col overflow-hidden border-r border-border/60 md:flex md:w-[var(--split)] md:min-w-[280px]`}>
          {left}
        </div>

        {/* Divider — desktop only */}
        <div
          onMouseDown={onMouseDownDivider}
          title="Drag to resize"
          className="group hidden w-3 shrink-0 cursor-col-resize select-none items-center justify-center md:flex"
        >
          <div className="h-full w-px bg-border/60 transition-colors group-hover:bg-primary/30" />
        </div>

        {/* Right pane — toggled on mobile, split on md+. Single mount. */}
        <div className={`${mobilePane === "right" ? "flex" : "hidden"} min-w-0 flex-1 flex-col overflow-hidden md:flex md:min-w-[280px]`}>
          {right}
        </div>
      </div>
    </div>
  );
}

function PaneTab({ active, onClick, icon: Icon, label, status }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted/50"
      }`}
    >
      <Icon className="size-3.5" />
      {label}
      {!active && status === "ready" && (
        <span className="absolute right-2 top-1.5 size-1.5 rounded-full bg-primary" aria-hidden="true" />
      )}
      {!active && status === "busy" && (
        <span className="absolute right-2 top-1.5 size-1.5 animate-pulse rounded-full bg-amber-500" aria-hidden="true" />
      )}
    </button>
  );
}
