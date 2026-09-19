"use client";

// Artifact library — durable agent outputs (reports first) for the active
// project. Lists the newest version per artifact group as the same thumbnail
// cards a thread's pane shows, so a document is recognised by its own first
// screen rather than by an icon; click through to the viewer at
// /artifacts/[artifactId].

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FileText, LockKeyhole } from "lucide-react";
import { ArtifactGallery } from "@/components/artifacts/ArtifactCards";
import { getActiveProject } from "../../../lib/projects";
import { hasAuthToken, isSessionExpired } from "../../../lib/authFetch";
import LoadError from "@/components/LoadError";
import EmptyState from "@/components/ui/empty-state";
import { listArtifacts } from "../../../lib/artifactsApi";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Mirrors models/artifact.py's `kind` — what an artifact *is*, not who made it.
const KIND_TABS = [
  { value: "", label: "All" },
  { value: "report", label: "Reports" },
  { value: "brief", label: "Briefs" },
  { value: "document", label: "Documents" },
];

export default function ArtifactsPage() {
  const router = useRouter();
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
    setError("");
    listArtifacts({ projectId: project.id, kind })
      .then((rows) => alive && setItems(rows))
      .catch((err) => {
        // A retired session is already redirecting to sign-in; anything shown
        // here would only flash past on the way out.
        if (!alive || isSessionExpired(err)) return;
        setItems([]);
        setError(err.message || "");
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
        <div style={{ marginTop: 18 }}>
          <EmptyState
            icon={LockKeyhole}
            title="Sign in to see your saved artifacts"
            actions={
              <Button size="sm" asChild>
                <Link href="/">Sign in</Link>
              </Button>
            }
          >
            Reports are stored against your account, so they survive the tab that made them.
          </EmptyState>
        </div>
      )}

      {signedIn && items === null && (
        <div
          className="@container mt-4 grid grid-cols-2 gap-4 @lg:grid-cols-3 @2xl:grid-cols-4"
          role="status"
          aria-label="Loading artifacts"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="aspect-[3/4] rounded-xl" />
          ))}
        </div>
      )}

      {signedIn && error && <LoadError what="your artifacts" detail={error} />}

      {signedIn && !error && items && items.length === 0 && (
        <div style={{ marginTop: 18 }}>
          <EmptyState
            icon={FileText}
            title="No artifacts yet"
            actions={
              <>
                <Button size="sm" asChild>
                  <Link href="/audit/seo">Run an SEO audit</Link>
                </Button>
                <Button size="sm" variant="ghost" asChild>
                  <Link href="/insights/organic-growth">Ask a question</Link>
                </Button>
              </>
            }
          >
            Run an audit with your project selected and its report lands here — versioned, so
            you can read what changed between two runs of the same check.
          </EmptyState>
        </div>
      )}

      {signedIn && items && items.length > 0 && (
        // `@container` because the gallery sizes its columns by its parent,
        // the way it does inside a split pane, not by the window.
        <div className="@container">
          <ArtifactGallery
            docs={items}
            onOpen={(doc) => router.push(`/artifacts/${doc.id}`)}
            labelFor={(doc) =>
              Number.isFinite(doc.meta?.overall_score) ? `${doc.kind} · ${doc.meta.overall_score}` : doc.kind
            }
            className="mt-4"
          />
        </div>
      )}
    </section>
  );
}
