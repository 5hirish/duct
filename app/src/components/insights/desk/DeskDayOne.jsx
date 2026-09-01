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
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SAMPLE_FINDINGS = [
  { title: "Real upgrades: 13, not 36.", detail: "23 came from your own team" },
  { title: "Ads says 4,212. Stripe settled 1,890.", detail: "Nobody had compared them" },
  { title: "An A/B test live 74 days with nobody in it.", detail: "Every dashboard called it healthy" },
];

const SAMPLE_RUNNING = [
  { title: "Where the funnel actually breaks", detail: "You'd pick this back up here" },
  { title: "Nightly check", detail: "Runs whether you are here or not" },
];

const SITE_QUESTIONS = [
  "Which pages should rank and don't?",
  "What is my site actually about?",
  "Where do competitors beat me?",
];

const DATA_QUESTIONS = [
  "Are my conversions real people?",
  "Did anything stop working?",
  "Did the revenue actually arrive?",
];

function Step({ done, title, children }) {
  return (
    <li className="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-3">
      <span
        className={cn(
          "mt-0.5 flex size-[17px] items-center justify-center rounded-full",
          done ? "bg-emerald-500/20" : "border-[1.5px] border-primary"
        )}
        aria-hidden
      >
        {done && <Check className="size-2.5 text-emerald-600 dark:text-emerald-400" strokeWidth={3.5} />}
      </span>
      <div>
        <p className={cn("text-[13.5px] font-medium leading-snug", done && "text-muted-foreground line-through")}>
          {title}
        </p>
        {!done && children}
      </div>
    </li>
  );
}

function SampleCard({ label, blurb, rows }) {
  return (
    <section className="flex flex-col rounded-xl border border-dashed p-5">
      <header className="mb-3 flex items-center gap-2.5">
        <span className="size-[7px] rounded-full bg-muted-foreground/40" aria-hidden />
        <h2 className="text-[13px] font-bold tracking-tight text-muted-foreground">{label}</h2>
        <span className="ml-auto rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Example
        </span>
      </header>
      <p className="mb-4 text-[11.5px] leading-relaxed text-muted-foreground">{blurb}</p>
      <div className="flex flex-col gap-4 opacity-60">
        {rows.map((row) => (
          <div key={row.title}>
            <p className="text-[13px] font-medium leading-snug">{row.title}</p>
            <p className="mt-1 text-[11.5px] text-muted-foreground">{row.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DeskDayOne({ hasWebsite, sourceCount, hasThread, onAsk }) {
  const done = [hasWebsite, sourceCount > 0, hasThread].filter(Boolean).length;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight">
          Duct checks a number before it trusts it.
        </h1>
        <p className="mt-2.5 max-w-[660px] text-sm leading-relaxed text-muted-foreground">
          Most reporting problems aren&apos;t bad decisions — they&apos;re good decisions made on
          numbers nobody checked. Three steps and this page starts filling itself in.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr_1fr]">
        <section className="flex flex-col rounded-xl border border-destructive/40 bg-card p-5">
          <header className="mb-4 flex items-center gap-2.5">
            <span className="size-[7px] rounded-full bg-destructive" aria-hidden />
            <h2 className="text-[13px] font-bold tracking-tight">Needs you</h2>
            <span className="ml-auto text-[11.5px] text-muted-foreground">{done} of 3 done</span>
          </header>

          <ol className="flex flex-col gap-4">
            <Step done={hasWebsite} title="Add your website">
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
                So I know what the account is for.
              </p>
              <Button asChild size="sm" className="mt-2.5 h-7 rounded-full text-[12.5px]">
                <Link href="/projects">Add it</Link>
              </Button>
            </Step>

            <Step done={sourceCount > 0} title="Connect one data source">
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
                Google Ads, GA4 or Mixpanel. This is the step that changes everything — I
                can&apos;t check a number I can&apos;t see.
              </p>
              <Button asChild size="sm" className="mt-2.5 h-7 rounded-full text-[12.5px]">
                <Link href="/connections">Connect a source</Link>
              </Button>
            </Step>

            <Step done={hasThread} title="Ask me something">
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
                Pick one of the questions below, or type your own.
              </p>
            </Step>
          </ol>
        </section>

        <SampleCard
          label="What I found"
          blurb="Real problems from a real account. Nothing lands here unchecked."
          rows={SAMPLE_FINDINGS}
        />
        <SampleCard
          label="In progress"
          blurb="Work still moving — mine or yours. Nothing here waits on you."
          rows={SAMPLE_RUNNING}
        />
      </div>

      <div>
        <h2 className="mb-3.5 text-[13px] font-bold uppercase tracking-[0.02em] text-muted-foreground">
          Start with a question
        </h2>
        <div className="flex flex-wrap gap-2">
          {SITE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onAsk(q)}
              className="rounded-full border bg-card px-4 py-2 text-[13px] transition-colors hover:bg-accent"
            >
              {q}
            </button>
          ))}
        </div>

        {sourceCount === 0 && (
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            <span className="mr-0.5 text-[11.5px] text-muted-foreground">
              Once you connect a source:
            </span>
            {DATA_QUESTIONS.map((q) => (
              <span
                key={q}
                className="rounded-full border border-dashed px-3.5 py-1.5 text-[12.5px] text-muted-foreground"
              >
                {q}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
