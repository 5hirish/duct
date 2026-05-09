"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { useAuth } from "../lib/auth";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import ProjectSwitcher from "./ProjectSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import AgentDrawer from "./AgentDrawer";
import EngineDialog from "./EngineDialog";
import { DEFAULT_ENGINE, ENGINE_STORAGE_KEY, getEngine, DEFAULT_AGENT_TYPE, AGENT_TYPE_STORAGE_KEY, getAgentType } from "@/lib/engines";

function navPillClass(active) {
  return cn(
    "rounded-full shadow-none",
    active
      ? "bg-primary/15 font-semibold text-primary hover:bg-primary/22 hover:text-primary"
      : "text-muted-foreground hover:bg-muted/70 hover:text-primary"
  );
}

export default function AppNav() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const isConnections = pathname.startsWith("/connections");
  const isInsights = pathname.startsWith("/insights");

  const [engineKey, setEngineKey] = useState(DEFAULT_ENGINE);
  const [agentTypeKey, setAgentTypeKey] = useState(DEFAULT_AGENT_TYPE);

  // Read persisted selections and listen for changes from dialogs
  useEffect(() => {
    const storedEngine = localStorage.getItem(ENGINE_STORAGE_KEY) || DEFAULT_ENGINE;
    const storedAgent = localStorage.getItem(AGENT_TYPE_STORAGE_KEY) || DEFAULT_AGENT_TYPE;
    setEngineKey(storedEngine);
    setAgentTypeKey(storedAgent);

    function handleStorage(e) {
      if (e.key === ENGINE_STORAGE_KEY) setEngineKey(e.newValue || DEFAULT_ENGINE);
      if (e.key === AGENT_TYPE_STORAGE_KEY) setAgentTypeKey(e.newValue || DEFAULT_AGENT_TYPE);
    }
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const engine = getEngine(engineKey);
  const agentType = getAgentType(agentTypeKey);

  return (
    <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
      {/* Agent drawer trigger */}
      <AgentDrawer>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 rounded-full text-muted-foreground hover:text-foreground"
          aria-label="Switch agent"
        >
          <span>{agentType.icon}</span>
          <span className="hidden sm:inline">{agentType.label}</span>
        </Button>
      </AgentDrawer>

      {/* Nav pills */}
      <div className="flex items-center gap-0.5 rounded-full bg-muted/80 p-1 ring-1 ring-border/70 sm:gap-1">
        <Button variant="ghost" size="sm" className={navPillClass(isConnections)} asChild>
          <Link href="/connections">Connections</Link>
        </Button>
        <Button variant="ghost" size="sm" className={navPillClass(isInsights)} asChild>
          <Link href="/insights">Insights</Link>
        </Button>
      </div>

      <ProjectSwitcher />
      <ThemeToggle />

      {user && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="relative rounded-full p-0.5 focus-visible:ring-2 focus-visible:ring-ring/50"
              aria-label="Profile menu"
            >
              <span className="relative inline-flex items-center justify-center">
                {user.picture ? (
                  <img
                    className="size-7 rounded-full object-cover"
                    src={user.picture}
                    alt={user.name || user.email}
                    width={28}
                    height={28}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <span className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                    {(user.name || user.email || "U").charAt(0).toUpperCase()}
                  </span>
                )}
                {/* Engine badge — shows active engine on the avatar */}
                <span
                  aria-hidden="true"
                  className="absolute -bottom-1 -right-1 rounded-full border border-background bg-muted px-1 py-px font-mono text-[8px] font-semibold leading-none text-muted-foreground"
                >
                  {engine.badge}
                </span>
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuItem asChild>
              <Link href="/projects">Manage projects</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {/* Engine selector — opens EngineDialog */}
            <EngineDialog>
              <DropdownMenuItem
                onSelect={(e) => e.preventDefault()}
                className="flex items-center justify-between"
              >
                <span>Engine</span>
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {engine.badge}
                </span>
              </DropdownMenuItem>
            </EngineDialog>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut}>
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
