"use client";

/**
 * What the agent did, in the transcript, where it happened.
 *
 * A run is mostly tool calls, and the app used to show almost none of them: a
 * data pull became a line in a separate tab, a web search and an image the
 * agent drew became nothing at all. The reader got ninety seconds of
 * "Working…" and then a brief citing a source they never saw it open.
 *
 * One row per call, in the flow of the conversation. Deliberately **one line**
 * until you ask for more: a run that reads twelve sources would otherwise push
 * the prose off the screen with twelve panels, and the point of the row is to
 * be glanceable while the agent is mid-thought. Expanded it carries what the
 * kind actually has — the window and the row count for a pull, the sources for
 * a search, the picture for an image — and, when something failed, the
 * provider's own sentence and the place the fix lives.
 *
 * The vocabulary is shared on purpose: the memory rows above it and these read
 * as the same quiet register, because to a reader "it remembered something"
 * and "it read Search Console" are the same kind of fact.
 */

import { useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronRight,
  Database,
  FileText,
  Globe,
  Image as ImageIcon,
  Layers,
  Link as LinkIcon,
  Sparkles,
} from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { ActivityKind } from "@/lib/agentEvents";
import { StepStatus } from "@/lib/agentSteps";
import { Spinner } from "@/components/ui/spinner";
import { Lightbox } from "@/components/ui/lightbox";
import { CONNECTOR_NAMES, LOGOS } from "@/components/connections/logos";
import { faviconUrl, safeHostname } from "@/lib/favicon";
import { formatDate } from "@/lib/format";

// A pull that failed for one of these is fixed on the Connections page, and
// nowhere else. Any other failure is the agent's problem to route around, so
// the row says what happened and offers nothing.
const RECONNECT_REASONS = new Set(["reauth_required", "not_connected", "needs_account"]);

const KIND_ICONS = {
  [ActivityKind.DATA]: Database,
  [ActivityKind.WEB_SEARCH]: Globe,
  [ActivityKind.WEB_FETCH]: LinkIcon,
  [ActivityKind.IMAGE]: ImageIcon,
  [ActivityKind.SLIDE]: Layers,
  [ActivityKind.SUBAGENT]: Sparkles,
  [ActivityKind.MEMORY]: Brain,
  [ActivityKind.CONTEXT]: BookOpen,
  [ActivityKind.ARTIFACT]: FileText,
  [ActivityKind.ACTION]: CheckCircle2,
};

// The verb for each tool whose card carries no sentence of its own — the
// reads of what the project holds and the things done on the person's
// behalf. The backend sends fields, never prose; the words live here so
// they are translated with the rest of the interface.
const TOOL_WORDS = {
  ProjectContext: msg`Read project context`,
  ListDataSources: msg`Checked connected sources`,
  fetch_brand_context: msg`Read the brand context`,
  fetch_topic_bank: msg`Read the topic bank`,
  fetch_format_library: msg`Read the format library`,
  fetch_avatar_library: msg`Read the avatar library`,
  fetch_content_history: msg`Read what was posted before`,
  fetch_content_assets: msg`Read the asset library`,
  fetch_discovered_references: msg`Read the discovered references`,
  fetch_post: msg`Opened the post`,
  fetch_slide_context: msg`Read the slide`,
  submit_plan: msg`Saved the plan`,
  submit_post_draft: msg`Saved the draft`,
  edit_slide: msg`Edited a slide`,
  publish_post: msg`Published the post`,
  mark_posted: msg`Marked as posted`,
  log_metrics: msg`Logged metrics`,
};

// What each block of a run's context is called on the row. The keys are the
// runners' own block names; an unknown one falls back to its key in words.
const BLOCK_WORDS = {
  business_context: msg`business`,
  user_context: msg`your profile`,
  profile: msg`your profile`,
  memory: msg`memory`,
  project_memory: msg`memory`,
  data_sources: msg`connected sources`,
  research_context: msg`research`,
  brand: msg`brand`,
  crawl_pages: msg`the crawl`,
  prompt: msg`your ask`,
};
// Run settings the person chose; not a thing the model "read".
const SETTING_BLOCKS = new Set(["artifact_format", "autonomy", "compress", "resume_primer"]);

function blockWords(blocks, i18n) {
  return (blocks || [])
    .filter((b) => !SETTING_BLOCKS.has(b))
    .map((b) => (BLOCK_WORDS[b] ? i18n._(BLOCK_WORDS[b]) : String(b).replace(/_/g, " ")))
    .join(" · ");
}

