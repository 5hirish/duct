"use client";

import { memo } from "react";
import { useLingui } from "@lingui/react/macro";
import { daySources } from "@/lib/contentFeed";
import { cn } from "@/lib/utils";
import { KindStone } from "./FeedKind";

/**
 * What a plan day from shipped work stands on, as chips that open the
 * source: the pull request or release on GitHub, the brief in the library.
 * Each leads with its kind's stone, so a row reads at a glance (a release is
 * terracotta, a pull request ochre) before a title is read. The title is the
 * source's own (the backend fills it from the feed, never from the model), so
 * a chip cannot claim something the source does not.
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
        const label = s.title || s.ref;
        const chip = (
          <>
            <KindStone kind={s.kind} size={size === "xs" ? "xs" : "sm"} />
            <span className="truncate">{label}</span>
          </>
        );
        const cls = cn(
          "inline-flex max-w-60 items-center rounded-full border border-border/60 bg-card text-muted-foreground transition-colors",
          size === "xs" ? "gap-1 py-0.5 pr-2 pl-0.5 text-2xs" : "gap-1.5 py-0.5 pr-2.5 pl-0.5 text-xs",
        );
        return (
          <li key={s.ref} className="min-w-0">
            {s.url ? (
              <a href={s.url} target={s.url.startsWith("/") ? undefined : "_blank"} rel="noreferrer"
                className={cn(cls, "hover:border-border hover:text-foreground")}>
                {chip}
              </a>
            ) : (
              <span className={cls}>{chip}</span>
            )}
          </li>
        );
      })}
      {more > 0 && <li className="text-xs text-muted-foreground tabular-nums">+{more}</li>}
    </ul>
  );
}

export default memo(SourceChips);
