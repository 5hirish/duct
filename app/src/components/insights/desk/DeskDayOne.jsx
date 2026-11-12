"use client";

// Day one: what to do first, then what this page will hold once it fills.
//
// It replaces "No insights yet", the least useful true sentence available:
// Duct already knows what it can reach and which questions are answerable now.
// One hero card holds the three steps, because on day one they are the only
// thing worth doing; the questions and the two labelled examples sit below it
// at a lower weight. The example numbers are invented on purpose: this page is
// public code, and a figure from a real account does not belong in it.

import Link from "next/link";
import { Check } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Page, PageHeader, Section, TileGrid } from "@/components/ui/page";
import { cn } from "@/lib/utils";

const SAMPLE_FINDINGS = [
  { title: msg`Real signups: 118, not 164.`, detail: msg`46 were your own team testing` },
  { title: msg`Ads counts 2,310 conversions. Stripe settled 1,402.`, detail: msg`Nobody had compared them` },
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

function Step({ done, title, children }) {
  return (
    <li className="grid grid-cols-[1.25rem_minmax(0,1fr)] items-start gap-3">
      <span
        className={cn(
          "mt-0.5 flex size-5 items-center justify-center rounded-full",
          done ? "bg-success/20" : "border-2 border-primary"
        )}
        aria-hidden
      >
        {done && <Check className="size-3 text-success" strokeWidth={3} />}
      </span>
      <div className="flex flex-col gap-2">
        <p className={cn("text-sm font-semibold", done && "font-normal text-muted-foreground line-through")}>
          {title}
        </p>
        {!done && children}
      </div>
    </li>
  );
}

function SampleCard({ label, rows }) {
  const { i18n } = useLingui();
  return (
    <Card variant="quiet">
      <header className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-muted-foreground">{label}</h2>
        <span className="ml-auto rounded-full border px-2 text-2xs font-medium leading-5 text-muted-foreground">
          <Trans>Example</Trans>
        </span>
      </header>
      {/* Invented rows drawn as the real thing would be; kept out of the
          accessibility tree so nobody is read a figure as fact. */}
      <div className="flex flex-col gap-3" aria-hidden>
        {rows.map((row) => (
          <div key={row.title.id}>
            <p className="text-sm font-medium">{i18n._(row.title)}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{i18n._(row.detail)}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function DeskDayOne({ greeting, hasProject, sourceCount, hasThread, onAsk }) {
  const { t, i18n } = useLingui();
  const done = [hasProject, sourceCount > 0, hasThread].filter(Boolean).length;

  return (
    <Page className="flex-1">
      <PageHeader
        size="hero"
        eyebrow={greeting}
        title={<Trans>Let&rsquo;s get your desk set up.</Trans>}
        status={<Trans>{done} of 3 done. It fills itself in after that.</Trans>}
      />

      <Card variant="hero" size="lg">
        <ol className="flex flex-col gap-6">
          {/* A project starts from a site: /start reads it and drafts the
              rest, so "add a project" and "audit a site" are the same click. */}
          <Step done={hasProject} title={t`Add your site`}>
            <Button asChild size="sm" className="self-start">
              <Link href="/start"><Trans>Audit a site</Trans></Link>
            </Button>
          </Step>
          <Step done={sourceCount > 0} title={t`Connect one data source`}>
            <p className="text-sm text-muted-foreground">
              <Trans>Search Console, Analytics or Google Ads. Duct can&rsquo;t check a number it can&rsquo;t see.</Trans>
            </p>
            <Button asChild size="sm" className="self-start">
              <Link href="/connections"><Trans>Connect a source</Trans></Link>
            </Button>
          </Step>
          <Step done={hasThread} title={t`Ask Duct something`}>
            <div className="flex flex-wrap gap-2">
              {SITE_QUESTIONS.map((q) => (
                <Button key={q.id} type="button" variant="outline" size="sm" onClick={() => onAsk(i18n._(q))}>
                  {i18n._(q)}
                </Button>
              ))}
            </div>
          </Step>
        </ol>
      </Card>

      <Section title={<Trans>What this page will hold</Trans>}>
        <TileGrid cols={2}>
          <SampleCard label={t`What I found`} rows={SAMPLE_FINDINGS} />
          <SampleCard label={t`In progress`} rows={SAMPLE_RUNNING} />
        </TileGrid>
      </Section>
    </Page>
  );
}
