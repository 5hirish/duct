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
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import EmptyState from "@/components/ui/empty-state";
import { HelpTip, Page, PageHeader, Section } from "@/components/ui/page";
import { LOGOS } from "@/components/connections/logos";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ShieldCheck } from "lucide-react";

// The status as a Badge tone: amber waits on someone, blue is moving, green
// landed, red failed, grey is over.
const STATUS_TONE = {
  proposed: "warning",
  approved: "info",
  applying: "info",
  applied: "success",
  partial: "warning",
  failed: "destructive",
  rejected: "secondary",
  rolled_back: "secondary",
  blocked: "destructive",
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
    <Badge variant={STATUS_TONE[status] || "secondary"}>
      {STATUS_LABEL[status] ? i18n._(STATUS_LABEL[status]) : status}
    </Badge>
  );
}

function ProvenanceBadges({ cs }) {
  return (
    <>
      {cs.applied_by === "auto" && (
        <Badge variant="outline">
          <Trans>Applied automatically</Trans>
        </Badge>
      )}
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
      {change.drift && (
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--destructive)" }}>
          <Trans>⛔ Changed in the account after you approved it, so it was not applied. Ask for a fresh proposal.</Trans>
        </p>
      )}
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

/**
 * How much the agents may do without asking, as a segmented control in the
 * page header. It was a card of its own with 65 words around three buttons;
 * the invariant that makes the top setting safe is still one click away, in
 * the "?" beside it, where someone deciding to turn the dial will look.
 */
function AutonomyControl({ project, level, onChange, saving, error }) {
  const { t, i18n } = useLingui();
  if (!project || !level) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          <Trans>Autonomy</Trans>
        </span>
        <div
          role="radiogroup"
          aria-label={t`Execution autonomy`}
          className="inline-flex rounded-lg bg-muted p-0.5"
        >
          {AUTONOMY_OPTIONS.map((opt) => {
            const selected = opt.value === level;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={selected}
                title={i18n._(opt.blurb)}
                disabled={saving || selected}
                onClick={() => onChange(opt.value)}
                className={cn(
                  "h-7 rounded-md px-3 text-sm font-medium transition-colors disabled:cursor-default",
                  selected
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {i18n._(opt.label)}
              </button>
            );
          })}
        </div>
        <HelpTip label={t`What autonomy allows`}>
          <Trans>
            Destructive work always waits for you: Tag Manager publishes, archives, unlinks,
            anything touching budget or status, and new keywords. Assisted and Auto may apply only
            negative keywords, Analytics key events and audiences, and Tag Manager workspace edits.
          </Trans>
        </HelpTip>
      </div>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error.includes("404") || error.toLowerCase().includes("owner")
            ? <Trans>Only the project owner can change autonomy.</Trans>
            : error}
        </p>
      )}
    </div>
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

  const count = Array.isArray(rows) ? rows.length : null;
  return (
    <Section
      title={<Trans>Guardrails</Trans>}
      count={count || null}
      help={
        <Trans>
          A change that matches a guardrail arrives blocked and can never apply on its own. Agents see
          the rules and propose around them. A rule with no matcher is guidance only.
        </Trans>
      }
      actions={
        <Button type="button" size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? <Trans>Hide</Trans> : <Trans>Show</Trans>}
        </Button>
      }
    >
      {open && (
        <div className="flex flex-col gap-4">
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          {rows === null ? (
            <SkeletonList rows={2} label={t`Loading guardrails`} />
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              <Trans>No guardrails yet.</Trans>
            </p>
          ) : (
            <Card className="gap-0 overflow-hidden p-0">
              {rows.map((g) => {
                const blockedOps = (g.match?.op_types || []).join(", ");
                const targetContains = g.match?.target_contains;
                return (
                  <div key={g.id} className="flex items-center justify-between gap-3 border-b px-4 py-3 last:border-0">
                    <div className="min-w-0">
                      <p className="text-sm">{g.rule}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
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
            </Card>
          )}

          <Card size="sm">
            <form onSubmit={onCreate} className="flex flex-col gap-3">
              <p className="text-sm font-semibold">
                <Trans>Add a guardrail</Trans>
              </p>
              <Input
                value={form.rule}
                aria-label={t`Guardrail rule`}
                onChange={(e) => setForm((f) => ({ ...f, rule: e.target.value }))}
                placeholder={t`Never pause the Brand campaign`}
                required
              />
              <div className="grid gap-3 @xl:grid-cols-2">
                <Select
                  value={form.connector_type}
                  onValueChange={(v) => setForm((f) => ({ ...f, connector_type: v }))}
                >
                  <SelectTrigger aria-label={t`Source`} className="w-full">
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
                <Input
                  value={form.account_id}
                  aria-label={t`Account id`}
                  onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
                  placeholder={t`Account id (blank = all)`}
                />
                <Input
                  value={form.op_types}
                  aria-label={t`Operation types`}
                  onChange={(e) => setForm((f) => ({ ...f, op_types: e.target.value }))}
                  placeholder={t`Op types to block, comma-separated (optional)`}
                />
                <Input
                  value={form.target_contains}
                  aria-label={t`Target contains`}
                  onChange={(e) => setForm((f) => ({ ...f, target_contains: e.target.value }))}
                  placeholder={t`Target contains (optional)`}
                />
              </div>
              <Button type="submit" size="sm" className="self-start" disabled={saving || !form.rule.trim()}>
                {saving ? <Trans>Adding…</Trans> : <Trans>Add guardrail</Trans>}
              </Button>
            </form>
          </Card>
        </div>
      )}
    </Section>
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
      if (action === "apply") await applyChangeSet(cs.id);
      if (action === "rollback") await rollbackChangeSet(cs.id);
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

  const waiting = (changeSets || []).filter((cs) => cs.status === "proposed").length;

  return (
    <Page>
      <PageHeader
        title={<Trans>Changes</Trans>}
        status={
          changeSets === null ? null : waiting ? (
            <Plural value={waiting} one="# change set waiting for you" other="# change sets waiting for you" />
          ) : (
            <Trans>Nothing is waiting for you.</Trans>
          )
        }
        help={
          <Trans>
            Agents propose changes to your accounts and you approve them. Every change is checked
            against your guardrails first, and anything applied can be rolled back.
          </Trans>
        }
        actions={
          <AutonomyControl
            project={activeProject}
            level={autonomy}
            onChange={onChangeAutonomy}
            saving={autonomySaving}
            error={autonomyError}
          />
        }
      />

      {error && <LoadError what={t`the execution queue`} detail={error} onRetry={load} />}

      <Section
        title={<Trans>All changes</Trans>}
        actions={
          <div className="flex flex-wrap justify-end gap-2">
            <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
              <SelectTrigger size="sm" aria-label={t`Status`}>
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
              <SelectTrigger size="sm" aria-label={t`Proposed by`}>
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
            {projectOptions.length > 1 && (
              <Select
                value={projectFilter || "all"}
                onValueChange={(v) => setProjectFilter(v === "all" ? "" : v)}
              >
                <SelectTrigger size="sm" aria-label={t`Project`}>
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
        }
      >
        {error ? null : changeSets === null ? (
          <SkeletonList rows={3} label={t`Loading change sets`} />
        ) : filtered.length === 0 ? (
          changeSets.length === 0 ? (
            <EmptyState icon={ShieldCheck} title={t`Nothing proposed yet`}>
              <Trans>Fixes from an audit or a conversation land here for you to approve.</Trans>
            </EmptyState>
          ) : (
            <p className="text-sm text-muted-foreground">
              <Trans>Nothing matches these filters.</Trans>
            </p>
          )
        ) : (
          // A list, not a card per change set: these are items of one kind,
          // read to compare and act on (NN/g, cards vs lists). One row each,
          // the same columns in the same places.
          <Card className="gap-0 overflow-hidden p-0">
            {filtered.map((cs) => {
              const account = cs.account_name || cs.account_id;
              const changeCount = cs.changes.length;
              const when = relativeTime(cs.created_at, { fallbackAfterDays: 7, locale: i18n.locale });
              return (
                // A grid, so a narrow pane puts the status and actions on a
                // second line under the title instead of squeezing the title
                // to two letters beside them.
                <article
                  key={cs.id}
                  className="grid grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-x-4 gap-y-3 border-b px-4 py-4 last:border-0 @2xl:grid-cols-[2.25rem_minmax(0,1fr)_auto]"
                >
                  <span
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background [&_img]:size-5 [&_svg]:size-5"
                    aria-hidden
                  >
                    {LOGOS[cs.connector_type]}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-sm font-medium">
                      <button
                        type="button"
                        onClick={() => setDrawerId(cs.id)}
                        className="text-left outline-none hover:underline focus-visible:underline"
                      >
                        {cs.title}
                      </button>
                    </h3>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {CONNECTOR_LABEL[cs.connector_type] || cs.connector_type}
                      {account ? ` · ${account}` : ""}
                      {projectOptions.length > 1 && cs.project_id && projectNames[cs.project_id]
                        ? ` · ${projectNames[cs.project_id]}`
                        : ""}
                      {" · "}
                      <time dateTime={cs.created_at} title={new Date(cs.created_at).toLocaleString(i18n.locale)}>
                        {when}
                      </time>
                      {" · "}
                      <Plural value={changeCount} one="# change" other="# changes" />
                    </p>
                  </div>
                  <div className="col-start-2 flex flex-wrap items-center gap-2 @2xl:col-start-3">
                    <ProvenanceBadges cs={cs} />
                    <Pill status={cs.status} />
                    {busyId === cs.id && <Spinner className="size-4 text-muted-foreground" />}
                    <Button type="button" size="sm" variant="ghost" onClick={() => setDrawerId(cs.id)}>
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
                  </div>
                </article>
              );
            })}
          </Card>
        )}
      </Section>

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
    </Page>
  );
}
