"use client";

// How much of the model's window a thread has spent.
//
// A donut rather than a number because the useful reading is "how close to the
// edge", not the figure itself. Neutral until it matters, then amber, then red
// — a gauge that is always coloured is a gauge nobody looks at. The ring is
// the whole control: no percentage beside it, because "3% context" on every
// message is a number nobody acts on, and the composer footer is where the
// clutter was. The figures — percent, tokens, cost, cached share — live in
// the tooltip, for the person who wants to know what a turn cost.

import { plural } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const R = 8;
const CIRCUMFERENCE = 2 * Math.PI * R;

export function formatTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 10_000) return `${Math.round(v / 1000)}k`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

function Ring({ pct }) {
  const tone =
    pct >= 0.9 ? "stroke-destructive"
    : pct >= 0.75 ? "stroke-warning"
    : "stroke-primary";
  return (
    <span className="inline-flex items-center text-muted-foreground">
      <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden className="shrink-0">
        <circle cx="10" cy="10" r={R} fill="none" strokeWidth="2.5" className="stroke-border" />
        {pct > 0 && (
          <circle
            cx="10"
            cy="10"
            r={R}
            fill="none"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - pct)}
            transform="rotate(-90 10 10)"
            className={cn(tone)}
          />
        )}
      </svg>
    </span>
  );
}

/** One figure with a caption under it. */
function Stat({ label, headline, detail }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span>{label}</span>
        {headline && <span className="tabular-nums">{headline}</span>}
      </div>
      {detail && <p className="mt-0.5 text-2xs leading-snug opacity-70">{detail}</p>}
    </div>
  );
}

// Sentences and a bar, not a table of joined figures: the first cut read
// "61k in · 7.2k out · 48k cached (79%) · $0.21" in monospace, which is a
// log line, and nobody hovering a ring wants a log line. No cost here either:
// the ring is about room left in the window, and money has its own page
// (/usage) — a dollar figure beside every message made people watch the
// meter instead of the answer.
function UsageDetails({ last, total, percent }) {
  const { t } = useLingui();
  const used = formatTokens((last?.input || 0) + (last?.output || 0));
  const window = formatTokens(last?.window);
  const calls = total?.calls ? plural(total.calls, { one: "# call", other: "# calls" }) : "";

  // A closure, not a module-level helper: the macro only transforms a t`…`
  // whose `t` is the one useLingui() returned in this scope. Handed to a
  // helper as an argument it is left untransformed and renders nothing.
  function tokenLine(bucket) {
    const input = formatTokens(bucket.input);
    const output = formatTokens(bucket.output);
    const parts = [t`${input} in, ${output} out`];
    // The cached share is the prompt-cache hit rate a person can act on: a
    // low one after a pause means the cache expired; after a model switch
    // it means the whole prompt was re-sent.
    if (bucket.cached && bucket.input) {
      const share = Math.round((bucket.cached / bucket.input) * 100);
      parts.push(t`${share}% from cache`);
    }
    return parts.join(" · ");
  }

  return (
    <div className="flex w-60 flex-col gap-3 text-xs">
      {last?.window && (
        <div>
          <div className="flex items-baseline justify-between gap-4">
            <span>{t`Context window`}</span>
            <span className="tabular-nums">{last.stale ? "" : t`${percent}% used`}</span>
          </div>
          {/* The tooltip paints in inverse ink, so the bar is drawn in the
              text colour: full strength for the used part, faint for the rest. */}
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-background/20">
            <div className="h-full rounded-full bg-background" style={{ width: `${last.stale ? 0 : percent}%` }} />
          </div>
          <p className="mt-1 text-2xs leading-snug opacity-70">
            {last.stale ? t`Just compacted — recounted on the next call` : t`${used} of ${window} tokens`}
          </p>
        </div>
      )}
      {last?.window && <Stat label={t`Last call`} detail={tokenLine(last)} />}
      {total?.calls > 0 && <Stat label={t`This session`} headline={calls} detail={tokenLine(total)} />}
      {last?.model && <p className="text-2xs opacity-70">{last.model}</p>}
    </div>
  );
}

/**
 * `used` is a 0–1 fraction of the window. `details` ({ last, total } from the
 * session reducer's `usage`) fills the tooltip with the figures; without it
 * the tooltip says `label` — "New thread", on a thread that has not started
 * — so the ring always answers a hover.
 */
export default function ContextRing({ used = 0, label = "", details = null }) {
  const { t } = useLingui();
  // Right after a compaction the last reading is of the context that was
  // replaced: show an empty ring that says so rather than a stale figure.
  const stale = Boolean(details?.last?.stale);
  const pct = stale ? 0 : Math.max(0, Math.min(1, used));
  const percent = Math.round(pct * 100);
  // No local Provider — see ui/tooltip.tsx: a second one here would only
  // override delayDuration for this tooltip and desync it from the rest of
  // the app, which is exactly what used to happen (it wrapped its own at
  // 150ms).
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={t`Context used: ${percent} percent. Show token usage.`}
          className="flex size-8 items-center justify-center rounded-md hover:bg-muted transition-colors"
        >
          <Ring pct={pct} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" align="end" className="max-w-xs">
        {details ? (
          <UsageDetails last={details.last} total={details.total} percent={percent} />
        ) : (
          <p className="text-xs">{label || t`New thread`}</p>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
