"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  const isGenerate = pathname.startsWith("/generate");
  const isReports = pathname.startsWith("/reports");

  return (
    <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
      <div className="flex items-center gap-0.5 rounded-full bg-muted/80 p-1 ring-1 ring-border/70 sm:gap-1">
        <Button variant="ghost" size="sm" className={navPillClass(isConnections)} asChild>
          <Link href="/connections">Connections</Link>
        </Button>
        <Button variant="ghost" size="sm" className={navPillClass(isGenerate)} asChild>
          <Link href="/generate">Generate</Link>
        </Button>
        <Button variant="ghost" size="sm" className={navPillClass(isReports)} asChild>
          <Link href="/reports">Reports</Link>
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
                <span
                  aria-hidden="true"
                  className="absolute -bottom-0.5 -right-0.5 size-2 rounded-full border-[1.5px] border-background bg-primary"
                />
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuItem asChild>
              <Link href="/projects">Manage projects</Link>
            </DropdownMenuItem>
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
