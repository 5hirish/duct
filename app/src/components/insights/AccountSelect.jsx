"use client";

// The connector is authorized but this project has not chosen which account,
// property or site to read. The agent only asks when there is a real choice —
// a single candidate is bound server-side without interrupting anyone — so if
// this card is on screen there are genuinely two or more answers.
//
// The choice persists as a project binding, which is why the card says so: the
// user is configuring the project, not answering a one-off question.

import { useState } from "react";
import { Button } from "@/components/ui/button";

export default function AccountSelect({ request, onAnswer, disabled }) {
  const { label, candidates = [] } = request;
  const [selected, setSelected] = useState("");

  const chosen = candidates.find((c) => c.account_id === selected);

  return (
    <div className="my-3 space-y-3 rounded-xl border border-violet-200 bg-violet-50/60 p-4 dark:border-violet-800/60 dark:bg-violet-950/20">
      <div className="space-y-0.5">
        <p className="text-sm font-semibold">Which {label} account should Duct use?</p>
        <p className="text-xs text-muted-foreground">
          Saved to this project, so you won't be asked again.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {candidates.map((c) => {
          const active = selected === c.account_id;
          return (
            <button
              key={c.account_id}
              type="button"
              onClick={() => setSelected(c.account_id)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background hover:bg-muted"
              }`}
            >
              {c.account_name || c.account_id}
              {c.account_name && (
                <span className="ml-1 opacity-60">{c.account_id}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <Button
          size="sm"
          disabled={disabled || !selected}
          onClick={() =>
            onAnswer({ account_id: selected, account_name: chosen?.account_name || "" })
          }
        >
          Use this account →
        </Button>
        <button
          type="button"
          onClick={() => onAnswer({})}
          disabled={disabled}
          className="text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
        >
          Skip
        </button>
      </div>
    </div>
  );
}
