"use client";

import { useId } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { MAX_SAMPLE_CHARS, MAX_SAMPLES } from "@/lib/voiceRules";

/**
 * Posts the brand already wrote, pasted on the Brand tab (issue #271). The
 * text writer reads them before every X or LinkedIn draft, and a carousel's
 * caption hears them too, so a draft starts in a real voice instead of a
 * generic one. Controlled: `samples` is the list, `onChange` gets the next.
 */
export default function WritingSamples({ samples, onChange }) {
  const { t, i18n } = useLingui();
  const baseId = useId();
  const list = samples.length ? samples : [""];

  const update = (i, value) => onChange(list.map((s, j) => (j === i ? value.slice(0, MAX_SAMPLE_CHARS) : s)));
  const remove = (i) => onChange(list.filter((_, j) => j !== i));
  const add = () => onChange([...list, ""].slice(0, MAX_SAMPLES));

  return (
    <div className="space-y-3">
      {list.map((sample, i) => {
        const n = i + 1;
        const used = sample.length;
        return (
          <div key={i} className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <label htmlFor={`${baseId}-${i}`} className="text-xs font-medium">
                <Trans>Post {n}</Trans>
              </label>
              {list.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => remove(i)}
                  aria-label={t`Remove post ${n}`}
                  title={t`Remove post ${n}`}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              )}
            </div>
            <textarea
              id={`${baseId}-${i}`}
              value={sample}
              onChange={(e) => update(i, e.target.value)}
              rows={4}
              placeholder={t`Paste a post you wrote and liked, exactly as it went out.`}
              className="flex w-full resize-y rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
            />
            <p className="text-right text-2xs text-muted-foreground">
              <span className="numeric">{used.toLocaleString(i18n.locale)}</span> / {MAX_SAMPLE_CHARS.toLocaleString(i18n.locale)}
            </p>
          </div>
        );
      })}
      <button
        type="button"
        onClick={add}
        disabled={list.length >= MAX_SAMPLES}
        className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Plus className="size-4" aria-hidden="true" /> <Trans>Add a post</Trans>
        <span className="text-xs text-muted-foreground">({list.length}/{MAX_SAMPLES})</span>
      </button>
    </div>
  );
}
