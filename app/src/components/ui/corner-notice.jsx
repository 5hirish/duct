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

import { X } from "lucide-react";

/**
 * @param {object}   props
 * @param {any}      props.icon      lucide component, rendered decorative
 * @param {string}   props.title     one line; the condition, not a category
 * @param {any}      props.children  supporting copy and any error text
 * @param {any}      props.actions   buttons — primary first
 * @param {Function} [props.onDismiss] omit for a notice that cannot be dismissed
 * @param {boolean}  [props.dismissDisabled] busy: dismissing mid-action loses it
 * @param {string}   [props.dismissLabel]    accessible name for the ✕
 */
export function CornerNotice({
  icon: Icon,
  title,
  children,
  actions,
  onDismiss,
  dismissDisabled = false,
  dismissLabel = "Dismiss notification",
}) {
  return (
    <div
      role="status"
      // Polite, never assertive: an assertive live region interrupts a screen
      // reader mid-sentence, which is the audible version of the modal this
      // component exists to avoid.
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-border bg-background/95 p-4 shadow-lg ring-1 ring-border/40 backdrop-blur-xl"
    >
      <div className="flex items-start gap-3">
        {Icon ? (
          <Icon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{title}</p>
          {children}
          {actions ? <div className="mt-3 flex items-center gap-2">{actions}</div> : null}
        </div>
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            disabled={dismissDisabled}
            aria-label={dismissLabel}
            className="-mr-1 -mt-1 rounded p-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default CornerNotice;
