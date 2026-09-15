import { cn } from "@/lib/utils";

/**
 * Content that just finished loading eases in instead of popping — the same
 * motion budget every Radix overlay already uses (`tw-animate-css`, tuned to
 * <300ms, ease-out) applied to a plain mount instead of a `data-state` open.
 * For a screen with a known loaded shape, animate the swap from its own
 * skeleton to this (DESIGN.md's Desk pattern); for one that doesn't, wrap
 * the resolved content once data arrives.
 *
 * Nothing to gate for `prefers-reduced-motion` here — `.animate-in` is
 * stripped globally in `base.css`.
 */
export function Reveal({ as: Comp = "div", className, children, ...rest }) {
  return (
    <Comp className={cn("animate-in fade-in slide-in-from-bottom-1 duration-200", className)} {...rest}>
      {children}
    </Comp>
  );
}

export default Reveal;
