"use client";

import { STEP_LABELS as BACKEND_STEP_LABELS } from "../../lib/auditEvents";

// Merge canonical backend labels with any display-only steps
const STEP_LABELS = {
  ...BACKEND_STEP_LABELS,
  plan_crawl: "Planning crawl",
  render_report: "Finalizing report",
};

const STATUS_STYLE = {
  running: "text-blue-500",
  success: "text-green-500",
  error: "text-destructive",
};

export default function AuditStepProgress({ steps }) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="space-y-1 py-2">
      {steps.map((step) => (
        <div key={step.step_id} className="flex items-center gap-2 text-sm">
          <span className={STATUS_STYLE[step.status] || "text-muted-foreground"}>
            {step.status === "running" ? "⟳" : step.status === "success" ? "✓" : "✗"}
          </span>
          <span className={step.status === "running" ? "font-medium" : "text-muted-foreground"}>
            {STEP_LABELS[step.step_id] || step.label || step.step_id}
          </span>
          {step.payload?.landing_pages != null && (
            <span className="text-xs text-muted-foreground ml-1">
              ({step.payload.landing_pages} landing, {step.payload.blog_posts} blog)
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
