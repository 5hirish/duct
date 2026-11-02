"use client";

import { useState } from "react";
import { Trans } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card, CardFooter } from "@/components/ui/card";
import { ExampleFrame } from "@/components/ui/empty-state";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import VendorKeyForm from "./VendorKeyForm";

// A choice of more than three is a research project, not a first step.
const MAX_CONNECTORS = 3;

/**
 * The first run of a Content Studio surface that needs a connector the
 * person brings (a scheduler for Accounts and Analytics, Apify for
 * Discover): what the surface does, what they get, and the connectors that
 * unlock it, with the filled surface beside it as an example.
 *
 * It replaced a bare "paste your key" card, and before that an error: the
 * reader had already opened the tab because they wanted the feature, and
 * neither said what the feature was. This is the `DeskDayOne` argument
 * (DESIGN.md, "First-run") applied to a connector: show the filled state,
 * say exactly what unlocks it, and make the unlock the one button.
 *
 * Props:
 *   - title, lead: what the surface does, in a heading and one sentence
 *   - benefits: [{ icon, title, text }] — three is the shape it is drawn for
 *   - connectors: [{ id, label, homeUrl, isOwner, platforms?, onConnect }] —
 *     the first three are offered; `platforms` draws "Numbers from" glyphs,
 *     which is the difference between two schedulers worth choosing on
 *   - connectLabel: the line above the connectors
 *   - footnote: whose account and who pays, in one line
 *   - example: the real component over sample props, framed as an example
 */
export default function ConnectorGate({ title, lead, benefits = [], connectors = [], connectLabel, footnote, example }) {
  const offered = connectors.slice(0, MAX_CONNECTORS);
  return (
    <section className="grid items-start gap-8 @4xl:grid-cols-2">
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {lead && <p className="mt-1 max-w-prose text-sm text-muted-foreground">{lead}</p>}
        </div>

        {benefits.length > 0 && (
          <ul className="space-y-3">
            {benefits.map(({ icon: Icon, title: benefit, text }) => (
              <li key={String(benefit)} className="flex gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-brand" aria-hidden="true">
                  <Icon className="size-4" strokeWidth={1.75} />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{benefit}</p>
                  <p className="text-xs leading-relaxed text-muted-foreground">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {offered.length > 0 && (
          <div className="space-y-2.5">
            {connectLabel && <p className="text-xs font-medium text-muted-foreground">{connectLabel}</p>}
            <div className={`grid gap-3 ${offered.length > 1 ? "@lg:grid-cols-2" : ""}`}>
              {offered.map((c) => <ConnectorOption key={c.id} connector={c} />)}
            </div>
            {footnote && <p className="text-2xs leading-relaxed text-muted-foreground">{footnote}</p>}
          </div>
        )}
      </div>

      {example && <ExampleFrame className="hidden @2xl:block">{example}</ExampleFrame>}
    </section>
  );
}

function ConnectorOption({ connector }) {
  const [open, setOpen] = useState(false);
  const vendor = connector.label;
  // A project spends its owner's key, so anyone else is told who connects it
  // rather than offered a button whose key would never be used here.
  const canConnect = connector.isOwner !== false;
  return (
    <Card size="sm">
      <h3 className="text-sm font-semibold">{vendor}</h3>
      {connector.platforms?.length > 0 && <ReportedPlatforms platforms={connector.platforms} />}
      {!open && canConnect && (
        <CardFooter>
          <Button size="sm" onClick={() => setOpen(true)}>
            <Trans>Connect {vendor}</Trans>
          </Button>
        </CardFooter>
      )}
      {(open || !canConnect) && (
        <VendorKeyForm
          layout="inline"
          vendor={vendor}
          homeUrl={connector.homeUrl}
          isOwner={connector.isOwner}
          onConnect={connector.onConnect}
        />
      )}
    </Card>
  );
}

// The channels people choose a scheduler for, in one order so two cards
// line up glyph for glyph; anything else is counted after them.
const REPORT_ORDER = ["linkedin", "twitter", "tiktok", "instagram", "youtube", "facebook", "pinterest"];

/** "Numbers from" and the platforms a scheduler reports, glyphs first. */
export function ReportedPlatforms({ platforms }) {
  const shown = REPORT_ORDER.filter((p) => platforms.includes(p));
  const rest = platforms.filter((p) => !REPORT_ORDER.includes(p));
  const restNames = rest.map((p) => platformMeta(p).label).join(", ");
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-muted-foreground">
      <span className="mr-0.5"><Trans>Numbers from</Trans></span>
      {shown.map((platform) => (
        <span key={platform} title={platformMeta(platform).label} className="inline-flex">
          <PlatformGlyph platform={platform} className="size-3.5" />
          <span className="sr-only">{platformMeta(platform).label}</span>
        </span>
      ))}
      {rest.length > 0 && (
        <span title={restNames} className="tabular-nums">
          +{rest.length}
          <span className="sr-only">{restNames}</span>
        </span>
      )}
    </div>
  );
}

/** The schedulers from GET /content/publishers as connector options. */
export function schedulerOptions(publishers, onConnect) {
  return (publishers || []).map((p) => ({
    id: p.id,
    label: p.label,
    homeUrl: p.dashboard_url,
    isOwner: p.is_owner,
    platforms: p.reports,
    onConnect: (apiKey) => onConnect(p, apiKey),
  }));
}
