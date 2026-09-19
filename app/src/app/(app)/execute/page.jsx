"use client";

// Execution review queue — the human gate in the staged-execution flow.
// Agents propose change sets (previewed + guardrail-checked server-side);
// this page is where the user reviews diffs and approves (all or a subset),
// applies, rolls back, or rejects them. Nothing mutates a connected account
// until Apply — except reversible, guardrail-clean sets the project's
// autonomy dial (below) allows to auto-apply, which land here already
// applied with an "auto" badge and a rollback handle.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { getActiveProject } from "../../../lib/projects";
import { hasAuthToken, isSessionExpired } from "../../../lib/authFetch";
import LoadError from "@/components/LoadError";
import {
  AUTONOMY_ASK,
  AUTONOMY_OPTIONS,
  fetchProjectsRemote,
  setProjectAutonomy,
} from "../../../lib/projectsApi";
import {
  applyChangeSet,
  approveChangeSet,
  createGuardrail,
  deleteGuardrail,
  listChangeSets,
  listGuardrails,
  listOps,
  rejectChangeSet,
  rollbackChangeSet,
} from "../../../lib/executionApi";
import { Spinner } from "@/components/ui/spinner";
import { SkeletonList } from "@/components/ui/skeleton";

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
  proposed: msg`Awaiting review`,
  approved: msg`Approved — ready to apply`,
  applying: msg`Applying…`,
  applied: msg`Applied`,
  partial: msg`Partially applied`,
  failed: msg`Failed`,
  rejected: msg`Rejected`,
  rolled_back: msg`Rolled back`,
};

const STATUS_FILTERS = [
  { value: "", label: msg`All statuses` },
  { value: "proposed", label: msg`Awaiting review` },
  { value: "approved", label: msg`Approved` },
  { value: "applied", label: msg`Applied` },
  { value: "partial", label: msg`Partially applied` },
  { value: "failed", label: msg`Failed` },
  { value: "rejected", label: msg`Rejected` },
  { value: "rolled_back", label: msg`Rolled back` },
];

const SOURCE_FILTERS = [
  { value: "", label: msg`All sources` },
  { value: "agent", label: msg`Agent-proposed` },
  { value: "user", label: msg`Proposed by you` },
];

const CONNECTOR_LABEL = {
  google_ads: "Google Ads",
  ga4: "Google Analytics",
  gtm: "Google Tag Manager",
  mixpanel: "Mixpanel",
};

const GUARDRAIL_CONNECTORS = ["google_ads", "ga4", "gtm", "mixpanel"];

function Pill({ status }) {
  const { i18n } = useLingui();
  return (
    <span className={`status-pill ${STATUS_PILL[status] || "grey"}`}>
      {STATUS_LABEL[status] ? i18n._(STATUS_LABEL[status]) : status}
    </span>
  );
}

function ProvenanceBadges({ cs }) {
  return (
    <>
      {cs.source === "agent" && <span className="status-pill green"><Trans>agent</Trans></span>}
      {cs.applied_by === "auto" && <span className="status-pill yellow"><Trans>auto-applied</Trans></span>}
    </>
  );
}

