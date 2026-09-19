"use client";

import { useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { STEP_LABELS as BACKEND_STEP_LABELS, AuditStep } from "../../lib/auditEvents";
import { StepStatus } from "../../lib/agentSteps";
import { Spinner } from "@/components/ui/spinner";

// Message descriptors (the backend table is one too); StepRow resolves them.
const STEP_LABELS = {
  ...BACKEND_STEP_LABELS,
  plan_crawl:    msg`Planning crawl`,
  render_report: msg`Finalizing report`,
};

// Lives outside JSX so the literal-string check does not read a CSS rule as copy.
const STEP_FILL_KEYFRAMES = `@keyframes duct-step-fill { from { width: 0% } to { width: 85% } }`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n) {
  if (n == null) return "—";
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function StatusBadge({ code }) {
  if (!code) return <span className="font-mono text-2xs text-muted-foreground">—</span>;
  const colour = code >= 200 && code < 300 ? "text-success"
               : code >= 300 && code < 400 ? "text-warning"
               : "text-destructive";
  return <span className={`font-mono text-2xs font-semibold ${colour}`}>{code}</span>;
}

function Pill({ children, variant = "default" }) {
  const cls = {
    default: "bg-muted text-muted-foreground",
    warn:    "bg-warning/15 text-warning",
    danger:  "bg-destructive/15 text-destructive",
    ok:      "bg-success/15 text-success",
  }[variant];
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-px text-2xs font-medium ${cls}`}>
      {children}
    </span>
  );
}

function CharCount({ n, lo, hi }) {
  const variant = !n ? "danger" : n < lo || n > hi ? "warn" : "ok";
  return <Pill variant={variant}><Trans>{n} chars</Trans></Pill>;
}

// ---------------------------------------------------------------------------
// SitemapDetails — expanded panel for fetch_sitemap
// ---------------------------------------------------------------------------

function SitemapDetails({ payload }) {
  const p = payload || {};
  const hasRobots = p.robots_txt_found;
  const hasLlms   = p.llms_txt_found;
  const robotsLines = p.robots_txt_lines;
  const llmsLines = p.llms_txt_lines;
  const landingPages = p.landing_page_urls?.length ?? 0;
  const blogPosts = p.blog_post_urls?.length ?? 0;

  return (
    <div className="space-y-3 text-xs">
      {/* Sitemap */}
      <div className="flex items-start gap-2">
        <span className="text-muted-foreground shrink-0 w-16"><Trans>Sitemap</Trans></span>
        {p.sitemap_url
          ? <span className="font-mono text-2xs break-all text-foreground/80">{p.sitemap_url}</span>
          : <Pill variant="warn"><Trans>not found</Trans></Pill>}
      </div>

      {/* robots.txt */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-16 shrink-0"><Trans>robots.txt</Trans></span>
          {hasRobots ? (
            <>
              <Pill variant="ok"><Trans>found</Trans></Pill>
              <span className="text-muted-foreground">{fmt(p.robots_txt_bytes)}</span>
              <span className="text-muted-foreground"><Trans>{robotsLines} lines</Trans></span>
            </>
          ) : (
            <Pill variant="warn"><Trans>not found</Trans></Pill>
          )}
        </div>
        {hasRobots && p.robots_txt_preview && (
          <pre className="ml-[4.5rem] text-2xs text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-20 overflow-y-auto">
            {p.robots_txt_preview}
          </pre>
        )}
      </div>

      {/* llms.txt */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-16 shrink-0"><Trans>llms.txt</Trans></span>
          {hasLlms ? (
            <>
              <Pill variant="ok"><Trans>found</Trans></Pill>
              <span className="text-muted-foreground">{fmt(p.llms_txt_bytes)}</span>
              <span className="text-muted-foreground"><Trans>{llmsLines} lines</Trans></span>
            </>
          ) : (
            <Pill variant="warn"><Trans>not found</Trans></Pill>
          )}
        </div>
        {hasLlms && p.llms_txt_preview && (
          <pre className="ml-[4.5rem] text-2xs text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-20 overflow-y-auto">
            {p.llms_txt_preview}
          </pre>
        )}
      </div>

      {/* Landing pages */}
      {landingPages > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground"><Plural value={landingPages} one="# landing page" other="# landing pages" /></span>
          <div className="max-h-28 overflow-y-auto rounded bg-muted/40 px-2 py-1.5 space-y-0.5">
            {p.landing_page_urls.map((url) => (
              <div key={url} className="font-mono text-2xs text-foreground/70 truncate" title={url}>{url}</div>
            ))}
          </div>
        </div>
      )}

      {/* Blog posts */}
      {blogPosts > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground"><Plural value={blogPosts} one="# blog post" other="# blog posts" /></span>
          <div className="max-h-24 overflow-y-auto rounded bg-muted/40 px-2 py-1.5 space-y-0.5">
            {p.blog_post_urls.map((url) => (
              <div key={url} className="font-mono text-2xs text-foreground/70 truncate" title={url}>{url}</div>
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
  const { t } = useLingui();
  const [open, setOpen] = useState(false);
  const missingAlt = page.images_missing_alt;
  const issues = [];
  if (page.is_noindex)           issues.push({ label: t`noindex`,       v: "danger" });
  if (!page.has_canonical)       issues.push({ label: t`no canonical`,  v: "warn"   });
  if (!page.has_schema_org)      issues.push({ label: t`no schema`,     v: "warn"   });
  if (page.images_missing_alt)   issues.push({ label: t`alt ×${missingAlt}`, v: "warn" });
  if (!page.meta_description_chars) issues.push({ label: t`no meta desc`, v: "danger" });

  const statusColour = page.http_status >= 200 && page.http_status < 300 ? "text-success"
                     : page.http_status >= 300 && page.http_status < 400 ? "text-warning"
                     : "text-destructive";

  const wordCount = page.word_count;
  const images = page.images;
  const internalLinks = page.internal_links;
  const externalLinks = page.external_links;
  const hreflangCount = page.hreflang_count;

  return (
    <div className="rounded border border-border/50 overflow-hidden">
      {/* Row header */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-2 px-2.5 py-2 text-left hover:bg-muted/40 transition-colors"
      >
        <span className={`font-mono text-2xs font-bold shrink-0 mt-0.5 ${statusColour}`}>
          {page.http_status || "ERR"}
        </span>
        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="font-mono text-2xs text-foreground/80 truncate">{page.url}</div>
          <div className="flex flex-wrap gap-1">
            <span className="text-2xs text-muted-foreground"><Trans>{wordCount} words</Trans></span>
            {issues.map(i => <Pill key={i.label} variant={i.v}>{i.label}</Pill>)}
          </div>
        </div>
        <span className={`text-muted-foreground text-2xs shrink-0 mt-0.5 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>

      {/* Expanded detail */}
      <div
        className="overflow-hidden transition-all duration-150"
        style={{ maxHeight: open ? "500px" : "0px" }}
      >
        <div className="px-2.5 pb-2.5 space-y-2 border-t border-border/40 pt-2 bg-muted/20">
          {/* Title */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-2xs text-muted-foreground w-14 shrink-0"><Trans>Title</Trans></span>
            <span className="text-2xs text-foreground/80 flex-1 min-w-0">{page.title || <em className="text-destructive/70"><Trans>missing</Trans></em>}</span>
            <CharCount n={page.title_chars} lo={30} hi={70} />
          </div>

          {/* Meta description */}
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-2xs text-muted-foreground w-14 shrink-0"><Trans>Meta desc</Trans></span>
            <span className="text-2xs text-foreground/80 flex-1 min-w-0 break-words">{page.meta_description || <em className="text-destructive/70"><Trans>missing</Trans></em>}</span>
            <CharCount n={page.meta_description_chars} lo={140} hi={160} />
          </div>

          {/* Body preview */}
          {page.body_preview && (
            <div className="flex items-start gap-2">
              <span className="text-2xs text-muted-foreground w-14 shrink-0 mt-0.5"><Trans>Preview</Trans></span>
              <p className="text-2xs text-muted-foreground leading-relaxed line-clamp-3 flex-1">{page.body_preview}</p>
            </div>
          )}

          {/* Signal grid */}
          <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-2xs @sm:grid-cols-2">
            <span className="text-muted-foreground"><Trans>Canonical</Trans></span>
            <span className={page.has_canonical ? "text-success" : "text-destructive/70"}>
              {page.has_canonical ? page.canonical : t`missing`}
            </span>
            <span className="text-muted-foreground"><Trans>Schema</Trans></span>
            <span className={page.has_schema_org ? "text-success" : "text-muted-foreground"}>
              {page.has_schema_org ? (page.schema_types?.join(", ") || t`yes`) : t`none`}
            </span>
            <span className="text-muted-foreground"><Trans>Images</Trans></span>
            <span>
              {missingAlt
                ? <Trans>{images} total, {missingAlt} missing alt</Trans>
                : <Trans>{images} total</Trans>}
            </span>
            <span className="text-muted-foreground"><Trans>Links</Trans></span>
            <span><Trans>{internalLinks} internal · {externalLinks} external</Trans></span>
            {page.hreflang_count > 0 && <>
              <span className="text-muted-foreground"><Trans>Hreflang</Trans></span>
              <span><Plural value={hreflangCount} one="# lang" other="# langs" /></span>
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
          <p className="text-2xs font-medium text-destructive"><Trans>Crawl errors</Trans></p>
          {errors.map((e, i) => (
            <p key={i} className="font-mono text-2xs text-destructive/80 break-all">{e}</p>
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
  const competitorCount = competitors.length;

  if (!competitors.length && !gaps.length && !notes.length) {
    return <p className="text-2xs text-muted-foreground italic"><Trans>No competitor research was returned for this audit.</Trans></p>;
  }

  return (
    <div className="space-y-3 text-xs">
      {competitors.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-muted-foreground"><Plural value={competitorCount} one="# competitor" other="# competitors" /></span>
          <div className="space-y-1.5">
            {competitors.map((c) => {
              const pillars = c.content_pillars;
              const differentiators = c.differentiators;
              return (
                <div key={c.domain} className="rounded bg-muted/40 px-2 py-1.5 space-y-1">
                  <div className="font-mono text-2xs text-foreground/80">{c.domain}</div>
                  {c.positioning && <p className="text-2xs text-muted-foreground leading-relaxed">{c.positioning}</p>}
                  {c.content_pillars && (
                    <p className="text-2xs text-muted-foreground">
                      <Trans><span className="text-foreground/50">Pillars:</span> {pillars}</Trans>
                    </p>
                  )}
                  {c.differentiators && (
                    <p className="text-2xs text-foreground/60">
                      <Trans><span className="text-muted-foreground">Differentiators:</span> {differentiators}</Trans>
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {gaps.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground"><Trans>Content gaps</Trans></span>
          <ul className="list-disc pl-4 space-y-0.5 text-2xs text-foreground/70">
            {gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}

      {notes.length > 0 && (
        <div className="space-y-1">
          <span className="text-muted-foreground"><Trans>Notes</Trans></span>
          <ul className="space-y-0.5 text-2xs text-muted-foreground italic">
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
  const { i18n } = useLingui();
  const { step_id, label, status, payload } = step;
  const isRunning    = status === StepStatus.RUNNING;
  const isDone       = status === StepStatus.SUCCESS || status === StepStatus.ERROR;
  const isSynthesize = step_id === AuditStep.SYNTHESIZE_AUDIT;
  const Details      = DETAIL_COMPONENTS[step_id];
  const canExpand    = isDone && !!Details && !!payload;

  const landingPages = payload?.landing_pages;
  const blogPosts = payload?.blog_posts;
  const crawledPages = payload?.pages?.length;
  const competitors = payload?.competitors?.length;
  const contentGaps = payload?.content_gaps?.length;

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
          <Spinner className="size-3 text-info" />
        ) : status === StepStatus.SUCCESS ? (
          <span className="text-success text-xs shrink-0">✓</span>
        ) : status === StepStatus.ERROR ? (
          <span className="text-destructive text-xs shrink-0">✗</span>
        ) : (
          <span className="size-3 shrink-0 rounded-full border border-muted-foreground/20" />
        )}

        <span className={isRunning ? "font-medium flex-1" : "text-muted-foreground flex-1"}>
          {STEP_LABELS[step_id] ? i18n._(STEP_LABELS[step_id]) : label || step_id}
        </span>

        {/* Crawl page count */}
        {payload?.landing_pages != null && !isSynthesize && (
          <span className="text-xs text-muted-foreground tabular-nums">
            <Plural value={landingPages} one="# page" other="# pages" />
            {blogPosts > 0 && <>, <Plural value={blogPosts} one="# post" other="# posts" /></>}
          </span>
        )}

        {/* Crawled page count */}
        {payload?.pages != null && (
          <span className="text-xs text-muted-foreground tabular-nums">
            <Plural value={crawledPages} one="# page" other="# pages" />
          </span>
        )}

        {/* Competitor research summary */}
        {payload?.competitors != null && (
          <span className="text-xs text-muted-foreground tabular-nums">
            <Plural value={competitors} one="# competitor" other="# competitors" />
            {contentGaps > 0 && <>, <Plural value={contentGaps} one="# gap" other="# gaps" /></>}
          </span>
        )}

        {/* Time estimate on synthesize while running */}
        {isSynthesize && isRunning && (
          <span className="text-xs text-muted-foreground"><Trans>~3 min</Trans></span>
        )}

        {/* Extended thinking indicator */}
        {isSynthesize && isDone && payload?.reasoned && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-1.5 py-px text-2xs font-medium text-primary">
            <Trans>✦ Reasoned</Trans>
          </span>
        )}

        {/* Expand chevron */}
        {canExpand && (
          <span className={`text-muted-foreground text-xs transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}>
            ›
          </span>
        )}
      </HeaderRow>

      {/* Progress bar for synthesize */}
      {isSynthesize && isRunning && (
        <div className="ml-5 mt-1.5">
          <div className="h-0.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-info"
              style={{ animation: "duct-step-fill 180s cubic-bezier(0.08, 0, 0.2, 1) forwards" }}
            />
          </div>
          <style>{STEP_FILL_KEYFRAMES}</style>
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
