"use client"

// A run-on line/summary/log entry, capped visually and readable on demand.
//
// `line-clamp` only crops the box — the full string stays in the a11y tree,
// so screen readers already get the untruncated text (CSS Overflow spec;
// browser truncation is a paint-time effect, not a DOM one). What it doesn't
// give a sighted, mouse-or-keyboard user is a way to read the rest, so this
// pairs the crop with the tooltip: WCAG SC 1.4.13 (Content on Hover or
// Focus) requires that content to be dismissible, hoverable and persistent,
// which is exactly what Radix's Tooltip already does and a native `title`
// attribute does not (no Escape, no way to move the pointer into it).

import * as React from "react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

type ClampLines = 1 | 2 | 3 | 4

// Literal classes, not a template string — Tailwind only picks up utilities
// it can see verbatim in source. `clampClass` is the one place that mapping
// lives; a caller that needs to put the crop on an element ClampText doesn't
// own (e.g. inside its own pre-existing `<Link>`) reads it from here rather
// than re-guessing which line-clamp values exist.
const CLAMP: Record<ClampLines, string> = {
  1: "line-clamp-1",
  2: "line-clamp-2",
  3: "line-clamp-3",
  4: "line-clamp-4",
}

export function clampClass(lines: ClampLines): string {
  return CLAMP[lines]
}

/**
 * The tooltip half alone, for a clamp that has to sit inside an element
 * ClampText can't wrap itself — most often a `<Link>`/`<button>` that is
 * already the right tooltip trigger and already the row's one tab stop.
 * Pair with `Tooltip` + `TooltipTrigger asChild` around that element and
 * `clampClass(n)` on the clamped child. See `DeskCards.jsx`'s `Item`.
 */
export function ClampTooltipContent({
  text,
  lines = 4,
  className,
}: {
  text: string
  lines?: ClampLines
  className?: string
}) {
  return (
    <TooltipContent side="bottom" className={cn("max-w-xs whitespace-normal text-left", className)}>
      <p className={clampClass(lines)}>{text}</p>
    </TooltipContent>
  )
}

type ClampTextProps = {
  text: string
  lines?: ClampLines
  tooltipLines?: ClampLines
  as?: React.ElementType
  className?: string
}

/**
 * Self-contained: the clamped element is its own tooltip trigger, focusable
 * so the full text reaches keyboard and screen-reader users the same way it
 * reaches a mouse. Don't use this where the clamp already sits inside a
 * `<Link>`/`<button>` — that would add a second tab stop for one row. Use
 * `ClampTooltipContent` with that element's own `Tooltip`/`TooltipTrigger
 * asChild` instead.
 */
export function ClampText({ text, lines = 2, tooltipLines = 4, as: Comp = "span", className }: ClampTextProps) {
  if (!text) return null
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Comp tabIndex={0} className={cn(clampClass(lines), "cursor-default text-left outline-none", className)}>
          {text}
        </Comp>
      </TooltipTrigger>
      <ClampTooltipContent text={text} lines={tooltipLines} />
    </Tooltip>
  )
}
