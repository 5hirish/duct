"use client";

// Artifact viewer — renders one artifact version with a per-format renderer:
// template report → AuditReportV1, freehand HTML → sandboxed iframe, markdown/
// JSON → simple text views, anything else → download card. Version picker
// swaps between immutable versions of the same artifact group.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AuditReportV1 from "@/components/audit/AuditReportV1";
import { Button } from "@/components/ui/button";
import {
  deleteArtifact,
  downloadArtifact,
  getArtifact,
  getArtifactContent,
  listArtifactVersions,
} from "../../../../lib/artifactsApi";

export default function ArtifactViewerPage() {
  const { artifactId } = useParams();
  const router = useRouter();
  const [artifact, setArtifact] = useState(null);
  const [versions, setVersions] = useState([]);
  const [content, setContent] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!artifactId) return;
    let alive = true;
    setArtifact(null);
    setContent(null);
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

  const structuredData = artifact?.structured_json?.structured_data || null;
  const isHtml = (artifact?.content_type || "").startsWith("text/html");
  const isMarkdownish = ["text/markdown", "text/plain"].includes(artifact?.content_type);

  return (
    <section>
      <div className="page-toolbar-back" style={{ gap: 10, flexWrap: "wrap" }}>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/artifacts">← Artifacts</Link>
        </Button>
        <h1 className="page-toolbar-title text-xl font-semibold tracking-tight" style={{ minWidth: 0 }}>
          {artifact?.title || "Artifact"}
        </h1>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
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
          {artifact?.conversation_id && (
            <span className="status-pill grey" title="Produced by an agent conversation">chat-linked</span>
          )}
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

      {artifact && structuredData && <AuditReportV1 data={structuredData} />}

      {artifact && !structuredData && isHtml && content != null && (
        <iframe
          title={artifact.title || "Artifact"}
          srcDoc={content}
          sandbox="allow-modals allow-same-origin"
          style={{ width: "100%", height: "78vh", border: "1px solid var(--border, #e5e7eb)", borderRadius: 8, background: "#fff" }}
        />
      )}

      {artifact && !structuredData && isMarkdownish && content != null && (
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.5, padding: 16 }}>{content}</pre>
      )}

      {artifact && !structuredData && !isHtml && !isMarkdownish && content != null && (
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, padding: 16, overflowX: "auto" }}>{content}</pre>
      )}

      {artifact && !structuredData && !artifact.has_content && (
        <p className="app-subtle">
          This artifact has no stored file and no structured payload to render.
        </p>
      )}
    </section>
  );
}
