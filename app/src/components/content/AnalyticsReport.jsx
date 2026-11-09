"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Plug, RefreshCw, Share2, Sparkles } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { HelpTip, Section } from "@/components/ui/page";
import { Skeleton } from "@/components/ui/skeleton";
import Reveal from "@/components/ui/reveal";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LOGOS } from "@/components/connections/logos";
import GrowthReportView from "./report/GrowthReportView";
import { generateAnalyticsReport, getAnalyticsReport } from "@/lib/contentApi";
import {
  ReportState,
  SourceStatus,
  reconcileSelection,
  reportBody,
  reportState,
  ttlHours,
} from "@/lib/analyticsReport";
import { formatDate, formatTime, relativeTime } from "@/lib/format";
import { pollWhileVisible } from "@/lib/visibility";

/**
 * The growth report on the Analytics tab: pick a template and the sources to
 * read, Duct's insights agent writes the report once, the tab serves it for
 * a day and Refresh writes it again. The report itself is
 * `report/GrowthReportView`; this owns the choosing, the states and the wait.
 *
 * Nothing regenerates on its own. A run is a model call on the person's own
 * key, so the day-old copy stays on screen marked stale and the one thing
 * that spends again is the button. While a run writes, the old copy (if any)
 * stays up with the status line saying what is being read; the tab polls the
 * read while visible (`lib/visibility.js`) and swaps in the new one.
 *
 * `reads` is injectable so /preview can draw every state over fixtures.
 */

const API_READS = Object.freeze({ get: getAnalyticsReport, generate: generateAnalyticsReport });

// A run reads several sources and writes a dozen blocks: a minute or two.
const POLL_MS = 5000;

const SOURCE_REASON = {
  [SourceStatus.NEEDS_ACCOUNT]: msg`Choose an account in the Toolbox first`,
  [SourceStatus.NEEDS_ATTENTION]: msg`Needs signing in again`,
  [SourceStatus.NOT_CONNECTED]: msg`Not connected`,
};

