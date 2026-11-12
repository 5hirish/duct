"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Brain, FolderPlus, Trash2, Globe, Users } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { deleteProject, getProjects, resolveActiveProjectId, setActiveProjectId } from "../../../lib/projects";
import { faviconUrl, safeHostname } from "@/lib/favicon";
import EmptyState from "@/components/ui/empty-state";
import { Card, CardFooter, cardLinkClass } from "@/components/ui/card";
import { Page, PageHeader, TileGrid } from "@/components/ui/page";
import { cn } from "@/lib/utils";

export default function ProjectsPage() {
  const { t } = useLingui();
  const router = useRouter();
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [projectPendingDelete, setProjectPendingDelete] = useState(null);

  const hasProjects = projects.length > 0;

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.id === activeId) return -1;
        if (b.id === activeId) return 1;
        return (b.updatedAt || "").localeCompare(a.updatedAt || "");
      }),
    [projects, activeId]
  );

  useEffect(() => {
    const sync = () => {
      const ps = getProjects();
      setProjects(ps);
      setActiveId(resolveActiveProjectId(ps));
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener("duct:project-changed", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("duct:project-changed", sync);
    };
  }, []);

  function handleOpenProject(projectId) {
    // Opening a project is also picking it: setActiveProjectId remembers it
    // across reloads and notifies the switcher.
    setActiveProjectId(projectId);
    router.push(`/project/${projectId}`);
  }

  function requestDeleteProject(event, project) {
    event.stopPropagation();
    event.preventDefault();
    setProjectPendingDelete(project);
  }

  function openMembers(event, projectId) {
    event.stopPropagation();
    event.preventDefault();
    router.push(`/project/${projectId}/members`);
  }

  function openMemory(event, projectId) {
    event.stopPropagation();
    event.preventDefault();
    router.push(`/project/${projectId}/memory`);
  }

  function confirmDeleteProject() {
    if (!projectPendingDelete?.id) return;
    deleteProject(projectPendingDelete.id);
    setProjectPendingDelete(null);
    const nextProjects = getProjects();
    setProjects(nextProjects);
    setActiveId(resolveActiveProjectId(nextProjects));
    window.dispatchEvent(new Event("duct:project-changed"));
  }

  const pendingName =
    projectPendingDelete?.name || projectPendingDelete?.company?.name || t`Untitled project`;

  return (
    <Page>
      <PageHeader
        title={<Trans>Projects</Trans>}
        actions={
          <Button asChild>
            <Link href="/start"><Trans>New project</Trans></Link>
          </Button>
        }
      />

      {!hasProjects && (
        <EmptyState
          icon={FolderPlus}
          title={t`No projects yet`}
          actions={
            <Button size="sm" asChild>
              <Link href="/start"><Trans>Audit a site</Trans></Link>
            </Button>
          }
        >
          <Trans>
            A project starts from a site. Duct reads it and drafts the rest — name, industry,
            competitors — for you to correct.
          </Trans>
        </EmptyState>
      )}

      <TileGrid>
        {sortedProjects.map((project) => {
          const name = project.name || project.company?.name || t`Untitled project`;
          const industry = project.company?.industry || "";
          const url = project.company?.website_url || "";
          const favicon = faviconUrl(url);
          const host = safeHostname(url);
          const isShared = project.role === "collaborator";
          const owner = project.ownerEmail || t`another user`;

          return (
            <Card key={project.id} variant="interactive" size="sm">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border bg-muted/40">
                    {favicon ? (
                      <img src={favicon} alt="" width={18} height={18} className="size-[18px] rounded-sm" />
                    ) : (
                      <Globe className="size-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <button
                      type="button"
                      data-card-link
                      onClick={() => handleOpenProject(project.id)}
                      className={cn("block max-w-full truncate text-left text-sm font-semibold", cardLinkClass)}
                    >
                      {name}
                    </button>
                    {industry && <p className="truncate text-xs text-muted-foreground">{industry}</p>}
                  </div>
                </div>

                <div className="relative z-10 flex items-center gap-1">
                  {project.id === activeId && <Badge variant="secondary"><Trans>Active</Trans></Badge>}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-full text-muted-foreground hover:text-foreground"
                    aria-label={t`Memory of ${name}`}
                    onClick={(event) => openMemory(event, project.id)}
                  >
                    <Brain className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-full text-muted-foreground hover:text-foreground"
                    aria-label={t`Members of ${name}`}
                    onClick={(event) => openMembers(event, project.id)}
                  >
                    <Users className="size-4" />
                  </Button>
                  {/* Only the owner can delete a project; a collaborator leaves
                      it from the members screen instead. */}
                  {!isShared && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-full text-muted-foreground hover:text-destructive"
                      aria-label={t`Delete ${name}`}
                      onClick={(event) => requestDeleteProject(event, project)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </div>
              </div>

              {(url || isShared) && (
                <CardFooter className="min-h-5 text-xs text-muted-foreground">
                  {url && <span className="truncate">{host || url}</span>}
                  {isShared && (
                    <Badge variant="outline" className="ml-auto shrink-0 font-normal">
                      <Trans>Shared by {owner}</Trans>
                    </Badge>
                  )}
                </CardFooter>
              )}
            </Card>
          );
        })}
      </TileGrid>

      <AlertDialog
        open={Boolean(projectPendingDelete)}
        onOpenChange={(open) => {
          if (!open) setProjectPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {projectPendingDelete
                ? <Trans>Delete “{pendingName}”?</Trans>
                : <Trans>Delete project?</Trans>}
            </AlertDialogTitle>
            <AlertDialogDescription>
              <Trans>
                This removes the project and its configuration from this browser, and cannot be
                undone. Saved reports stay where they are.
              </Trans>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button"><Trans>Cancel</Trans></AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className={buttonVariants({ variant: "destructive" })}
              onClick={confirmDeleteProject}
            >
              <Trans>Delete project</Trans>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
