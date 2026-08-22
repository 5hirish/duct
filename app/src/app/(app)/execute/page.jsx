"use client";

// Execution review queue — the human gate in the staged-execution flow.
// Agents propose change sets (previewed + guardrail-checked server-side);
// this page is where the user reviews diffs and approves, applies, rolls
// back, or rejects them. Nothing mutates a connected account until Apply.

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  applyChangeSet,
  approveChangeSet,
  listChangeSets,
  rejectChangeSet,
  rollbackChangeSet,
} from "../../../lib/executionApi";

const STATUS_PILL = {
  proposed: "yellow",
  approved: "yellow",
  applying: "yellow",
  applied: "green",
  partial: "yellow",
  failed: "red",
  rejected: "grey",
  rolled_back: "grey",
  blocked: "red",
};

const STATUS_LABEL = {
  proposed: "Awaiting review",
  approved: "Approved — ready to apply",
  applying: "Applying…",
  applied: "Applied",
  partial: "Partially applied",
  failed: "Failed",
  rejected: "Rejected",
  rolled_back: "Rolled back",
};

const CONNECTOR_LABEL = { google_ads: "Google Ads", ga4: "Google Analytics" };

function Pill({ status }) {
  return (
    <span className={`status-pill ${STATUS_PILL[status] || "grey"}`}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

function ChangeRow({ change }) {
  const preview = change.preview || {};
  return (
    <div
      style={{
        borderTop: "1px solid var(--border, rgba(128,128,128,0.2))",
        padding: "10px 0",
        display: "grid",
        gap: 4,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <strong style={{ fontSize: 14 }}>{change.summary || change.op_type}</strong>
        <Pill status={change.status} />
      </div>
      {preview.diff ? (
        <code style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{preview.diff}</code>
      ) : null}
      {(preview.warnings || []).map((warning) => (
        <p key={warning} className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
          ⚠ {warning}
        </p>
      ))}
      {preview.error ? (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Preview failed: {preview.error}
        </p>
      ) : null}
      {(change.guardrail_violations || []).map((rule) => (
        <p key={rule} style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          ⛔ Guardrail: {rule}
        </p>
      ))}
      {change.result?.error ? (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Apply failed: {change.result.error}
        </p>
      ) : null}
      {change.result?.rollback_error ? (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Rollback failed: {change.result.rollback_error}
        </p>
      ) : null}
    </div>
  );
}

function ChangeSetCard({ changeSet, onAction, busy }) {
  const [expanded, setExpanded] = useState(false);
  const cs = changeSet;
  const account = cs.account_name || cs.account_id;

  return (
    <article className="connection-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <div>
          <h2 className="connection-title" style={{ marginBottom: 2 }}>{cs.title}</h2>
          <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
            {CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}
            {account ? ` · ${account}` : ""} · {new Date(cs.created_at).toLocaleString()} ·{" "}
            {cs.changes.length} change{cs.changes.length === 1 ? "" : "s"}
          </p>
        </div>
        <Pill status={cs.status} />
      </div>

      {cs.context ? (
        <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>{cs.context}</p>
      ) : null}

      <div>
        <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Hide changes" : "Review changes"}
        </Button>
      </div>
      {expanded ? <div>{cs.changes.map((c) => <ChangeRow key={c.id} change={c} />)}</div> : null}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {cs.status === "proposed" ? (
          <>
            <Button size="sm" disabled={busy} onClick={() => onAction("approve", cs)}>
              Approve
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
              Reject
            </Button>
          </>
        ) : null}
        {cs.status === "approved" ? (
          <>
            <Button size="sm" disabled={busy} onClick={() => onAction("apply", cs)}>
              Apply now
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
              Reject
            </Button>
          </>
        ) : null}
        {cs.status === "applied" || cs.status === "partial" ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("rollback", cs)}>
            Roll back
          </Button>
        ) : null}
      </div>
    </article>
  );
}

export default function ExecutePage() {
  const [changeSets, setChangeSets] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      setChangeSets(await listChangeSets());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setChangeSets([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onAction(action, cs) {
    setBusyId(cs.id);
    setError(null);
    try {
      if (action === "approve") await approveChangeSet(cs.id);
      if (action === "reject") await rejectChangeSet(cs.id);
      if (action === "apply") {
        // eslint-disable-next-line no-alert
        if (!window.confirm(`Apply ${cs.changes.length} change(s) to ${CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}? This mutates the live account.`)) {
          setBusyId(null);
          return;
        }
        await applyChangeSet(cs.id, cs.connector_type);
      }
      if (action === "rollback") await rollbackChangeSet(cs.id, cs.connector_type);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Executions</h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Review and approve the changes agents propose to your connected accounts. Every change is
        previewed and checked against your guardrails; nothing is applied until you approve it, and
        applied changes keep a rollback handle.
      </p>

      {error ? (
        <p style={{ color: "var(--destructive, #e5484d)", marginBottom: 12 }}>{error}</p>
      ) : null}

      {changeSets === null ? (
        <p className="app-subtle">Loading…</p>
      ) : changeSets.length === 0 ? (
        <p className="app-subtle">
          No proposed changes yet. Run an audit or insight session — recommended fixes will land
          here for your approval.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {changeSets.map((cs) => (
            <ChangeSetCard key={cs.id} changeSet={cs} onAction={onAction} busy={busyId === cs.id} />
          ))}
        </div>
      )}
    </section>
  );
}
