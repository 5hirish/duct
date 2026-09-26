"use client";

import { ArrowUpRight, CopyPlus } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { CLONE_APPROACH_LABELS } from "@/lib/contentEnums";
import { parseTikTokPostUrl } from "@/lib/tiktokUrl";

/**
 * Where a cloned post came from: the reference, why it worked, and what the
 * clone kept. Renders nothing for a post that was not cloned.
 *
 * `source` is the post's `clone_source` (backend agents/content/schema.py
 * `clone_source`). The link is re-checked before it becomes an href: it is
 * written from a parsed URL server-side, and a page should not have to take
 * that on trust.
 */
export default function CloneSourceNote({ source }) {
  const { i18n } = useLingui();
  if (!source || typeof source !== "object") return null;

  const href = parseTikTokPostUrl(source.url).url || "";
  const author = source.author || "";
  const approach = CLONE_APPROACH_LABELS[source.approach];
  const why = (source.why_it_worked || "").trim();
  const kept = (source.kept || "").trim();

  const name = author ? `@${author}` : "TikTok";
  const reference = href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-0.5 font-medium text-foreground underline-offset-2 hover:underline"
    >
      {name}
      <ArrowUpRight className="size-3" aria-hidden="true" />
    </a>
  ) : (
    <span className="font-medium text-foreground">{name}</span>
  );

  return (
    <section className="space-y-2 rounded-2xl border border-border bg-card p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-muted-foreground">
          <CopyPlus className="size-3.5 shrink-0" aria-hidden="true" />
          <Trans>Modelled on {reference}</Trans>
        </p>
        {approach && <Badge variant="secondary">{i18n._(approach)}</Badge>}
      </div>
      {why && (
        <p className="measure text-muted-foreground">
          <span className="font-medium text-foreground"><Trans>Why it worked:</Trans></span> {why}
        </p>
      )}
      {kept && (
        <p className="measure text-muted-foreground">
          <span className="font-medium text-foreground"><Trans>Kept:</Trans></span> {kept}
        </p>
      )}
    </section>
  );
}
