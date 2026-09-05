"use client";

// How much of the model's window a thread has spent.
//
// A donut rather than a number because the useful reading is "how close to the
// edge", not the figure itself. Neutral until it matters, then amber, then red
// — a gauge that is always coloured is a gauge nobody looks at. The figures
// live in the tooltip, for the person who wants to know what a turn cost.

import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

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
  const tone =
    pct >= 0.9 ? "stroke-destructive"
    : pct >= 0.75 ? "stroke-amber-500"
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
      <span className="text-[12.5px]">{label || `${Math.round(pct * 100)}% context`}</span>
    </span>
  );
}

function UsageDetails({ last, total }) {
  const rows = [];
  // Cost rides on the same rows as the tokens it explains; a model the backend
  // has no price for shows tokens alone rather than a guessed figure.
  const lastCost = formatUsd(last?.cost);
  const totalCost = formatUsd(total?.cost);
  // The cached share is the prompt-cache hit rate a person can act on: a low
  // one after a pause means the cache expired; after a model switch it means
  // the whole prompt was re-billed.
  const share = (cached, input) => (cached && input ? ` (${Math.round((cached / input) * 100)}%)` : "");
  if (last?.window) {
    rows.push([
      "Context",
      last.stale ? "recomputed at the next call" : `${formatTokens(last.input + last.output)} of ${formatTokens(last.window)}`,
    ]);
    rows.push(["Last call", `${formatTokens(last.input)} in · ${formatTokens(last.output)} out${last.cached ? ` · ${formatTokens(last.cached)} cached${share(last.cached, last.input)}` : ""}${lastCost ? ` · ${lastCost}` : ""}`]);
  }
  if (total?.calls) {
    rows.push(["This session", `${formatTokens(total.input)} in · ${formatTokens(total.output)} out${total.cached ? ` · ${formatTokens(total.cached)} cached${share(total.cached, total.input)}` : ""} · ${total.calls} call${total.calls === 1 ? "" : "s"}${totalCost ? ` · ${totalCost}` : ""}`]);
  }
  if (last?.model) rows.push(["Model", last.model]);
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="tabular-nums">{v}</dd>
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
  // Right after a compaction the last reading is of the context that was
  // replaced: show an empty ring that says so rather than a stale figure.
  const stale = Boolean(details?.last?.stale);
  const pct = stale ? 0 : Math.max(0, Math.min(1, used));
  const text = stale ? "context compacted" : label;
  if (!details) return <Ring pct={pct} label={text} />;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={`Context used: ${Math.round(pct * 100)} percent. Show token usage.`}
            className="rounded-md px-1 -mx-1 hover:bg-muted transition-colors"
          >
            <Ring pct={pct} label={text} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" align="end" className="max-w-xs">
          <UsageDetails last={details.last} total={details.total} />
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
