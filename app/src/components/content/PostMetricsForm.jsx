"use client";

import { useId, useState } from "react";
import { msg } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { enterPostMetrics } from "@/lib/contentApi";
import {
  SYNCED_METRICS,
  editableMetrics,
  isSyncedPost,
  lastUpdatedAt,
  metricChanges,
  metricInputs,
  metricValue,
} from "@/lib/contentMetrics";
import { formatNumber, relativeTime } from "@/lib/format";

// Label and input shape per metric, keyed by the contract's canonical names
// (lib/contentMetrics.js). The unit rides in the label rather than beside the
// box, so a row of inputs keeps one width and the unit is read out with it.
const FIELDS = Object.freeze({
  views:           { label: msg`Views`, step: 1 },
  likes:           { label: msg`Likes`, step: 1 },
  comments:        { label: msg`Comments`, step: 1 },
  shares:          { label: msg`Shares`, step: 1 },
  saves:           { label: msg`Saves`, step: 1 },
  reach:           { label: msg`Reach`, step: 1 },
  avg_watch_time:  { label: msg`Average watch time (s)`, step: 0.1 },
  completion_rate: { label: msg`Watched to the end (%)`, step: 0.1, max: 100 },
});

/**
 * The numbers of a posted post that PostBridge cannot pull: saves, reach, watch
 * time and completion, plus the four counts when PostBridge did not publish it.
 * One form, no charts. What is typed here is stored as manual, and a sync never
 * overwrites it (backend/service/content_metrics.py).
 *
 * Only changed fields are sent, and clearing a field withdraws that value. The
 * parent keys this by post id; `save` is injectable so /preview can render the
 * saved state without a backend.
 */
export default function PostMetricsForm({ post, onSaved, save = enterPostMetrics }) {
  const { t, i18n } = useLingui();
  const formId = useId();
  const names = editableMetrics(post);
  const synced = isSyncedPost(post);
  const [perf, setPerf] = useState(post?.perf || {});
  const [inputs, setInputs] = useState(() => metricInputs(post?.perf, names));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const changes = metricChanges(inputs, perf, names);
  const dirty = Object.keys(changes).length > 0;
  const updatedAt = lastUpdatedAt(perf);
  const when = updatedAt ? relativeTime(updatedAt, { locale: i18n.locale }) : "";

  async function submit(e) {
    e.preventDefault();
    if (!dirty || saving) return;
    setSaving(true);
    setError("");
    try {
      const updated = await save(post.id, changes);
      const next = updated?.perf || {};
      setPerf(next);
      setInputs(metricInputs(next, names));
      onSaved?.(updated);
    } catch {
      setError(t`Those numbers didn’t save. Check them and try again.`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-labelledby={`${formId}-title`}
      className="@container space-y-4 rounded-2xl border border-border bg-card p-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={`${formId}-title`} className="text-sm font-semibold"><Trans>Performance</Trans></h2>
        {when && <span className="text-2xs text-muted-foreground"><Trans>Updated {when}</Trans></span>}
      </div>

      {synced && (
        <dl className="grid grid-cols-2 gap-3 @xl:grid-cols-4">
          {SYNCED_METRICS.map((name) => (
            <div key={name} className="space-y-1">
              <dt className="text-xs text-muted-foreground">{i18n._(FIELDS[name].label)}</dt>
              <dd className="numeric text-sm font-medium">
                {formatNumber(metricValue(perf, name), { locale: i18n.locale })}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid grid-cols-2 items-end gap-3 @xl:grid-cols-4">
        {names.map((name) => {
          const field = FIELDS[name];
          const id = `${formId}-${name}`;
          return (
            <div key={name} className="space-y-1">
              <label htmlFor={id} className="block text-xs text-muted-foreground">{i18n._(field.label)}</label>
              <Input
                id={id}
                type="number"
                inputMode={field.step < 1 ? "decimal" : "numeric"}
                min={0}
                max={field.max}
                step={field.step}
                value={inputs[name] ?? ""}
                onChange={(e) => setInputs((prev) => ({ ...prev, [name]: e.target.value }))}
                className="numeric"
              />
            </div>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground">
        {synced
          ? <Trans>Views, likes, comments and shares update on their own. Add the rest from the platform’s analytics; a sync never changes what you enter.</Trans>
          : <Trans>Copy these from the platform’s analytics. They stay as you enter them.</Trans>}
      </p>

      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}

      <div className="flex justify-end">
        <Button type="submit" size="sm" disabled={!dirty || saving}>
          {saving ? <Trans>Saving…</Trans> : <Trans>Save numbers</Trans>}
        </Button>
      </div>
    </form>
  );
}
