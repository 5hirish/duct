"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { TileGrid } from "@/components/ui/page";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { chartRows, drawableBlocks, sourcesUsed, tableColumns } from "@/lib/analyticsReport";
import { compactNumber, formatDate } from "@/lib/format";

/**
 * A growth report, drawn. The agent wrote the blocks and the rows
 * (backend/agents/insights/report.py); this puts each in the chart the
 * block type names and nothing else decides the layout: a block type the app
 * does not know, or a block with nothing in it, is skipped (lib/analyticsReport
 * `drawableBlocks`). Model text lands in clamped slots under translated
 * labels; the only large type is the verdict, which the contract holds to two
 * sentences.
 *
 * Shared by the Analytics tab (AnalyticsReport) and the artifact library
 * (ArtifactRenderer), so the stored copy and the live one cannot diverge.
 * Charts follow AnalyticsView's conventions, not the legacy `rpt-*` sheet:
 * one unit per chart, compact axes, the theme's series colours.
 */

// Recharts cannot read a CSS variable for a fill in a Cell on every browser
// the same way, but the five chart series are theme tokens checked for
// contrast on both canvases (scripts/check-contrast.mjs) and the app's other
// charts use them the same way.
const SERIES = ["var(--chart-1)", "var(--chart-3)", "var(--chart-5)", "var(--chart-2)", "var(--chart-4)", "var(--primary)"];
const AXIS = { fontSize: 11, fill: "var(--muted-foreground)" };
const CHART_HEIGHT = 220;
// A ranking is at most this many bars; the contract says ten and the chart
// stays readable at a phone's width with fewer.
const MAX_BARS = 10;
// A bar's label is a post title or a query the model wrote; past this many
// characters it wrapped to three lines and the bars lost their rhythm. The
// tooltip carries the whole string.
const BAR_LABEL_CHARS = 28;
const clipLabel = (v) => {
  const text = String(v ?? "");
  return text.length > BAR_LABEL_CHARS ? `${text.slice(0, BAR_LABEL_CHARS - 1)}…` : text;
};

const KPI_TONE = {
  good: "text-success",
  bad: "text-destructive",
  neutral: "text-muted-foreground",
};

const SIGNAL_KIND = {
  win: { variant: "success", label: msg`Win` },
  risk: { variant: "destructive", label: msg`Risk` },
  watch: { variant: "warning", label: msg`Watch` },
};

const SOURCE_STATUS = {
  read: { variant: "success", label: msg`read` },
  empty: { variant: "secondary", label: msg`nothing in the window` },
  failed: { variant: "destructive", label: msg`failed` },
  skipped: { variant: "secondary", label: msg`skipped` },
};

export default function GrowthReportView({ report, className = "" }) {
  const { i18n } = useLingui();
  const blocks = useMemo(() => drawableBlocks(report), [report]);
  if (!report) return null;
  const window = report.date_from && report.date_to
    ? `${formatDate(report.date_from, { withYear: false, locale: i18n.locale })} – ${formatDate(report.date_to, { locale: i18n.locale })}`
    : "";
  const used = sourcesUsed(report);

  return (
    <div className={`space-y-5 ${className}`}>
      <header className="space-y-2">
        <p className="text-base font-medium leading-snug text-foreground">{report.verdict}</p>
        {report.summary && <p className="max-w-prose text-sm text-muted-foreground">{report.summary}</p>}
        {report.takeaway && (
          <p className="text-sm">
            <span className="font-medium"><Trans>Takeaway:</Trans></span> <q className="text-muted-foreground">{report.takeaway}</q>
          </p>
        )}
        {window && <p className="text-xs text-muted-foreground tabular-nums">{window}</p>}
      </header>

      {blocks.map((block) => (
        <ReportBlock key={block.block_id} block={block} />
      ))}

      {(report.could_not_check?.length > 0 || used.length > 0 || report.method_note) && (
        <footer className="space-y-3 border-t border-border/60 pt-4 text-xs text-muted-foreground">
          {report.could_not_check?.length > 0 && (
            <div>
              <p className="font-medium text-foreground"><Trans>What could not be checked</Trans></p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {report.could_not_check.map((gap, i) => <li key={i}>{gap}</li>)}
              </ul>
            </div>
          )}
          {used.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium text-foreground"><Trans>Sources:</Trans></span>
              {used.map((s) => {
                const meta = SOURCE_STATUS[s.status] || SOURCE_STATUS.read;
                return (
                  <Badge key={s.id} variant={meta.variant} className="font-normal" title={s.note || undefined}>
                    {s.label} · {i18n._(meta.label)}
                  </Badge>
                );
              })}
            </div>
          )}
          {report.method_note && (
            <details>
              <summary className="cursor-pointer font-medium text-foreground"><Trans>How this was computed</Trans></summary>
              <p className="mt-1 max-w-prose">{report.method_note}</p>
            </details>
          )}
        </footer>
      )}
    </div>
  );
}

