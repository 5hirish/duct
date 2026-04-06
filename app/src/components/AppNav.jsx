"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../lib/auth";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
    <div className="nav-links flex flex-wrap items-center justify-end gap-2 sm:gap-3">
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
      {user && (
        <div className="nav-user">
          {user.picture ? (
            <img
              className="nav-avatar"
              src={user.picture}
              alt={user.name || user.email}
              width={28}
              height={28}
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className="nav-avatar nav-avatar-fallback">
              {(user.name || user.email || "U").charAt(0).toUpperCase()}
            </span>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-auto px-2 font-medium text-muted-foreground hover:text-primary"
            onClick={signOut}
          >
            Sign out
          </Button>
        </div>
      )}
    </div>
  );
}
