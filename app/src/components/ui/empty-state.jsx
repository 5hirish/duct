"use client";

/**
 * The empty state, once.
 *
 * `DESIGN.md` has specified this anatomy for a while — dashed panel, `size-12`
 * icon tile, `text-sm font-medium` title, `text-xs` body, verb-first
 * `Button size="sm"` — and the app had grown four hand-rolled versions of it
 * anyway (FormatLibrary's local `EmptyState`, AnalyticsView's inline one, and
 * a scattering of bare `<p className="app-subtle">No X yet.</p>`). They already
 * disagreed on the icon size, the border radius and whether there was a CTA at
 * all. The fourth copy is the one that makes a fork permanent, so this is the
 * implementation and `/preview`'s specimen renders it rather than restating it.
 *
 * Two things it is opinionated about, because both are the difference between
 * an empty state that activates and one that just reports:
 *
 * **A CTA is a prop, not an afterthought.** An empty state with nothing to
 * click is a dead end, and every dead end here had one thing the reader could
 * usefully do next — the pages simply hadn't said it. `actions` is a node so
 * the caller keeps `asChild`/`Link`/`onClick`; it is not optional in practice.
 *
 * **`example` is how a surface teaches instead of apologises.** NN/g's point
 * about empty states being onboarding surfaces only pays off if the reader can
 * see the filled state. Pass the real component fed fake props — never a
 * mock-up of it — and this frames it, labels it, dims it and hides the numbers
 * from the accessibility tree so nobody is read invented data as fact.
 *
 * Not for: a list inside a layout that must not jump (one muted line in place,
 * the `DeskCards` pattern), or a first run rich enough to deserve the
 * `DeskDayOne` treatment. This is the middle case, which is most of them.
 */

import { cn } from "@/lib/utils";

export default function EmptyState({
  icon: Icon,
  title,
  children,
  actions,
  example,
  exampleLabel = "Example",
  className,
}) {
  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className="rounded-xl border border-dashed p-10 text-center">
        {Icon && (
          <div
            className="mx-auto flex size-12 items-center justify-center rounded-xl bg-muted"
            aria-hidden="true"
          >
            <Icon className="size-5 text-muted-foreground" strokeWidth={1.75} />
          </div>
        )}
        <p className={cn("text-sm font-medium", Icon && "mt-3")}>{title}</p>
        {children && (
          // Capped at a measure: this copy is centred, and centred prose past
          // ~60 characters a line is the one place ragged-both edges actually
          // cost you the read.
          <div className="mx-auto mt-1 max-w-[46ch] text-xs leading-relaxed text-muted-foreground">
            {children}
          </div>
        )}
        {actions && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{actions}</div>
        )}
      </div>

      {example && (
        // Framed like a specimen, not laid out like the page's own content.
        // A centred rule and 55% opacity was the first attempt and it failed
        // the light theme: dimmed near-black on white is still near-black, and
        // an invented $6.41 that reads as live spending on a money page is a
        // worse bug than the empty state it replaced. The dashed border, the
        // recessed ground and a legend sitting on the border are three
        // independent signals, none of which depend on a colour holding up.
        <div className="relative rounded-xl border border-dashed bg-muted/40 px-4 pb-4 pt-6">
          <span className="absolute -top-2 left-4 rounded-full border bg-background px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {exampleLabel}
          </span>
          {/* The legend above is real text; the sample below is not. It is
              invented data drawn in the same components as the real thing, so
              a screen reader reading it would be read a figure the user never
              spent. `inert` takes the tab stops with it — the example must not
              be reachable by keyboard either. */}
          <div inert={true} aria-hidden="true" className="select-none opacity-75">
            {example}
          </div>
        </div>
      )}
    </div>
  );
}
