"use client";

// Artifact viewer — per-content-type renderers (ArtifactRenderer), linear
// version picker with labels, "Show changes" diff toggle, restore-as-new-
// version, derived exports, and "Open chat" resume for audit-produced
// artifacts. Sharing is deferred: everything here is private, authed API only.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import ArtifactRenderer, { CONTENT_TYPES, UnifiedDiffView } from "@/components/artifacts/ArtifactRenderer";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import {
  deleteArtifact,
  diffArtifact,
  downloadArtifact,
  exportArtifact,
  getArtifact,
  getArtifactContent,
  listArtifactVersions,
  restoreArtifactVersion,
} from "../../../../lib/artifactsApi";
import { startAuditResume } from "../../../../lib/auditResume";
import { createMemory } from "@/lib/memoryApi";

function exportFormatsFor(artifact) {
  if (!artifact) return [];
  const formats = [];
  if (artifact.kind === "report" && artifact.structured_json?.structured_data) formats.push("pdf");
  if ([CONTENT_TYPES.CSV, CONTENT_TYPES.TABLE_JSON].includes(artifact.content_type)) formats.push("csv");
  if (artifact.content_type === CONTENT_TYPES.MARKDOWN) formats.push("md");
  return formats;
}

/** "Remember this" from a report — the selected claim becomes a project memory
 * whose evidence points back at this artifact version and, when the reader
 * highlighted inside a section, that section. The agent extracts findings on
 * its own; this is where a human says "that one, specifically". */
function RememberFromArtifact({ artifact }) {
  const { t } = useLingui();
  const [state, setState] = useState("idle"); // idle | saving | saved | error

  async function save() {
    const selected = String(window.getSelection?.() || "").replace(/\s+/g, " ").trim();
    if (!selected) {
      setState("empty");
      return;
    }
    setState("saving");
    try {
      await createMemory({
        projectId: artifact.project_id,
        kind: "conclusion",
        title: selected.slice(0, 200),
        source_refs: [
          {
            artifact_id: artifact.id,
            slug: artifact.slug,
            version: artifact.version,
            source: "user",
          },
        ],
      });
      setState("saved");
    } catch {
      setState("error");
    }
  }

  const label = {
    idle: t`Remember selection`,
    empty: t`Select some text first`,
    saving: t`Remembering…`,
    saved: t`Remembered ✓`,
    error: t`Could not remember`,
  }[state];

  return (
    <Button size="sm" variant="ghost" onClick={save} disabled={state === "saving"}>
      {label}
    </Button>
  );
}