/** `ga4_landing_pages` → `landing pages`. The entity ids are written for the
 *  model; the connector's name is already beside it, so its prefix is noise. */
function entityWords(title, source) {
  const words = String(title || "").replace(/_/g, " ");
  const prefix = String(source || "").replace(/_/g, " ");
  return prefix && words.startsWith(`${prefix} `) ? words.slice(prefix.length + 1) : words;
}

/**
 * "20 Aug → 17 Sep" in the reader's locale, or "" when there is no window.
 *
 * No year on either end: the window is almost always inside one, it is the
 * aside on a one-line row, and "Aug 20, 2026 → Sep 17, 2026" is wider than
 * everything it sits beside.
 */
function windowLabel(meta, locale) {
  const from = meta?.date_from;
  const to = meta?.date_to;
  if (!from) return "";
  const opts = { locale, withYear: false };
  return to ? `${formatDate(from, opts)} → ${formatDate(to, opts)}` : formatDate(from, opts);
}

function Mark({ activity }) {
  const logo = activity.kind === ActivityKind.DATA ? LOGOS[activity.source] : null;
  if (logo) return <span className="flex size-4 shrink-0 items-center justify-center [&_img]:size-4 [&_svg]:size-4">{logo}</span>;
  const Icon = KIND_ICONS[activity.kind] || Database;
  return <Icon className="size-3.5 shrink-0" aria-hidden="true" />;
}

/** The one-line summary. Each kind says the one thing worth reading at a
 *  glance; everything else waits behind the chevron. `named` is false where
 *  the connector is already the heading above the row — the Data roll-up —
 *  and the entity then leads instead of being said twice. */
function useSummary(activity, named) {
  const { i18n, t } = useLingui();
  const meta = activity.meta || {};
  switch (activity.kind) {
    case ActivityKind.DATA: {
      const entity = entityWords(activity.title, activity.source);
      if (!named) return { lead: entity, detail: "", aside: windowLabel(meta, i18n.locale) };
      const name = CONNECTOR_NAMES[activity.source]
        ? i18n._(CONNECTOR_NAMES[activity.source])
        : String(activity.source || "").replace(/_/g, " ");
      return { lead: name, detail: entity, aside: windowLabel(meta, i18n.locale) };
    }
    case ActivityKind.WEB_SEARCH:
      return {
        lead: t`Searched the web`,
        detail: activity.title,
        aside: meta.source_count ? t`${meta.source_count} sources` : "",
      };
    case ActivityKind.WEB_FETCH: {
      const count = typeof meta.count === "number" && Array.isArray(meta.urls) ? meta.count : 0;
      return {
        lead: count > 1 ? t`Read ${count} pages of` : t`Read`,
        detail: activity.title,
        aside: meta.failed ? t`${meta.failed} failed` : "",
      };
    }
    case ActivityKind.IMAGE:
      return { lead: t`Drew an image`, detail: activity.title, aside: "" };
    case ActivityKind.SLIDE:
      return { lead: t`Rendered a slide`, detail: activity.title, aside: "" };
    case ActivityKind.MEMORY:
      if (meta.read) return { lead: t`Read a memory`, detail: activity.title, aside: "" };
      return {
        lead: t`Searched memory`,
        detail: activity.title,
        aside: typeof meta.count === "number" ? t`${meta.count} matches` : "",
      };
    case ActivityKind.CONTEXT: {
      const word = TOOL_WORDS[activity.tool] ? i18n._(TOOL_WORDS[activity.tool]) : t`Read project context`;
      const detail = Array.isArray(meta.blocks) ? blockWords(meta.blocks, i18n) : activity.title;
      return { lead: word, detail, aside: typeof meta.count === "number" ? String(meta.count) : "" };
    }
    case ActivityKind.ARTIFACT:
      if (meta.listing) return { lead: t`Listed this thread's documents`, detail: "", aside: typeof meta.count === "number" ? String(meta.count) : "" };
      return { lead: t`Opened`, detail: activity.title, aside: meta.version ? `v${meta.version}` : "" };
    case ActivityKind.ACTION: {
      const word = TOOL_WORDS[activity.tool] ? i18n._(TOOL_WORDS[activity.tool]) : t`Did something`;
      // When it goes out is the one fact a publish has that the verb does not.
      return { lead: word, detail: activity.title, aside: meta.scheduled_at ? formatDate(meta.scheduled_at, { locale: i18n.locale }) : "" };
    }
    default:
      return { lead: t`Asked ${activity.title}`, detail: meta.brief || "", aside: "" };
  }
}

