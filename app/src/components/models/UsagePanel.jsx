"use client";

/**
 * What Duct spent running your agents — the whole Usage view, minus a heading.
 *
 * Lifted out of `app/(app)/usage/page.jsx` rather than copied, because it now
 * has two homes: that route (reached from the sidebar) and the third tab on
 * Models & providers. Two homes and two implementations is how one of them
 * stops matching the API — and this one reads a shape with six fields.
 *
 * Three breakdowns rather than one chart, because they answer three different
 * questions people arrive with. "Which agent is expensive" is a decision about
 * what to run. "Which model is expensive" is a decision about the tier map.
 * "Which provider" is a decision about keys. A single stacked chart would
 * answer none of them without a legend nobody reads.
 *
 * It also does a second job quietly, and it is the reason this belongs beside
 * the tier pickers rather than only in the sidebar: seeing that the expensive
 * model was 2% of the month and wrote the brief is the entire argument for the
 * Heavy/Standard/Light split, made in numbers the user already trusts, without
 * the word "tier" appearing anywhere.
 *
 * ── On the empty states, which are most of what this file now is ──
 *
 * An empty window used to render one muted sentence and a "Run something"
 * button, and that button was wrong for half the people who saw it. "No model
 * calls in the last 30 days" covers two situations that want opposite actions:
 * somebody who has never run an agent, and somebody who ran plenty in March
 * and is looking at April. Telling the second one to go run something implies
 * their spending vanished. So the empty path spends one extra read of the
 * widest window to tell them apart, and says the true thing either way.
 *
 * The never-ran case then gets the sample below rather than a sentence,
 * because this page's whole argument is a shape — a tiny bar next to the
 * biggest number — and you cannot make that argument in prose to somebody who
 * has not seen the layout yet. `SAMPLE_USAGE` goes through `UsageReport`, the
 * same component the real data goes through, for the obvious reason: a sample
 * built out of its own markup is a sample that drifts.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Cpu, KeyRound, Layers, LockKeyhole, Wallet } from "lucide-react";
import { hasAuthToken } from "@/lib/authFetch";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import LoadError from "@/components/LoadError";
import {
  DEFAULT_WINDOW_DAYS,
  EMPTY_USAGE,
  WIDEST_WINDOW_DAYS,
  WINDOWS,
  agentLabel,
  fetchUsage,
  formatCost,
  formatTokens,
  providerLabel,
  share,
} from "@/lib/usageApi";
import { modelLabel } from "@/lib/modelTiers";

/**
 * A month that makes the tier argument by itself: the Heavy model is 2% of the
 * calls and 40% of the bill. Every column adds up — the rows sum to the total,
 * because somebody will check, and a sample that doesn't add up teaches the
 * reader to distrust the real one.
 *
 * The labels are spelled out rather than being model ids, since the catalogue
 * that turns an id into a name is the user's own and a first-run reader has
 * none. They are the only strings here the real path would not produce.
 */
const SAMPLE_USAGE = Object.freeze({
  window_days: 30,
  total: {
    calls: 1284,
    input_tokens: 3_600_000,
    output_tokens: 610_000,
    cached_tokens: 2_560_000,
    total_tokens: 4_210_000,
    cost_usd: 6.41,
  },
  by_agent: [
    { key: "insights", calls: 742, total_tokens: 2_450_000, cached_tokens: 1_690_000, cost_usd: 3.62 },
    { key: "audit", calls: 388, total_tokens: 1_180_000, cached_tokens: 640_000, cost_usd: 1.94 },
    { key: "content", calls: 154, total_tokens: 580_000, cached_tokens: 230_000, cost_usd: 0.85 },
  ],
  by_model: [
    { key: "standard", calls: 604, total_tokens: 2_690_000, cached_tokens: 1_980_000, cost_usd: 3.12 },
    { key: "light", calls: 649, total_tokens: 1_260_000, cached_tokens: 490_000, cost_usd: 0.71 },
    { key: "heavy", calls: 31, total_tokens: 260_000, cached_tokens: 90_000, cost_usd: 2.58 },
  ],
  by_provider: [
    { key: "anthropic", calls: 1190, total_tokens: 3_950_000, cached_tokens: 2_430_000, cost_usd: 6.02 },
    { key: "openai", calls: 94, total_tokens: 260_000, cached_tokens: 130_000, cost_usd: 0.39 },
  ],
  daily: [],
});

const SAMPLE_MODEL_NAMES = {
  heavy: "Heavy — the deep model",
  standard: "Standard — the everyday model",
  light: "Light — the cheap one",
};

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
        <p className="app-subtle usage-empty-line">{empty}</p>
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

/**
 * The filled view: four figures and three breakdowns. Split out from the panel
 * so the empty state can render it over invented numbers — the sample and the
 * real thing are the same component or the sample is a lie about the product.
 */
function UsageReport({ usage, modelName }) {
  const total = usage.total || EMPTY_USAGE.total;
  const cost = formatCost(total.cost_usd);
  const cachedShare = total.input_tokens
    ? Math.round((total.cached_tokens / total.input_tokens) * 100)
    : 0;

  return (
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
          labelFor={modelName}
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
    </>
  );
}

