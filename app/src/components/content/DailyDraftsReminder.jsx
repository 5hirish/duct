"use client";

import { useEffect } from "react";
import { plural } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import { listPosts } from "@/lib/contentApi";
import { PostStatus } from "@/lib/contentEnums";
import {
  REMINDER_INTERVAL_MS,
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
 * is open: "3 drafts ready". Renders nothing. It only speaks while the window
 * is not being looked at, and a notice that could not be shown is tried again
 * next time round rather than marked sent, so a day is never spent on a
 * notice nobody saw.
 */
export default function DailyDraftsReminder() {
  const { t } = useLingui();

  useEffect(() => {
    let stopped = false;

    async function tick() {
      const now = new Date();
      if (!isDue(readReminder(), now)) return;
      const projectId = getActiveProjectId();
      if (!projectId || (await notificationSurface()) === "none") return;
      try {
        const drafts = await listPosts(projectId, { status: PostStatus.DRAFT });
        if (stopped) return;
        const notice = reminderFor(drafts);
        if (!notice) {
          writeReminder({ last: localDay(now) });
          return;
        }
        const shown = await notifyIfAway({
          title: plural(notice.count, { one: "# draft ready", other: "# drafts ready" }),
          body: t`Approve, edit or skip them on Content Studio's Posts tab.`,
          tag: "daily-drafts",
        });
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
