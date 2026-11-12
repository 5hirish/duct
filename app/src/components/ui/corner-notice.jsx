"use client";

// The corner notice: something the app needs to tell you, that must not
// interrupt what you are doing.
//
// `UpdateToast` established this anatomy and DESIGN.md made it canon while it
// was still one hand-rolled component. `preview/surfaces.jsx` then reproduced
// the positioning "as a position, not as a component, because there is no
// shared primitive to import", and a second real notice (a new web build) would
// have made three copies of the same fixed-position card. This is that
// primitive, extracted at the third use rather than after it — the repo rule is
// to reorganise while it is still one file.
//
// It is deliberately not a toast *system*: no queue, no timers, no imperative
// `notify()`. Every notice here is a persistent condition the caller already
// tracks in state, and a stack manager for two of them would be machinery
// standing in for a decision about which one matters.
//
// That decision is one rule, held by one flag: **a notice that tells you
// something outranks a notice that asks you for something.** Telling is the
// update and reload notices, the connection banner, the cookie question and
// any other CornerNotice; asking is the GitHub star ask (StarAsk), the only
// one so far. A teller holds the corner while it is mounted (`useHoldCorner`,
// which every CornerNotice calls for itself); an asker passes `yields`, never
// appears while the corner is held, and steps aside if a teller arrives. The
// connection banner holds it from the opposite corner too: the rule is about
// attention, not pixels, and a lost backend is the worst moment to ask for a
// favour. Between tellers nothing needs deciding: UpdateToast is shell-only,
// ReloadToast browser-only, and the banner sits in the other corner.

import { useEffect, useSyncExternalStore } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

let holders = 0;
const listeners = new Set();

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function changed(delta) {
  holders += delta;
  for (const listener of listeners) listener();
}

/** Whether a notice that outranks a request is on screen, read at call time. */
export function isCornerTaken() {
  return holders > 0;
}

/** The same, as state: re-renders when a teller arrives or leaves. */
export function useCornerTaken() {
  return useSyncExternalStore(subscribe, isCornerTaken, () => false);
}

/** Hold the corner while `active` and mounted. For a teller that is not a CornerNotice. */
export function useHoldCorner(active = true) {
  useEffect(() => {
    if (!active) return undefined;
    changed(1);
    return () => changed(-1);
  }, [active]);
}

/**
 * @param {object}   props
 * @param {any}      props.icon      lucide component, rendered decorative
 * @param {string}   [props.iconClassName] colour or motion for the icon; muted by default
 * @param {string}   props.title     one line; the condition, not a category
 * @param {any}      props.children  supporting copy and any error text
 * @param {any}      props.actions   buttons — primary first
 * @param {any}      [props.footer]  one quiet line under the actions: the other way out
 * @param {Function} [props.onDismiss] omit for a notice that cannot be dismissed
 * @param {boolean}  [props.dismissDisabled] busy: dismissing mid-action loses it
 * @param {string}   [props.dismissLabel]    accessible name for the ✕
 * @param {boolean}  [props.yields]  a request, not news: does not hold the corner;
 *                                   its owner reads `useCornerTaken()` and stands aside
 */
export function CornerNotice({
  icon: Icon,
  iconClassName,
  title,
  children,
  actions,
  footer,
  onDismiss,
  dismissDisabled = false,
  dismissLabel = "Dismiss notification",
  yields = false,
}) {
  useHoldCorner(!yields);
  return (
    <div
      role="status"
      // Polite, never assertive: an assertive live region interrupts a screen
      // reader mid-sentence, which is the audible version of the modal this
      // component exists to avoid.
      aria-live="polite"
      // Inset from the corner by at least the safe area: a landscape notch or
      // the home indicator would otherwise sit on the card. It arrives
      // unbidden at the edge of the eye, so a 200ms rise says where; the
      // reduced-motion rule in base.css takes it out.
      className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-[max(1rem,env(safe-area-inset-right))] z-50 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-border bg-background/95 p-4 shadow-lg ring-1 ring-border/40 backdrop-blur-xl animate-in fade-in slide-in-from-bottom-2 duration-200"
    >
      <div className="flex items-start gap-3">
        {Icon ? (
          <Icon className={cn("mt-0.5 size-5 shrink-0 text-muted-foreground", iconClassName)} aria-hidden />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{title}</p>
          {children}
          {/* On a touchscreen the actions grow to Apple's 44pt floor; a
              mouse keeps the denser 32px the desktop is built at. */}
          {actions ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 pointer-coarse:*:h-11">{actions}</div>
          ) : null}
          {footer ? <div className="mt-2">{footer}</div> : null}
        </div>
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            disabled={dismissDisabled}
            aria-label={dismissLabel}
            // Under a finger the target grows to 44px by an invisible ring
            // reaching into the card's own padding, so the glyph, the layout
            // and the text column stay exactly where a mouse has them.
            className="relative -mr-1 -mt-1 rounded p-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50 pointer-coarse:after:absolute pointer-coarse:after:-inset-2.5"
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default CornerNotice;
