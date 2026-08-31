"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getProjects,
  resolveActiveProjectId,
  setActiveProjectId,
} from "../lib/projects";

function loadProjectsState() {
  const projects = getProjects();
  // Resolving persists the fallback, so the trigger label and the id the rest
  // of the app reads back never disagree.
  return { projects, activeId: resolveActiveProjectId(projects) };
}

export default function ProjectSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    const sync = () => {
      const next = loadProjectsState();
      setProjects(next.projects);
      setActiveId(next.activeId);
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener("duct:project-changed", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("duct:project-changed", sync);
    };
  }, []);

  const activeProject = projects.find((project) => project.id === activeId) || null;

  function handleProjectSelect(id) {
    // setActiveProjectId persists the pick and notifies listeners.
    setActiveProjectId(id);
    setActiveId(id);
    if (pathname?.startsWith("/insights/organic-growth")) {
      router.refresh();
    }
  }

  function handleNewProject() {
    router.push("/projects");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="rounded-full">
          {activeProject?.name || "Select project"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {projects.map((project) => (
          <DropdownMenuItem key={project.id} onClick={() => handleProjectSelect(project.id)}>
            {project.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleNewProject}>+ New project</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
