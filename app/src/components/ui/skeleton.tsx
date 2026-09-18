import { cn } from "@/lib/utils"

/**
 * The loading placeholder. shadcn's primitive, restyled at its source:
 * `.skeleton` in styles/skeleton.css is a sheen sweeping over the muted
 * ground instead of `animate-pulse`, so every skeleton in the app shimmers
 * the same way and a page of them reads as one pass of light.
 *
 * A bare `Skeleton` is one block; size it with `h-*`/`w-*`/`aspect-*` and it
 * takes any radius override. The shapes below are the three layouts that
 * kept being hand-rolled: a run of text, a list of rows, a document.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("skeleton rounded-lg", className)}
      {...props}
    />
  )
}

// Line widths cycle so a paragraph reads as prose rather than a bar chart;
// the last line is always the short one, the way a paragraph ends.
const TEXT_WIDTHS = ["w-full", "w-11/12", "w-4/5", "w-full", "w-3/4"]
const LAST_LINE = "w-1/2"

type SkeletonTextProps = React.ComponentProps<"div"> & { lines?: number }

/** A paragraph of `lines` text-sm lines. */
function SkeletonText({ lines = 3, className, ...props }: SkeletonTextProps) {
  return (
    <div className={cn("flex flex-col gap-2.5", className)} {...props}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          className={cn(
            "h-3.5 rounded",
            i === lines - 1 && lines > 1 ? LAST_LINE : TEXT_WIDTHS[i % TEXT_WIDTHS.length]
          )}
        />
      ))}
    </div>
  )
}

type SkeletonListProps = React.ComponentProps<"div"> & { rows?: number; label?: string }

/**
 * A bordered list of rows, each an icon tile beside two lines: the shape of
 * the activity feed, the artifacts list and the memory timeline. `label` is
 * what a screen reader hears; the blocks themselves say nothing.
 */
function SkeletonList({ rows = 4, label = "Loading", className, ...props }: SkeletonListProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn("overflow-hidden rounded-xl border border-border", className)}
      {...props}
    >
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className={cn("flex items-center gap-3 px-4 py-3", i > 0 && "border-t border-border/60")}
        >
          <Skeleton className="size-9 shrink-0" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className={cn("h-3.5 rounded", i % 2 ? "w-2/5" : "w-1/3")} />
            <Skeleton className={cn("h-3 rounded", i % 2 ? "w-3/5" : "w-3/4")} />
          </div>
        </div>
      ))}
    </div>
  )
}

type SkeletonDocumentProps = React.ComponentProps<"div"> & { label?: string }

/**
 * A written page: title, subtitle, two paragraphs around a figure. What a
 * brief, an artifact or a report looks like before its bytes arrive, so the
 * pane changes texture rather than shape when they do.
 */
function SkeletonDocument({ label = "Loading", className, ...props }: SkeletonDocumentProps) {
  return (
    <div role="status" aria-label={label} className={cn("flex flex-col gap-5", className)} {...props}>
      <div className="flex flex-col gap-2.5">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-3.5 w-1/3 rounded" />
      </div>
      <SkeletonText lines={4} />
      <Skeleton className="h-32" />
      <SkeletonText lines={3} />
    </div>
  )
}

export { Skeleton, SkeletonText, SkeletonList, SkeletonDocument }
