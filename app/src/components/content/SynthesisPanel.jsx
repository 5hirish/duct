"use client";

// What a Discover result set says, above the grid that says it post by post:
// which format earns more here, which tags recur, and which openings won.
// The numbers come from lib/discoverSynthesis.js; this file only draws them.

import { useId, useMemo } from "react";
import { Play } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";

import { synthesize } from "@/lib/discoverSynthesis";
import { compactNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

// A stable empty default: a fresh `[]` per render would defeat the memo below.
const NO_TAGS = [];

export default function SynthesisPanel({ posts, searchedTags = NO_TAGS }) {
  const { i18n } = useLingui();
  const headingId = useId();
  const s = useMemo(() => synthesize(posts, { exclude: searchedTags }), [posts, searchedTags]);
  if (!s) return null;

  const pct = (ratio) => formatPercent(ratio, { locale: i18n.locale });
  const total = s.total;
  const median = pct(s.engagement);

  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-border/70 bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <h3 id={headingId} className="text-sm font-semibold">
          <Trans>What&apos;s working</Trans>
        </h3>
        <p className="text-2xs text-muted-foreground tabular-nums">
          <Trans>
            Across <Plural value={total} one="# post" other="# posts" /> · median engagement {median}
          </Trans>
        </p>
      </div>

      <div className="mt-4 grid gap-5 @2xl:grid-cols-2">
        <FormatSplit slideshow={s.slideshow} video={s.video} pct={pct} />
        <RecurringTags tags={s.hashtags} />
      </div>

      {s.hooks.length > 0 && <WinningHooks hooks={s.hooks} pct={pct} />}
    </section>
  );
}

function Heading({ children, hint }) {
  return (
    <div className="mb-2">
      <h4 className="text-xs font-medium">{children}</h4>
      {hint && <p className="text-2xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function FormatSplit({ slideshow, video, pct }) {
  // The leader is only named when both formats are present; one format out
  // of one "wins" nothing.
  const both = slideshow.count > 0 && video.count > 0;
  const leader = both && slideshow.engagement !== video.engagement
    ? (slideshow.engagement > video.engagement ? "slideshow" : "video")
    : null;
  const slideShare = pct(slideshow.share);
  const videoShare = pct(video.share);
  const slideEng = pct(slideshow.engagement);
  const videoEng = pct(video.engagement);

  return (
    <div>
      <Heading hint={<Trans>Share of posts, and the median engagement each earns</Trans>}>
        <Trans>Format</Trans>
      </Heading>
      <div className="flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <div className="bg-primary" style={{ width: `${slideshow.share * 100}%` }} />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="flex items-center gap-1.5">
            <span className="size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
            <Trans>Slideshows</Trans>
          </dt>
          <dd className="mt-0.5 tabular-nums text-muted-foreground">
            <Trans>
              {slideShare} of posts · <span className={cn(leader === "slideshow" && "font-semibold text-foreground")}>{slideEng}</span> eng.
            </Trans>
          </dd>
        </div>
        <div>
          <dt className="flex items-center gap-1.5">
            <span className="size-2 shrink-0 rounded-full border border-border bg-muted" aria-hidden="true" />
            <Trans>Videos</Trans>
          </dt>
          <dd className="mt-0.5 tabular-nums text-muted-foreground">
            <Trans>
              {videoShare} of posts · <span className={cn(leader === "video" && "font-semibold text-foreground")}>{videoEng}</span> eng.
            </Trans>
          </dd>
        </div>
      </dl>
    </div>
  );
}

function RecurringTags({ tags }) {
  return (
    <div>
      <Heading hint={<Trans>Beyond the ones you searched, on two posts or more</Trans>}>
        <Trans>Recurring hashtags</Trans>
      </Heading>
      {tags.length ? (
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {tags.map(({ tag, count }) => (
            <li key={tag} className="whitespace-nowrap">
              <span className="font-medium">#{tag}</span>{" "}
              <span className="tabular-nums text-muted-foreground" aria-hidden="true">×{count}</span>
              <span className="sr-only">
                <Plural value={count} one="# post" other="# posts" />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          <Trans>No other tag repeats across these posts.</Trans>
        </p>
      )}
    </div>
  );
}

function WinningHooks({ hooks, pct }) {
  return (
    <div className="mt-4 border-t border-border/60 pt-4">
      <Heading hint={<Trans>Opening lines of the most engaging posts that reached at least a typical audience</Trans>}>
        <Trans>Winning hooks</Trans>
      </Heading>
      <ol className="space-y-2">
        {hooks.map((h) => (
          <li key={h.id} className="flex items-baseline gap-3 text-xs">
            <span className="w-12 shrink-0 font-semibold tabular-nums">{pct(h.engagement)}</span>
            {h.url ? (
              <a href={h.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 hover:underline">
                {h.text}
              </a>
            ) : (
              <span className="min-w-0 flex-1">{h.text}</span>
            )}
            <span className="inline-flex shrink-0 items-center gap-1 tabular-nums text-muted-foreground">
              <Play className="size-3" aria-hidden="true" /> {compactNumber(h.plays)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
