"use client";

import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { useLingui } from "@lingui/react/macro";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { REMINDER_TIMES, readReminder, writeReminder } from "@/lib/dailyReminder";
import { notificationSurface } from "@/lib/notify";

const OFF = "off";

/**
 * When the drafts queue's daily notice arrives, or that it does not (issue
 * #266). Per device, like the notice. Hidden where nothing can notify: a
 * setting for a notice that can never arrive is a promise the page breaks.
 */
export default function ReminderSetting({ surface: surfaceOverride }) {
  const { t, i18n } = useLingui();
  const [surface, setSurface] = useState(surfaceOverride || null);
  const [value, setValue] = useState(DEFAULT_VALUE);

  useEffect(() => {
    const saved = readReminder();
    setValue(saved.off ? OFF : saved.time);
    if (!surfaceOverride) notificationSurface().then(setSurface);
  }, [surfaceOverride]);

  if (!surface || surface === "none") return null;

  function change(next) {
    setValue(next);
    writeReminder(next === OFF ? { off: true } : { off: false, time: next, last: "" });
  }

  const label = (time) => {
    const [h, m] = time.split(":").map(Number);
    return new Date(2000, 0, 1, h, m).toLocaleTimeString(i18n.locale, { hour: "numeric", minute: "2-digit" });
  };

  return (
    <Select value={value} onValueChange={change}>
      <SelectTrigger size="sm" className="h-8 gap-1.5 text-xs" aria-label={t`Daily reminder`}>
        <BellRing className="size-3.5 text-muted-foreground" aria-hidden="true" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper" align="end">
        {REMINDER_TIMES.map((time) => {
          const at = label(time);
          return (
            <SelectItem key={time} value={time}>
              {t`Remind me at ${at}`}
            </SelectItem>
          );
        })}
        <SelectItem value={OFF}>{t`No daily reminder`}</SelectItem>
      </SelectContent>
    </Select>
  );
}

const DEFAULT_VALUE = "09:00";
