import { Spinner } from "@/components/ui/spinner";
import { Reveal } from "@/components/ui/reveal";

// Next's own Suspense-boundary convention for this segment — fires on any
// route inside (app)/ while its RSC payload is in flight, including a cold
// client-side navigation, so the alternative is a blank flash rather than
// nothing. Unknown shape, so this is the "Loading…" line from DESIGN.md's
// canon table, not a fake skeleton pretending to know the page. A route
// with a known shape (the Desk pattern) still renders its own skeleton
// first — this is only what shows before that component has even mounted.
export default function Loading() {
  return (
    <Reveal
      as="div"
      className="flex min-h-[50svh] items-center justify-center gap-2 text-sm text-muted-foreground"
    >
      <Spinner />
      <span role="status">Loading…</span>
    </Reveal>
  );
}
