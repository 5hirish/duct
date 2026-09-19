"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, SlidersHorizontal } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import ProjectMembers from "@/components/ProjectMembers";
import { getProjectById, hydrateProjectsFromBackend } from "@/lib/projects";

export default function ProjectMembersPage({ params }) {
  const { t } = useLingui();
  const { projectId } = use(params);
  const router = useRouter();
  const [name, setName] = useState("");

  useEffect(() => {
    setName(getProjectById(projectId)?.name || "");
  }, [projectId]);

  // Leaving drops the project from the caller's list; re-sync so the sidebar and
  // projects page don't keep offering a project they can no longer open.
  async function handleLeft() {
    await hydrateProjectsFromBackend();
    router.push("/projects");
  }

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          {name ? t`${name} · Members` : t`Members`}
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href={`/project/${encodeURIComponent(projectId)}`}>
              <SlidersHorizontal className="size-4" />
              <Trans>Project context</Trans>
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/projects">
              <ArrowLeft className="size-4" />
              <Trans>All projects</Trans>
            </Link>
          </Button>
        </div>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        <Trans>
          Invite teammates to collaborate on this project. Everyone here shares the same reports,
          audits, and content.
        </Trans>
      </p>

      <div className="max-w-2xl rounded-3xl border border-border bg-card p-5 shadow-sm ring-1 ring-foreground/5">
        <ProjectMembers projectId={projectId} onLeft={handleLeft} />
      </div>
    </section>
  );
}
