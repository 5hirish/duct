import { cn } from "@/lib/utils";

/**
 * The busy ring.
 *
 * There were twelve hand-rolled copies of this markup across the app — six
 * sizes and four hardcoded border colours (current, primary, blue-500,
 * orange-500) — so "the app is working" looked like a different thing on every
 * surface, and only two of the twelve told a screen reader anything.
 *
 * Colour comes from `currentColor`, so callers tint it the same way they tint
 * text (`text-primary`, `text-blue-500`) instead of restating the ring. Size
 * and any other override go through `className`; tailwind-merge means a passed
 * `size-*` or `border-*` replaces the default rather than fighting it.
 *
 * Accessibility: decorative by default (`aria-hidden`), because a spinner next
 * to text that already says "Analysing…" is noise. Pass `label` when the ring
 * is the ONLY indication that something is happening — it becomes a live
 * `role="status"` with that accessible name.
 */
export function Spinner({ className = "", label, ...rest }) {
  return (
    <span
      role={label ? "status" : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : "true"}
      className={cn(
        "inline-block size-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent",
        className
      )}
      {...rest}
    />
  );
}

export default Spinner;
