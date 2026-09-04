"use client";

/**
 * The staged-execution review card — one component, every agent.
 *
 * It was defined inside the audit chat pane while audit was the only agent that
 * could propose changes. Insights is the second, which is the point at which
 * a shared component is worth writing rather than a copy: the approve/reject/
 * rollback buttons ARE the human review gate, and two drifting copies of a
 * safety surface is exactly the drift worth preventing.
 *
 * What the card must always show, at any autonomy level:
 *   - `destructive` per change — those never auto-apply and never will;
 *   - guardrail violations and preview errors, in full, not summarised away;
 *   - who applied it: a set marked "auto-applied" arrived without a click, and
 *     the user should be able to tell that at a glance and roll it back here.
 */

import { useState, useEffect } from "react";
import {
  approveChangeSet,
  applyChangeSet,
  rejectChangeSet,
  rollbackChangeSet,
} from "@/lib/executionApi";

/** API change-set response → SSE-card shape, preserving per-change flags the
 * API rows don't carry (destructive comes only from the SSE card). */
export function apiToCard(cs, prevCard) {
  const prevById = Object.fromEntries((prevCard?.changes || []).map((c) => [c.id, c]));
  return {
    change_set_id: cs.id,
    connector_type: cs.connector_type,
    account_id: cs.account_id,
    account_name: cs.account_name,
    title: cs.title,
    context: cs.context,
    status: cs.status,
    source: cs.source ?? prevCard?.source ?? "agent",
    applied_by: cs.applied_by ?? "",
    auto_apply_eligible: cs.auto_apply_eligible ?? prevCard?.auto_apply_eligible ?? false,
    changes: (cs.changes || []).map((c) => ({
      id: c.id,
      op_type: c.op_type,
      summary: c.summary || "",
      status: c.status || "",
      diff: c.preview?.diff || "",
      warnings: c.preview?.warnings || [],
      guardrail_violations: c.guardrail_violations || [],
      preview_error: c.preview?.error || "",
      destructive: prevById[c.id]?.destructive ?? false,
    })),
  };
}

const CHANGE_SET_STATUS_STYLES = {
  proposed: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  applied: "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-400",
  rejected: "bg-muted text-muted-foreground",
  rolled_back: "bg-muted text-muted-foreground",
};

/** Inline review card for a staged change set the agent proposed. Reversible,
 * allowlisted, guardrail-clean sets may arrive already auto-applied (assisted
 * or auto autonomy — the allowlist is the same at both); everything else waits
 * here for Approve & apply. Destructive changes are flagged and always wait. */
export default function ChangeSetCard({ changeSet: initial }) {
  const [cs, setCs] = useState(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // A later SSE upsert (e.g. rollback via agent tool) replaces the card data.
  useEffect(() => setCs(initial), [initial]);

  if (!cs) return null;
  const autoApplied = cs.applied_by === "auto";
  const canReview = cs.status === "proposed";
  const canRollback = ["applied", "partial"].includes(cs.status);
  const hasDestructive = (cs.changes || []).some((c) => c.destructive);

  const run = async (label, fn) => {
    setBusy(label);
    setError("");
    try {
      const result = await fn();
      setCs((prev) => apiToCard(result, prev));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  };

  const onApprove = () =>
    run("approve", async () => {
      await approveChangeSet(cs.change_set_id);
      return applyChangeSet(cs.change_set_id, cs.connector_type);
    });
  const onReject = () => run("reject", () => rejectChangeSet(cs.change_set_id));
  const onRollback = () =>
    run("rollback", () => rollbackChangeSet(cs.change_set_id, cs.connector_type));

  return (
    <div className="my-2 rounded-lg border border-input bg-muted/20 max-w-md overflow-hidden">
      <div className="px-3 py-2 border-b border-border/60 flex items-start gap-2">
        <span aria-hidden="true" className="text-base leading-tight">⚡</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">{cs.title}</p>
          <p className="text-xs text-muted-foreground truncate">
            {cs.connector_type}
            {cs.account_name ? ` · ${cs.account_name}` : cs.account_id ? ` · ${cs.account_id}` : ""}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            CHANGE_SET_STATUS_STYLES[cs.status] || "bg-muted text-muted-foreground"
          }`}
        >
          {autoApplied && cs.status === "applied" ? "auto-applied" : cs.status.replace("_", " ")}
        </span>
      </div>

      {cs.context && (
        <p className="px-3 pt-2 text-xs text-muted-foreground leading-relaxed">{cs.context}</p>
      )}

      <ul className="px-3 py-2 space-y-1.5">
        {(cs.changes || []).map((c) => (
          <li key={c.id} className="text-xs leading-snug">
            <span className="flex items-start gap-1.5">
              <span aria-hidden="true" className="mt-0.5 shrink-0">
                {c.status === "applied" ? "✓" : c.status === "blocked" || c.preview_error ? "✕" : c.status === "rolled_back" ? "↺" : "•"}
              </span>
              <span className="min-w-0">
                <span className="text-foreground/90">{c.diff || c.summary || c.op_type}</span>
                {c.destructive && (
                  <span className="ml-1.5 rounded bg-red-100 dark:bg-red-950/50 px-1 py-px text-[10px] font-medium text-red-700 dark:text-red-400">
                    destructive
                  </span>
                )}
                {(c.warnings || []).map((w, j) => (
                  <span key={j} className="block text-amber-700 dark:text-amber-400">⚠ {w}</span>
                ))}
                {(c.guardrail_violations || []).map((v, j) => (
                  <span key={j} className="block text-red-700 dark:text-red-400">⛔ {v}</span>
                ))}
                {c.preview_error && (
                  <span className="block text-red-700 dark:text-red-400">Preview failed: {c.preview_error}</span>
                )}
              </span>
            </span>
          </li>
        ))}
      </ul>

      {error && (
        <p className="px-3 pb-1 text-xs text-destructive break-words">{error}</p>
      )}

      {(canReview || canRollback) && (
        <div className="px-3 pb-2.5 flex items-center gap-2">
          {canReview && (
            <>
              <button
                onClick={onApprove}
                disabled={!!busy}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                  hasDestructive
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-primary text-primary-foreground hover:bg-primary/90"
                }`}
              >
                {busy === "approve" ? "Applying…" : hasDestructive ? "Approve & apply (destructive)" : "Approve & apply"}
              </button>
              <button
                onClick={onReject}
                disabled={!!busy}
                className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/60 transition-colors disabled:opacity-50"
              >
                {busy === "reject" ? "Rejecting…" : "Reject"}
              </button>
            </>
          )}
          {canRollback && (
            <button
              onClick={onRollback}
              disabled={!!busy}
              className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/60 transition-colors disabled:opacity-50"
            >
              {busy === "rollback" ? "Rolling back…" : "↺ Roll back"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
