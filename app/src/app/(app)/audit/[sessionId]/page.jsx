"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuditWorkspace from "../../../../components/audit/AuditWorkspace";

export default function AuditSessionPage() {
  const { sessionId } = useParams();
  const router = useRouter();
  const [params, setParams] = useState(null);

  useEffect(() => {
    if (!sessionId) return;
    const stored = sessionStorage.getItem(`audit_session_${sessionId}`);
    if (stored) {
      try {
        setParams(JSON.parse(stored));
        return;
      } catch {
        /* fall through */
      }
    }
    // No stored params — redirect to setup (e.g. direct URL or page refresh)
    router.replace("/audit");
  }, [sessionId, router]);

  if (!params) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading audit session…</p>
      </div>
    );
  }

  return <AuditWorkspace sessionId={sessionId} auditParams={params} />;
}