function JsonDetails({ label, value }) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) return null;
  return (
    <details style={{ fontSize: "var(--text-xs)" }}>
      <summary className="app-subtle" style={{ cursor: "pointer", userSelect: "none" }}>
        {label}
      </summary>
      <pre
        style={{
          margin: "4px 0 0",
          padding: 8,
          borderRadius: 6,
          background: "var(--muted, rgba(128,128,128,0.08))",
          overflowX: "auto",
          fontSize: "var(--text-2xs)",
        }}
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Detail drawer — full per-change review with subset approval
// ---------------------------------------------------------------------------

function changeApprovable(change) {
  return (
    ["proposed", "approved"].includes(change.status) && !(change.preview || {}).error
  );
}

function DrawerChange({ change, destructive, selectable, checked, onToggle }) {
  const { t } = useLingui();
  const preview = change.preview || {};
  const name = change.summary || change.op_type;
  const previewError = preview.error;
  const applyError = change.result?.error;
  const rollbackError = change.result?.rollback_error;
  return (
    <div
      style={{
        borderTop: "1px solid var(--border, rgba(128,128,128,0.2))",
        padding: "10px 0",
        display: "grid",
        gap: 5,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        {selectable && (
          <input
            type="checkbox"
            checked={checked}
            onChange={onToggle}
            disabled={!changeApprovable(change)}
            style={{ marginTop: 3 }}
            aria-label={t`Include ${name}`}
          />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
            <strong style={{ fontSize: "var(--text-sm)" }}>
              {change.summary || change.op_type}
              {destructive && (
                <span
                  className="status-pill red"
                  style={{ marginLeft: 8, fontSize: "var(--text-2xs)", verticalAlign: "middle" }}
                >
                  <Trans>destructive</Trans>
                </span>
              )}
            </strong>
            <Pill status={change.status} />
          </div>
          <p className="app-subtle" style={{ margin: "2px 0 0", fontSize: "var(--text-xs)" }}>{change.op_type}</p>
        </div>
      </div>

      {preview.diff && <code style={{ fontSize: "var(--text-sm)", whiteSpace: "pre-wrap" }}>{preview.diff}</code>}
      {(preview.warnings || []).map((warning) => (
        <p key={warning} style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--warning)" }}>
          ⚠ {warning}
        </p>
      ))}
      {(change.guardrail_violations || []).map((rule) => (
        <p key={rule} style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>
          <Trans>⛔ Guardrail: {rule}</Trans>
        </p>
      ))}
      {previewError && (
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>
          <Trans>Preview failed: {previewError}</Trans>
        </p>
      )}
      {applyError && (
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>
          <Trans>Apply failed: {applyError}</Trans>
        </p>
      )}
      {rollbackError && (
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>
          <Trans>Rollback failed: {rollbackError}</Trans>
        </p>
      )}

      <JsonDetails label={t`Current state (snapshot before change)`} value={change.current} />
      <JsonDetails label={t`Proposed target + payload`} value={{ target: change.target, payload: change.payload }} />
      <JsonDetails label={t`Result`} value={change.result} />
      <JsonDetails label={t`Rollback result`} value={change.rollback_result} />
    </div>
  );
}

function DetailDrawer({ cs, destructiveMap, busy, onClose, onAction, projectName }) {
  // Subset approval: all approvable changes start selected.
  const [selected, setSelected] = useState(() => new Set());
  useEffect(() => {
    if (cs) setSelected(new Set(cs.changes.filter(changeApprovable).map((c) => c.id)));
  }, [cs?.id, cs?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!cs) return null;
  const account = cs.account_name || cs.account_id;
  const approvable = cs.changes.filter(changeApprovable);
  const allSelected = selected.size === approvable.length;
  const selectedCount = selected.size;
  const approvableCount = approvable.length;

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            {cs.title} <Pill status={cs.status} /> <ProvenanceBadges cs={cs} />
          </SheetTitle>
          <SheetDescription>
            {CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}
            {account ? ` · ${account}` : ""}
            {projectName ? ` · ${projectName}` : ""} · {new Date(cs.created_at).toLocaleString()}
          </SheetDescription>
        </SheetHeader>

        <div style={{ padding: "0 16px 16px", display: "grid", gap: 10 }}>
          {cs.context && (
            <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-sm)" }}>{cs.context}</p>
          )}

          {cs.status === "proposed" && approvable.length > 1 && (
            <button
              type="button"
              className="app-subtle"
              style={{ fontSize: "var(--text-xs)", textAlign: "left", cursor: "pointer", background: "none", border: 0, padding: 0 }}
              onClick={() =>
                setSelected(allSelected ? new Set() : new Set(approvable.map((c) => c.id)))
              }
            >
              {allSelected ? (
                <Trans>Deselect all ({selectedCount}/{approvableCount} selected)</Trans>
              ) : (
                <Trans>Select all ({selectedCount}/{approvableCount} selected)</Trans>
              )}
            </button>
          )}

          <div>
            {cs.changes.map((change) => (
              <DrawerChange
                key={change.id}
                change={change}
                destructive={!!destructiveMap[change.op_type]}
                selectable={cs.status === "proposed"}
                checked={selected.has(change.id)}
                onToggle={() =>
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(change.id)) next.delete(change.id);
                    else next.add(change.id);
                    return next;
                  })
                }
              />
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 4 }}>
            {cs.status === "proposed" && (
              <>
                <Button
                  size="sm"
                  disabled={busy || selected.size === 0}
                  onClick={() =>
                    onAction("approve", cs, {
                      changeIds: allSelected ? null : [...selected],
                    })
                  }
                >
                  {allSelected ? <Trans>Approve all</Trans> : <Trans>Approve {selectedCount} selected</Trans>}
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
                  <Trans>Reject</Trans>
                </Button>
              </>
            )}
            {cs.status === "approved" && (
              <>
                <Button size="sm" disabled={busy} onClick={() => onAction("apply", cs)}>
                  <Trans>Apply now</Trans>
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
                  <Trans>Reject</Trans>
                </Button>
              </>
            )}
            {(cs.status === "applied" || cs.status === "partial") && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("rollback", cs)}>
                <Trans>Roll back</Trans>
              </Button>
            )}
            {cs.status === "applying" && (
              <span className="app-subtle" style={{ fontSize: "var(--text-sm)" }}>
                <Spinner
                  className="size-3"
                  style={{ marginRight: 6, verticalAlign: "-2px" }}
                />
                <Trans>Applying changes…</Trans>
              </span>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Confirm dialog — apply/rollback go through an explicit gate; destructive
// changes are called out and turn the confirm button red.
// ---------------------------------------------------------------------------

function ConfirmDialog({ confirm, destructiveMap, onCancel, onConfirm }) {
  if (!confirm) return null;
  const { action, cs } = confirm;
  const relevant =
    action === "apply"
      ? cs.changes.filter((c) => c.status === "approved")
      : cs.changes.filter((c) => c.status === "applied");
  const destructive = relevant.filter((c) => destructiveMap[c.op_type]);
  const connector = CONNECTOR_LABEL[cs.connector_type] || cs.connector_type;
  const count = relevant.length;
  const destructiveCount = destructive.length;
  const destructiveNames = destructive.map((c) => c.summary || c.op_type).join("; ");

  return (
    <AlertDialog open onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {action === "apply" ? (
              <Trans>
                Apply <Plural value={count} one="# change" other="# changes" /> to {connector}?
              </Trans>
            ) : (
              <Trans>
                Roll back <Plural value={count} one="# applied change" other="# applied changes" />?
              </Trans>
            )}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>
              <p style={{ margin: 0 }}>
                {action === "apply"
                  ? <Trans>This mutates the live account. Applied changes record a rollback handle.</Trans>
                  : <Trans>Each change is reverted using the rollback handle recorded when it was applied.</Trans>}
              </p>
              {destructiveCount > 0 && (
                <p style={{ margin: "8px 0 0", color: "var(--destructive)" }}>
                  <Trans>
                    <Plural value={destructiveCount} one="# destructive change" other="# destructive changes" /> —{" "}
                    {destructiveNames}.
                  </Trans>
                  {action === "apply" && (
                    <>
                      {" "}
                      <Trans>Destructive operations change what is live for every visitor.</Trans>
                    </>
                  )}
                </p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel><Trans>Cancel</Trans></AlertDialogCancel>
          <AlertDialogAction
            className={destructiveCount > 0 ? buttonVariants({ variant: "destructive" }) : undefined}
            onClick={onConfirm}
          >
            {action === "apply"
              ? destructiveCount > 0
                ? <Trans>Apply (destructive)</Trans>
                : <Trans>Apply</Trans>
              : <Trans>Roll back</Trans>}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// Autonomy panel — the human-owned dial for what may skip this queue
// ---------------------------------------------------------------------------

function AutonomyPanel({ project, level, onChange, saving, error }) {
  const { t, i18n } = useLingui();
  if (!project || !level) return null;
  const current = AUTONOMY_OPTIONS.find((o) => o.value === level) || AUTONOMY_OPTIONS[0];
  const projectName = project.name;
  return (
    <article className="connection-card" style={{ display: "grid", gap: 10, marginBottom: 16 }}>
      <div>
        <h2 className="connection-title" style={{ marginBottom: 2 }}>
          <Trans>Autonomy — {projectName}</Trans>
        </h2>
        <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-sm)" }}>{i18n._(current.blurb)}</p>
      </div>

      <div role="radiogroup" aria-label={t`Execution autonomy`} style={{ display: "flex", gap: 8 }}>
        {AUTONOMY_OPTIONS.map((opt) => {
          const selected = opt.value === level;
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={saving || selected}
              onClick={() => onChange(opt.value)}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-default ${
                selected
                  ? "border-primary bg-primary/10 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-border/80"
              }`}
            >
              {i18n._(opt.label)}
            </button>
          );
        })}
      </div>

      {/* The invariant, stated where the dial is turned. It is the reason the
          top of the ladder is safe to offer at all, and a user who does not
          know it will read "Auto" as "anything". */}
      <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-xs)" }}>
        <Trans>
          Destructive work waits here at every level — GTM publishes, archives, unlinks,
          anything touching budget or status. Assisted and Auto share one narrow allowlist:
          keywords, GA4 key events and audiences, GTM workspace edits.
        </Trans>
      </p>

      {error && (
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--destructive)" }}>
          {error.includes("404") || error.toLowerCase().includes("owner")
            ? <Trans>Only the project owner can change autonomy.</Trans>
            : error}
        </p>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Guardrails panel — per-account invariants enforced in code at preview+apply
// ---------------------------------------------------------------------------

function GuardrailsPanel() {
  const { t } = useLingui();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    connector_type: "google_ads",
    account_id: "",
    rule: "",
    op_types: "",
    target_contains: "",
  });

  const load = useCallback(() => {
    listGuardrails()
      .then(setRows)
      .catch((err) => {
        setRows([]);
        setError(err.message || t`Couldn't load your guardrails. The queue above is unaffected.`);
      });
  }, [t]);

  useEffect(() => {
    if (open && rows === null) load();
  }, [open, rows, load]);

  async function onCreate(e) {
    e.preventDefault();
    if (!form.rule.trim()) return;
    setSaving(true);
    setError("");
    try {
      const opTypes = form.op_types
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const match = {};
      if (opTypes.length) match.op_types = opTypes;
      if (form.target_contains.trim()) match.target_contains = form.target_contains.trim();
      await createGuardrail({
        connector_type: form.connector_type,
        account_id: form.account_id.trim(),
        rule: form.rule.trim(),
        match,
      });
      setForm((f) => ({ ...f, rule: "", op_types: "", target_contains: "" }));
      load();
    } catch (err) {
      setError(err.message || t`That guardrail wasn't saved — nothing on your account changed.`);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id) {
    try {
      await deleteGuardrail(id);
      load();
    } catch (err) {
      setError(err.message || t`That guardrail is still in place — removing it didn't go through.`);
    }
  }

  return (
    <div style={{ marginTop: 28 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-sm font-semibold text-muted-foreground uppercase tracking-wider"
        style={{ background: "none", border: 0, padding: 0, cursor: "pointer" }}
      >
        {open ? "▾" : "▸"} <Trans>Guardrails</Trans>{Array.isArray(rows) && rows.length ? ` (${rows.length})` : ""}
      </button>
      {open && (
        <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
          <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-sm)" }}>
            <Trans>
              A change that matches a guardrail arrives <em>blocked</em> and can never
              auto-apply; agents see the rules and propose around them. A rule with no matcher
              is guidance only.
            </Trans>
          </p>

          {error && (
            <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>{error}</p>
          )}

          {rows === null ? (
            <SkeletonList rows={2} label={t`Loading guardrails`} />
          ) : rows.length === 0 ? (
            <p className="app-subtle" style={{ fontSize: "var(--text-sm)" }}><Trans>No guardrails yet.</Trans></p>
          ) : (
            <div style={{ display: "grid", gap: 6 }}>
              {rows.map((g) => {
                const blockedOps = (g.match?.op_types || []).join(", ");
                const targetContains = g.match?.target_contains;
                return (
                <div
                  key={g.id}
                  className="connection-card"
                  style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", padding: "10px 12px" }}
                >
                  <div style={{ minWidth: 0 }}>
                    <p style={{ margin: 0, fontSize: "var(--text-sm)" }}>{g.rule}</p>
                    <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-xs)" }}>
                      {CONNECTOR_LABEL[g.connector_type] || g.connector_type}
                      {g.account_id ? ` · ${g.account_id}` : <> · <Trans>all accounts</Trans></>}
                      {blockedOps ? <> · <Trans>blocks: {blockedOps}</Trans></> : ""}
                      {targetContains ? <> · <Trans>target contains “{targetContains}”</Trans></> : ""}
                    </p>
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => onDelete(g.id)}>
                    <Trans>Remove</Trans>
                  </Button>
                </div>
                );
              })}
            </div>
          )}

          <form onSubmit={onCreate} className="connection-card" style={{ display: "grid", gap: 8, padding: 12 }}>
            <strong style={{ fontSize: "var(--text-sm)" }}><Trans>Add a guardrail</Trans></strong>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Select
                value={form.connector_type}
                onValueChange={(v) => setForm((f) => ({ ...f, connector_type: v }))}
              >
                <SelectTrigger size="sm" style={{ width: 180 }}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GUARDRAIL_CONNECTORS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {CONNECTOR_LABEL[c]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <input
                value={form.account_id}
                aria-label={t`Account id`}
                onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
                placeholder={t`Account id (blank = all)`}
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, width: 200 }}
              />
            </div>
            <input
              value={form.rule}
              aria-label={t`Guardrail rule`}
              onChange={(e) => setForm((f) => ({ ...f, rule: e.target.value }))}
              placeholder={t`Rule, e.g. “Never pause the Brand campaign”`}
              className="rounded-md border border-input bg-transparent px-2 text-sm"
              style={{ height: 32 }}
              required
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                value={form.op_types}
                aria-label={t`Operation types`}
                onChange={(e) => setForm((f) => ({ ...f, op_types: e.target.value }))}
                placeholder={t`Op types to block, comma-separated (optional)`}
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, flex: 1, minWidth: 220 }}
              />
              <input
                value={form.target_contains}
                aria-label={t`Target contains`}
                onChange={(e) => setForm((f) => ({ ...f, target_contains: e.target.value }))}
                placeholder={t`Target contains (optional)`}
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, width: 200 }}
              />
            </div>
            <div>
              <Button type="submit" size="sm" disabled={saving || !form.rule.trim()}>
                {saving ? <Trans>Adding…</Trans> : <Trans>Add guardrail</Trans>}
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ExecutePage() {
  const { t, i18n } = useLingui();
  const [changeSets, setChangeSets] = useState(null);
  const [destructiveMap, setDestructiveMap] = useState({});
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [drawerId, setDrawerId] = useState(null);
  const [confirm, setConfirm] = useState(null); // {action, cs}

  // Autonomy dial for the active project.
  const [activeProject, setActiveProject] = useState(null);
  const [autonomy, setAutonomy] = useState("");
  const [autonomySaving, setAutonomySaving] = useState(false);
  const [autonomyError, setAutonomyError] = useState("");
  const [remoteProjects, setRemoteProjects] = useState([]);

  const load = useCallback(async () => {
    try {
      setChangeSets(await listChangeSets());
      setError(null);
    } catch (err) {
      // A retired session is already redirecting to sign-in; anything shown
      // here would only flash past on the way out.
      if (isSessionExpired(err)) return;
      setError(err instanceof Error ? err.message : String(err));
      // Deliberately NOT []: an empty array is the claim "nothing has been
      // proposed yet", and a request that failed has no standing to make it.
      setChangeSets(null);
    }
  }, []);

  useEffect(() => {
    load();
    listOps()
      .then((ops) =>
        setDestructiveMap(Object.fromEntries(ops.map((op) => [op.op_type, op.destructive])))
      )
      .catch(() => {});
    setActiveProject(getActiveProject());
    if (hasAuthToken()) {
      fetchProjectsRemote().then(setRemoteProjects).catch(() => {});
    }
  }, [load]);

  useEffect(() => {
    const remote = remoteProjects.find((p) => p.id === activeProject?.id);
    if (remote) setAutonomy(remote.autonomyLevel || AUTONOMY_ASK);
  }, [remoteProjects, activeProject]);

  // Auto-refresh: 20s idle, 3s while a set is applying; paused in hidden tabs.
  const applying = (changeSets || []).some((cs) => cs.status === "applying");
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) load();
    }, applying ? 3000 : 20000);
    return () => clearInterval(timer);
  }, [load, applying]);

  async function runAction(action, cs, { changeIds = null } = {}) {
    setBusyId(cs.id);
    setError(null);
    try {
      if (action === "approve") await approveChangeSet(cs.id, changeIds);
      if (action === "reject") await rejectChangeSet(cs.id);
      if (action === "apply") await applyChangeSet(cs.id, cs.connector_type);
      if (action === "rollback") await rollbackChangeSet(cs.id, cs.connector_type);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  // Apply and rollback go through the confirm dialog; approve/reject act directly.
  function onAction(action, cs, opts) {
    if (action === "apply" || action === "rollback") {
      setConfirm({ action, cs });
      return;
    }
    runAction(action, cs, opts);
  }

  async function onChangeAutonomy(level) {
    if (!activeProject?.id) return;
    setAutonomySaving(true);
    setAutonomyError("");
    const prev = autonomy;
    setAutonomy(level);
    try {
      const updated = await setProjectAutonomy(activeProject.id, level);
      setAutonomy(updated.autonomyLevel);
    } catch (err) {
      setAutonomy(prev);
      setAutonomyError(err.message || t`Autonomy is unchanged — that didn't save.`);
    } finally {
      setAutonomySaving(false);
    }
  }

  const projectNames = useMemo(
    () => Object.fromEntries(remoteProjects.map((p) => [p.id, p.name])),
    [remoteProjects]
  );
  const projectOptions = useMemo(() => {
    const ids = new Set((changeSets || []).map((cs) => cs.project_id).filter(Boolean));
    return [...ids].map((id) => ({ id, name: projectNames[id] || t`Unnamed project` }));
  }, [changeSets, projectNames, t]);

  const filtered = (changeSets || []).filter(
    (cs) =>
      (!statusFilter || cs.status === statusFilter) &&
      (!sourceFilter || (cs.source || "user") === sourceFilter) &&
      (!projectFilter ||
        (projectFilter === "none" ? !cs.project_id : cs.project_id === projectFilter))
  );

  const drawerCs = drawerId ? (changeSets || []).find((cs) => cs.id === drawerId) : null;

  return (
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight"><Trans>Executions</Trans></h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        <Trans>
          Agents propose, you approve. Every change is previewed against your guardrails, and
          anything applied can be rolled back.
        </Trans>
      </p>

      <AutonomyPanel
        project={activeProject}
        level={autonomy}
        onChange={onChangeAutonomy}
        saving={autonomySaving}
        error={autonomyError}
      />

      {error && <LoadError what={t`the execution queue`} detail={error} onRetry={load} />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
          <SelectTrigger size="sm" style={{ width: 180 }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((f) => (
              <SelectItem key={f.value || "all"} value={f.value || "all"}>
                {i18n._(f.label)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={sourceFilter || "all"} onValueChange={(v) => setSourceFilter(v === "all" ? "" : v)}>
          <SelectTrigger size="sm" style={{ width: 170 }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SOURCE_FILTERS.map((f) => (
              <SelectItem key={f.value || "all"} value={f.value || "all"}>
                {i18n._(f.label)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {projectOptions.length > 0 && (
          <Select
            value={projectFilter || "all"}
            onValueChange={(v) => setProjectFilter(v === "all" ? "" : v)}
          >
            <SelectTrigger size="sm" style={{ width: 190 }}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all"><Trans>All projects</Trans></SelectItem>
              {projectOptions.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
              <SelectItem value="none"><Trans>No project</Trans></SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      {error ? null : changeSets === null ? (
        <SkeletonList rows={3} label={t`Loading change sets`} />
      ) : filtered.length === 0 ? (
        <p className="app-subtle">
          {changeSets.length === 0
            ? <Trans>Nothing proposed yet. Run an audit or an insight session and the fixes land here for approval.</Trans>
            : <Trans>Nothing matches these filters.</Trans>}
        </p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {filtered.map((cs) => {
            const account = cs.account_name || cs.account_id;
            const changeCount = cs.changes.length;
            return (
              <article key={cs.id} className="connection-card" style={{ display: "grid", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                  <div style={{ minWidth: 0 }}>
                    <h2 className="connection-title" style={{ marginBottom: 2 }}>{cs.title}</h2>
                    <p className="app-subtle" style={{ margin: 0, fontSize: "var(--text-sm)" }}>
                      {CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}
                      {account ? ` · ${account}` : ""}
                      {cs.project_id && projectNames[cs.project_id]
                        ? ` · ${projectNames[cs.project_id]}`
                        : ""}{" "}
                      · {new Date(cs.created_at).toLocaleString()} ·{" "}
                      <Plural value={changeCount} one="# change" other="# changes" />
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <ProvenanceBadges cs={cs} />
                    <Pill status={cs.status} />
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Button type="button" size="sm" variant="secondary" onClick={() => setDrawerId(cs.id)}>
                    <Trans>Review</Trans>
                  </Button>
                  {cs.status === "proposed" && (
                    <Button size="sm" disabled={busyId === cs.id} onClick={() => onAction("approve", cs)}>
                      <Trans>Approve all</Trans>
                    </Button>
                  )}
                  {cs.status === "approved" && (
                    <Button size="sm" disabled={busyId === cs.id} onClick={() => onAction("apply", cs)}>
                      <Trans>Apply now</Trans>
                    </Button>
                  )}
                  {(cs.status === "applied" || cs.status === "partial") && (
                    <Button size="sm" variant="outline" disabled={busyId === cs.id} onClick={() => onAction("rollback", cs)}>
                      <Trans>Roll back</Trans>
                    </Button>
                  )}
                  {busyId === cs.id && (
                    <span className="app-subtle" style={{ fontSize: "var(--text-sm)", alignSelf: "center" }}>
                      <Trans>Working…</Trans>
                    </span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      <GuardrailsPanel />

      <DetailDrawer
        cs={drawerCs}
        destructiveMap={destructiveMap}
        busy={busyId === drawerCs?.id}
        onClose={() => setDrawerId(null)}
        onAction={onAction}
        projectName={drawerCs?.project_id ? projectNames[drawerCs.project_id] : ""}
      />

      <ConfirmDialog
        confirm={confirm}
        destructiveMap={destructiveMap}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const pending = confirm;
          setConfirm(null);
          if (pending) runAction(pending.action, pending.cs);
        }}
      />
    </section>
  );
}
