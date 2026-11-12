import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * shadcn's Textarea, which the app never generated: every multi-line field
 * was a raw <textarea> wearing `.app-input`, a single-line pill's 22px radius
 * and fixed height. Text ran into the rounded corners and a scrollbar sat
 * inside the pill.
 *
 * It grows with what is typed (`field-sizing: content`) up to `max-h-80`, then
 * scrolls; a browser without field-sizing keeps `min-h` and the resize handle.
 * Same edge, fill and focus ring as `Input`, so a form reads as one family.
 */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-20 max-h-80 w-full resize-y rounded-lg border border-control bg-input/50 px-3 py-2 text-base leading-relaxed transition-[color,box-shadow,background-color] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
