"use client";

// Artifact library — durable agent outputs (reports first) for the active
// project. Lists the newest version per artifact group; click through to the
// viewer at /artifacts/[artifactId].

import Link from "next/link";
import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { getActiveProject } from "../../../lib/projects";
import { hasAuthToken } from "../../../lib/authFetch";
import { relativeTime } from "@/lib/format";
import { listArtifacts } from "../../../lib/artifactsApi";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Mirrors models/artifact.py's `kind` — what an artifact *is*, not who made it.
const KIND_TABS = [
  { value: "", label: "All" },
  { value: "report", label: "Reports" },
  { value: "brief", label: "Briefs" },
  { value: "document", label: "Documents" },
];

export default function ArtifactsPage() {
  const [project, setProject] = useState(null);
  const [signedIn, setSignedIn] = useState(true);
  const [kind, setKind] = useState("");
  const [items, setItems] = useState(null); // null = loading
  const [error, setError] = useState("");

  useEffect(() => {
    setProject(getActiveProject());
    setSignedIn(hasAuthToken());
  }, []);

  useEffect(() => {
    if (!project?.id || !signedIn) {
      if (project !== null) setItems([]);
      return;
    }
    let alive = true;
    setItems(null);
    listArtifacts({ projectId: project.id, kind })
      .then((rows) => alive && setItems(rows))
      .catch((err) => {
        if (!alive) return;
        setItems([]);
        setError(err.message || "Failed to load artifacts.");
      });
    return () => {
      alive = false;
    };
  }, [project, kind, signedIn]);

  return (
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Artifacts</h1>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 14 }}>
        Everything your agents have produced for{" "}
        <strong>{project?.name || "this project"}</strong> — reports, documents, exports.
        Stored durably; open one to view, download, or continue its chat.
      </p>

      <Tabs value={kind} onValueChange={setKind}>
        <TabsList>
          {KIND_TABS.map((tab) => (
            <TabsTrigger key={tab.value || "all"} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {!signedIn && (
        <p className="app-subtle" style={{ marginTop: 18 }}>
          Sign in to see your saved artifacts.
        </p>
      )}

      {signedIn && items === null && (
        <p className="app-subtle" style={{ marginTop: 18 }}>Loading…</p>
      )}

      {signedIn && items && items.length === 0 && (
        <div style={{ marginTop: 18 }}>
          <p className="app-subtle">
            {error || "No artifacts yet. Run an audit with your project selected and its report lands here."}
          </p>
          <Button asChild size="sm" style={{ marginTop: 8 }}>
            <Link href="/audit/seo">Run an SEO audit</Link>
          </Button>
        </div>
      )}

      {signedIn && items && items.length > 0 && (
        <div className="connection-grid" style={{ marginTop: 18 }}>
          {items.map((artifact) => (
            <Link
              key={artifact.id}
              href={`/artifacts/${artifact.id}`}
              className="connection-card"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="connection-card-head">
                <div className="connection-logo" aria-hidden="true">
                  <FileText size={22} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <h2 className="connection-title">{artifact.title || artifact.filename || "Untitled"}</h2>
                  <p className="connection-description" style={{ marginBottom: 0 }}>
                    {artifact.summary
                      ? `${artifact.summary.slice(0, 140)}${artifact.summary.length > 140 ? "…" : ""}`
                      : artifact.meta?.url || ""}
                  </p>
                </div>
              </div>
              <div className="connection-status-row" style={{ flexWrap: "wrap", gap: 6 }}>
                <span className="status-pill grey">{artifact.kind}</span>
                {Number.isFinite(artifact.meta?.overall_score) && (
                  <span className="status-pill green">score {artifact.meta.overall_score}</span>
                )}
                {artifact.version_count > 1 && (
                  <span className="status-pill grey">v{artifact.version} · {artifact.version_count} versions</span>
                )}
                <span className="app-subtle" style={{ marginLeft: "auto", fontSize: 12 }}>
                  {relativeTime(artifact.created_at)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
