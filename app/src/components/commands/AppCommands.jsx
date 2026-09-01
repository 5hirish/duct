"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Folder, Moon, Plug, Plus, Brain, Settings, Sun } from "lucide-react";
import { navigableItems } from "@/lib/navigation";
import { getProjects, resolveActiveProjectId, setActiveProjectId } from "@/lib/projects";
import { useRegisterCommands } from "./CommandRegistry";

/**
 * The app-wide commands: everywhere you can go, every project you can switch
 * to, and the handful of global toggles.
 *
 * Registered through the same public hook any other surface would use, rather
 * than baked into the palette — the palette knows nothing about routes or
 * projects, and a route that wants to contribute its own commands does it
 * exactly like this.
 */
export default function AppCommands() {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [projects, setProjects] = useState([]);
  const [activeId, setActiveId] = useState("");

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

  useRegisterCommands(
    [
      ...navigableItems().map((item) => ({
        id: `nav:${item.key}`,
        label: `Go to ${item.label}`,
        group: "Navigate",
        keywords: [item.label, item.sectionLabel, item.href],
        icon: item.icon,
        run: () => router.push(item.href),
      })),

      {
        id: "nav:connections",
        label: "Go to Connections",
        group: "Navigate",
        keywords: ["integrations", "connectors", "sources", "oauth"],
        icon: Plug,
        run: () => router.push("/connections"),
      },
      {
        id: "nav:memory",
        label: "Go to Memory",
        group: "Navigate",
        keywords: ["facts", "remember", "context"],
        icon: Brain,
        run: () => router.push("/memory"),
      },
      {
        id: "nav:projects",
        label: "Manage projects",
        group: "Navigate",
        keywords: ["settings", "delete", "members"],
        icon: Settings,
        run: () => router.push("/projects"),
      },

      // Switching project is the single most repeated action in the app, and
      // until now it was reachable only by aiming at the sidebar dropdown.
      ...projects
        .filter((project) => project.id !== activeId)
        .map((project) => ({
          id: `project:${project.id}`,
          label: `Switch to ${project.name}`,
          group: "Projects",
          keywords: [project.name, project.company?.name, "project", "switch"].filter(Boolean),
          icon: Folder,
          run: () => setActiveProjectId(project.id),
        })),
      {
        id: "project:new",
        label: "New project",
        group: "Projects",
        keywords: ["create", "add", "onboarding"],
        icon: Plus,
        run: () => router.push("/onboarding?new=1"),
      },

      {
        id: "theme:toggle",
        label: resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        group: "Preferences",
        keywords: ["dark", "light", "appearance", "theme"],
        icon: resolvedTheme === "dark" ? Sun : Moon,
        run: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
      },
    ],
    [router, resolvedTheme, setTheme, projects, activeId]
  );

  return null;
}
