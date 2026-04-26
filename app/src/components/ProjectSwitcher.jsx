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
  getActiveProjectId,
  getProjects,
  setActiveProjectId,
} from "../lib/projects";

function loadProjectsState() {
  const projects = getProjects();
  const activeId = getActiveProjectId();
  const active = projects.find((project) => project.id === activeId) || projects[0] || null;
  return { projects, activeId: active?.id || "" };
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
    return () => window.removeEventListener("storage", sync);
  }, []);

  const activeProject = projects.find((project) => project.id === activeId) || null;

  function handleProjectSelect(id) {
    setActiveProjectId(id);
    setActiveId(id);
    window.dispatchEvent(new Event("duct:project-changed"));
    if (pathname?.startsWith("/insights")) {
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
