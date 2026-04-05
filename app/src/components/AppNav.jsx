"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../lib/auth";

export default function AppNav() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const isConnections = pathname.startsWith("/connections");
  const isGenerate = pathname.startsWith("/generate");
  const isReports = pathname.startsWith("/reports");

  return (
    <div className="nav-links">
      <Link className={`nav-link ${isConnections ? "nav-link--active" : ""}`} href="/connections">
        Connections
      </Link>
      <Link className={`nav-link ${isGenerate ? "nav-link--active" : ""}`} href="/generate">
        Generate
      </Link>
      <Link className={`nav-link ${isReports ? "nav-link--active" : ""}`} href="/reports">
        Reports
      </Link>
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
          <button type="button" className="nav-signout" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
