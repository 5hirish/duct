"use client";

import Link from "next/link";
import {
  Brain,
  FileText,
  GitCommitHorizontal,
  GitPullRequest,
  Link2,
  NotebookPen,
  SlidersHorizontal,
} from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import EmptyState from "@/components/ui/empty-state";
import { SCHEDULED_META, statusMeta } from "@/lib/contentStatus";
import { PostStatus } from "@/lib/contentEnums";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";

// A claim's source, as the model cites it: gh:pr-412, art:organic-slip,
// cs:3f2a9c1d, mem:9c1d2e3f (agents/content/reflection.py mints them).
const REF = /\[((?:gh|art|cs|mem):[A-Za-z0-9._#/-]+)\]/g;

const KIND_ICON = {
  pull_request: GitPullRequest,
  commit: GitCommitHorizontal,
  issue: FileText,
  release: FileText,
  docs_change: FileText,
  artifact: FileText,
  change_set: SlidersHorizontal,
  memory: Brain,
};

/** An ISO day as the reader's calendar shows it, never shifted by timezone. */
export function dayLabel(day, locale) {
  if (!day) return "";
  const d = new Date(`${day}T12:00:00`);
  if (Number.isNaN(d.getTime())) return day;
  return d.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" });
}

function draftsOf(reflection) {
  const drafts = reflection?.drafts;
  if (!drafts) return [];
  return Array.isArray(drafts) ? drafts : Object.values(drafts);
}

/**
 * The Daily Reflection (issue #270), as the right-hand pane of its workspace
 * and on its own page: each work stream's what happened with its sources as
 * chips, what the field says with the quoted line, the lesson, and the
 * drafts derived from it. Provenance comes before the drafts, always: the
 * reflection is worth reading even when nothing gets posted.
 *
 * `reflection` is the ARTIFACT_VERSION payload or GET /content/reflections/{id}:
 * { title, version, label?, reflection: { date, sections, sources }, drafts }.
 */
export default function ReflectionViewport({ reflection, building = false }) {
  const { i18n } = useLingui();
  const data = reflection?.reflection || {};
  const sections = Array.isArray(data.sections) ? data.sections : [];
  const sources = data.sources || {};
  const drafts = draftsOf(reflection);
  const version = reflection?.version || 1;

  if (!sections.length) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <EmptyState icon={NotebookPen} title={building ? <Trans>Reading the day…</Trans> : <Trans>No reflection yet</Trans>}>
          {building ? (
            <Trans>
              What shipped in the repository, and what Duct wrote, proposed and learned on this project.
              The reflection appears here as each stream is written.
            </Trans>
          ) : (
            <Trans>Ask in chat for today&apos;s reflection.</Trans>
          )}
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <article className="mx-auto max-w-2xl space-y-6 p-5">
        <header className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {dayLabel(data.date, i18n.locale)}
          </p>
          <h2 className="text-xl font-semibold leading-snug text-balance">{reflection.title}</h2>
          {version > 1 && (
            <p className="text-xs text-muted-foreground">
              <Trans>Version {version}</Trans>
              {reflection.label ? ` · ${reflection.label}` : ""}
            </p>
          )}
        </header>

        {sections.map((section) => (
          <Section
            key={section.id}
            section={section}
            sources={sources}
            drafts={drafts.filter((p) => p.reflection?.section_id === section.id)}
          />
        ))}

        <p className="border-t pt-4 text-xs text-muted-foreground">
          <Trans>
            Read it wrong? Say so in chat. The reflection gets a new version and its drafts follow.
          </Trans>
        </p>
      </article>
    </div>
  );
}

function Section({ section, sources, drafts }) {
  return (
    <section className="space-y-4 rounded-xl border bg-card p-4">
      <h3 className="text-base font-semibold">{section.title}</h3>

      <Part label={<Trans>What happened</Trans>}>
        <CitedText text={section.happened} sources={sources} />
      </Part>

      {section.field?.quote && (
        <Part label={<Trans>What the field says</Trans>}>
          <blockquote className="border-l-2 border-primary/40 pl-3 text-sm italic leading-relaxed">
            {section.field.quote}
          </blockquote>
          <a
            href={section.field.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            <Link2 className="size-3" aria-hidden="true" />
            {section.field.title || hostOf(section.field.url)}
          </a>
        </Part>
      )}

      <Part label={<Trans>The lesson</Trans>}>
        <p className="text-sm font-medium leading-relaxed">{section.lesson}</p>
      </Part>

      {drafts.length > 0 && (
        <Part label={<Trans>Say it</Trans>}>
          <div className="grid grid-cols-1 gap-2 @lg:grid-cols-2">
            {drafts.map((post) => <DraftCard key={post.id} post={post} />)}
          </div>
        </Part>
      )}
    </section>
  );
}

function Part({ label, children }) {
  return (
    <div className="space-y-1.5">
      <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}

/** The model's prose with each [ref] turned into a chip that opens its source. */
export function CitedText({ text, sources }) {
  const parts = [];
  let last = 0;
  for (const match of String(text || "").matchAll(REF)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(<SourceChip key={`${match[1]}-${match.index}`} refId={match[1]} source={sources?.[match[1]]} />);
    last = match.index + match[0].length;
  }
  if (last < String(text || "").length) parts.push(text.slice(last));
  return <p className="whitespace-pre-line text-sm leading-relaxed">{parts}</p>;
}

function SourceChip({ refId, source }) {
  const Icon = KIND_ICON[source?.kind] || FileText;
  const label = source?.title || refId;
  const chip = (
    <span
      className="mx-0.5 inline-flex max-w-[16rem] items-center gap-1 rounded-full border bg-muted/60 px-1.5 py-px align-baseline text-2xs font-medium text-muted-foreground"
      title={label}
    >
      <Icon className="size-3 shrink-0" aria-hidden="true" />
      <span className="truncate">{label}</span>
    </span>
  );
  if (!source?.url) return chip;
  const external = /^https?:/.test(source.url);
  return external ? (
    <a href={source.url} target="_blank" rel="noreferrer" className="hover:opacity-80">{chip}</a>
  ) : (
    <Link href={source.url} className="hover:opacity-80">{chip}</Link>
  );
}

function DraftCard({ post }) {
  const { i18n } = useLingui();
  const channel = post.platforms?.[0] || "";
  // A scheduled post's colour and word live apart from the other statuses'.
  const meta = post.status === PostStatus.SCHEDULED ? SCHEDULED_META : statusMeta(post.status || PostStatus.PENDING);
  return (
    <Link
      href={`/content/posts/${post.id}`}
      className="group flex flex-col gap-2 rounded-lg border bg-background p-3 transition-colors hover:border-primary/40"
    >
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <PlatformGlyph platform={channel} className="size-3.5" />
        {platformMeta(channel).label}
        <Badge variant={meta.badgeVariant} className="ml-auto px-1.5 py-0 text-2xs font-normal">
          {i18n._(meta.label)}
        </Badge>
      </span>
      <span className="line-clamp-4 whitespace-pre-line text-sm leading-snug">{post.caption}</span>
    </Link>
  );
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
