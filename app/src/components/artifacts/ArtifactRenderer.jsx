"use client";

// Per-content-type artifact renderers — the "source in, renderer per type"
// dispatch. Vendor MIME types (application/vnd.duct.*) are Duct-native
// objects rendered by app components; primitives (markdown/html/csv/mermaid)
// get their standard treatments. Anything unknown falls back to raw text.

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import AuditReportV1 from "@/components/audit/AuditReportV1";

export const CONTENT_TYPES = {
  REPORT_JSON: "application/vnd.duct.report+json",
  TABLE_JSON: "application/vnd.duct.table+json",
  CHART_JSON: "application/vnd.duct.chart+json",
  DIFF_JSON: "application/vnd.duct.diff+json",
  MERMAID: "text/vnd.mermaid",
  MARKDOWN: "text/markdown",
  HTML: "text/html",
  CSV: "text/csv",
};

const CHART_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#0ea5e9", "#a855f7"];

function safeJson(text) {
  try {
    return JSON.parse(text || "");
  } catch {
    return null;
  }
}

export function MarkdownView({ source }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-3xl px-1 py-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}

export function MermaidView({ source }) {
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
        const { svg: rendered } = await mermaid.render(
          `mmd-${Math.random().toString(36).slice(2)}`,
          source
        );
        // Diagram source is agent-authored (untrusted): mermaid strict mode
        // sanitizes labels, and DOMPurify re-sanitizes the SVG output.
        const DOMPurify = (await import("dompurify")).default;
        // No foreignObject: strict mode renders plain-text labels, so pure
        // SVG profiles suffice and HTML-in-SVG stays blocked.
        const clean = DOMPurify.sanitize(rendered, {
          USE_PROFILES: { svg: true, svgFilters: true },
        });
        if (alive) setSvg(clean);
      } catch (err) {
        if (alive) setError(err.message || "Mermaid render failed.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [source]);

  if (error) {
    return (
      <div>
        <p className="app-subtle text-sm">Diagram failed to render ({error}) — source below.</p>
        <pre className="text-xs p-3 overflow-x-auto">{source}</pre>
      </div>
    );
  }
  if (!svg) return <p className="app-subtle text-sm p-2">Rendering diagram…</p>;
  // Mermaid output with securityLevel "strict" sanitizes labels/links.
  return <div className="overflow-x-auto p-2" dangerouslySetInnerHTML={{ __html: svg }} />;
}

function DataTable({ columns, rows }) {
  return (
    <div className="overflow-x-auto border border-input rounded-md">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-input bg-muted/40">
            {columns.map((c, i) => (
              <th key={i} className="text-left font-semibold px-3 py-2 whitespace-nowrap">{String(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-b border-input/50 last:border-0">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1.5 align-top">{String(cell ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TableJsonView({ source }) {
  const table = safeJson(source);
  if (!table?.columns) return <pre className="text-xs p-3 overflow-x-auto">{source}</pre>;
  return <DataTable columns={table.columns} rows={table.rows || []} />;
}

function parseCsvLine(line) {
  // Minimal CSV: handles quoted fields with commas; good enough for exports.
  const out = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}

export function CsvView({ source }) {
  const { columns, rows } = useMemo(() => {
    const lines = (source || "").split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return { columns: [], rows: [] };
    return { columns: parseCsvLine(lines[0]), rows: lines.slice(1, 501).map(parseCsvLine) };
  }, [source]);
  if (!columns.length) return <p className="app-subtle text-sm p-2">Empty dataset.</p>;
  return <DataTable columns={columns} rows={rows} />;
}

export function ChartJsonView({ source }) {
  // Spec: {type: "line"|"bar", x: "key", series: [{key, label?}], data: [{...}], title?}
  const spec = safeJson(source);
  if (!spec?.data?.length || !spec?.x || !spec?.series?.length) {
    return <pre className="text-xs p-3 overflow-x-auto">{source}</pre>;
  }
  const ChartComp = spec.type === "line" ? LineChart : BarChart;
  return (
    <div style={{ width: "100%", height: 360 }}>
      {spec.title && <p className="text-sm font-medium mb-1 px-1">{spec.title}</p>}
      <ResponsiveContainer>
        <ChartComp data={spec.data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey={spec.x} fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Legend />
          {spec.series.map((s, i) =>
            spec.type === "line" ? (
              <Line key={s.key} dataKey={s.key} name={s.label || s.key} stroke={CHART_COLORS[i % CHART_COLORS.length]} dot={false} />
            ) : (
              <Bar key={s.key} dataKey={s.key} name={s.label || s.key} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            )
          )}
        </ChartComp>
      </ResponsiveContainer>
    </div>
  );
}

export function DiffJsonView({ source }) {
  // Spec: {title?, changes: [{summary, before?, after?, status?}]}
  const spec = safeJson(source);
  if (!spec?.changes) return <pre className="text-xs p-3 overflow-x-auto">{source}</pre>;
  return (
    <div className="grid gap-3">
      {spec.title && <p className="text-sm font-medium">{spec.title}</p>}
      {spec.changes.map((c, i) => (
        <div key={i} className="border border-input rounded-md p-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium">{c.summary || `Change ${i + 1}`}</span>
            {c.status && <span className="status-pill grey">{c.status}</span>}
          </div>
          {(c.before != null || c.after != null) && (
            <div className="grid md:grid-cols-2 gap-2 text-xs">
              {c.before != null && (
                <pre className="p-2 rounded bg-red-500/5 border border-red-500/20 overflow-x-auto whitespace-pre-wrap">{typeof c.before === "string" ? c.before : JSON.stringify(c.before, null, 2)}</pre>
              )}
              {c.after != null && (
                <pre className="p-2 rounded bg-emerald-500/5 border border-emerald-500/20 overflow-x-auto whitespace-pre-wrap">{typeof c.after === "string" ? c.after : JSON.stringify(c.after, null, 2)}</pre>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Unified-diff text ("Show changes") with per-line coloring. */
export function UnifiedDiffView({ diff }) {
  if (!diff?.trim()) return <p className="app-subtle text-sm p-2">No textual changes between these versions.</p>;
  return (
    <pre className="text-xs p-3 overflow-x-auto leading-5 border border-input rounded-md">
      {diff.split("\n").map((line, i) => {
        let cls = "";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "text-emerald-600 dark:text-emerald-400";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "text-red-600 dark:text-red-400";
        else if (line.startsWith("@@")) cls = "text-sky-600 dark:text-sky-400";
        return (
          <span key={i} className={`block ${cls}`}>{line || " "}</span>
        );
      })}
    </pre>
  );
}

/**
 * Main dispatch. `artifact` is the API row; `content` is the fetched source
 * text (null while loading / when none exists).
 */
export default function ArtifactRenderer({ artifact, content }) {
  const ct = artifact?.content_type || "";
  const structured = artifact?.structured_json?.structured_data || null;

  // Structured report (vendor type; legacy rows used application/json)
  if (structured && (ct === CONTENT_TYPES.REPORT_JSON || ct === "application/json" || artifact.kind === "report")) {
    return <AuditReportV1 data={structured} />;
  }
  if (ct === CONTENT_TYPES.HTML) {
    if (content == null) return <p className="app-subtle text-sm p-2">Loading…</p>;
    return (
      <iframe
        title={artifact.title || "Artifact"}
        srcDoc={content}
        sandbox="allow-modals allow-same-origin"
        style={{ width: "100%", height: "74vh", border: "1px solid var(--border, #e5e7eb)", borderRadius: 8, background: "#fff" }}
      />
    );
  }
  if (content == null) {
    return (
      <p className="app-subtle text-sm p-2">
        {artifact?.has_content ? "Loading…" : "This artifact has no stored content to render."}
      </p>
    );
  }
  switch (ct) {
    case CONTENT_TYPES.MARKDOWN:
      return <MarkdownView source={content} />;
    case CONTENT_TYPES.MERMAID:
      return <MermaidView source={content} />;
    case CONTENT_TYPES.TABLE_JSON:
      return <TableJsonView source={content} />;
    case CONTENT_TYPES.CSV:
      return <CsvView source={content} />;
    case CONTENT_TYPES.CHART_JSON:
      return <ChartJsonView source={content} />;
    case CONTENT_TYPES.DIFF_JSON:
      return <DiffJsonView source={content} />;
    default:
      return <pre className="text-xs p-3 overflow-x-auto whitespace-pre-wrap">{content}</pre>;
  }
}