export default function ArtifactViewerPage() {
  const { t } = useLingui();
  const { artifactId } = useParams();
  const router = useRouter();
  const [artifact, setArtifact] = useState(null);
  const [versions, setVersions] = useState([]);
  const [content, setContent] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { confirm, dialog } = useConfirm();
  const [showChanges, setShowChanges] = useState(false);
  const [diff, setDiff] = useState(null); // {diff, base_version, target_version, summary?}

  useEffect(() => {
    if (!artifactId) return;
    let alive = true;
    setArtifact(null);
    setContent(null);
    setDiff(null);
    setShowChanges(false);
    setError("");
    getArtifact(artifactId)
      .then(async (row) => {
        if (!alive) return;
        setArtifact(row);
        listArtifactVersions(artifactId).then((v) => alive && setVersions(v)).catch(() => {});
        const structured = row.structured_json?.structured_data;
        if (!structured && row.has_content) {
          try {
            const text = await getArtifactContent(artifactId);
            if (alive) setContent(text);
          } catch (err) {
            if (alive) setError(err.message);
          }
        }
      })
      .catch((err) => alive && setError(err.message || t`Artifact not found.`));
    return () => {
      alive = false;
    };
  }, [artifactId]);

  const isHead = versions.length === 0 || versions[0]?.id === artifact?.id;

  async function toggleChanges() {
    if (showChanges) {
      setShowChanges(false);
      return;
    }
    try {
      setDiff(await diffArtifact(artifact.id, "prev"));
      setShowChanges(true);
    } catch (err) {
      setError(err.message || t`No earlier version to compare.`);
    }
  }

  async function handleRestore() {
    setBusy(true);
    try {
      const newHead = await restoreArtifactVersion(artifact.id);
      router.push(`/artifacts/${newHead.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  async function handleDelete() {
    const ok = await confirm({
      title: t`Delete this artifact?`,
      description: t`Every version of it goes with it. This cannot be undone.`,
      action: t`Delete`,
      destructive: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteArtifact(artifact.id);
      router.push("/artifacts");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const exportFormats = exportFormatsFor(artifact);

  // Plain identifiers for the diff header: a member expression inside a
  // message becomes `{0}` in the catalogue, which a translator cannot read.
  const baseVersion = diff?.base_version;
  const targetVersion = diff?.target_version;
  const scoreBefore = diff?.summary?.score_before ?? "?";
  const scoreAfter = diff?.summary?.score_after ?? "?";
  const newCount = diff?.summary?.new_findings?.length || 0;
  const resolvedCount = diff?.summary?.resolved_findings?.length || 0;
  const newFindings = newCount > 0 ? diff.summary.new_findings.slice(0, 6).join(" · ") : "";
  const resolvedFindings = resolvedCount > 0 ? diff.summary.resolved_findings.slice(0, 6).join(" · ") : "";

  return (
    <section>
      {dialog}
      <div className="page-toolbar-back" style={{ gap: 10, flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/artifacts"><Trans>← Artifacts</Trans></Link>
        </Button>
        <div style={{ minWidth: 0 }}>
          <h1 className="page-toolbar-title text-xl font-semibold tracking-tight truncate">
            {artifact?.title || t`Artifact`}
          </h1>
          {artifact?.slug && (
            <p className="app-subtle" style={{ margin: 0, fontSize: 12 }}>
              {artifact.slug} · v{artifact.version}
              {artifact.meta?.label ? ` — ${artifact.meta.label}` : ""}
            </p>
          )}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {versions.length > 1 && (
            <select
              className="app-subtle"
              style={{ fontSize: 13, padding: "4px 6px", borderRadius: 6 }}
              value={artifact?.id || ""}
              onChange={(e) => router.push(`/artifacts/${e.target.value}`)}
              aria-label={t`Version`}
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} — {v.meta?.label || v.created_at.slice(0, 10)}
                </option>
              ))}
            </select>
          )}
          {versions.length > 1 && (
            <Button size="sm" variant={showChanges ? "default" : "ghost"} onClick={toggleChanges}>
              {showChanges ? <Trans>Hide changes</Trans> : <Trans>Show changes</Trans>}
            </Button>
          )}
          {!isHead && artifact && (
            <Button size="sm" variant="secondary" onClick={handleRestore} disabled={busy}>
              <Trans>Restore this version</Trans>
            </Button>
          )}
          {artifact && <RememberFromArtifact artifact={artifact} />}
          {artifact?.conversation_id && artifact?.agent_type === "audit_seo" && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                startAuditResume(router, {
                  conversationId: artifact.conversation_id,
                  projectId: artifact.project_id,
                  url: artifact.meta?.url || "",
                  reportMode: artifact.meta?.report_mode || "",
                })
              }
            >
              <Trans>Open chat</Trans>
            </Button>
          )}
          {exportFormats.map((fmt) => {
            const format = fmt.toUpperCase();
            return (
              <Button
                key={fmt}
                size="sm"
                variant="secondary"
                onClick={() => exportArtifact(artifact, fmt).catch((e) => setError(e.message))}
              >
                <Trans>Export {format}</Trans>
              </Button>
            );
          })}
          {artifact?.has_content && (
            <Button size="sm" variant="secondary" onClick={() => downloadArtifact(artifact).catch((e) => setError(e.message))}>
              <Trans>Download</Trans>
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={handleDelete} disabled={busy || !artifact}>
            <Trans>Delete</Trans>
          </Button>
        </div>
      </div>

      {error && (
        <p className="app-subtle" style={{ color: "var(--destructive, var(--destructive))" }}>{error}</p>
      )}
      {!artifact && !error && <p className="app-subtle"><Trans>Loading…</Trans></p>}

      {showChanges && diff && (
        <div style={{ marginBottom: 14 }}>
          <p className="app-subtle" style={{ fontSize: 13, marginBottom: 6 }}>
            <Trans>Changes v{baseVersion} → v{targetVersion}</Trans>
            {diff.summary && (
              <>
                {" · "}<Trans>score {scoreBefore} → {scoreAfter}</Trans>
                {" · "}<Trans>{newCount} new, {resolvedCount} resolved</Trans>
              </>
            )}
          </p>
          {newFindings && (
            <p className="app-subtle" style={{ fontSize: 12 }}>
              <Trans>New: {newFindings}</Trans>
            </p>
          )}
          {resolvedFindings && (
            <p className="app-subtle" style={{ fontSize: 12 }}>
              <Trans>Resolved: {resolvedFindings}</Trans>
            </p>
          )}
          <UnifiedDiffView diff={diff.diff} />
        </div>
      )}

      {artifact && !showChanges && <ArtifactRenderer artifact={artifact} content={content} />}
    </section>
  );
}