function StatusMark({ status }) {
  const { t } = useLingui();
  if (status === StepStatus.RUNNING) return <Spinner className="size-3 text-info" aria-label={t`Working`} />;
  if (status === StepStatus.ERROR) {
    return <span className="size-1.5 shrink-0 rounded-full bg-destructive" aria-label={t`Failed`} />;
  }
  return null;
}

/** The sources a search came back with, as chips. The favicon is the fastest
 *  "which site is this" there is; the title is what makes it a link. */
function SourceChips({ sources }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {sources.map((s, i) => {
        const host = safeHostname(s.url) || s.title;
        return (
          <a
            key={`${s.url}-${i}`}
            href={s.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex max-w-[16rem] items-center gap-1.5 rounded-full border border-border bg-card px-2 py-0.5 text-2xs text-muted-foreground no-underline transition-colors hover:text-foreground"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={faviconUrl(s.url, 32)} alt="" width="12" height="12" className="size-3 rounded-sm" loading="lazy" />
            <span className="truncate">{s.title || host}</span>
          </a>
        );
      })}
    </div>
  );
}

/** Pictures the agent made, at thumbnail size, full size on click. */
function ImageStrip({ images, alt }) {
  const [open, setOpen] = useState("");
  const { t } = useLingui();
  return (
    <div className="flex flex-wrap gap-2">
      {images.map((url) => {
        return (
          <button
            key={url}
            type="button"
            onClick={() => setOpen(url)}
            title={t`View full screen`}
            className="overflow-hidden rounded-lg border border-border/60 bg-muted/40 transition-opacity hover:opacity-95"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={url} alt={alt || t`Generated image`} loading="lazy" className="block h-28 w-auto max-w-[12rem] object-cover" />
          </button>
        );
      })}
      <Lightbox open={Boolean(open)} onOpenChange={() => setOpen("")} src={open} alt={alt} />
    </div>
  );
}

/** What the chevron reveals — per kind, and only what that kind has. */
function ActivityDetail({ activity }) {
  const { i18n, t } = useLingui();
  const meta = activity.meta || {};
  const failed = activity.status === StepStatus.ERROR;
  const images = Array.isArray(meta.images) ? meta.images.filter(Boolean) : [];
  const sources = Array.isArray(meta.sources) ? meta.sources.filter((s) => s?.url) : [];

  return (
    <div className="space-y-2 pb-2 pl-6 pr-1 text-xs text-muted-foreground">
      {activity.kind === ActivityKind.DATA && !failed && (
        // What the line could not carry: the catalogue id the agent actually
        // asked for — the name to quote when a number looks wrong — and how
        // much came back. The window is already in the row above.
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-mono text-2xs">{activity.title}</span>
          {typeof meta.rows === "number" && <span><Trans>{meta.rows} rows</Trans></span>}
        </p>
      )}

      {activity.kind === ActivityKind.WEB_SEARCH && sources.length > 0 && <SourceChips sources={sources} />}

      {activity.kind === ActivityKind.WEB_FETCH && meta.url && (
        <p className="break-all">
          <a href={meta.url} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2 hover:text-foreground">
            {meta.url}
          </a>
          {meta.truncated && <span className="ml-2"><Trans>(read the first part of the page)</Trans></span>}
        </p>
      )}
      {activity.kind === ActivityKind.WEB_FETCH && Array.isArray(meta.urls) && meta.urls.length > 0 && (
        // Every page of the audit's read, each a link — the row above names
        // only the site.
        <ul className="space-y-0.5 break-all">
          {meta.urls.map((url) => (
            <li key={url}>
              <a href={url} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2 hover:text-foreground">{url}</a>
            </li>
          ))}
        </ul>
      )}
      {activity.kind === ActivityKind.CONTEXT && activity.tool === "ProjectContext" && (
        <p><Trans>The turn the model read was composed from these, on top of your message — the same way every run on this project starts.</Trans></p>
      )}
      {activity.kind === ActivityKind.ARTIFACT && meta.artifact_id && !meta.listing && (
        <Link href={`/artifacts/${meta.artifact_id}`} className="inline-block underline underline-offset-2 hover:text-foreground">
          <Trans>Open the document →</Trans>
        </Link>
      )}

      {images.length > 0 && <ImageStrip images={images} alt={activity.title} />}

      {activity.kind === ActivityKind.SUBAGENT && meta.summary && (
        // What it came back with. The brief is already on the line above, so
        // repeating it here would make the chevron a no-op.
        <p className="whitespace-pre-wrap">{meta.summary}</p>
      )}

      {failed && activity.error && (
        // The provider's own sentence, not the model's paraphrase of it: the
        // person deciding whether to reconnect needs what the API said.
        <p className="break-words font-mono text-2xs text-destructive/80">{activity.error}</p>
      )}
      {failed && RECONNECT_REASONS.has(activity.reason) && (
        <Link href="/connections" className="inline-block text-2xs underline underline-offset-2 hover:text-foreground">
          <Trans>Reconnect this source →</Trans>
        </Link>
      )}
      {activity.kind === ActivityKind.IMAGE && (meta.model || meta.attached_to) && (
        <p className="flex flex-wrap gap-x-3 text-2xs">
          {meta.attached_to && <span>{t`On slide ${meta.attached_to}`}</span>}
          {meta.model && <span>{t`Drawn by ${meta.model}`}</span>}
        </p>
      )}
    </div>
  );
}

