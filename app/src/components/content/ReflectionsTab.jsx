"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { NotebookPen, Plus } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import LoadError from "@/components/LoadError";
import { dayLabel } from "@/components/content/ReflectionViewport";
import { listReflections } from "@/lib/contentApi";
import { dayKey } from "@/lib/format";

export const REFLECT_HREF = "/content/reflect";

/**
 * The Reflections tab (issue #270): the journal, one row per day, newest
 * first, each with how many of its drafts still wait for a yes or no.
 *
 * `load` is injectable so /preview can render it without a backend.
 */
export default function ReflectionsTab({ projectId, load = listReflections }) {
  const { t } = useLingui();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load(projectId)
      .then((list) => !cancelled && setRows(Array.isArray(list) ? list : []))
      .catch((e) => !cancelled && setError(String(e?.message || e)));
    return () => { cancelled = true; };
  }, [projectId, load, reloadKey]);

  if (error) {
    return (
      <LoadError
        what={t`your reflections`}
        detail={error}
        onRetry={() => { setError(""); setRows(null); setReloadKey((k) => k + 1); }}
      />
    );
  }
  if (rows === null) {
    return (
      <div className="space-y-2" role="status" aria-label={t`Loading`}>
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
      </div>
    );
  }
  return <ReflectionJournal rows={rows} />;
}

/** The journal itself, from rows already loaded. */
export function ReflectionJournal({ rows }) {
  const { i18n } = useLingui();
  const today = dayKey(new Date());
  const hasToday = rows.some((r) => r.day === today);

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={NotebookPen}
        title={<Trans>No reflections yet</Trans>}
        actions={
          <Button asChild size="sm">
            <Link href={REFLECT_HREF}><Plus className="size-3.5" /> <Trans>Reflect on today</Trans></Link>
          </Button>
        }
      >
        <Trans>
          Once a day, Duct reads what you shipped and what it did on this project, writes what it
          taught you with every claim cited, and drafts the X and LinkedIn posts worth making from it.
        </Trans>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          <Trans>What each day taught, cited to the work it came from.</Trans>
        </p>
        <Button asChild size="sm" variant={hasToday ? "outline" : "default"}>
          <Link href={REFLECT_HREF}>
            {hasToday ? <Trans>Open today&apos;s</Trans> : <><Plus className="size-3.5" /> <Trans>Reflect on today</Trans></>}
          </Link>
        </Button>
      </div>

      <ul className="divide-y rounded-xl border">
        {rows.map((r) => {
          const { waiting, drafts } = r;
          return (
          <li key={r.group_id}>
            <Link
              href={`${REFLECT_HREF}?day=${encodeURIComponent(r.day)}`}
              className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/40"
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">{dayLabel(r.day, i18n.locale)}</p>
                <p className="truncate text-sm font-medium">{r.title}</p>
              </div>
              {waiting > 0 ? (
                <Badge variant="secondary" className="shrink-0 px-1.5 py-0 text-2xs font-normal">
                  <Plural value={waiting} one="# draft waiting" other="# drafts waiting" />
                </Badge>
              ) : drafts > 0 ? (
                <span className="shrink-0 text-2xs text-muted-foreground">
                  <Plural value={drafts} one="# draft" other="# drafts" />
                </span>
              ) : null}
            </Link>
          </li>
          );
        })}
      </ul>
    </div>
  );
}
