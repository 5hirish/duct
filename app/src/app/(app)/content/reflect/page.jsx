"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Trans } from "@lingui/react/macro";
import ContentWorkspace from "@/components/content/ContentWorkspace";
import ReflectionViewport from "@/components/content/ReflectionViewport";
import { getReflection, listReflections } from "@/lib/contentApi";
import { dayKey } from "@/lib/format";
import { getActiveProjectId } from "@/lib/projects";

/**
 * A day's reflection in the split workspace (issue #270): chat on the left,
 * the reflection on the right.
 *
 * Query params:
 *   - day (optional) — an ISO date; today on the reader's calendar when absent
 *
 * A day that already has a reflection opens it and resumes the conversation
 * that wrote it, so reopening never spends a run; a day without one starts
 * the run that reads it.
 */
export default function ReflectPage() {
  const router = useRouter();
  const search = useSearchParams();
  // Today on the reader's own calendar, not the server's UTC one.
  const day = search.get("day") || dayKey(new Date());
  const [projectId, setProjectId] = useState(null);
  const [existing, setExisting] = useState(undefined); // undefined: still looking
  const [saved, setSaved] = useState(null);

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) { router.replace("/content"); return; }
    setProjectId(id);
    let cancelled = false;
    listReflections(id)
      .then((rows) => {
        if (cancelled) return;
        const row = (rows || []).find((r) => r.day === day) || null;
        setExisting(row);
        if (row) getReflection(row.group_id).then((r) => !cancelled && setSaved(r)).catch(() => {});
      })
      .catch(() => !cancelled && setExisting(null));
    return () => { cancelled = true; };
  }, [router, day]);

  if (!projectId || existing === undefined) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground"><Trans>Loading session…</Trans></p>
      </div>
    );
  }

  return (
    <div className="h-full">
      <ContentWorkspace
        mode="reflect_day"
        context={{
          projectId,
          day,
          groupId: existing?.group_id,
          ...(existing ? { resume: true, artifactType: "reflection", artifactId: existing.group_id } : {}),
        }}
        renderViewport={({ payload, building }) => (
          <ReflectionViewport reflection={payload || saved} building={building && !saved} />
        )}
      />
    </div>
  );
}
