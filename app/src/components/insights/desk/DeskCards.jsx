"use client";

// The desk's own cards: the ones it leads with when no waiting item is the
// news. Each belongs to one state of `arrangeDesk` (lib/desk.js), and at most
// one of them is on the page, so the mosaic rule holds by construction: one
// panel a screen, and only where someone arrives.
//
// The three bucket cards that used to live here ("Needs you", "What I found",
// "In progress") are gone. Buckets let the content decide the layout — seven
// items beside one beside an empty box — and DeskQueue's fixed slots replaced
// them (DESIGN.md, "Content awareness").

import Link from "next/link";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import MosaicPanel, { MOSAIC } from "@/components/MosaicPanel";
import { LOGOS } from "@/components/connections/logos";
import { formatDate } from "@/lib/format";

/**
 * Nothing waiting, nothing found, nothing running, and Duct has looked: the
 * desk's inbox-zero. The one place on the daily path that earns the mosaic,
 * because it is the reward for an empty queue (DESIGN.md, delight where use is
 * rare), and it says when Duct last looked so the calm is trustworthy.
 */
export function DeskAllClear({ lastChecked }) {
  return (
    <Card variant="quiet" size="lg" className="items-center gap-6 @2xl:flex-row">
      <MosaicPanel name={MOSAIC.otium} size={240} className="shrink-0" />
      <div className="flex flex-col gap-2 @2xl:max-w-sm">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {lastChecked ? (
            <Trans>Duct last looked {lastChecked} and found nothing worth your time. Enjoy the quiet.</Trans>
          ) : (
            <Trans>Duct found nothing worth your time. Enjoy the quiet.</Trans>
          )}
        </p>
      </div>
    </Card>
  );
}

/**
 * Back after a long gap. What is on the desk is old news, so the page leads
 * with the one useful act — ask Duct to look again — under the threshold
 * mosaic that greets an arrival (`salve`). Only a click starts a run: opening
 * the page never spends a model call.
 */
export function DeskFreshLook({ lookedAt, onAsk }) {
  const { t, i18n } = useLingui();
  const since = formatDate(lookedAt, { locale: i18n.locale, withYear: false });
  return (
    <Card variant="hero" size="lg" className="items-center gap-6 @2xl:flex-row">
      <MosaicPanel name={MOSAIC.salve} size={240} className="shrink-0" />
      <div className="flex min-w-0 flex-col items-start gap-4 @2xl:max-w-sm">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold">
            <Trans>Welcome back. Take a fresh look?</Trans>
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            <Trans>Duct reads your sources again and tells you what changed since {since}.</Trans>
          </p>
        </div>
        <Button onClick={() => onAsk(t`What changed since ${since}?`)}>
          <Trans>Take a fresh look</Trans>
        </Button>
      </div>
    </Card>
  );
}

// The connectors a first source most often is. Logos, not a list of names:
// the reader recognises them before reading them.
const FIRST_SOURCES = ["gsc", "ga4", "google_ads", "stripe"];

/**
 * The one thing to do while nothing is connected: the screen's hero.
 * `returning` is a desk that had sources and lost them, which is not a first.
 */
export function DeskConnectFirst({ returning = false }) {
  return (
    <Card variant="hero" size="lg" className="gap-5 @2xl:flex-row @2xl:items-center">
      <div className="flex shrink-0 -space-x-2" aria-hidden>
        {FIRST_SOURCES.map((key) => (
          <span
            key={key}
            className="flex size-11 items-center justify-center rounded-xl border bg-background ring-4 ring-card [&_img]:size-6 [&_svg]:size-6"
          >
            {LOGOS[key]}
          </span>
        ))}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {returning ? (
          <>
            <p className="text-sm font-semibold">
              <Trans>Reconnect a source</Trans>
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">
              <Trans>Duct can't read anything right now. What it found before is still below.</Trans>
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-semibold">
              <Trans>Connect your first source</Trans>
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">
              <Trans>Search Console is the easiest start. Your first brief takes about three minutes.</Trans>
            </p>
          </>
        )}
      </div>
      <Button asChild className="shrink-0 self-start @2xl:self-center">
        <Link href="/connections">
          <Trans>Connect a source</Trans>
        </Link>
      </Button>
    </Card>
  );
}
