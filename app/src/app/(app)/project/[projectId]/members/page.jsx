"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { SlidersHorizontal } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import ProjectMembers from "@/components/ProjectMembers";
import { getProjectById, hydrateProjectsFromBackend } from "@/lib/projects";
import { Page, PageHeader } from "@/components/ui/page";
import { Card } from "@/components/ui/card";

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
    <Page width="narrow">
      <PageHeader
        title={<Trans>Members</Trans>}
        status={name ? <Trans>Everyone on {name} shares its reports, audits and content.</Trans> : null}
        back={{ href: "/projects", label: t`Projects` }}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={`/project/${encodeURIComponent(projectId)}`}>
              <SlidersHorizontal className="size-4" />
              <Trans>Project context</Trans>
            </Link>
          </Button>
        }
      />

      <Card>
        <ProjectMembers projectId={projectId} onLeft={handleLeft} />
      </Card>
    </Page>
  );
}
