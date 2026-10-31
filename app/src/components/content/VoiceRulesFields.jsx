"use client";

import { useId, useState } from "react";
import { RotateCcw, X } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { MAX_BANNED_WORDS, addBannedWord } from "@/lib/voiceRules";

/**
 * The rules an X or LinkedIn draft keeps, per project (issue #271): words it
 * never uses, and two switches that used to be the same for everyone. The
 * writer refuses a draft with a banned word, so the list is a promise, not a
 * hint. Controlled: `rules` is `{ banned_words, no_client_names,
 * protect_the_edge }`; `onChange` gets the next. `onReset` goes back to
 * Duct's defaults, offered only while `customised`.
 */
export default function VoiceRulesFields({ rules, onChange, onReset, customised = false }) {
  const { t } = useLingui();
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const words = rules.banned_words || [];
  const full = words.length >= MAX_BANNED_WORDS;

  const set = (patch) => onChange({ ...rules, ...patch });
  const add = () => {
    set({ banned_words: addBannedWord(words, draft) });
    setDraft("");
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-1.5">
        <label htmlFor={inputId} className="text-xs font-medium"><Trans>Banned words</Trans></label>
        <div className="flex gap-2">
          <Input
            id={inputId}
            value={draft}
            disabled={full}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); add(); }
            }}
            placeholder={full ? t`The list is full` : t`A word or phrase, then Enter`}
          />
          <Button type="button" variant="secondary" onClick={add} disabled={!draft.trim() || full}>
            <Trans>Add</Trans>
          </Button>
        </div>
        {words.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5 pt-1" aria-label={t`Banned words`}>
            {words.map((word) => (
              <li key={word} className="inline-flex items-center gap-1 rounded-full border bg-muted/50 py-0.5 pl-2.5 pr-1 text-xs">
                {word}
                <button
                  type="button"
                  onClick={() => set({ banned_words: words.filter((w) => w !== word) })}
                  className="inline-flex size-6 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label={t`Allow "${word}" again`}
                >
                  <X className="size-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-2xs text-muted-foreground"><Trans>Nothing banned. Drafts follow plain good writing.</Trans></p>
        )}
        <p className="text-2xs text-muted-foreground">
          <Trans>Duct won&apos;t save an X or LinkedIn draft that uses one, and says which.</Trans>
        </p>
      </div>

      <RuleSwitch
        checked={rules.no_client_names}
        onChange={(v) => set({ no_client_names: v })}
        title={t`Keep client names out`}
        on={t`Customers, clients and partners are never named unless you say so.`}
        off={t`Drafts may name customers, clients and partners.`}
      />
      <RuleSwitch
        checked={rules.protect_the_edge}
        onChange={(v) => set({ protect_the_edge: v })}
        title={t`Protect the edge`}
        on={t`Drafts share the lesson, never the exact prompt, model or sequence that's working.`}
        off={t`You build in public: drafts may show exactly how it works.`}
      />

      {customised && onReset && (
        <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={onReset}>
          <RotateCcw className="size-3.5" aria-hidden="true" /> <Trans>Back to Duct&apos;s defaults</Trans>
        </Button>
      )}
    </div>
  );
}

function RuleSwitch({ checked, onChange, title, on, off }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-0.5">
        <label htmlFor={id} className="text-xs font-medium">{title}</label>
        <p className="text-2xs text-muted-foreground">{checked ? on : off}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
