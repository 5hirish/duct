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
 *
 * How it says those things matters as much as that it says them. The first
 * version painted every flag in its own colour — a red approve button, a red
 * "destructive" tag, an amber warning line, a red guardrail line — and the
 * card that exists to make a calm decision read as an alarm. Colour is now
 * spent once per row at most; the words carry the rest, and the summary line
 * above the buttons says how many changes are waiting on a person.
 */

import { useState, useEffect } from "react";
import { Ban, Check, RotateCcw, TriangleAlert, X, Zap } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  approveChangeSet,
  applyChangeSet,
  rejectChangeSet,
  rollbackChangeSet,
} from "@/lib/executionApi";
import { titleCase } from "@/lib/format";

/**
 * The per-change mark. Four states, four lucide glyphs — it was ✓ ✕ ↺ •, which
 * is emoji-as-icon, the tell DESIGN.md's anti-slop table names, and the only
 * place in the app that drew status that way. A dot for "still waiting" rather
 * than an icon: pending is the absence of an outcome, not an outcome.
 */
function StatusMark({ status, failed }) {
  const cls = "mt-1 size-3.5 shrink-0";
  if (status === "applied") return <Check className={`${cls} text-success`} aria-hidden="true" />;
  if (status === "blocked" || failed) return <X className={`${cls} text-muted-foreground`} aria-hidden="true" />;
  if (status === "rolled_back") return <RotateCcw className={`${cls} text-muted-foreground`} aria-hidden="true" />;
  return <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" aria-hidden="true" />;
}

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
      drifted: !!c.drift,
      preview_error: c.preview?.error || "",
      destructive: prevById[c.id]?.destructive ?? false,
    })),
  };
}

// The set's state, in words a person would use, with the one colour it earns.
// Descriptors, rendered with `i18n._` — a module-level `t` is fixed at load.
const SET_STATUS = {
  proposed: { label: msg`Waiting for you`, className: "bg-warning/10 text-warning" },
  applied: { label: msg`Applied`, className: "bg-success/10 text-success" },
  partial: { label: msg`Partly applied`, className: "bg-warning/10 text-warning" },
  failed: { label: msg`Failed`, className: "bg-destructive/10 text-destructive" },
  rejected: { label: msg`Rejected`, className: "bg-muted text-muted-foreground" },
  rolled_back: { label: msg`Rolled back`, className: "bg-muted text-muted-foreground" },
};

/** One line under a change: an icon and the reason, in the muted voice. The
 * icon is the only colour, so the eye lands on the text, not the alarm. */
function Note({ icon: Icon, tone, children }) {
  return (
    <p className="mt-0.5 flex items-start gap-1.5 text-xs text-muted-foreground">
      <Icon className={`mt-px size-3 shrink-0 ${tone}`} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

/** Inline review card for a staged change set the agent proposed. Reversible,
 * allowlisted, guardrail-clean sets may arrive already auto-applied (assisted
 * or auto autonomy — the allowlist is the same at both); everything else waits
 * here for Approve & apply. Destructive changes are flagged and always wait. */
export default function ChangeSetCard({ changeSet: initial }) {
  const { t, i18n } = useLingui();
  const [cs, setCs] = useState(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // A later SSE upsert (e.g. rollback via agent tool) replaces the card data.
  useEffect(() => setCs(initial), [initial]);

  if (!cs) return null;
  const changes = cs.changes || [];
  const autoApplied = cs.applied_by === "auto";
  const canReview = cs.status === "proposed";
  const canRollback = ["applied", "partial"].includes(cs.status);
  const blocked = changes.filter((c) => c.status === "blocked" || c.preview_error).length;
  const total = changes.length;
  const ready = total - blocked;
  // An unknown status falls through as the raw enum: it is not copy we wrote.
  const setStatus =
    autoApplied && cs.status === "applied"
      ? { label: t`Applied automatically`, className: SET_STATUS.applied.className }
      : SET_STATUS[cs.status]
        ? { label: i18n._(SET_STATUS[cs.status].label), className: SET_STATUS[cs.status].className }
        : { label: cs.status.replace("_", " "), className: "bg-muted text-muted-foreground" };
  const where = [cs.connector_type ? titleCase(cs.connector_type) : "", cs.account_name || cs.account_id]
    .filter(Boolean)
    .join(" · ");

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
    <div className="my-2 max-w-md overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-start gap-3 p-4">
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <Zap className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug">{cs.title}</p>
          {where && <p className="mt-0.5 truncate text-xs text-muted-foreground">{where}</p>}
        </div>
        <Badge className={`shrink-0 ${setStatus.className}`}>{setStatus.label}</Badge>
      </div>

      {cs.context && (
        <p className="px-4 pb-4 text-xs leading-relaxed text-muted-foreground">{cs.context}</p>
      )}

      <ul className="divide-y divide-border/60 border-t border-border/60">
        {changes.map((c) => {
          const held = c.status === "blocked" || c.preview_error;
          const previewError = c.preview_error;
          return (
            <li key={c.id} className="flex items-start gap-3 px-4 py-3">
              <StatusMark status={c.status} failed={!!c.preview_error} />
              <div className="min-w-0 flex-1">
                <p className={`text-sm leading-snug ${held ? "text-muted-foreground" : ""}`}>
                  {c.diff || c.summary || c.op_type}
                </p>
                {(c.warnings || []).map((w, j) => (
                  <Note key={j} icon={TriangleAlert} tone="text-warning">{w}</Note>
                ))}
                {(c.guardrail_violations || []).map((v, j) => (
                  <Note key={j} icon={Ban} tone="text-muted-foreground">{v}</Note>
                ))}
                {c.drifted && (
                  <Note icon={Ban} tone="text-muted-foreground">
                    <Trans>Changed in the account after you approved it, so it was not applied. Ask for a fresh proposal.</Trans>
                  </Note>
                )}
                {previewError && (
                  <Note icon={Ban} tone="text-destructive"><Trans>Preview failed: {previewError}</Trans></Note>
                )}
              </div>
              {c.destructive && (
                <Badge variant="outline" className="shrink-0 text-muted-foreground">
                  <Trans>destructive</Trans>
                </Badge>
              )}
            </li>
          );
        })}
      </ul>

      {error && <p className="px-4 pb-2 pt-3 text-xs text-destructive break-words">{error}</p>}

      {(canReview || canRollback) && (
        <div className="flex items-center gap-2 border-t border-border/60 px-4 py-3">
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            {canReview && blocked > 0 ? (
              <Trans>
                {ready} of {total} will apply ·{" "}
                <Plural value={blocked} one="# needs a person" other="# need a person" />
              </Trans>
            ) : canReview && changes.some((c) => c.destructive) ? (
              <Trans>Includes a pause. It can be rolled back from here.</Trans>
            ) : (
              ""
            )}
          </p>
          {canReview && (
            <>
              <Button size="sm" variant="ghost" onClick={onReject} disabled={!!busy}>
                {busy === "reject" ? <Trans>Rejecting…</Trans> : <Trans>Reject</Trans>}
              </Button>
              <Button size="sm" onClick={onApprove} disabled={!!busy}>
                {busy === "approve" ? <Trans>Applying…</Trans> : <Trans>Approve & apply</Trans>}
              </Button>
            </>
          )}
          {canRollback && (
            <Button size="sm" variant="outline" onClick={onRollback} disabled={!!busy}>
              {busy === "rollback" ? <Trans>Rolling back…</Trans> : <><RotateCcw aria-hidden="true" /> <Trans>Roll back</Trans></>}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