function ReportBlock({ block }) {
  switch (block.block_type) {
    case "kpi_strip":
      return <KpiStrip block={block} />;
    case "time_series":
      return <ChartCard block={block}><TimeSeries block={block} /></ChartCard>;
    case "bar_chart":
      return <ChartCard block={block}><Bars block={block} /></ChartCard>;
    case "pie_chart":
      return <ChartCard block={block}><Slices block={block} /></ChartCard>;
    case "table":
      return <ChartCard block={block} flush><DataTable block={block} /></ChartCard>;
    case "signal_list":
      return <Signals block={block} />;
    case "action_list":
      return <Actions block={block} />;
    default:
      return null;
  }
}

/** The block's frame: a translated-shape header the model's title fills, the
 *  chart, and the one-sentence note under it. */
function ChartCard({ block, flush = false, children }) {
  return (
    <Card className={flush ? "gap-0 p-0" : "gap-3 p-4"}>
      <BlockHeader block={block} className={flush ? "px-4 pt-4" : ""} />
      {children}
      {block.insight_note && (
        <p className={`text-xs text-muted-foreground ${flush ? "px-4 pb-4" : ""}`}>{block.insight_note}</p>
      )}
    </Card>
  );
}

function BlockHeader({ block, className = "" }) {
  return (
    <div className={`flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 ${className}`}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{block.title}</h3>
      {(block.source || block.window) && (
        <p className="text-2xs text-muted-foreground tabular-nums">
          {[block.source, block.window].filter(Boolean).join(" · ")}
        </p>
      )}
    </div>
  );
}

function KpiStrip({ block }) {
  const kpis = block.kpis || [];
  return (
    <section className="space-y-2">
      <BlockHeader block={block} />
      <TileGrid size="sm">
        {kpis.map((kpi, i) => (
          <Card key={`${kpi.label}-${i}`} variant="quiet" className="gap-0.5 p-4">
            <p className="text-xs font-medium text-muted-foreground">{kpi.label}</p>
            <p className="text-2xl font-semibold tabular-nums">{kpi.value}</p>
            {kpi.delta && <p className={`text-xs tabular-nums ${KPI_TONE[kpi.tone] || KPI_TONE.neutral}`}>{kpi.delta}</p>}
            {kpi.source && <p className="text-2xs text-muted-foreground">{kpi.source}</p>}
          </Card>
        ))}
      </TileGrid>
      {block.insight_note && <p className="text-xs text-muted-foreground">{block.insight_note}</p>}
    </section>
  );
}

