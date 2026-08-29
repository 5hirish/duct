"use client";

// Artifact viewer — per-content-type renderers (ArtifactRenderer), linear
// version picker with labels, "Show changes" diff toggle, restore-as-new-
// version, derived exports, and "Open chat" resume for audit-produced
// artifacts. Sharing is deferred: everything here is private, authed API only.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ArtifactRenderer, { CONTENT_TYPES, UnifiedDiffView } from "@/components/artifacts/ArtifactRenderer";
import { Button } from "@/components/ui/button";
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
    idle: "Remember selection",
    empty: "Select some text first",
    saving: "Remembering…",
    saved: "Remembered ✓",
    error: "Could not remember",
  }[state];

  return (
    <Button size="sm" variant="ghost" onClick={save} disabled={state === "saving"}>
      {label}
    </Button>
  );
}

export default function ArtifactViewerPage() {
  const { artifactId } = useParams();
  const router = useRouter();
  const [artifact, setArtifact] = useState(null);
  const [versions, setVersions] = useState([]);
  const [content, setContent] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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
      .catch((err) => alive && setError(err.message || "Artifact not found."));
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
      setError(err.message || "No earlier version to compare.");
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
    if (!window.confirm("Delete this artifact and all of its versions?")) return;
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

  return (
    <section>
      <div className="page-toolbar-back" style={{ gap: 10, flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/artifacts">← Artifacts</Link>
        </Button>
        <div style={{ minWidth: 0 }}>
          <h1 className="page-toolbar-title text-xl font-semibold tracking-tight truncate">
            {artifact?.title || "Artifact"}
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
              aria-label="Version"
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
              {showChanges ? "Hide changes" : "Show changes"}
            </Button>
          )}
          {!isHead && artifact && (
            <Button size="sm" variant="secondary" onClick={handleRestore} disabled={busy}>
              Restore this version
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
              Open chat
            </Button>
          )}
          {exportFormats.map((fmt) => (
            <Button
              key={fmt}
              size="sm"
              variant="secondary"
              onClick={() => exportArtifact(artifact, fmt).catch((e) => setError(e.message))}
            >
              Export {fmt.toUpperCase()}
            </Button>
          ))}
          {artifact?.has_content && (
            <Button size="sm" variant="secondary" onClick={() => downloadArtifact(artifact).catch((e) => setError(e.message))}>
              Download
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={handleDelete} disabled={busy || !artifact}>
            Delete
          </Button>
        </div>
      </div>

      {error && (
        <p className="app-subtle" style={{ color: "var(--destructive, #b91c1c)" }}>{error}</p>
      )}
      {!artifact && !error && <p className="app-subtle">Loading…</p>}

      {showChanges && diff && (
        <div style={{ marginBottom: 14 }}>
          <p className="app-subtle" style={{ fontSize: 13, marginBottom: 6 }}>
            Changes v{diff.base_version} → v{diff.target_version}
            {diff.summary && (
              <>
                {" · "}score {diff.summary.score_before ?? "?"} → {diff.summary.score_after ?? "?"}
                {" · "}{diff.summary.new_findings?.length || 0} new, {diff.summary.resolved_findings?.length || 0} resolved
              </>
            )}
          </p>
          {diff.summary?.new_findings?.length > 0 && (
            <p className="app-subtle" style={{ fontSize: 12 }}>
              New: {diff.summary.new_findings.slice(0, 6).join(" · ")}
            </p>
          )}
          {diff.summary?.resolved_findings?.length > 0 && (
            <p className="app-subtle" style={{ fontSize: 12 }}>
              Resolved: {diff.summary.resolved_findings.slice(0, 6).join(" · ")}
            </p>
          )}
          <UnifiedDiffView diff={diff.diff} />
        </div>
      )}

      {artifact && !showChanges && <ArtifactRenderer artifact={artifact} content={content} />}
    </section>
  );
}
