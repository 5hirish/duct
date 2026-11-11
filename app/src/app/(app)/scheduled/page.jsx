"use client";

// Scheduled — every run nobody starts by hand, for the active project
// (#562). The page is the loop's state as the server holds it: what runs and
// when, on which host, whether it is running or needs the person, what the
// last run came to and cost, and the history of every run, skips included.
// Nothing here is cached locally: only the server knows whether a run is going.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CalendarClock } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import LoadError from "@/components/LoadError";
import ScheduleCard from "@/components/schedules/ScheduleCard";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { Page, PageHeader } from "@/components/ui/page";
import { SkeletonList } from "@/components/ui/skeleton";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { getActiveProjectId } from "@/lib/projects";
import { deleteSchedule, listSchedules, runScheduleNow, scheduleHistory, updateSchedule } from "@/lib/schedulesApi";
import { pollWhileVisible } from "@/lib/visibility";

// The plan board opens its From your work sheet on this, where Repeat weekly is.
const FEED_SHEET_HREF = "/content?tab=plans&from=work";

// What a schedule looks like after a month of Mondays, drawn by the real card
// in the empty state's example frame. Dates are relative, so it never ages.
const DAY_MS = 86_400_000;
const EXAMPLE_NOW = Date.now();
const ago = (days) => new Date(EXAMPLE_NOW - days * DAY_MS).toISOString();
const EXAMPLE_SCHEDULE = {
  id: "example", name: "", cadence: "weekly", weekday: 0, at_time: "09:00", timezone: "UTC",
  enabled: true, host: "cloud", monthly_cap: 6, running: false, needs_reason: "", mine: false,
  next_run_at: new Date(EXAMPLE_NOW + 3 * DAY_MS).toISOString(), runs_this_month: 2,
  last: { at: ago(4), outcome: "proposed", cost_usd: 0.1, conversation_id: "example" },
  recent: [
    { at: ago(4), outcome: "proposed" }, { at: ago(11), outcome: "nothing_new" },
    { at: ago(18), outcome: "proposed" }, { at: ago(25), outcome: "proposed" },
  ],
};

// While a run is going the card changes on its own; a quiet page is not polled.
const RUNNING_POLL_MS = 10_000;

export default function ScheduledPage() {
  const { t } = useLingui();
  const [projectId, setProjectId] = useState(null);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const { confirm, dialog } = useConfirm();

  const load = useCallback(async (id) => {
    try {
      setRows(await listSchedules(id));
      setError("");
    } catch (e) {
      setError(e?.message || "");
    }
  }, []);

  useEffect(() => {
    const id = getActiveProjectId();
    setProjectId(id);
    if (id) load(id);
    else setRows([]);
  }, [load]);

  const anyRunning = Array.isArray(rows) && rows.some((r) => r.running);
  useEffect(() => {
    if (!anyRunning || !projectId) return undefined;
    return pollWhileVisible(() => load(projectId), RUNNING_POLL_MS);
  }, [anyRunning, projectId, load]);

  async function act(id, fn) {
    setBusy(id);
    try {
      const updated = await fn();
      if (updated) setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (e) {
      setError(e?.message || "");
    } finally {
      setBusy(null);
    }
  }

  async function remove(row) {
    const ok = await confirm({
      title: t`Delete this schedule?`,
      description: t`Runs it already made stay in the project's activity, and their conversations stay open to you.`,
      action: t`Delete`,
      destructive: true,
    });
    if (!ok) return;
    setBusy(row.id);
    try {
      await deleteSchedule(row.id);
      setRows((prev) => prev.filter((r) => r.id !== row.id));
    } catch (e) {
      setError(e?.message || "");
    } finally {
      setBusy(null);
    }
  }

  const count = Array.isArray(rows) ? rows.length : 0;
  const waiting = Array.isArray(rows) ? rows.filter((r) => r.needs_reason || r.last?.outcome === "proposed").length : 0;

  return (
    <Page>
      <PageHeader
        title={t`Scheduled`}
        status={rows === null ? undefined : waiting > 0 ? t`${waiting} need you` : count > 0 ? t`${count} scheduled` : undefined}
        help={t`A schedule runs an agent at a set time and leaves its result for you to accept. It runs on the backend that made it: Duct cloud, or this computer while the app is open. A laptop that was asleep catches up once when it wakes.`}
      />
      {dialog}
      {error && (
        <LoadError what={t`your schedules`} detail={error} onRetry={() => { setError(""); if (projectId) load(projectId); }} />
      )}
      {rows === null ? (
        <SkeletonList rows={2} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title={t`Nothing scheduled yet`}
          exampleLabel={t`Example`}
          example={<ScheduleCard schedule={EXAMPLE_SCHEDULE} />}
          actions={
            <Button asChild size="sm">
              <Link href={FEED_SHEET_HREF}><Trans>Plan from your work weekly</Trans></Link>
            </Button>
          }
        >
          <Trans>Every Monday, Duct reads what you shipped and has a plan waiting for you to accept.</Trans>
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((row) => (
            <ScheduleCard
              key={row.id}
              schedule={row}
              busy={busy === row.id}
              onRunNow={() => act(row.id, () => runScheduleNow(row.id))}
              onToggle={(enabled) => act(row.id, () => updateSchedule(row.id, { enabled }))}
              onDelete={() => remove(row)}
              loadHistory={() => scheduleHistory(row.id)}
            />
          ))}
        </div>
      )}
    </Page>
  );
}
