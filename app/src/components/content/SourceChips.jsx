"use client";

import { memo } from "react";
import { useLingui } from "@lingui/react/macro";
import { BookOpen, Brain, FileText, GitCommitHorizontal, GitPullRequest, ShieldCheck, Tag } from "lucide-react";
import { daySources } from "@/lib/contentFeed";
import { cn } from "@/lib/utils";

// One glyph per kind of source, so a row of chips reads at a glance: a
// release, a pull request, a change Duct applied. Unknown kinds get the page.
const KIND_ICONS = {
  release: Tag,
  pull_request: GitPullRequest,
  commit: GitCommitHorizontal,
  docs_change: BookOpen,
  issue: GitPullRequest,
  change_set: ShieldCheck,
  artifact: FileText,
  memory: Brain,
};

/**
 * What a plan day from shipped work stands on, as chips that open the
 * source: the pull request or release on GitHub, the brief in the library.
 * The title is the source's own (the backend fills it from the feed, never
 * from the model), so a chip cannot claim something the source does not.
 *
 * Props: `sources` ([{ ref, kind, title, url }]) or `day` (reads its
 * `sources`), `max` chips before "+N", `size` "sm" | "xs".
 */
function SourceChips({ sources, day, max = 3, size = "sm", className }) {
  const { t } = useLingui();
  const list = sources ? sources.filter((s) => s && s.ref) : daySources(day);
  if (!list.length) return null;
  const shown = list.slice(0, max);
  const more = list.length - shown.length;
  return (
    <ul className={cn("flex min-w-0 flex-wrap items-center gap-1", className)} aria-label={t`Sources`}>
      {shown.map((s) => {
        const Icon = KIND_ICONS[s.kind] || FileText;
        const label = s.title || s.ref;
        const chip = (
          <>
            <Icon className={cn("shrink-0", size === "xs" ? "size-3" : "size-3.5")} aria-hidden />
            <span className="truncate">{label}</span>
          </>
        );
        const cls = cn(
          "inline-flex max-w-56 items-center gap-1 rounded-md border border-border/60 bg-muted/40 text-muted-foreground",
          size === "xs" ? "px-1.5 py-0.5 text-2xs" : "px-2 py-0.5 text-xs",
        );
        return (
          <li key={s.ref} className="min-w-0">
            {s.url ? (
              <a href={s.url} target={s.url.startsWith("/") ? undefined : "_blank"} rel="noreferrer" className={cn(cls, "hover:text-foreground")}>
                {chip}
              </a>
            ) : (
              <span className={cls}>{chip}</span>
            )}
          </li>
        );
      })}
      {more > 0 && <li className="text-xs text-muted-foreground">+{more}</li>}
    </ul>
  );
}

export default memo(SourceChips);
