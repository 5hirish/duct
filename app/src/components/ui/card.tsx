import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * The one card. Every bordered surface that groups content is this, so that
 * every card in the app has the same radius, padding, border and hover, and a
 * grid of them lines up.
 *
 * Lining up is the reason for the anatomy. `CardFooter` takes `mt-auto`, so in
 * a grid row of cards with different amounts of text the footers (a status, a
 * button) sit on one line instead of stepping up and down the row. That
 * stepping was the most visible defect in the 2026-11-02 UI audit.
 *
 * Variants carry weight, which is how a screen gets one hero:
 * - `default`: a surface. Most cards.
 * - `interactive`: the whole card is one target. Put `cardLinkClass` on the
 *   title's link or button so the hit area stretches over the card and there
 *   is still one tab stop with a readable name (app/AGENTS.md).
 * - `hero`: the one thing on the screen you most want done. At most one per
 *   screen; it is the brand tint.
 * - `quiet`: a recessed group with no border, for secondary content.
 */
const CARD_VARIANTS = {
  default: "border-border",
  interactive:
    "border-border transition-colors hover:border-foreground/20 hover:bg-accent/50 has-[[data-card-link]:focus-visible]:ring-3 has-[[data-card-link]:focus-visible]:ring-ring/40",
  hero: "border-primary/30 bg-primary/5",
  quiet: "border-transparent bg-muted/60",
} as const

function Card({
  className,
  variant = "default",
  size = "default",
  ...props
}: React.ComponentProps<"div"> & {
  variant?: keyof typeof CARD_VARIANTS
  size?: "default" | "sm" | "lg"
}) {
  return (
    <div
      data-slot="card"
      data-variant={variant}
      data-size={size}
      className={cn(
        // On the 8px grid: 24 padding, 16 between the card's own groups (sm:
        // 16 and 12). The border does the grouping (common region), which is
        // why a grid of cards can sit only 12px apart.
        "group/card relative flex min-w-0 flex-col gap-4 rounded-xl border bg-card p-6 text-sm text-card-foreground",
        "data-[size=sm]:gap-3 data-[size=sm]:p-4 data-[size=lg]:gap-6 data-[size=lg]:p-8",
        CARD_VARIANTS[variant],
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "grid auto-rows-min items-start gap-1 has-data-[slot=card-action]:grid-cols-[1fr_auto]",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("text-sm font-semibold leading-snug", className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm leading-relaxed text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("min-w-0", className)} {...props} />
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("mt-auto flex items-center gap-2", className)}
      {...props}
    />
  )
}

/**
 * For the title link or button of an `interactive` card: stretches its hit area
 * over the whole card. Add `data-card-link` beside it so the card can draw the
 * focus ring on itself.
 */
const cardLinkClass =
  "outline-none after:absolute after:inset-0 after:rounded-xl after:content-['']"

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
  cardLinkClass,
}
