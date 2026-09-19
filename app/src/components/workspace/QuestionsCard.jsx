"use client";

import { useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";

/**
 * The AskUserQuestion card: one or more questions with option chips, an
 * "Other" free-text escape, and a skip that lets the agent decide. The copy
 * is a prop because the same card sits in three agents with three voices.
 */
export default function QuestionsCard({
  questions,
  onSubmit,
  disabled,
  // The copy props default to the card's own voice, resolved below so the
  // defaults follow the interface language.
  title,
  hint,
  submitLabel,
  skipLabel,
}) {
  const { t } = useLingui();
  const titleText = title ?? t`Duct has a quick question`;
  const hintText = hint ?? t`Your answers sharpen the result. Skip if you'd rather Duct decide.`;
  const submitText = submitLabel ?? t`Continue →`;
  const skipText = skipLabel ?? t`Let Duct decide`;
  const [answers, setAnswers] = useState({});
  const [freeText, setFreeText] = useState({});

  function handleSelect(question, label) {
    setAnswers((prev) => ({ ...prev, [question]: label }));
    if (label !== "__other__") setFreeText((prev) => ({ ...prev, [question]: "" }));
  }

  function handleFreeText(question, text) {
    setFreeText((prev) => ({ ...prev, [question]: text }));
    setAnswers((prev) => ({ ...prev, [question]: text }));
  }

  function handleSubmit() {
    const resolved = {};
    for (const q of questions) resolved[q.question] = freeText[q.question] || answers[q.question] || "";
    onSubmit(resolved);
  }

  // Empty answers: the agent uses its best judgement from context.
  function handleSkip() {
    const resolved = {};
    for (const q of questions) resolved[q.question] = "";
    onSubmit(resolved);
  }

  const allAnswered = questions.every((q) => {
    const ans = answers[q.question];
    return ans && ans.trim() !== "";
  });

  return (
    <div className="rounded-xl border border-warning/30 bg-warning/5 p-4 space-y-4 my-3">
      <div className="space-y-0.5">
        <p className="text-sm font-semibold">{titleText}</p>
        <p className="text-xs text-muted-foreground">{hintText}</p>
      </div>

      {questions.map((q) => (
        <div key={q.question} className="space-y-2">
          <p className="text-sm font-medium">{q.question}</p>
          <div className="flex flex-wrap gap-2">
            {(q.options || []).map((opt) => {
              const label = opt.label || opt;
              const selected = answers[q.question] === label;
              return (
                <button
                  key={label}
                  type="button"
                  onClick={() => handleSelect(q.question, label)}
                  aria-pressed={selected}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                    selected
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background hover:bg-muted"
                  }`}
                >
                  {label}
                  {opt.description && <span className="ml-1 opacity-60">— {opt.description}</span>}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => handleSelect(q.question, "__other__")}
              aria-pressed={answers[q.question] === "__other__"}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                answers[q.question] === "__other__"
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background hover:bg-muted"
              }`}
            >
              <Trans>Other</Trans>
            </button>
          </div>
          {answers[q.question] === "__other__" && (
            <input
              type="text"
              placeholder={t`Type your answer…`}
              aria-label={t`Your answer`}
              value={freeText[q.question] || ""}
              onChange={(e) => handleFreeText(q.question, e.target.value)}
              className="w-full rounded-3xl border border-control bg-input/50 px-3 py-1.5 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 md:text-sm"
              autoFocus
            />
          )}
        </div>
      ))}

      <div className="flex items-center gap-2 pt-1">
        <Button size="sm" onClick={handleSubmit} disabled={disabled || !allAnswered}>
          {submitText}
        </Button>
        <button
          type="button"
          onClick={handleSkip}
          disabled={disabled}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
        >
          {skipText}
        </button>
      </div>
    </div>
  );
}
