"use client";

// Execution review queue — the human gate in the staged-execution flow.
// Agents propose change sets (previewed + guardrail-checked server-side);
// this page is where the user reviews diffs and approves (all or a subset),
// applies, rolls back, or rejects them. Nothing mutates a connected account
// until Apply — except reversible, guardrail-clean sets the project's
// autonomy dial (below) allows to auto-apply, which land here already
// applied with an "auto" badge and a rollback handle.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
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
import { hasAuthToken } from "../../../lib/authFetch";
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

const STATUS_FILTERS = [
  { value: "", label: "All statuses" },
  { value: "proposed", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
  { value: "applied", label: "Applied" },
  { value: "partial", label: "Partially applied" },
  { value: "failed", label: "Failed" },
  { value: "rejected", label: "Rejected" },
  { value: "rolled_back", label: "Rolled back" },
];

const SOURCE_FILTERS = [
  { value: "", label: "All sources" },
  { value: "agent", label: "Agent-proposed" },
  { value: "user", label: "Proposed by you" },
];

const CONNECTOR_LABEL = {
  google_ads: "Google Ads",
  ga4: "Google Analytics",
  gtm: "Google Tag Manager",
  mixpanel: "Mixpanel",
};

const GUARDRAIL_CONNECTORS = ["google_ads", "ga4", "gtm", "mixpanel"];

function Pill({ status }) {
  return (
    <span className={`status-pill ${STATUS_PILL[status] || "grey"}`}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

function ProvenanceBadges({ cs }) {
  return (
    <>
      {cs.source === "agent" && <span className="status-pill green">agent</span>}
      {cs.applied_by === "auto" && <span className="status-pill yellow">auto-applied</span>}
    </>
  );
}

function JsonDetails({ label, value }) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) return null;
  return (
    <details style={{ fontSize: 12 }}>
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
          fontSize: 11,
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
  const preview = change.preview || {};
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
            aria-label={`Include ${change.summary || change.op_type}`}
          />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
            <strong style={{ fontSize: 14 }}>
              {change.summary || change.op_type}
              {destructive && (
                <span
                  className="status-pill red"
                  style={{ marginLeft: 8, fontSize: 11, verticalAlign: "middle" }}
                >
                  destructive
                </span>
              )}
            </strong>
            <Pill status={change.status} />
          </div>
          <p className="app-subtle" style={{ margin: "2px 0 0", fontSize: 12 }}>{change.op_type}</p>
        </div>
      </div>

      {preview.diff && <code style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{preview.diff}</code>}
      {(preview.warnings || []).map((warning) => (
        <p key={warning} style={{ margin: 0, fontSize: 13, color: "var(--warning, #b98900)" }}>
          ⚠ {warning}
        </p>
      ))}
      {(change.guardrail_violations || []).map((rule) => (
        <p key={rule} style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          ⛔ Guardrail: {rule}
        </p>
      ))}
      {preview.error && (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Preview failed: {preview.error}
        </p>
      )}
      {change.result?.error && (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Apply failed: {change.result.error}
        </p>
      )}
      {change.result?.rollback_error && (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          Rollback failed: {change.result.rollback_error}
        </p>
      )}

      <JsonDetails label="Current state (snapshot before change)" value={change.current} />
      <JsonDetails label="Proposed target + payload" value={{ target: change.target, payload: change.payload }} />
      <JsonDetails label="Result" value={change.result} />
      <JsonDetails label="Rollback result" value={change.rollback_result} />
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
            <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>{cs.context}</p>
          )}

          {cs.status === "proposed" && approvable.length > 1 && (
            <button
              type="button"
              className="app-subtle"
              style={{ fontSize: 12, textAlign: "left", cursor: "pointer", background: "none", border: 0, padding: 0 }}
              onClick={() =>
                setSelected(allSelected ? new Set() : new Set(approvable.map((c) => c.id)))
              }
            >
              {allSelected ? "Deselect all" : "Select all"} ({selected.size}/{approvable.length} selected)
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
                  Approve {allSelected ? "all" : `${selected.size} selected`}
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
                  Reject
                </Button>
              </>
            )}
            {cs.status === "approved" && (
              <>
                <Button size="sm" disabled={busy} onClick={() => onAction("apply", cs)}>
                  Apply now
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reject", cs)}>
                  Reject
                </Button>
              </>
            )}
            {(cs.status === "applied" || cs.status === "partial") && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("rollback", cs)}>
                Roll back
              </Button>
            )}
            {cs.status === "applying" && (
              <span className="app-subtle" style={{ fontSize: 13 }}>
                <Spinner
                  className="size-3"
                  style={{ marginRight: 6, verticalAlign: "-2px" }}
                />
                Applying changes…
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

  return (
    <AlertDialog open onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {action === "apply"
              ? `Apply ${relevant.length} change${relevant.length === 1 ? "" : "s"} to ${connector}?`
              : `Roll back ${relevant.length} applied change${relevant.length === 1 ? "" : "s"}?`}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>
              <p style={{ margin: 0 }}>
                {action === "apply"
                  ? "This mutates the live account. Applied changes record a rollback handle."
                  : "Each change is reverted using the rollback handle recorded when it was applied."}
              </p>
              {destructive.length > 0 && (
                <p style={{ margin: "8px 0 0", color: "var(--destructive, #e5484d)" }}>
                  {destructive.length} destructive change{destructive.length === 1 ? "" : "s"} —{" "}
                  {destructive.map((c) => c.summary || c.op_type).join("; ")}.
                  {action === "apply" && " Destructive operations change what is live for every visitor."}
                </p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={destructive.length > 0 ? "bg-red-600 text-white hover:bg-red-700" : undefined}
            onClick={onConfirm}
          >
            {action === "apply"
              ? destructive.length > 0
                ? "Apply (destructive)"
                : "Apply"
              : "Roll back"}
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
  if (!project || !level) return null;
  const current = AUTONOMY_OPTIONS.find((o) => o.value === level) || AUTONOMY_OPTIONS[0];
  return (
    <article className="connection-card" style={{ display: "grid", gap: 10, marginBottom: 16 }}>
      <div>
        <h2 className="connection-title" style={{ marginBottom: 2 }}>
          Autonomy — {project.name}
        </h2>
        <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>{current.blurb}</p>
      </div>

      <div role="radiogroup" aria-label="Execution autonomy" style={{ display: "flex", gap: 8 }}>
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
              {opt.label}
            </button>
          );
        })}
      </div>

      {/* The invariant, stated where the dial is turned. It is the reason the
          top of the ladder is safe to offer at all, and a user who does not
          know it will read "Auto" as "anything". */}
      <p className="app-subtle" style={{ margin: 0, fontSize: 12 }}>
        At every level: destructive operations — GTM publishes, archives, unlinks — and
        anything budget- or status-related wait for your approval here. Assisted and Auto
        share one narrow allowlist (negative/positive keywords, GA4 key events and
        audiences, GTM workspace edits), and every auto-applied set keeps a rollback handle.
      </p>

      {error && (
        <p style={{ margin: 0, fontSize: 12, color: "var(--destructive, #e5484d)" }}>
          {error.includes("404") || error.toLowerCase().includes("owner")
            ? "Only the project owner can change autonomy."
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
        setError(err.message || "Failed to load guardrails.");
      });
  }, []);

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
      setError(err.message || "Failed to create guardrail.");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id) {
    try {
      await deleteGuardrail(id);
      load();
    } catch (err) {
      setError(err.message || "Failed to delete guardrail.");
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
        {open ? "▾" : "▸"} Guardrails{Array.isArray(rows) && rows.length ? ` (${rows.length})` : ""}
      </button>
      {open && (
        <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
          <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
            Account invariants enforced in code: a change matching a guardrail arrives{" "}
            <em>blocked</em> and can never auto-apply. Rules are also shown to agents so they
            propose around them. A rule with no matcher is prose-only guidance.
          </p>

          {error && (
            <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>{error}</p>
          )}

          {rows === null ? (
            <p className="app-subtle" style={{ fontSize: 13 }}>Loading…</p>
          ) : rows.length === 0 ? (
            <p className="app-subtle" style={{ fontSize: 13 }}>No guardrails yet.</p>
          ) : (
            <div style={{ display: "grid", gap: 6 }}>
              {rows.map((g) => (
                <div
                  key={g.id}
                  className="connection-card"
                  style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", padding: "10px 12px" }}
                >
                  <div style={{ minWidth: 0 }}>
                    <p style={{ margin: 0, fontSize: 13 }}>{g.rule}</p>
                    <p className="app-subtle" style={{ margin: 0, fontSize: 12 }}>
                      {CONNECTOR_LABEL[g.connector_type] || g.connector_type}
                      {g.account_id ? ` · ${g.account_id}` : " · all accounts"}
                      {(g.match?.op_types || []).length
                        ? ` · blocks: ${g.match.op_types.join(", ")}`
                        : ""}
                      {g.match?.target_contains ? ` · target contains “${g.match.target_contains}”` : ""}
                    </p>
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => onDelete(g.id)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          )}

          <form onSubmit={onCreate} className="connection-card" style={{ display: "grid", gap: 8, padding: 12 }}>
            <strong style={{ fontSize: 13 }}>Add a guardrail</strong>
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
                onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
                placeholder="Account id (blank = all)"
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, width: 200 }}
              />
            </div>
            <input
              value={form.rule}
              onChange={(e) => setForm((f) => ({ ...f, rule: e.target.value }))}
              placeholder="Rule, e.g. “Never pause the Brand campaign”"
              className="rounded-md border border-input bg-transparent px-2 text-sm"
              style={{ height: 32 }}
              required
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                value={form.op_types}
                onChange={(e) => setForm((f) => ({ ...f, op_types: e.target.value }))}
                placeholder="Op types to block, comma-separated (optional)"
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, flex: 1, minWidth: 220 }}
              />
              <input
                value={form.target_contains}
                onChange={(e) => setForm((f) => ({ ...f, target_contains: e.target.value }))}
                placeholder="Target contains (optional)"
                className="rounded-md border border-input bg-transparent px-2 text-sm"
                style={{ height: 32, width: 200 }}
              />
            </div>
            <div>
              <Button type="submit" size="sm" disabled={saving || !form.rule.trim()}>
                {saving ? "Adding…" : "Add guardrail"}
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
      setError(err instanceof Error ? err.message : String(err));
      setChangeSets([]);
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
      setAutonomyError(err.message || "Failed to update autonomy.");
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
    return [...ids].map((id) => ({ id, name: projectNames[id] || "Unnamed project" }));
  }, [changeSets, projectNames]);

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
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Executions</h1>
      </div>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Review and approve the changes agents propose to your connected accounts. Every change is
        previewed and checked against your guardrails; nothing is applied until you approve it, and
        applied changes keep a rollback handle.
      </p>

      <AutonomyPanel
        project={activeProject}
        level={autonomy}
        onChange={onChangeAutonomy}
        saving={autonomySaving}
        error={autonomyError}
      />

      {error && <p style={{ color: "var(--destructive, #e5484d)", marginBottom: 12 }}>{error}</p>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
          <SelectTrigger size="sm" style={{ width: 180 }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((f) => (
              <SelectItem key={f.value || "all"} value={f.value || "all"}>
                {f.label}
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
                {f.label}
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
              <SelectItem value="all">All projects</SelectItem>
              {projectOptions.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
              <SelectItem value="none">No project</SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      {changeSets === null ? (
        <p className="app-subtle">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="app-subtle">
          {changeSets.length === 0
            ? "No proposed changes yet. Run an audit or insight session — recommended fixes will land here for your approval."
            : "Nothing matches these filters."}
        </p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {filtered.map((cs) => {
            const account = cs.account_name || cs.account_id;
            return (
              <article key={cs.id} className="connection-card" style={{ display: "grid", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                  <div style={{ minWidth: 0 }}>
                    <h2 className="connection-title" style={{ marginBottom: 2 }}>{cs.title}</h2>
                    <p className="app-subtle" style={{ margin: 0, fontSize: 13 }}>
                      {CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}
                      {account ? ` · ${account}` : ""}
                      {cs.project_id && projectNames[cs.project_id]
                        ? ` · ${projectNames[cs.project_id]}`
                        : ""}{" "}
                      · {new Date(cs.created_at).toLocaleString()} · {cs.changes.length} change
                      {cs.changes.length === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <ProvenanceBadges cs={cs} />
                    <Pill status={cs.status} />
                  </div>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Button type="button" size="sm" variant="secondary" onClick={() => setDrawerId(cs.id)}>
                    Review
                  </Button>
                  {cs.status === "proposed" && (
                    <Button size="sm" disabled={busyId === cs.id} onClick={() => onAction("approve", cs)}>
                      Approve all
                    </Button>
                  )}
                  {cs.status === "approved" && (
                    <Button size="sm" disabled={busyId === cs.id} onClick={() => onAction("apply", cs)}>
                      Apply now
                    </Button>
                  )}
                  {(cs.status === "applied" || cs.status === "partial") && (
                    <Button size="sm" variant="outline" disabled={busyId === cs.id} onClick={() => onAction("rollback", cs)}>
                      Roll back
                    </Button>
                  )}
                  {busyId === cs.id && (
                    <span className="app-subtle" style={{ fontSize: 13, alignSelf: "center" }}>
                      Working…
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
