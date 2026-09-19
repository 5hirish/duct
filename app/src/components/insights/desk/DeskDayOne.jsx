"use client";

// Day one — the same three columns, so nothing jumps once they fill.
//
// It replaces "No insights yet", which is the least useful true sentence
// available: Duct already knows what it can reach, what it cannot, and which
// questions are answerable right now. Two of the cards carry clearly-labelled
// SAMPLES — real failure classes from a real account — so you can see what is
// on offer before granting anything.
//
// There is no check scoreboard here on purpose. On day one it would be an
// empty board, and an empty board teaches nothing.

import Link from "next/link";
import { Check } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SAMPLE_FINDINGS = [
  { title: msg`Real upgrades: 13, not 36.`, detail: msg`23 came from your own team` },
  { title: msg`Ads says 4,212. Stripe settled 1,890.`, detail: msg`Nobody had compared them` },
  { title: msg`An A/B test live 74 days with nobody in it.`, detail: msg`Every dashboard called it healthy` },
];

const SAMPLE_RUNNING = [
  { title: msg`Where the funnel actually breaks`, detail: msg`You'd pick this back up here` },
  { title: msg`Nightly check`, detail: msg`Runs whether you are here or not` },
];

const SITE_QUESTIONS = [
  msg`Which pages should rank and don't?`,
  msg`What is my site actually about?`,
  msg`Where do competitors beat me?`,
];

const DATA_QUESTIONS = [
  msg`Are my conversions real people?`,
  msg`Did anything stop working?`,
  msg`Did the revenue actually arrive?`,
];

function Step({ done, title, children }) {
  return (
    <li className="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-3">
      <span
        className={cn(
          "mt-0.5 flex size-[17px] items-center justify-center rounded-full",
          done ? "bg-success/20" : "border-[1.5px] border-primary"
        )}
        aria-hidden
      >
        {done && <Check className="size-2.5 text-success" strokeWidth={3.5} />}
      </span>
      <div>
        <p className={cn("text-sm font-medium leading-snug", done && "text-muted-foreground line-through")}>
          {title}
        </p>
        {!done && children}
      </div>
    </li>
  );
}

function SampleCard({ label, blurb, rows }) {
  const { i18n } = useLingui();
  return (
    <section className="flex flex-col rounded-xl border border-dashed p-5">
      <header className="mb-3 flex items-center gap-2.5">
        <span className="size-[7px] rounded-full bg-muted-foreground/40" aria-hidden />
        <h2 className="text-sm font-bold tracking-tight text-muted-foreground">{label}</h2>
        <span className="ml-auto rounded-full border px-2 py-0.5 text-2xs font-medium uppercase tracking-wider text-muted-foreground">
          <Trans>Example</Trans>
        </span>
      </header>
      <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{blurb}</p>
      <div className="flex flex-col gap-4 opacity-60">
        {rows.map((row) => (
          <div key={row.title.id}>
            <p className="text-sm font-medium leading-snug">{i18n._(row.title)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{i18n._(row.detail)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DeskDayOne({ hasProject, sourceCount, hasThread, onAsk }) {
  const { t, i18n } = useLingui();
  const done = [hasProject, sourceCount > 0, hasThread].filter(Boolean).length;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-bold leading-tight tracking-tight">
          <Trans>Duct checks a number before it trusts it.</Trans>
        </h1>
        <p className="measure mt-2.5 text-sm leading-relaxed text-muted-foreground">
          <Trans>
            Most reporting problems aren’t bad decisions — they’re good decisions made on
            numbers nobody checked. Three steps and this page starts filling itself in.
          </Trans>
        </p>
      </div>

      <div className="grid gap-4 @3xl:grid-cols-[1.35fr_1fr_1fr]">
        <section className="flex flex-col rounded-xl border border-destructive/40 bg-card p-5">
          <header className="mb-4 flex items-center gap-2.5">
            <span className="size-[7px] rounded-full bg-destructive" aria-hidden />
            <h2 className="text-sm font-bold tracking-tight"><Trans>Needs you</Trans></h2>
            <span className="ml-auto text-xs text-muted-foreground"><Trans>{done} of 3 done</Trans></span>
          </header>

          <ol className="flex flex-col gap-4">
            {/* A project starts from a site: /start reads it and drafts the
                rest, so "add a project" and "audit a site" are the same
                click. The project is the thing everything else hangs off —
                sources, threads and claims are all scoped to one. */}
            <Step done={hasProject} title={t`Add a project`}>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                <Trans>One site or account. Everything I check hangs off it.</Trans>
              </p>
              <Button asChild size="sm" className="mt-2.5 h-7 rounded-full text-xs">
                <Link href="/start"><Trans>Audit a site</Trans></Link>
              </Button>
            </Step>

            <Step done={sourceCount > 0} title={t`Connect one data source`}>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                <Trans>
                  Google Ads, GA4 or Mixpanel. This is the step that changes everything — I
                  can’t check a number I can’t see.
                </Trans>
              </p>
              <Button asChild size="sm" className="mt-2.5 h-7 rounded-full text-xs">
                <Link href="/connections"><Trans>Connect a source</Trans></Link>
              </Button>
            </Step>

            <Step done={hasThread} title={t`Ask me something`}>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                <Trans>Pick one of the questions below, or type your own.</Trans>
              </p>
            </Step>
          </ol>
        </section>

        <SampleCard
          label={t`What I found`}
          blurb={t`Real problems from a real account. Nothing lands here unchecked.`}
          rows={SAMPLE_FINDINGS}
        />
        <SampleCard
          label={t`In progress`}
          blurb={t`Work still moving — mine or yours. Nothing here waits on you.`}
          rows={SAMPLE_RUNNING}
        />
      </div>

      <div>
        <h2 className="mb-3.5 text-sm font-bold uppercase tracking-[0.02em] text-muted-foreground">
          <Trans>Start with a question</Trans>
        </h2>
        <div className="flex flex-wrap gap-2">
          {SITE_QUESTIONS.map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => onAsk(i18n._(q))}
              className="rounded-full border bg-card px-4 py-2 text-sm transition-colors hover:bg-accent"
            >
              {i18n._(q)}
            </button>
          ))}
        </div>

        {sourceCount === 0 && (
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            <span className="mr-0.5 text-xs text-muted-foreground">
              <Trans>Once you connect a source:</Trans>
            </span>
            {DATA_QUESTIONS.map((q) => (
              <span
                key={q.id}
                className="rounded-full border border-dashed px-3.5 py-1.5 text-xs text-muted-foreground"
              >
                {i18n._(q)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
