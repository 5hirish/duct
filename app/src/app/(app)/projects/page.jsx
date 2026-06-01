"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Trash2, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { deleteProject, getActiveProjectId, getProjects, setActiveProjectId } from "../../../lib/projects";

function safeHostname(url) {
  if (!url) return "";
  try {
    const normalized = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    return new URL(normalized).hostname;
  } catch {
    return "";
  }
}

function faviconUrl(url) {
  const host = safeHostname(url);
  if (!host) return "";
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
}

export default function ProjectsPage() {
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
      setProjects(getProjects());
      setActiveId(getActiveProjectId() || "");
    };
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  function handleOpenProject(projectId) {
    setActiveProjectId(projectId);
    window.dispatchEvent(new Event("duct:project-changed"));
    router.push(`/project/${projectId}`);
  }

  function requestDeleteProject(event, project) {
    event.stopPropagation();
    event.preventDefault();
    setProjectPendingDelete(project);
  }

  function confirmDeleteProject() {
    if (!projectPendingDelete?.id) return;
    deleteProject(projectPendingDelete.id);
    setProjectPendingDelete(null);
    const nextProjects = getProjects();
    setProjects(nextProjects);
    setActiveId(getActiveProjectId() || "");
    window.dispatchEvent(new Event("duct:project-changed"));
  }

  return (
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Manage projects</h1>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Select a project to edit its configuration, or manage existing projects safely.
      </p>

      {!hasProjects && (
        <div className="rounded-3xl border border-border bg-card p-6">
          <p className="text-sm text-muted-foreground">No projects yet. Start by completing onboarding.</p>
          <div className="mt-3">
            <Button asChild>
              <Link href="/onboarding?new=1">Create a new project</Link>
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {sortedProjects.map((project) => {
          const name = project.name || project.company?.name || "Untitled project";
          const industry = project.company?.industry || "Unspecified industry";
          const url = project.company?.website_url || "";
          const favicon = faviconUrl(url);
          const host = safeHostname(url);

          return (
            <div
              key={project.id}
              role="button"
              tabIndex={0}
              onClick={() => handleOpenProject(project.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleOpenProject(project.id);
                }
              }}
              className="group cursor-pointer rounded-3xl border border-border bg-card p-4 text-left shadow-sm ring-1 ring-foreground/5 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            >
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
                    <p className="truncate font-semibold text-foreground">{name}</p>
                    <p className="truncate text-xs text-muted-foreground">{industry}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {project.id === activeId && <Badge variant="secondary">Active</Badge>}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-full text-muted-foreground hover:text-destructive"
                    aria-label={`Delete ${name}`}
                    onClick={(event) => requestDeleteProject(event, project)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>

              <div className="mt-3 min-h-5 text-xs text-muted-foreground">
                {url ? (
                  <span className="truncate block">{host || url}</span>
                ) : (
                  <span>No website URL</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

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
                ? `Delete “${projectPendingDelete.name || projectPendingDelete.company?.name || "Untitled project"}”?`
                : "Delete project?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              This removes the project and its saved configuration from this browser. Saved reports are not removed
              automatically. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
            <AlertDialogAction
              type="button"
              className="bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30"
              onClick={confirmDeleteProject}
            >
              Delete project
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
