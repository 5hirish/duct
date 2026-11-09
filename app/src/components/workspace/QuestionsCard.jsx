"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// The sentinel an "Other" pick stores until the person types; never sent.
const OTHER = "__other__";
// Chips hold a word or three. Past this, or with a description, an option is
// a row: on 2026-11-08 a plan review put four twenty-word options in centred
// pills and the card was unreadable. Rows are the AskUserQuestion shape the
// agent is told to write (agents/core/lc.py), chips the yes/no degenerate case.
const CHIP_LABEL_MAX_CHARS = 24;
// A multi-select answer travels as one string, the way the single one does.
const ANSWER_JOIN = ", ";

function optionLabel(opt) {
  return typeof opt === "string" ? opt : opt.label || "";
}

function optionDescription(opt) {
  return typeof opt === "string" ? "" : opt.description || "";
}

function isChipList(options) {
  return options.every((opt) => !optionDescription(opt) && optionLabel(opt).length <= CHIP_LABEL_MAX_CHARS);
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * The AskUserQuestion card: up to three questions, each a single or multiple
 * choice over the options the agent wrote, an "Other" row for an answer of the
 * person's own, and a skip that lets the agent decide. Resolves to one string
 * per question. The copy is a prop because the same card sits in three agents
 * with three voices.
 */
export default function QuestionsCard({
  questions,
  onSubmit,
  disabled,
  // The copy props default to the card's own voice, resolved below so the
  // defaults follow the interface language.
  title,
  submitLabel,
  skipLabel,
}) {
  const { t } = useLingui();
  const titleText = title ?? t`Duct has a quick question`;
  const submitText = submitLabel ?? t`Continue`;
  const skipText = skipLabel ?? t`Let Duct decide`;
  // Per question: the picked label (or OTHER) for a single choice, the list of
  // picked labels for a multiple one; `freeText` holds what "Other" typed.
  const [picks, setPicks] = useState({});
  const [freeText, setFreeText] = useState({});

  function pick(q, label) {
    setPicks((prev) => ({
      ...prev,
      [q.question]: q.multiSelect ? toggle(prev[q.question] || [], label) : label,
    }));
  }

  function isPicked(q, label) {
    const current = picks[q.question];
    return q.multiSelect ? (current || []).includes(label) : current === label;
  }

  function resolve(q) {
    const typed = (freeText[q.question] || "").trim();
    const current = picks[q.question];
    if (q.multiSelect) {
      return (current || []).map((label) => (label === OTHER ? typed : label)).filter(Boolean).join(ANSWER_JOIN);
    }
    return current === OTHER ? typed : current || "";
  }

  const allAnswered = questions.every((q) => resolve(q) !== "");

  function handleSubmit(event) {
    event.preventDefault();
    if (disabled || !allAnswered) return;
    const resolved = {};
    for (const q of questions) resolved[q.question] = resolve(q);
    onSubmit(resolved);
  }

  // Empty answers: the agent uses its best judgement from context.
  function handleSkip() {
    const resolved = {};
    for (const q of questions) resolved[q.question] = "";
    onSubmit(resolved);
  }

  return (
    <form onSubmit={handleSubmit} className="my-3 space-y-4 rounded-xl border border-warning/30 bg-warning/5 p-4">
      <p className="text-xs font-medium text-muted-foreground">{titleText}</p>

      {questions.map((q) => {
        const options = q.options || [];
        const chips = isChipList(options);
        const otherOn = isPicked(q, OTHER);
        const otherField = otherOn && (
          <Input
            type="text"
            placeholder={t`Type your answer…`}
            aria-label={t`Your answer`}
            value={freeText[q.question] || ""}
            onChange={(e) => setFreeText((prev) => ({ ...prev, [q.question]: e.target.value }))}
            disabled={disabled}
            autoFocus
          />
        );
        return (
          <fieldset key={q.question} className="min-w-0 space-y-2" disabled={disabled}>
            <legend className="text-sm font-semibold text-pretty">{q.question}</legend>
            {chips ? (
              <>
                <div role={q.multiSelect ? "group" : "radiogroup"} className="flex flex-wrap gap-2">
                  {options.map((opt) => (
                    <Chip key={optionLabel(opt)} multi={q.multiSelect} selected={isPicked(q, optionLabel(opt))} onClick={() => pick(q, optionLabel(opt))}>
                      {optionLabel(opt)}
                    </Chip>
                  ))}
                  <Chip multi={q.multiSelect} selected={otherOn} onClick={() => pick(q, OTHER)}>
                    <Trans>Other</Trans>
                  </Chip>
                </div>
                {otherField}
              </>
            ) : (
              <div role={q.multiSelect ? "group" : "radiogroup"} className="space-y-1.5">
                {options.map((opt) => (
                  <OptionRow
                    key={optionLabel(opt)}
                    multi={q.multiSelect}
                    selected={isPicked(q, optionLabel(opt))}
                    label={optionLabel(opt)}
                    description={optionDescription(opt)}
                    onClick={() => pick(q, optionLabel(opt))}
                  />
                ))}
                <OptionRow multi={q.multiSelect} selected={otherOn} label={t`Other`} onClick={() => pick(q, OTHER)}>
                  {otherField}
                </OptionRow>
              </div>
            )}
          </fieldset>
        );
      })}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" type="submit" disabled={disabled || !allAnswered}>
          {submitText}
        </Button>
        <Button size="sm" type="button" variant="ghost" onClick={handleSkip} disabled={disabled}>
          {skipText}
        </Button>
      </div>
    </form>
  );
}

// The picked state has a shape as well as a colour: a filled dot for one of
// many, a ticked box for any of many, so it survives greyscale and reads as
// the native control it stands in for.
function Mark({ multi, selected }) {
  if (multi) {
    return (
      <span
        aria-hidden="true"
        className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[4px] border ${
          selected ? "border-primary bg-primary text-primary-foreground" : "border-control bg-background"
        }`}
      >
        {selected && <Check className="size-3" strokeWidth={3} />}
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`mt-0.5 size-4 shrink-0 rounded-full ${selected ? "border-5 border-primary" : "border border-control bg-background"}`}
    />
  );
}

// A full-width row: label on its own line, the clause that tells it apart
// under it, left-aligned so four of them scan as a list. `children` is the
// "Other" row's text field, which opens inside the row it belongs to.
function OptionRow({ multi, selected, label, description, onClick, children }) {
  return (
    <div
      className={`rounded-lg border transition-colors ${
        selected ? "border-primary bg-primary/5" : "border-border bg-background hover:bg-muted/50"
      }`}
    >
      <button
        type="button"
        role={multi ? "checkbox" : "radio"}
        aria-checked={selected}
        onClick={onClick}
        className="flex min-h-11 w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed"
      >
        <Mark multi={multi} selected={selected} />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{label}</span>
          {description && <span className="mt-0.5 block text-xs text-pretty text-muted-foreground">{description}</span>}
        </span>
      </button>
      {children && <div className="px-3 pb-3 pl-10">{children}</div>}
    </div>
  );
}

function Chip({ multi, selected, onClick, children }) {
  return (
    <button
      type="button"
      role={multi ? "checkbox" : "radio"}
      aria-checked={selected}
      onClick={onClick}
      className={`inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed ${
        selected ? "border-primary bg-primary font-medium text-primary-foreground" : "border-border bg-background hover:bg-muted"
      }`}
    >
      {multi && selected && <Check className="size-3.5" aria-hidden="true" />}
      {children}
    </button>
  );
}
