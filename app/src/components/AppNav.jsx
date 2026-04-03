"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function AppNav() {
  const pathname = usePathname();
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
    </div>
  );
}
