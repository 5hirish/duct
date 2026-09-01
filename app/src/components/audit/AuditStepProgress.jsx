"use client";

import { useState } from "react";
import { STEP_LABELS as BACKEND_STEP_LABELS, AuditStep } from "../../lib/auditEvents";
import { StepStatus } from "../../lib/agentSteps";
import { Spinner } from "@/components/ui/spinner";

const STEP_LABELS = {
  ...BACKEND_STEP_LABELS,
  plan_crawl:    "Planning crawl",
  render_report: "Finalizing report",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function StatusBadge({ code }) {
  if (!code) return <span className="font-mono text-[10px] text-muted-foreground">—</span>;
  const colour = code >= 200 && code < 300 ? "text-green-500"
               : code >= 300 && code < 400 ? "text-amber-500"
               : "text-destructive";
  return <span className={`font-mono text-[10px] font-semibold ${colour}`}>{code}</span>;
}

function Pill({ children, variant = "default" }) {
  const cls = {
    default: "bg-muted text-muted-foreground",
    warn:    "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    danger:  "bg-destructive/15 text-destructive",
    ok:      "bg-green-500/15 text-green-600 dark:text-green-400",
  }[variant];
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-px text-[10px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function CharCount({ n, lo, hi }) {
  const variant = !n ? "danger" : n < lo || n > hi ? "warn" : "ok";
  return <Pill variant={variant}>{n} chars</Pill>;
}

// ---------------------------------------------------------------------------
// SitemapDetails — expanded panel for fetch_sitemap
// ---------------------------------------------------------------------------

function SitemapDetails({ payload }) {
  const p = payload || {};
  const hasRobots = p.robots_txt_found;
  const hasLlms   = p.llms_txt_found;

  return (
    <div className="space-y-3 text-xs">
      {/* Sitemap */}
      <div className="flex items-start gap-2">
        <span className="text-muted-foreground shrink-0 w-16">Sitemap</span>
        {p.sitemap_url
          ? <span className="font-mono text-[10px] break-all text-foreground/80">{p.sitemap_url}</span>
          : <Pill variant="warn">not found</Pill>}
      </div>

      {/* robots.txt */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-16 shrink-0">robots.txt</span>
          {hasRobots ? (
            <>
              <Pill variant="ok">found</Pill>
              <span className="text-muted-foreground">{fmt(p.robots_txt_bytes)}</span>
              <span className="text-muted-foreground">{p.robots_txt_lines} lines</span>
            </>
          ) : (
            <Pill variant="warn">not found</Pill>
          )}
        </div>
        {hasRobots && p.robots_txt_preview && (
          <pre className="ml-[4.5rem] text-[10px] text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-20 overflow-y-auto">
            {p.robots_txt_preview}
          </pre>
        )}
      </div>

      {/* llms.txt */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-16 shrink-0">llms.txt</span>
          {hasLlms ? (
            <>
              <Pill variant="ok">found</Pill>
              <span className="text-muted-foreground">{fmt(p.llms_txt_bytes)}</span>
              <span className="text-muted-foreground">{p.llms_txt_lines} lines</span>
            </>
          ) : (
            <Pill variant="warn">not found</Pill>
          )}
        </div>
        {hasLlms && p.llms_txt_preview && (
          <pre className="ml-[4.5rem] text-[10px] text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-20 overflow-y-auto">
            {p.llms_txt_preview}
          </pre>
        )}
      </div>

      {/* Landing pages */}
      {p.landing_page_urls?.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground">{p.landing_page_urls.length} landing page{p.landing_page_urls.length !== 1 ? "s" : ""}</span>
          <div className="max-h-28 overflow-y-auto rounded bg-muted/40 px-2 py-1.5 space-y-0.5">
            {p.landing_page_urls.map((url) => (
              <div key={url} className="font-mono text-[10px] text-foreground/70 truncate" title={url}>{url}</div>
            ))}
          </div>
        </div>
      )}

      {/* Blog posts */}
      {p.blog_post_urls?.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground">{p.blog_post_urls.length} blog post{p.blog_post_urls.length !== 1 ? "s" : ""}</span>
          <div className="max-h-24 overflow-y-auto rounded bg-muted/40 px-2 py-1.5 space-y-0.5">
            {p.blog_post_urls.map((url) => (
              <div key={url} className="font-mono text-[10px] text-foreground/70 truncate" title={url}>{url}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CrawlDetails — expanded panel for crawl_pages
// ---------------------------------------------------------------------------

function PageRow({ page }) {
  const [open, setOpen] = useState(false);
  const issues = [];
  if (page.is_noindex)           issues.push({ label: "noindex",       v: "danger" });
  if (!page.has_canonical)       issues.push({ label: "no canonical",  v: "warn"   });
  if (!page.has_schema_org)      issues.push({ label: "no schema",     v: "warn"   });
  if (page.images_missing_alt)   issues.push({ label: `alt ×${page.images_missing_alt}`, v: "warn" });
  if (!page.meta_description_chars) issues.push({ label: "no meta desc", v: "danger" });

  const statusColour = page.http_status >= 200 && page.http_status < 300 ? "text-green-500"
                     : page.http_status >= 300 && page.http_status < 400 ? "text-amber-500"
                     : "text-destructive";

  return (
    <div className="rounded border border-border/50 overflow-hidden">
      {/* Row header */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-2 px-2.5 py-2 text-left hover:bg-muted/40 transition-colors"
      >
        <span className={`font-mono text-[10px] font-bold shrink-0 mt-0.5 ${statusColour}`}>
          {page.http_status || "ERR"}
        </span>
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="font-mono text-[10px] text-foreground/80 truncate">{page.url}</div>
          <div className="flex flex-wrap gap-1">
            <span className="text-[10px] text-muted-foreground">{page.word_count} words</span>
            {issues.map(i => <Pill key={i.label} variant={i.v}>{i.label}</Pill>)}
          </div>
        </div>
        <span className={`text-muted-foreground/50 text-[10px] shrink-0 mt-0.5 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>

      {/* Expanded detail */}
      <div
        className="overflow-hidden transition-all duration-150"
        style={{ maxHeight: open ? "500px" : "0px" }}
      >
        <div className="px-2.5 pb-2.5 space-y-2 border-t border-border/40 pt-2 bg-muted/20">
          {/* Title */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[10px] text-muted-foreground w-14 shrink-0">Title</span>
            <span className="text-[10px] text-foreground/80 flex-1 min-w-0">{page.title || <em className="text-destructive/70">missing</em>}</span>
            <CharCount n={page.title_chars} lo={30} hi={70} />
          </div>

          {/* Meta description */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[10px] text-muted-foreground w-14 shrink-0">Meta desc</span>
            <span className="text-[10px] text-foreground/80 flex-1 min-w-0 break-words">{page.meta_description || <em className="text-destructive/70">missing</em>}</span>
            <CharCount n={page.meta_description_chars} lo={140} hi={160} />
          </div>

          {/* Body preview */}
          {page.body_preview && (
            <div className="flex items-start gap-2">
              <span className="text-[10px] text-muted-foreground w-14 shrink-0 mt-0.5">Preview</span>
              <p className="text-[10px] text-muted-foreground leading-relaxed line-clamp-3 flex-1">{page.body_preview}</p>
            </div>
          )}

          {/* Signal grid */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
            <span className="text-muted-foreground">Canonical</span>
            <span className={page.has_canonical ? "text-green-500" : "text-destructive/70"}>
              {page.has_canonical ? page.canonical : "missing"}
            </span>
            <span className="text-muted-foreground">Schema</span>
            <span className={page.has_schema_org ? "text-green-500" : "text-muted-foreground"}>
              {page.has_schema_org ? (page.schema_types?.join(", ") || "yes") : "none"}
            </span>
            <span className="text-muted-foreground">Images</span>
            <span>{page.images} total{page.images_missing_alt ? `, ${page.images_missing_alt} missing alt` : ""}</span>
            <span className="text-muted-foreground">Links</span>
            <span>{page.internal_links} internal · {page.external_links} external</span>
            {page.hreflang_count > 0 && <>
              <span className="text-muted-foreground">Hreflang</span>
              <span>{page.hreflang_count} lang{page.hreflang_count !== 1 ? "s" : ""}</span>
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}

function CrawlDetails({ payload }) {
  const p = payload || {};
  const pages = p.pages || [];
  const errors = p.errors || [];

  return (
    <div className="space-y-2">
      <div className="max-h-80 overflow-y-auto space-y-1.5 pr-0.5">
        {pages.map((page) => <PageRow key={page.url} page={page} />)}
      </div>
      {errors.length > 0 && (
        <div className="rounded border border-destructive/20 bg-destructive/5 p-2 space-y-0.5">
          <p className="text-[10px] font-medium text-destructive">Crawl errors</p>
          {errors.map((e, i) => (
            <p key={i} className="font-mono text-[10px] text-destructive/80 break-all">{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EnrichingDetails — expanded panel for the competitor-research sub-agent
// ---------------------------------------------------------------------------

function EnrichingDetails({ payload }) {
  const p = payload || {};
  const competitors = p.competitors || [];
  const gaps = p.content_gaps || [];
  const notes = p.enrichment_notes || [];

  if (!competitors.length && !gaps.length && !notes.length) {
    return <p className="text-[10px] text-muted-foreground italic">No competitor research was returned for this audit.</p>;
  }

  return (
    <div className="space-y-3 text-xs">
      {competitors.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-muted-foreground">{competitors.length} competitor{competitors.length !== 1 ? "s" : ""}</span>
          <div className="space-y-1.5">
            {competitors.map((c) => (
              <div key={c.domain} className="rounded bg-muted/40 px-2 py-1.5 space-y-1">
                <div className="font-mono text-[10px] text-foreground/80">{c.domain}</div>
                {c.positioning && <p className="text-[10px] text-muted-foreground leading-relaxed">{c.positioning}</p>}
                {c.content_pillars && (
                  <p className="text-[10px] text-muted-foreground">
                    <span className="text-foreground/50">Pillars:</span> {c.content_pillars}
                  </p>
                )}
                {c.differentiators && (
                  <p className="text-[10px] text-foreground/60">
                    <span className="text-muted-foreground/50">Differentiators:</span> {c.differentiators}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {gaps.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground">Content gaps</span>
          <ul className="list-disc pl-4 space-y-0.5 text-[10px] text-foreground/70">
            {gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}

      {notes.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground">Notes</span>
          <ul className="space-y-0.5 text-[10px] text-muted-foreground italic">
            {notes.map((n, i) => <li key={i}>• {n}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step row — header + expandable details
// ---------------------------------------------------------------------------

const DETAIL_COMPONENTS = {
  [AuditStep.FETCH_SITEMAP]: SitemapDetails,
  [AuditStep.CRAWL_PAGES]:   CrawlDetails,
  [AuditStep.ENRICHING]:     EnrichingDetails,
};


function HeaderRow({ expandable, onToggle, expanded, children }) {
  const className = `flex w-full items-center gap-2 text-left text-sm ${
    expandable
      ? "cursor-pointer rounded-sm transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      : ""
  }`;
  if (!expandable) return <div className={className}>{children}</div>;
  return (
    <button type="button" onClick={onToggle} aria-expanded={expanded} className={className}>
      {children}
    </button>
  );
}

function StepRow({ step, expanded, onToggle }) {
  const { step_id, label, status, payload } = step;
  const isRunning    = status === StepStatus.RUNNING;
  const isDone       = status === StepStatus.SUCCESS || status === StepStatus.ERROR;
  const isSynthesize = step_id === AuditStep.SYNTHESIZE_AUDIT;
  const Details      = DETAIL_COMPONENTS[step_id];
  const canExpand    = isDone && !!Details && !!payload;

  return (
    <div>
      {/* Header row — a real <button> when it expands, so it is focusable and
          Enter/Space work; a plain <div> when there is nothing to toggle. */}
      <HeaderRow
        expandable={canExpand}
        onToggle={onToggle}
        expanded={expanded}
      >
        {/* Status icon */}
        {isRunning ? (
          <Spinner className="size-3 text-blue-500" />
        ) : status === StepStatus.SUCCESS ? (
          <span className="text-green-500 text-xs shrink-0">✓</span>
        ) : status === StepStatus.ERROR ? (
          <span className="text-destructive text-xs shrink-0">✗</span>
        ) : (
          <span className="size-3 shrink-0 rounded-full border border-muted-foreground/20" />
        )}

        <span className={isRunning ? "font-medium flex-1" : "text-muted-foreground flex-1"}>
          {STEP_LABELS[step_id] || label || step_id}
        </span>

        {/* Crawl page count */}
        {payload?.landing_pages != null && !isSynthesize && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {payload.landing_pages} page{payload.landing_pages !== 1 ? "s" : ""}
            {payload.blog_posts > 0 && `, ${payload.blog_posts} post${payload.blog_posts !== 1 ? "s" : ""}`}
          </span>
        )}

        {/* Crawled page count */}
        {payload?.pages != null && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {payload.pages.length} page{payload.pages.length !== 1 ? "s" : ""}
          </span>
        )}

        {/* Competitor research summary */}
        {payload?.competitors != null && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {payload.competitors.length} competitor{payload.competitors.length !== 1 ? "s" : ""}
            {payload.content_gaps?.length > 0 && `, ${payload.content_gaps.length} gap${payload.content_gaps.length !== 1 ? "s" : ""}`}
          </span>
        )}

        {/* Time estimate on synthesize while running */}
        {isSynthesize && isRunning && (
          <span className="text-xs text-muted-foreground">~3 min</span>
        )}

        {/* Extended thinking indicator */}
        {isSynthesize && isDone && payload?.reasoned && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-px text-[10px] font-medium text-primary">
            ✦ Reasoned
          </span>
        )}

        {/* Expand chevron */}
        {canExpand && (
          <span className={`text-muted-foreground/50 text-xs transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}>
            ›
          </span>
        )}
      </HeaderRow>

      {/* Progress bar for synthesize */}
      {isSynthesize && isRunning && (
        <div className="ml-5 mt-1.5">
          <div className="h-0.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-400"
              style={{ animation: "duct-step-fill 180s cubic-bezier(0.08, 0, 0.2, 1) forwards" }}
            />
          </div>
          <style>{`@keyframes duct-step-fill { from { width: 0% } to { width: 85% } }`}</style>
        </div>
      )}

      {/* Expandable detail panel */}
      {canExpand && (
        <div
          className="overflow-hidden transition-all duration-200 ml-5"
          style={{ maxHeight: expanded ? "700px" : "0px" }}
        >
          <div className="pt-2 pb-1">
            <Details payload={payload} />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AuditStepProgress
// ---------------------------------------------------------------------------

export default function AuditStepProgress({ steps }) {
  const [expanded, setExpanded] = useState(new Set());

  if (!steps || steps.length === 0) return null;

  function toggle(id) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-2.5 py-2">
      {steps.map((step) => (
        <StepRow
          key={step.step_id}
          step={step}
          expanded={expanded.has(step.step_id)}
          onToggle={() => toggle(step.step_id)}
        />
      ))}
    </div>
  );
}
