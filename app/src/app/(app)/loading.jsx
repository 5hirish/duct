import { Skeleton, SkeletonText } from "@/components/ui/skeleton";

// Next's own Suspense-boundary convention for this segment — fires on any
// route inside (app)/ while its RSC payload is in flight, including a cold
// client-side navigation, so the alternative is a blank flash rather than
// nothing. It cannot know the page, so it draws the shape most of them share
// (a title, a line under it, a row of cards — the Desk pattern) in the
// app's one shimmer, which is what DESIGN.md's canon table asks of every
// wait now: the layout arrives first, the words follow. A route with a
// known shape still renders its own skeleton first; this is only what shows
// before that component has even mounted.
export default function Loading() {
  return (
    <div className="flex flex-col gap-8" role="status" aria-label="Loading">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-8 w-[420px] max-w-full" />
        <Skeleton className="h-4 w-[300px] max-w-full rounded" />
      </div>
      <div className="grid gap-4 @md:grid-cols-2 @3xl:grid-cols-3">
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
      <SkeletonText lines={3} className="max-w-2xl" />
    </div>
  );
}
