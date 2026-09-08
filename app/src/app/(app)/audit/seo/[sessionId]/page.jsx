"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuditWorkspace from "../../../../../components/audit/AuditWorkspace";
import ProviderRequiredCard from "../../../../../components/onboarding/ProviderRequiredCard";
import { readAuditSession, writeAuditSession } from "../../../../../lib/auditSession";

export default function AuditSessionPage() {
  const { sessionId } = useParams();
  const router = useRouter();
  const [params, setParams] = useState(null);
  // Client-only state the starter parked beside the request (lib/auditSession.js).
  const [client, setClient] = useState({});

  useEffect(() => {
    if (!sessionId) return;
    const stored = readAuditSession(sessionId);
    if (!stored) {
      router.replace("/audit/seo");
      return;
    }
    setClient(stored.client);
    setParams(stored.request);
    if (stored.client.kickoff) {
      // Spent once. A reload must reattach quietly, not ask the agent the
      // same thing a second time.
      writeAuditSession(sessionId, stored.request, { ...stored.client, kickoff: "" });
    }
  }, [sessionId, router]);

  if (!params) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading audit session…</p>
      </div>
    );
  }

  if (client.pendingProvider) {
    return (
      <div className="h-full overflow-auto">
        <ProviderRequiredCard
          siteUrl={params.url}
          onConnected={() => {
            // A reload after this must not show the card again.
            const next = { ...client, pendingProvider: false };
            writeAuditSession(sessionId, params, next);
            setClient(next);
          }}
        />
      </div>
    );
  }

  return (
    <div className="h-full">
      <AuditWorkspace
        sessionId={sessionId}
        auditParams={params}
        kickoff={client.kickoff || ""}
        projectMode={client.projectMode || ""}
      />
    </div>
  );
}