/** Whether a row has anything behind the chevron. A search with no sources and
 *  a pull that came back clean with no counts have nothing to open, and a
 *  control that opens an empty panel is worse than no control. */
function hasDetail(activity) {
  const meta = activity.meta || {};
  if (activity.status === StepStatus.ERROR) return Boolean(activity.error || RECONNECT_REASONS.has(activity.reason));
  switch (activity.kind) {
    case ActivityKind.DATA:
      return typeof meta.rows === "number" || Boolean(activity.title);
    case ActivityKind.WEB_SEARCH:
      return Array.isArray(meta.sources) && meta.sources.length > 0;
    case ActivityKind.WEB_FETCH:
      return Boolean(meta.url) || (Array.isArray(meta.urls) && meta.urls.length > 0);
    case ActivityKind.IMAGE:
    case ActivityKind.SLIDE:
      return Array.isArray(meta.images) && meta.images.length > 0;
    case ActivityKind.SUBAGENT:
      return Boolean(meta.summary);
    case ActivityKind.CONTEXT:
      return activity.tool === "ProjectContext";
    case ActivityKind.ARTIFACT:
      return Boolean(meta.artifact_id) && !meta.listing;
    default:
      return false;
  }
}

export function ActivityRow({ activity, defaultOpen = false, named = true }) {
  const [open, setOpen] = useState(defaultOpen);
  const { lead, detail, aside } = useSummary(activity, named);
  const expandable = hasDetail(activity);
  const failed = activity.status === StepStatus.ERROR;

  const line = (
    <>
      {named && <Mark activity={activity} />}
      <span className={`shrink-0 font-medium ${failed ? "text-destructive" : "text-foreground/80"}`}>{lead}</span>
      {/* The flexible middle, even when empty: without it the chevron and the
          window bunch against the label instead of holding the right edge. */}
      <span className="min-w-0 flex-1 truncate text-muted-foreground">{detail}</span>
      {aside && <span className="shrink-0 text-2xs text-muted-foreground">{aside}</span>}
      <StatusMark status={activity.status} />
    </>
  );

  if (!expandable) {
    return <div className="flex items-center gap-2 py-1 pl-1 pr-2 text-xs">{line}</div>;
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-md py-1 pl-1 pr-2 text-left text-xs transition-colors hover:bg-muted/50"
      >
        {line}
        <ChevronRight
          className={`size-3 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && <ActivityDetail activity={activity} />}
    </div>
  );
}

/**
 * A burst of calls as one block. The agent reads four sources in a row and
 * then says something about them; the rail is what makes that read as one
 * action rather than four interruptions.
 */
export function ActivityGroup({ activities, defaultOpen = false }) {
  if (!activities?.length) return null;
  return (
    <div className="my-1.5 border-l border-border/60 pl-2">
      {activities.map((activity) => (
        <ActivityRow key={activity.id} activity={activity} defaultOpen={defaultOpen} />
      ))}
    </div>
  );
}

export default ActivityGroup;
