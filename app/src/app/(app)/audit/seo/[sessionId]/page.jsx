"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuditWorkspace from "../../../../../components/audit/AuditWorkspace";
import ProviderRequiredCard from "../../../../../components/onboarding/ProviderRequiredCard";
import { KICKOFF_KEY } from "../../../../../lib/auditResume";

// Onboarding parks a flag on the stored params when the user skipped the
// provider step. It is not part of the request — the backend forbids unknown
// fields — so it is lifted off here and decides what renders first.
const PENDING_PROVIDER = "pending_provider";

export default function AuditSessionPage() {
  const { sessionId } = useParams();
  const router = useRouter();
  const [params, setParams] = useState(null);
  const [pendingProvider, setPendingProvider] = useState(false);
  const [kickoff, setKickoff] = useState("");

  useEffect(() => {
    if (!sessionId) return;
    const stored = sessionStorage.getItem(`audit_session_${sessionId}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        const { [PENDING_PROVIDER]: pending, [KICKOFF_KEY]: firstMessage, ...request } = parsed;
        setPendingProvider(Boolean(pending));
        setKickoff(firstMessage || "");
        if (firstMessage) {
          // Sent once. A reload of this page must reattach quietly, not ask
          // the agent the same thing again.
          sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify({ ...request, ...(pending ? { [PENDING_PROVIDER]: true } : {}) }));
        }
        setParams(request);
        return;
      } catch {
        /* fall through */
      }
    }
    router.replace("/audit/seo");
  }, [sessionId, router]);

  if (!params) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading audit session…</p>
      </div>
    );
  }

  if (pendingProvider) {
    return (
      <div className="h-full overflow-auto">
        <ProviderRequiredCard
          siteUrl={params.url}
          onConnected={() => {
            // A reload after this must not show the card again.
            sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify(params));
            setPendingProvider(false);
          }}
        />
      </div>
    );
  }

  return (
    <div className="h-full">
      <AuditWorkspace sessionId={sessionId} auditParams={params} kickoff={kickoff} />
    </div>
  );
}
