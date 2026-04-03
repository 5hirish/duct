"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function AppNav() {
  const pathname = usePathname();
  const isReports = pathname.startsWith("/reports");
  const isConnections = pathname.startsWith("/connections");

  return (
    <div className="nav-links">
      <Link className={`nav-link ${isConnections ? "nav-link--active" : ""}`} href="/connections">
        Connections
      </Link>
      <Link className={`nav-link ${isReports ? "nav-link--active" : ""}`} href="/reports">
        Reports
      </Link>
    </div>
  );
}
