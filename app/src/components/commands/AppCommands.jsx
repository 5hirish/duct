"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Folder, Moon, Plug, Plus, Brain, Settings, Sun } from "lucide-react";
import { useLingui } from "@lingui/react/macro";
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
  const { t, i18n } = useLingui();
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
      // `i18n._` reads a nav label whether lib/navigation.js holds it as a
      // message descriptor or a plain string.
      ...navigableItems().map((item) => {
        const itemLabel = i18n._(item.label);
        return {
          id: `nav:${item.key}`,
          label: t`Go to ${itemLabel}`,
          group: t`Navigate`,
          keywords: [itemLabel, i18n._(item.sectionLabel), item.href],
          icon: item.icon,
          run: () => router.push(item.href),
        };
      }),

      {
        id: "nav:connections",
        label: t`Go to Connections`,
        group: t`Navigate`,
        keywords: ["integrations", "connectors", "sources", "oauth"],
        icon: Plug,
        run: () => router.push("/connections"),
      },
      {
        id: "nav:memory",
        label: t`Go to Memory`,
        group: t`Navigate`,
        keywords: ["facts", "remember", "context"],
        icon: Brain,
        run: () => router.push("/memory"),
      },
      {
        id: "nav:projects",
        label: t`Manage projects`,
        group: t`Navigate`,
        keywords: ["settings", "delete", "members"],
        icon: Settings,
        run: () => router.push("/projects"),
      },

      // Switching project is the single most repeated action in the app, and
      // until now it was reachable only by aiming at the sidebar dropdown.
      ...projects
        .filter((project) => project.id !== activeId)
        .map((project) => {
          const projectName = project.name;
          return {
            id: `project:${project.id}`,
            label: t`Switch to ${projectName}`,
            group: t`Projects`,
            keywords: [project.name, project.company?.name, "project", "switch"].filter(Boolean),
            icon: Folder,
            run: () => setActiveProjectId(project.id),
          };
        }),
      {
        id: "project:new",
        label: t`New project — audit a site`,
        group: t`Projects`,
        keywords: ["create", "add", "start", "audit"],
        icon: Plus,
        run: () => router.push("/start"),
      },

      {
        id: "theme:toggle",
        label: resolvedTheme === "dark" ? t`Switch to light theme` : t`Switch to dark theme`,
        group: t`Preferences`,
        keywords: ["dark", "light", "appearance", "theme"],
        icon: resolvedTheme === "dark" ? Sun : Moon,
        run: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
      },
    ],
    [router, resolvedTheme, setTheme, projects, activeId, t, i18n]
  );

  return null;
}
