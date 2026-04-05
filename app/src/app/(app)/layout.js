"use client";

import Link from "next/link";
import AppNav from "../../components/AppNav";
import { AuthProvider, AuthGuard } from "../../lib/auth";

export default function AppLayout({ children }) {
  return (
    <AuthProvider>
      <AuthGuard>
        <div className="app-shell">
          <header className="app-header">
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
          <main className="app-main">{children}</main>
        </div>
      </AuthGuard>
    </AuthProvider>
  );
}
