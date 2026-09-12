"use client";

// Usage — what Duct spent on your provider key.
//
// Under bring-your-own-key every figure here is a charge on the user's own
// account, which is why this page exists at all: Duct was computing the number
// per model call and throwing it away, so the one person actually paying could
// not see it.
//
// Three breakdowns rather than one chart, because they answer three different
// questions people arrive with. "Which agent is expensive" is a decision about
// what to run. "Which model is expensive" is a decision about the tier map.
// "Which provider" is a decision about keys. A single stacked chart would
// answer none of them without a legend nobody reads.
//
// It also does a second job quietly: seeing that the expensive model was 2% of
// the month and wrote the brief is the entire argument for the Heavy/Standard/
// Light split, made in numbers the user already trusts, without the word
// "tier" appearing anywhere.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Gauge, Layers, Cpu, KeyRound } from "lucide-react";
import { hasAuthToken } from "../../../lib/authFetch";
import { Button } from "@/components/ui/button";
import {
  DEFAULT_WINDOW_DAYS,
  EMPTY_USAGE,
  WINDOWS,
  agentLabel,
  fetchUsage,
  formatCost,
  formatTokens,
  providerLabel,
  share,
} from "@/lib/usageApi";

/** One number, said plainly. */
function Stat({ label, value, hint }) {
  return (
    <div className="usage-stat">
      <span className="usage-stat-label">{label}</span>
      <strong className="usage-stat-value">{value}</strong>
      {hint ? <span className="usage-stat-hint">{hint}</span> : null}
    </div>
  );
}

/**
 * A breakdown. The bar is the share of the window's total, so the eye gets the
 * proportion before it reads any number — which is the whole point of showing
 * a breakdown rather than a list.
 */
function Breakdown({ title, icon: Icon, rows, total, labelFor, empty }) {
  return (
    <section className="usage-panel">
      <h2 className="usage-panel-title">
        <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="app-subtle usage-empty">{empty}</p>
      ) : (
        <ul className="usage-rows">
          {rows.map((row) => {
            const cost = formatCost(row.cost_usd);
            return (
              <li key={row.key} className="usage-row">
                <div className="usage-row-head">
                  <span className="usage-row-name">{labelFor(row.key)}</span>
                  {/* No dollar figure rather than a made-up one: the price
                      table does not know every model, and $0.00 would read as
                      free. */}
                  <span className="usage-row-cost">{cost ?? formatTokens(row.total_tokens)}</span>
                </div>
                <div
                  className="usage-bar"
                  role="img"
                  aria-label={`${Math.round(share(row.total_tokens, total) * 100)}% of tokens`}
                >
                  <span style={{ width: `${share(row.total_tokens, total) * 100}%` }} />
                </div>
                <div className="usage-row-foot app-subtle">
                  {formatTokens(row.total_tokens)} tokens · {row.calls.toLocaleString()} calls
                  {row.cached_tokens > 0 ? ` · ${formatTokens(row.cached_tokens)} cached` : ""}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function UsagePage() {
  const [usage, setUsage] = useState(EMPTY_USAGE);
  const [windowDays, setWindowDays] = useState(DEFAULT_WINDOW_DAYS);
  const [state, setState] = useState("loading"); // loading | ready | error | signed-out
  const [error, setError] = useState("");

  const load = useCallback(async (days) => {
    if (!hasAuthToken()) {
      setState("signed-out");
      return;
    }
    setState("loading");
    setError("");
    try {
      setUsage(await fetchUsage({ windowDays: days }));
      setState("ready");
    } catch (err) {
      setError(String(err?.message || err));
      setState("error");
    }
  }, []);

  useEffect(() => {
    load(windowDays);
  }, [load, windowDays]);

  const total = usage.total || EMPTY_USAGE.total;
  const cost = formatCost(total.cost_usd);
  const cachedShare = total.input_tokens
    ? Math.round((total.cached_tokens / total.input_tokens) * 100)
    : 0;

  return (
    <>
      <div className="usage-head">
        <div>
          <h1 className="app-title">
            <Gauge size={20} strokeWidth={1.75} aria-hidden="true" />
            Usage
          </h1>
          <p className="app-subtle mt-lede">
            What Duct spent running your agents. These are charges on your own provider key —
            Duct never bills them.
          </p>
        </div>
        <div className="usage-windows" role="group" aria-label="Time window">
          {WINDOWS.map((w) => (
            <Button
              key={w.days}
              size="sm"
              variant={w.days === windowDays ? "secondary" : "ghost"}
              onClick={() => setWindowDays(w.days)}
              aria-pressed={w.days === windowDays}
            >
              {w.label}
            </Button>
          ))}
        </div>
      </div>

      {state === "signed-out" ? (
        <p className="app-subtle usage-empty">Sign in to see what your runs have cost.</p>
      ) : state === "error" ? (
        <div className="usage-empty">
          <p className="app-subtle">{error}</p>
          <Button size="sm" onClick={() => load(windowDays)}>
            Try again
          </Button>
        </div>
      ) : state === "loading" ? (
        <p className="app-subtle usage-empty">Adding it up…</p>
      ) : total.calls === 0 ? (
        // An empty window is not an error and not a blank page: say which
        // window is empty, and point at the thing that fills it.
        <div className="usage-empty">
          <p className="app-subtle">
            No model calls in the last {usage.window_days} days. Usage appears here as soon as an
            agent runs.
          </p>
          <Button size="sm" asChild>
            <Link href="/insights/organic-growth">Run something</Link>
          </Button>
        </div>
      ) : (
        <>
          <div className="usage-stats">
            <Stat
              label="Spent"
              value={cost ?? "—"}
              hint={cost ? `over ${usage.window_days} days` : "no price for these models"}
            />
            <Stat
              label="Tokens"
              value={formatTokens(total.total_tokens)}
              hint={`${formatTokens(total.input_tokens)} in · ${formatTokens(total.output_tokens)} out`}
            />
            <Stat label="Model calls" value={total.calls.toLocaleString()} />
            {/* Cached input is the one number here a user can act on without
                changing anything: it is the discount prompt caching already
                won them, and it goes down when a prompt churns. */}
            <Stat
              label="Cached input"
              value={`${cachedShare}%`}
              hint="charged at a fraction of the rate"
            />
          </div>

          <div className="usage-grid">
            <Breakdown
              title="By agent"
              icon={Layers}
              rows={usage.by_agent}
              total={total.total_tokens}
              labelFor={agentLabel}
              empty="Nothing ran in this window."
            />
            <Breakdown
              title="By model"
              icon={Cpu}
              rows={usage.by_model}
              total={total.total_tokens}
              labelFor={(k) => k}
              empty="No model calls in this window."
            />
            <Breakdown
              title="By provider"
              icon={KeyRound}
              rows={usage.by_provider}
              total={total.total_tokens}
              labelFor={providerLabel}
              empty="No provider recorded."
            />
          </div>

          <p className="app-subtle usage-foot">
            Which model runs which job is set in{" "}
            <Link href="/settings/models">Models &amp; providers</Link>.
          </p>
        </>
      )}
    </>
  );
}
