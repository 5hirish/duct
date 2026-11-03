"use client";

/**
 * The page frame. Every routed screen in the app shell is
 *
 *   <Page>
 *     <PageHeader title=… status=… actions=… />
 *     <Section title=…>…</Section>
 *   </Page>
 *
 * and nothing else draws an <h1>. Before this existed each page composed its
 * own header, and the 2026-11-02 UI audit measured the result: page titles in
 * six different horizontal positions, at three sizes and three weights, and
 * eight of sixteen screens opening on a title plus a paragraph explaining the
 * page. `check:design` now refuses an <h1> anywhere else.
 *
 * Three decisions are built in so a caller cannot get them wrong:
 *
 * - **No description paragraph.** PageHeader has `status`, one line of state
 *   ("3 of 15 connected", "Last checked 2 hours ago"): one line on a desktop,
 *   two at most on a phone, clamped there, and held to it by check:layout.
 *   An explanation of how the page works goes in `help`, behind a "?" the
 *   reader opens when they want it (NN/g: help at the moment of need, not
 *   instructions up front). A sentence that would only make sense to someone
 *   who has never seen the page should not be on it every visit.
 * - **One left edge.** The header and every section share the page's edge; a
 *   narrow page (`width="narrow"`, forms and settings) caps its width but stays
 *   left-aligned, so moving between screens never moves the title.
 * - **One rhythm, on the 8px grid.** Header to content and section to
 *   section are the page's gap (40px); a section's heading to its content is
 *   16px; inside a card 16px; between cards 12px. Space between groups is
 *   always larger than space within them (NN/g, Gestalt proximity), so
 *   whitespace does the grouping and borders are only for what it cannot.
 * - **Three type sizes a screen** (NN/g): the title (24px; 36px display on
 *   the one hero screen), body 14px with section headings in its semibold,
 *   and 12px for metadata.
 */

import Link from "next/link";
import { ChevronLeft, CircleHelp } from "lucide-react";
import { useLingui } from "@lingui/react/macro";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const WIDTHS = {
  // Grids, lists and dashboards: the container's width (capped by .app-main).
  default: "",
  // Forms and settings: a field wider than this is a field nobody reads across.
  narrow: "max-w-2xl",
  // A page that is mostly prose.
  reading: "max-w-3xl",
};

export function Page({ width = "default", className, children, ...props }) {
  return (
    <div data-slot="page" className={cn("flex min-w-0 flex-col gap-10", WIDTHS[width], className)} {...props}>
      {children}
    </div>
  );
}

// Past this many words a "status" has become a description again.
const STATUS_WORDS = 14;

/**
 * @param title   The page's name, or for a hero page the one sentence that
 *                matters ("2 things need you").
 * @param status  One line of live state. Never an explanation of the page.
 * @param actions The page's buttons, right-aligned; the primary one last.
 * @param help    What the page is for and how it works, behind a "?".
 * @param back    `{ href, label }` for a page nested under another (an
 *                artifact under the library). Top-level pages have none: the
 *                breadcrumb and the sidebar already say where you are.
 * @param size    "default" | "hero". Hero is the home screen's greeting, in
 *                the display serif. One screen uses it.
 * @param eyebrow A short label above a hero title ("Good morning, Maya").
 */
export function PageHeader({
  title,
  status,
  actions,
  help,
  back,
  size = "default",
  eyebrow,
  className,
}) {
  if (process.env.NODE_ENV !== "production" && typeof status === "string") {
    const words = status.trim().split(/\s+/).length;
    if (words > STATUS_WORDS) {
      console.warn(
        `PageHeader: status is ${words} words. It is one line of state, not a description; ` +
          "move the explanation to `help`."
      );
    }
  }
  const hero = size === "hero";
  return (
    <header
      data-slot="page-header"
      data-size={size}
      className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-4", className)}
    >
      {/* basis-72: the title column wraps under the actions before it is
          squeezed, instead of being crushed to a sliver beside them. */}
      <div className="min-w-0 flex-1 basis-72">
        {back && (
          <Link
            href={back.href}
            className="mb-3 inline-flex items-center gap-1 rounded-md text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronLeft className="size-4" aria-hidden />
            {back.label}
          </Link>
        )}
        {eyebrow && <p className="mb-2 text-sm font-medium text-muted-foreground">{eyebrow}</p>}
        <div className="flex items-center gap-2">
          <h1
            className={cn(
              "min-w-0 text-balance",
              hero
                ? "font-display text-4xl leading-tight tracking-tight"
                : "text-2xl font-semibold leading-tight tracking-tight"
            )}
          >
            {title}
          </h1>
          {help && <HelpTip>{help}</HelpTip>}
        </div>
        {status && (
          <p
            data-slot="page-status"
            className={cn("line-clamp-2 text-muted-foreground", hero ? "mt-3 text-base" : "mt-1.5 text-sm")}
          >
            {status}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/**
 * A titled group of content on a page. The heading is an <h2> at the one
 * section size; `count` sits beside it in muted ink; `actions` on the right.
 */
export function Section({ title, count, actions, help, className, children, ...props }) {
  return (
    <section data-slot="section" className={cn("flex min-w-0 flex-col gap-4", className)} {...props}>
      {(title || actions) && (
        <div className="flex min-h-8 items-center justify-between gap-3">
          {title && (
            <div className="flex min-w-0 items-center gap-2">
              {/* Body size, heavier weight: Apple's Headline is the same size
                  as Body, and NN/g's ceiling is three type sizes a screen
                  (title, body, meta). Space above the section and weight do
                  the separating, not a fourth size. */}
              <h2 className="truncate text-sm font-semibold">{title}</h2>
              {count != null && <span className="text-sm text-muted-foreground">{count}</span>}
              {help && <HelpTip>{help}</HelpTip>}
            </div>
          )}
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

const TILE_MIN = {
  sm: "grid-cols-[repeat(auto-fill,minmax(min(13rem,100%),1fr))]",
  md: "grid-cols-[repeat(auto-fill,minmax(min(17rem,100%),1fr))]",
  lg: "grid-cols-[repeat(auto-fill,minmax(min(22rem,100%),1fr))]",
};

// A fixed column count for a set whose size is known (four starters), so it
// lands as 2×2 or 4×1 and never as three plus an orphan.
const TILE_COLS = {
  2: "grid-cols-1 @xl:grid-cols-2",
  3: "grid-cols-1 @xl:grid-cols-2 @4xl:grid-cols-3",
  4: "grid-cols-1 @xl:grid-cols-2 @5xl:grid-cols-4",
};

/**
 * The one grid for a collection of cards. Columns come from the container's
 * width (`size` is the narrowest a tile may get) or, for a set of known size,
 * from `cols`. Every tile in a row is the same height, and Card's pinned
 * footer keeps their last lines on one baseline.
 */
export function TileGrid({ size = "md", cols, className, children, ...props }) {
  return (
    <div
      data-slot="tile-grid"
      className={cn("grid items-stretch gap-3", cols ? TILE_COLS[cols] : TILE_MIN[size], className)}
      {...props}
    >
      {children}
    </div>
  );
}

/** The "?" beside a title: the page's explanation, for whoever asks. */
export function HelpTip({ label, children, className }) {
  const { t } = useLingui();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label || t`What is this?`}
          className={cn(
            "inline-flex size-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/40 outline-none",
            className
          )}
        >
          <CircleHelp className="size-4" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-4 text-sm leading-relaxed text-popover-foreground">
        {children}
      </PopoverContent>
    </Popover>
  );
}