export default function AnalyticsReport({ projectId, onLinkAccounts, reads = API_READS, initialTemplate = "" }) {
  const { t, i18n } = useLingui();
  const [payload, setPayload] = useState(null);
  const [template, setTemplate] = useState(initialTemplate);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  // A request that failed (the read, or the start): one line, role=alert.
  // Distinct from a run that failed, which the payload carries.
  const [requestError, setRequestError] = useState("");
  // Held in a ref: a caller passing `reads={{ … }}` inline (every /preview
  // scene does) would otherwise give `load` a new identity on each render
  // and the effect below a reason to fetch forever.
  const readsRef = useRef(reads);
  readsRef.current = reads;

  const load = useCallback(async (tmpl) => {
    try {
      const data = await readsRef.current.get(projectId, { template: tmpl || "" });
      setPayload(data);
      setTemplate(data?.template?.id || tmpl || "");
      setSelected((prev) => reconcileSelection(prev, data?.sources));
      setRequestError("");
    } catch (e) {
      setRequestError(e.message || t`Couldn't load the report.`);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => { setLoading(true); load(template); }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const state = reportState(payload);
  const generating = state === ReportState.GENERATING;

  // While a run writes, read again every few seconds the page is visible.
  useEffect(() => {
    if (!generating) return undefined;
    return pollWhileVisible(() => load(template), POLL_MS);
  }, [generating, load, template]);

  async function pickTemplate(id) {
    if (id === template) return;
    setTemplate(id);
    setLoading(true);
    // The selection starts over for a template: its sources differ.
    setSelected([]);
    await load(id);
  }

  function toggleSource(id) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function generate() {
    setStarting(true);
    setRequestError("");
    try {
      const data = await readsRef.current.generate(projectId, { template, sources: selected });
      setPayload(data);
    } catch (e) {
      setRequestError(e.message || t`Couldn't start the report.`);
    } finally {
      setStarting(false);
    }
  }

  const sources = payload?.sources || [];
  const ready = useMemo(() => sources.filter((s) => s.status === SourceStatus.READY), [sources]);
  const body = reportBody(payload);
  const canStart = selected.length > 0 && !generating && !starting;
  const stored = payload?.report;

  return (
    <Section
      title={t`Growth report`}
      help={<HelpTip label={t`About the growth report`}><Trans>Duct's insights agent reads the sources you tick, puts search, traffic, posts and signups on one page, and says what moved and what to do. A report is kept for a day; Refresh writes it again on your own model key.</Trans></HelpTip>}
      actions={
        stored || state === ReportState.FAILED ? (
          <Button size="sm" variant={stored?.stale ? "default" : "outline"} onClick={generate} disabled={!canStart}>
            <RefreshCw className={`size-3.5 ${generating || starting ? "animate-spin" : ""}`} aria-hidden="true" />
            {generating ? <Trans>Writing…</Trans> : <Trans>Refresh report</Trans>}
          </Button>
        ) : null
      }
    >
      {payload?.templates?.length > 1 && (
        <Tabs value={template} onValueChange={pickTemplate}>
          {/* Four templates at a phone's width: the list wraps rather than overflowing the frame. */}
          <TabsList aria-label={t`Report template`} className="h-auto max-w-full flex-wrap gap-y-1 group-data-horizontal/tabs:h-auto">
            {payload.templates.map((tm) => (
              // A fixed height: the trigger's default is a share of the
              // list's, which collapses once the list wraps to two rows.
              <TabsTrigger key={tm.id} value={tm.id} className="h-7 flex-none">{tm.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}
      {payload?.template?.description && (
        <p className="text-xs text-muted-foreground">{payload.template.description}</p>
      )}

      {sources.length > 0 && (
        <SourcePicker sources={sources} selected={selected} onToggle={toggleSource} disabled={generating} />
      )}

      <StatusLine state={state} payload={payload} i18n={i18n} />

      {requestError && <p className="text-sm text-destructive" role="alert">{requestError}</p>}

      {loading && !payload ? (
        <ReportSkeleton />
      ) : state === ReportState.NO_SOURCES ? (
        <EmptyState
          icon={Sparkles}
          title={t`Nothing to read from yet`}
          actions={
            <>
              <Button size="sm" asChild><Link href="/connections"><Trans>Open the Toolbox</Trans></Link></Button>
              {onLinkAccounts && (
                <Button size="sm" variant="ghost" onClick={onLinkAccounts}><Trans>Connect a scheduler</Trans></Button>
              )}
            </>
          }
        >
          <Trans>Connect Search Console or Google Analytics, a scheduler for your posts, or an analytics MCP server such as PostHog or OpenSEO. The report reads whichever you tick.</Trans>
        </EmptyState>
      ) : state === ReportState.EMPTY ? (
        <EmptyState
          icon={Sparkles}
          title={t`No report yet`}
          actions={
            <Button size="sm" onClick={generate} disabled={!canStart}>
              <Sparkles className="size-3.5" aria-hidden="true" />
              {starting ? <Trans>Starting…</Trans> : <Trans>Write the report</Trans>}
            </Button>
          }
        >
          <ReadyList ready={ready} />
        </EmptyState>
      ) : (
        <>
          {state === ReportState.FAILED && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm" role="alert">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
              <div className="min-w-0 space-y-1">
                <p>{payload?.error?.error || t`The report could not be written.`}</p>
                {payload?.error?.problems?.length > 0 && (
                  <p className="text-xs text-muted-foreground">{payload.error.problems.join(" · ")}</p>
                )}
                {!stored && (
                  <Button size="sm" variant="outline" onClick={generate} disabled={!canStart}>
                    <RefreshCw className="size-3.5" aria-hidden="true" /> <Trans>Try again</Trans>
                  </Button>
                )}
              </div>
            </div>
          )}
          {generating && !body && <ReportSkeleton />}
          {body && (
            <Reveal className={generating ? "opacity-60 transition-opacity" : ""}>
              <GrowthReportView report={body} />
            </Reveal>
          )}
        </>
      )}
    </Section>
  );
}

/** The sources as toggles: logo, name, and for the ones that cannot be read
 *  yet, the reason in place of a switch. */
function SourcePicker({ sources, selected, onToggle, disabled }) {
  const { t, i18n } = useLingui();
  return (
    <fieldset className="min-w-0" disabled={disabled}>
      <legend className="mb-1.5 text-xs font-medium text-muted-foreground"><Trans>Read from</Trans></legend>
      <ul className="flex flex-wrap gap-1.5">
        {sources.map((s) => {
          const isReady = s.status === SourceStatus.READY;
          const on = isReady && selected.includes(s.id);
          const reason = SOURCE_REASON[s.status];
          return (
            <li key={s.id}>
              <button
                type="button"
                aria-pressed={isReady ? on : undefined}
                disabled={!isReady || disabled}
                onClick={() => onToggle(s.id)}
                title={isReady ? (s.detail || undefined) : reason ? i18n._(reason) : undefined}
                className={`inline-flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:cursor-not-allowed ${
                  on
                    ? "border-primary/40 bg-primary/10 text-foreground"
                    : isReady
                      ? "border-border bg-card text-muted-foreground hover:bg-muted"
                      : "border-dashed border-border text-muted-foreground"
                }`}
              >
                <SourceMark source={s} />
                <span className="font-medium">{s.label}</span>
                {!isReady && reason && <span className="text-2xs">· {i18n._(reason)}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="sr-only">{t`Ticked sources are read into the report.`}</p>
    </fieldset>
  );
}

function SourceMark({ source }) {
  const logo = LOGOS[source.id];
  if (logo) return <span className="flex size-4 shrink-0 items-center justify-center [&>img]:size-4 [&>svg]:size-4" aria-hidden="true">{logo}</span>;
  if (source.kind === "publishers") return <Share2 className="size-3.5 shrink-0" aria-hidden="true" />;
  return <Plug className="size-3.5 shrink-0" aria-hidden="true" />;
}

function ReadyList({ ready }) {
  const names = ready.map((s) => s.label).join(", ");
  if (!names) return null;
  return <Trans>Reads {names}. The first report takes a minute or two and is kept for a day.</Trans>;
}

/** One line of state under the pickers: when it was written and how long it
 *  is good for, or what is being read right now. */
function StatusLine({ state, payload, i18n }) {
  const stored = payload?.report;
  const ttl = ttlHours(payload);
  if (state === ReportState.GENERATING) {
    const names = (payload?.run_sources || [])
      .map((id) => payload?.sources?.find((s) => s.id === id)?.label || id)
      .join(", ");
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
        <RefreshCw className="size-3 animate-spin" aria-hidden="true" />
        {names ? <Trans>Writing the report · reading {names}</Trans> : <Trans>Writing the report</Trans>}
      </p>
    );
  }
  if (!stored) return null;
  const when = relativeTime(stored.generated_at, { locale: i18n.locale });
  const until = stored.stale_after ? `${formatDate(stored.stale_after, { withYear: false, locale: i18n.locale })} ${formatTime(stored.stale_after, { locale: i18n.locale })}` : "";
  return (
    <p className="text-xs text-muted-foreground" role="status">
      {stored.stale ? (
        <Trans>Written {when}, older than {ttl} hours. The numbers may have moved; Refresh writes it again.</Trans>
      ) : until ? (
        <Trans>Written {when} · kept until {until}</Trans>
      ) : (
        <Trans>Written {when}</Trans>
      )}
    </p>
  );
}

/** The loaded layout's shape, so the swap changes texture, not geometry. */
function ReportSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 gap-4 @2xl:grid-cols-2">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    </div>
  );
}
