"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquare, PanelRight } from "lucide-react";

/**
 * SplitWorkspace — the shared chat-left / viewport-right shell for every agent
 * UI (content, audit, insights). It owns ONLY layout + responsiveness so those
 * fixes live in one place:
 *   - desktop (md+): a draggable divider + split ratio, persisted per `storageKey`
 *   - mobile (<md): a pure CSS-driven pane TOGGLE — one pane at a time, switched
 *     by a built-in segmented control. No overlay/sheet, no portals, no extra
 *     mounts; `right` renders exactly once and is shown/hidden via classes.
 *
 * Everything agent-specific (streaming, chat, the viewport) stays in the
 * caller — just pass `left` / `right` as plain nodes. No render-props, no
 * triggers to wire: the responsive behavior is fully self-contained here.
 *
 * Three things here exist specifically because this is a desktop app:
 *
 *  1. POINTER EVENTS + POINTER CAPTURE, not mouse events. Every consumer of
 *     this shell renders an <iframe> in the right pane (the audit report, the
 *     insights report, the slide preview). With window-level mousemove, the
 *     drag dies the instant the cursor crosses into the iframe, because the
 *     iframe's document — a separate event target — swallows the move events.
 *     setPointerCapture routes them back to the handle regardless of what is
 *     underneath, and pointer events cover mouse, trackpad, pen and touch in
 *     one path.
 *  2. KEYBOARD RESIZE + role="separator". A pane divider a keyboard user
 *     cannot move is a dead control on the platform where keyboards are the
 *     primary input. Follows the WAI-ARIA window splitter pattern.
 *  3. BOTH PANES ARE CONTAINERS. They are user-resizable, so a child's width
 *     has no fixed relation to the viewport: at one window size the right pane
 *     can be 280px or 1400px, and `md:` answers about the wrong box. Children
 *     use `@`-variants (`@2xl:grid-cols-3`) and get the pane's real width.
 *
 *     This is declared per REGION — here, and on `.app-main`/`.app-main-wide`
 *     for ordinary pages — rather than per component, so the same component is
 *     correct in a pane and on a page without knowing where it is.
 *
 *     It requires that no descendant relies on `position: fixed` escaping to
 *     the viewport, because `container-type` implies `contain: layout`, which
 *     makes this element their containing block. Three overlays here used to
 *     break that rule; they now go through the portalled Radix dialog
 *     (ui/dialog, ui/lightbox), which renders at <body> and is unaffected.
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

const MIN_SPLIT = 20;
const MAX_SPLIT = 80;
const KEY_STEP = 2;
const KEY_STEP_LARGE = 10;

const clampSplit = (value) => Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, value));

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
  // Starts at the prop and adopts the stored ratio in an effect rather than in
  // the initializer: reading localStorage during the first render makes the
  // client's markup disagree with the prerendered HTML.
  const [leftWidth, setLeftWidth] = useState(clampSplit(initialSplit));
  const [mobilePane, setMobilePane] = useState("left"); // "left" | "right"
  const containerRef = useRef(null);
  const collapsedFrom = useRef(null); // where Enter should restore to

  useEffect(() => {
    try {
      const stored = Number(localStorage.getItem(storageKey));
      if (Number.isFinite(stored) && stored > 0) setLeftWidth(clampSplit(stored));
    } catch {
      // storage unavailable (private mode, embedded webview) — keep the default
    }
  }, [storageKey]);

  const commit = useCallback(
    (pct) => {
      const next = clampSplit(pct);
      setLeftWidth(next);
      try {
        localStorage.setItem(storageKey, String(next));
      } catch {
        // ignore storage write errors
      }
      return next;
    },
    [storageKey]
  );

  const pctFromClientX = useCallback((clientX) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || !rect.width) return null;
    return ((clientX - rect.left) / rect.width) * 100;
  }, []);

  function onPointerDown(e) {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    e.preventDefault();
    // Capture keeps the drag alive over the iframes in the right pane.
    e.currentTarget.setPointerCapture?.(e.pointerId);
    // The cursor has to persist while the pointer is over other elements, and
    // text must stop selecting under a drag that started on the handle.
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function onPointerMove(e) {
    if (!e.currentTarget.hasPointerCapture?.(e.pointerId)) return;
    const pct = pctFromClientX(e.clientX);
    if (pct !== null) commit(pct);
  }

  function endDrag(e) {
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }

  // WAI-ARIA window splitter keys: arrows nudge, Shift+arrow jumps, Home/End
  // go to the extremes, Enter collapses the primary pane and restores it.
  function onKeyDown(e) {
    const step = e.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
    let next = null;
    if (e.key === "ArrowLeft") next = leftWidth - step;
    else if (e.key === "ArrowRight") next = leftWidth + step;
    else if (e.key === "Home") next = MIN_SPLIT;
    else if (e.key === "End") next = MAX_SPLIT;
    else if (e.key === "Enter") {
      if (collapsedFrom.current !== null) {
        next = collapsedFrom.current;
        collapsedFrom.current = null;
      } else {
        collapsedFrom.current = leftWidth;
        next = MIN_SPLIT;
      }
    } else return;
    e.preventDefault();
    commit(next);
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
        <div
          id={`${storageKey}-left`}
          className={`@container ${mobilePane === "left" ? "flex" : "hidden"} w-full flex-col overflow-hidden border-r border-border/60 md:flex md:w-[var(--split)] md:min-w-[17.5rem]`}
        >
          {left}
        </div>

        {/* Divider — desktop only */}
        <div
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-label="Resize panes"
          aria-controls={`${storageKey}-left`}
          aria-valuenow={Math.round(leftWidth)}
          aria-valuemin={MIN_SPLIT}
          aria-valuemax={MAX_SPLIT}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onKeyDown}
          onDoubleClick={() => commit(initialSplit)}
          title="Drag to resize — double-click to reset, arrow keys to nudge"
          className="group hidden w-3 shrink-0 cursor-col-resize touch-none select-none items-center justify-center focus-visible:outline-none md:flex"
        >
          <div className="h-full w-px bg-border/60 transition-colors group-hover:bg-primary/30 group-focus-visible:bg-primary group-focus-visible:w-0.5" />
        </div>

        {/* Right pane — toggled on mobile, split on md+. Single mount. */}
        <div
          className={`@container ${mobilePane === "right" ? "flex" : "hidden"} min-w-0 flex-1 flex-col overflow-hidden md:flex md:min-w-[17.5rem]`}
        >
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
