"use client";

import { useEffect } from "react";
import { plural } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { getReflectionQueue, listReflections } from "@/lib/contentApi";
import {
  REMINDER_INTERVAL_MS,
  ReminderKind,
  isDue,
  localDay,
  readReminder,
  reminderFor,
  writeReminder,
} from "@/lib/dailyReminder";
import { notificationSurface, notifyIfAway } from "@/lib/notify";
import { getActiveProjectId } from "@/lib/projects";

/**
 * One notice a day about the drafts queue (issue #266), from wherever the app
 * is open: "3 drafts ready", or a nudge when today has no reflection yet.
 * Renders nothing. It only speaks while the window is not being looked at,
 * and a notice that could not be shown is tried again next time round rather
 * than marked sent, so a day is never spent on a notice nobody saw.
 */
export default function DailyReflectionReminder() {
  const { t } = useLingui();

  useEffect(() => {
    let stopped = false;

    async function tick() {
      const now = new Date();
      if (!isDue(readReminder(), now)) return;
      const projectId = getActiveProjectId();
      if (!projectId || (await notificationSurface()) === "none") return;
      try {
        const [queue, journal] = await Promise.all([
          getReflectionQueue(projectId),
          listReflections(projectId),
        ]);
        if (stopped) return;
        const notice = reminderFor({ queue, journal, now });
        if (!notice) {
          writeReminder({ last: localDay(now) });
          return;
        }
        const { count } = notice;
        const shown = await notifyIfAway(
          notice.kind === ReminderKind.DRAFTS
            ? {
                title: plural(count, { one: "# draft ready", other: "# drafts ready" }),
                body: t`From your daily reflection. Approve, edit or skip them in Content Studio.`,
                tag: "daily-reflection",
              }
            : {
                title: t`Reflect on today`,
                body: t`Duct is ready to read today's work and draft what's worth posting.`,
                tag: "daily-reflection",
              },
        );
        if (shown) writeReminder({ last: localDay(now) });
      } catch {
        /* offline or signed out: the next tick tries again */
      }
    }

    tick();
    const timer = setInterval(tick, REMINDER_INTERVAL_MS);
    return () => { stopped = true; clearInterval(timer); };
    // `t` follows the locale; the loop is started once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
