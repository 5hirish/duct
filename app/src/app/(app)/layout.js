"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import AppNav from "../../components/AppNav";
import AppSidebar from "../../components/AppSidebar";
import { AuthProvider, AuthGuard } from "../../lib/auth";
import { hydrateProjectsFromBackend, migrateFromLegacyProfile } from "../../lib/projects";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AuditNavProvider } from "../../lib/auditNavContext";
import LocalBackendGate from "../../components/LocalBackendGate.jsx";
import UpdateToast from "../../components/UpdateToast.jsx";
import ConnectionBanner from "../../components/ConnectionBanner.jsx";
import { CommandProvider } from "../../components/commands/CommandRegistry";
import CommandPalette from "../../components/commands/CommandPalette";
import AppCommands from "../../components/commands/AppCommands";
import CommandPaletteTrigger from "../../components/commands/CommandPaletteTrigger";

// Routes whose main content must fill the remaining viewport (no scroll, no padding)
const FULL_BLEED_PREFIXES = [
  "/audit/seo/",
  "/content/sessions/",
  "/content/posts/",
  "/content/plan",
  "/insights/session",
];

// Routes that use the full viewport width (fluid) but still scroll with padding
const WIDE_PREFIXES = ["/content"];

// The gate must wrap the layout rather than sit inside it: this component's
// own effects hit the API, so they must not run until the base URL is settled.
export default function AppLayout({ children }) {
  return (
    <LocalBackendGate>
      <AppLayoutInner>{children}</AppLayoutInner>
      {/* Outside AppLayoutInner so these survive route changes and are not
          clipped by the sidebar's overflow handling. Both render nothing until
          they have something to say. */}
      <UpdateToast />
      <ConnectionBanner />
    </LocalBackendGate>
  );
}

function AppLayoutInner({ children }) {
  const pathname = usePathname();
  const isFullBleed = FULL_BLEED_PREFIXES.some((p) => pathname?.startsWith(p));
  const isWide = !isFullBleed && WIDE_PREFIXES.some((p) => pathname?.startsWith(p));

  useEffect(() => {
    // Migrate any legacy local profile, then reconcile with the backend
    // (pulls server projects down, pushes local-only ones up). Self-gates on
    // a valid auth token, so it's a no-op when signed out.
    migrateFromLegacyProfile();
    hydrateProjectsFromBackend();
  }, []);

  return (
    <AuthProvider>
      <AuthGuard>
        <AuditNavProvider>
        {/* CommandProvider wraps the shell so any surface inside it can
            contribute commands with useRegisterCommands. */}
        <CommandProvider>
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset
            className={
              isFullBleed
                ? "h-svh flex flex-col overflow-hidden"
                : "min-h-svh flex flex-col"
            }
          >
            <header className="shrink-0 app-header border-b border-border/70 bg-background/85 shadow-sm ring-1 ring-border/40 backdrop-blur-xl supports-[backdrop-filter]:bg-background/70">
              <div className="@container flex h-full w-full items-center gap-3 px-4">
                <SidebarTrigger className="-ml-1 text-muted-foreground hover:text-foreground" />
                <div className="h-4 w-px bg-border" aria-hidden />
                <AppNav />
                <CommandPaletteTrigger className="ml-auto" />
              </div>
            </header>

            {/* @container on both: a full-bleed route skips .app-main, and a
                component whose `@` variants find no container ancestor silently
                renders its narrowest layout forever. */}
            {isFullBleed ? (
              <div id="main-content" className="@container flex-1 min-h-0 overflow-hidden" tabIndex={-1}>
                {children}
              </div>
            ) : (
              <div
                id="main-content"
                className={isWide ? "app-main-wide" : "app-main"}
                tabIndex={-1}
              >
                {children}
              </div>
            )}
          </SidebarInset>
          <AppCommands />
          <CommandPalette />
        </SidebarProvider>
        </CommandProvider>
        </AuditNavProvider>
      </AuthGuard>
    </AuthProvider>
  );
}
