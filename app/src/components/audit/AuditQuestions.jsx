"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

export default function AuditQuestions({ questions, onSubmit, disabled }) {
  const [answers, setAnswers] = useState({});
  const [freeText, setFreeText] = useState({});

  function handleSelect(question, label) {
    setAnswers(prev => ({ ...prev, [question]: label }));
    if (label !== "__other__") {
      setFreeText(prev => ({ ...prev, [question]: "" }));
    }
  }

  function handleFreeText(question, text) {
    setFreeText(prev => ({ ...prev, [question]: text }));
    setAnswers(prev => ({ ...prev, [question]: text }));
  }

  function handleSubmit() {
    const resolved = {};
    for (const q of questions) {
      const ans = freeText[q.question] || answers[q.question] || "";
      resolved[q.question] = ans;
    }
    onSubmit(resolved);
  }

  const allAnswered = questions.every(q => {
    const ans = answers[q.question];
    return ans && ans.trim() !== "";
  });

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-4 my-3">
      <p className="text-sm font-medium">
        A few quick questions to improve your audit:
      </p>

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
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                    selected
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background hover:bg-muted"
                  }`}
                >
                  {label}
                  {opt.description && (
                    <span className="ml-1 opacity-60">— {opt.description}</span>
                  )}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => handleSelect(q.question, "__other__")}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                answers[q.question] === "__other__"
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background hover:bg-muted"
              }`}
            >
              Other
            </button>
          </div>
          {answers[q.question] === "__other__" && (
            <input
              type="text"
              placeholder="Type your answer…"
              value={freeText[q.question] || ""}
              onChange={e => handleFreeText(q.question, e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              autoFocus
            />
          )}
        </div>
      ))}

      <Button
        size="sm"
        onClick={handleSubmit}
        disabled={disabled || !allAnswered}
      >
        Continue audit →
      </Button>
    </div>
  );
}
