"use client";

// How much of the model's window a thread has spent.
//
// A donut rather than a number because the useful reading is "how close to the
// edge", not the figure itself. Neutral until it matters, then amber, then red
// — a gauge that is always coloured is a gauge nobody looks at. The figures
// live in the tooltip, for the person who wants to know what a turn cost.

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

/** Dollars at the precision a model call needs: cents for a session, tenths
 *  of a cent for one call, and "<$0.01" rather than a row of zeros. */
export function formatUsd(v) {
  const n = Number(v);
  if (!n || n <= 0) return "";
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n >= 0.01) return `$${n.toFixed(3).replace(/0$/, "")}`;
  return "<$0.01";
}

function Ring({ pct, label }) {
  const { t } = useLingui();
  const percent = Math.round(pct * 100);
  const tone =
    pct >= 0.9 ? "stroke-destructive"
    : pct >= 0.75 ? "stroke-warning"
    : "stroke-primary";
  return (
    <span className="inline-flex items-center gap-2 text-muted-foreground">
      <svg width="17" height="17" viewBox="0 0 20 20" aria-hidden className="shrink-0">
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
      <span className="text-xs">{label || t`${percent}% context`}</span>
    </span>
  );
}

function UsageDetails({ last, total }) {
  const { t } = useLingui();
  const rows = [];
  // Cost rides on the same rows as the tokens it explains; a model the backend
  // has no price for shows tokens alone rather than a guessed figure.
  const lastCost = formatUsd(last?.cost);
  const totalCost = formatUsd(total?.cost);
  // The cached share is the prompt-cache hit rate a person can act on: a low
  // one after a pause means the cache expired; after a model switch it means
  // the whole prompt was re-billed.
  const share = (cached, input) => (cached && input ? ` (${Math.round((cached / input) * 100)}%)` : "");
  // One figure per message, joined with the same separator the row always
  // used, so a translator sees "{n} in" and "{n} out" rather than one string
  // with four optional tails.
  const tokenRow = (bucket) => {
    const input = formatTokens(bucket.input);
    const output = formatTokens(bucket.output);
    const cached = formatTokens(bucket.cached);
    const cachedShare = share(bucket.cached, bucket.input);
    return [t`${input} in`, t`${output} out`, bucket.cached ? t`${cached} cached${cachedShare}` : ""];
  };
  if (last?.window) {
    const used = formatTokens(last.input + last.output);
    const window = formatTokens(last.window);
    rows.push([t`Context`, last.stale ? t`recomputed at the next call` : t`${used} of ${window}`]);
    rows.push([t`Last call`, [...tokenRow(last), lastCost].filter(Boolean).join(" · ")]);
  }
  if (total?.calls) {
    const calls = plural(total.calls, { one: "# call", other: "# calls" });
    rows.push([t`This session`, [...tokenRow(total), calls, totalCost].filter(Boolean).join(" · ")]);
  }
  if (last?.model) rows.push([t`Model`, last.model]);
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="numeric">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * `used` is a 0–1 fraction of the window. `details` ({ last, total } from the
 * session reducer's `usage`) turns the ring into a tooltip trigger; without
 * it the ring is decoration, as on a thread that has not started.
 */
export default function ContextRing({ used = 0, label = "", details = null }) {
  const { t } = useLingui();
  // Right after a compaction the last reading is of the context that was
  // replaced: show an empty ring that says so rather than a stale figure.
  const stale = Boolean(details?.last?.stale);
  const pct = stale ? 0 : Math.max(0, Math.min(1, used));
  const text = stale ? t`context compacted` : label;
  const percent = Math.round(pct * 100);
  if (!details) return <Ring pct={pct} label={text} />;
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
          className="rounded-md px-1 -mx-1 hover:bg-muted transition-colors"
        >
          <Ring pct={pct} label={text} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end" className="max-w-xs">
        <UsageDetails last={details.last} total={details.total} />
      </TooltipContent>
    </Tooltip>
  );
}