/**
 * The empty window, in its two meanings.
 *
 * Exported because `/preview` renders fixtures and never the API, and this
 * panel's first paint is a fetch — without a seam here the two states most
 * worth reviewing would be the two nobody could open. `earlier` is the widest
 * window's totals when there is earlier spending to point at, and null when
 * there is not; that one prop is the whole difference between the two
 * readings, so it is the whole prop list.
 */
export function UsageEmpty({ windowDays, earlier = null, onWiden }) {
  if (earlier) {
    const cost = formatCost(earlier.cost_usd);
    return (
      // Ran before, just not lately. The action is a wider window, not a nudge
      // to go and spend money they have already spent.
      <EmptyState
        icon={Wallet}
        title={`Nothing ran in the last ${windowDays} days`}
        actions={
          <>
            <Button size="sm" onClick={onWiden}>
              Show {WIDEST_WINDOW_DAYS} days
            </Button>
            <Button size="sm" variant="ghost" asChild>
              <Link href="/insights/organic-growth">Ask a question</Link>
            </Button>
          </>
        }
      >
        Your key was charged {cost ?? `${formatTokens(earlier.total_tokens)} tokens`} across{" "}
        {earlier.calls.toLocaleString()} model calls in the last {WIDEST_WINDOW_DAYS} days. This
        window is just a quiet one.
      </EmptyState>
    );
  }

  return (
    // Nothing has ever run. Show the page working rather than describing it:
    // the point this page exists to make is a shape, and a shape does not
    // survive being put into a sentence.
    <EmptyState
      icon={Wallet}
      title="Nothing has run on your key yet"
      exampleLabel="Example month"
      example={<UsageReport usage={SAMPLE_USAGE} modelName={(key) => SAMPLE_MODEL_NAMES[key]} />}
      actions={
        <>
          <Button size="sm" asChild>
            <Link href="/insights/organic-growth">Ask a question</Link>
          </Button>
          <Button size="sm" variant="ghost" asChild>
            <Link href="/start">Audit a site</Link>
          </Button>
        </>
      }
    >
      Your first agent run fills this in. Below is a normal month.
    </EmptyState>
  );
}

/**
 * `catalogue` is optional and only makes the "by model" rows read in the same
 * words the pickers use. Usage rows carry the id the *provider* answered with,
 * which can be a model the catalogue never listed — an alias, or a fallback
 * step — so an unknown id renders as itself rather than being dropped.
 *
 * `standalone` adds the pointer back to this page's own settings. Inside the
 * tab that link would land on the tab it was clicked from.
 */
export default function UsagePanel({ catalogue = null, standalone = false }) {
  const [usage, setUsage] = useState(EMPTY_USAGE);
  // What the widest window holds, read only when the chosen one came back
  // empty. Null means "not asked, or asked and it was empty too" — either way
  // there is no earlier spending to point at.
  const [earlier, setEarlier] = useState(null);
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
    setEarlier(null);
    try {
      const data = await fetchUsage({ windowDays: days });
      setUsage(data);
      if (!data.total?.calls && days < WIDEST_WINDOW_DAYS) {
        try {
          const wide = await fetchUsage({ windowDays: WIDEST_WINDOW_DAYS });
          if (wide.total?.calls) setEarlier(wide);
        } catch {
          // A failed probe is not a failed page. Falling through leaves the
          // first-run copy, which is wrong for one reader rather than broken
          // for every reader.
        }
      }
      // Flipped after the probe on purpose: resolving it later would show the
      // first-run sample for a beat and then yank it away.
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

  const modelName = (id) => {
    const model = (catalogue?.models ?? []).find((entry) => entry.id === id);
    return model ? modelLabel(model) : id || "Other";
  };

  return (
    <>
      <div className="usage-head">
        <p className="app-subtle mt-lede">
          What Duct spent running your agents. These are charges on your own provider key —
          Duct never bills them.
        </p>
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
        <EmptyState
          icon={LockKeyhole}
          title="Sign in to see what your runs cost"
          actions={
            <Button size="sm" asChild>
              <Link href="/">Sign in</Link>
            </Button>
          }
        >
          Spending is per account, and every figure on this page is a charge on your own
          provider key.
        </EmptyState>
      ) : state === "error" ? (
        <LoadError what="your usage" detail={error} onRetry={() => load(windowDays)} />
      ) : state === "loading" ? (
        <p className="app-subtle usage-empty-line">Adding it up…</p>
      ) : total.calls === 0 ? (
        <UsageEmpty
          windowDays={usage.window_days}
          earlier={earlier?.total ?? null}
          onWiden={() => setWindowDays(WIDEST_WINDOW_DAYS)}
        />
      ) : (
        <>
          <UsageReport usage={usage} modelName={modelName} />

          {standalone && (
            <p className="app-subtle usage-foot">
              Which model runs which job is set in{" "}
              <Link href="/settings/models">Models &amp; providers</Link>.
            </p>
          )}
        </>
      )}
    </>
  );
}