function TimeSeries({ block }) {
  const { i18n } = useLingui();
  const rows = chartRows(block);
  const x = block.x_field;
  const unit = block.y_unit || block.y_field;
  // Dates on the axis follow the interface language; anything else is drawn as written.
  const tick = (v) => {
    const d = /^\d{4}-\d{2}-\d{2}/.test(String(v)) ? formatDate(v, { withYear: false, locale: i18n.locale }) : v;
    return d;
  };
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
      <LineChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis dataKey={x} tickFormatter={tick} tick={AXIS} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tickFormatter={compactNumber} tick={AXIS} tickLine={false} axisLine={false} width={44} />
        <Tooltip content={<ReportTooltip unit={unit} labelFormatter={tick} />} />
        <Line type="monotone" dataKey="__value" stroke="var(--primary)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function Bars({ block }) {
  const rows = chartRows(block).slice(0, MAX_BARS);
  const x = block.x_field;
  const unit = block.y_unit || block.y_field;
  return (
    <ResponsiveContainer width="100%" height={Math.max(CHART_HEIGHT, rows.length * 28 + 40)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
        <XAxis type="number" tickFormatter={compactNumber} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey={x} width={150} tickFormatter={clipLabel} tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={false} interval={0} />
        <Tooltip content={<ReportTooltip unit={unit} labelFormatter={(v) => v} />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
        <Bar dataKey="__value" radius={[0, 4, 4, 0]} fill="var(--primary)" />
      </BarChart>
    </ResponsiveContainer>
  );
}

function Slices({ block }) {
  const rows = chartRows(block);
  const x = block.x_field;
  const unit = block.y_unit || block.y_field;
  const total = rows.reduce((a, r) => a + r.__value, 0) || 1;
  return (
    <div className="grid items-center gap-3 @md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <PieChart>
          <Pie data={rows} dataKey="__value" nameKey={x} innerRadius={48} outerRadius={84} paddingAngle={2} stroke="none">
            {rows.map((row, i) => <Cell key={`${row[x]}-${i}`} fill={SERIES[i % SERIES.length]} />)}
          </Pie>
          <Tooltip content={<ReportTooltip unit={unit} />} />
        </PieChart>
      </ResponsiveContainer>
      {/* Colour never carries the share alone (WCAG 1.4.1): the legend says it. */}
      <ul className="space-y-1 text-xs">
        {rows.map((row, i) => (
          <li key={`${row[x]}-${i}`} className="flex items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: SERIES[i % SERIES.length] }} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">{row[x]}</span>
            <span className="tabular-nums text-muted-foreground">{Math.round((row.__value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DataTable({ block }) {
  const columns = tableColumns(block);
  const rows = block.rows || [];
  const numeric = (key) => rows.every((r) => r?.[key] === undefined || typeof r[key] === "number" || /^[\d.,%\s−-]+$/.test(String(r[key])));
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((key) => (
              <TableHead key={key} className={numeric(key) ? "text-right" : ""}>{key.replace(/_/g, " ")}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i}>
              {columns.map((key) => (
                <TableCell key={key} className={numeric(key) ? "text-right tabular-nums" : "max-w-[18rem] truncate"} title={typeof row?.[key] === "string" && row[key].length > 40 ? row[key] : undefined}>
                  {formatCell(row?.[key])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "–";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(value);
}

function Signals({ block }) {
  const { i18n } = useLingui();
  return (
    <section className="space-y-2">
      <BlockHeader block={block} />
      <Card className="gap-0 p-0">
        <ul className="divide-y divide-border/60">
          {(block.signals || []).map((s, i) => {
            const kind = SIGNAL_KIND[s.kind] || SIGNAL_KIND.watch;
            return (
              <li key={s.id || i} className="flex gap-3 p-4">
                <Badge variant={kind.variant} className="h-fit shrink-0">{i18n._(kind.label)}</Badge>
                <div className="min-w-0 space-y-0.5 text-sm">
                  <p className="font-medium">{s.title}</p>
                  {s.impact && <p className="text-muted-foreground">{s.impact}</p>}
                  {s.action && (
                    <p><span className="font-medium"><Trans>Action:</Trans></span> {s.action}</p>
                  )}
                  {s.source && <p className="text-2xs text-muted-foreground">{s.source}</p>}
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
      {block.insight_note && <p className="text-xs text-muted-foreground">{block.insight_note}</p>}
    </section>
  );
}

function Actions({ block }) {
  return (
    <section className="space-y-2">
      <BlockHeader block={block} />
      <Card className="gap-0 p-0">
        <ol className="divide-y divide-border/60">
          {(block.actions || []).map((a, i) => (
            <li key={a.id || i} className="flex gap-3 p-4 text-sm">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold tabular-nums text-brand" aria-hidden="true">{i + 1}</span>
              <div className="min-w-0 space-y-1">
                <p className="font-medium">{a.title}</p>
                {a.detail && <p className="text-muted-foreground">{a.detail}</p>}
                <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                  {a.size && <div><dt className="inline font-medium text-foreground"><Trans>Size:</Trans></dt> <dd className="inline">{a.size}</dd></div>}
                  {a.effort && <div><dt className="inline font-medium text-foreground"><Trans>Effort:</Trans></dt> <dd className="inline">{a.effort}</dd></div>}
                  {a.check && <div><dt className="inline font-medium text-foreground"><Trans>Check:</Trans></dt> <dd className="inline">{a.check}</dd></div>}
                  {a.owner && <div><dt className="inline font-medium text-foreground"><Trans>Owner:</Trans></dt> <dd className="inline">{a.owner}</dd></div>}
                </dl>
              </div>
            </li>
          ))}
        </ol>
      </Card>
      {block.insight_note && <p className="text-xs text-muted-foreground">{block.insight_note}</p>}
    </section>
  );
}

// One unit per chart, so the tooltip owns the unit's word.
function ReportTooltip({ active, payload, label, unit, labelFormatter }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const name = p.payload?.name ?? (labelFormatter ? labelFormatter(label) : label);
  return (
    <div className="rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md">
      {name !== undefined && name !== null && <p className="mb-0.5 max-w-[220px] truncate font-medium">{String(name)}</p>}
      <p className="tabular-nums text-muted-foreground">{Number(p.value ?? 0).toLocaleString()} {unit}</p>
    </div>
  );
}
