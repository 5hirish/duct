"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import { getBusinessProfileCompletion } from "../lib/businessProfile";
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
  const [menuOpen, setMenuOpen] = useState(false);
  const [profilePercent, setProfilePercent] = useState(0);
  const menuRef = useRef(null);
  const isConnections = pathname.startsWith("/connections");
  const isGenerate = pathname.startsWith("/generate");
  const isReports = pathname.startsWith("/reports");

  useEffect(() => {
    setProfilePercent(getBusinessProfileCompletion().percent);
  }, [pathname]);

  useEffect(() => {
    function handlePointerDown(event) {
      if (!menuRef.current) return;
      if (!menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, []);

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
        <div className="nav-user nav-user-menu" ref={menuRef}>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="nav-avatar-trigger"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="nav-avatar-wrap">
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
              <span className="nav-avatar-progress-dot" aria-hidden="true" />
            </span>
          </Button>
          {menuOpen && (
            <div className="nav-profile-menu" role="menu" aria-label="Profile menu">
              <Link
                href="/onboarding"
                className="nav-profile-menu-item"
                role="menuitem"
                onClick={() => setMenuOpen(false)}
              >
                Profile ({profilePercent}% complete)
              </Link>
              <button
                type="button"
                className="nav-profile-menu-item nav-profile-menu-item-button"
                role="menuitem"
                onClick={signOut}
              >
                Log out
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
