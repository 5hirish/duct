"use client";

import Link from "next/link";
import { useEffect } from "react";
import AppNav from "../../components/AppNav";
import { AuthProvider, AuthGuard } from "../../lib/auth";
import { migrateFromLegacyProfile } from "../../lib/projects";

export default function AppLayout({ children }) {
  useEffect(() => {
    migrateFromLegacyProfile();
  }, []);

  return (
    <AuthProvider>
      <AuthGuard>
        <div className="app-shell">
          <header className="app-header border-border/70 bg-background/85 shadow-sm ring-1 ring-border/40 backdrop-blur-xl supports-[backdrop-filter]:bg-background/70">
            <div className="app-header-inner">
              <div className="app-header-left">
                <Link className="logo" href="/reports">
                  duct <span className="logo-mark" aria-hidden="true" />
                </Link>
                <span className="app-subtle">app</span>
              </div>

              <AppNav />
            </div>
          </header>
          <main id="main-content" className="app-main" tabIndex={-1}>
            {children}
          </main>
        </div>
      </AuthGuard>
    </AuthProvider>
  );
}
