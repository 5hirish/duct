"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import AppNav from "../../components/AppNav";
import AppSidebar from "../../components/AppSidebar";
import { AuthProvider, AuthGuard } from "../../lib/auth";
import { hydrateProjectsFromBackend, migrateFromLegacyProfile } from "../../lib/projects";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AuditNavProvider } from "../../lib/auditNavContext";

// Routes whose main content must fill the remaining viewport (no scroll, no padding)
const FULL_BLEED_PREFIXES = ["/audit/seo/", "/content/sessions/", "/content/posts/"];

export default function AppLayout({ children }) {
  const pathname = usePathname();
  const isFullBleed = FULL_BLEED_PREFIXES.some((p) => pathname?.startsWith(p));

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
              <div className="flex h-full items-center gap-3 px-4">
                <SidebarTrigger className="-ml-1 text-muted-foreground hover:text-foreground" />
                <div className="h-4 w-px bg-border" aria-hidden />
                <AppNav />
              </div>
            </header>

            {isFullBleed ? (
              <div id="main-content" className="flex-1 min-h-0 overflow-hidden" tabIndex={-1}>
                {children}
              </div>
            ) : (
              <div id="main-content" className="app-main" tabIndex={-1}>
                {children}
              </div>
            )}
          </SidebarInset>
        </SidebarProvider>
        </AuditNavProvider>
      </AuthGuard>
    </AuthProvider>
  );
}
