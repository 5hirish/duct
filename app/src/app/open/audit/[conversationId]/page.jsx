"use client";

// The share link for an audit report: `/open/audit/<conversation>?p=<project>`.
//
// Nothing here is public. The link names a persisted conversation, and the
// backend hands it only to members of its project — a stranger gets a 404,
// which is the same answer a wrong id gets. So "share" is just "invite, then
// send the address", and this page is the address.
//
// Outside the `(app)` group on purpose, like the invite page: a recipient is
// often signed out, and the app shell's guard would bounce them to sign-in
// with no memory of where they were going. This page parks the destination
// first, then sends them, and the sign-in page brings them back.

import { use, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Spinner } from "@/components/ui/spinner";
import { startAuditResume } from "@/lib/auditResume";
import { authToken, isTokenValid } from "@/lib/authFetch";
import { setActiveProjectId } from "@/lib/projects";

// The same key the invite page and the sign-in page agree on.
const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";

export default function OpenAuditPage({ params }) {
  const { conversationId } = use(params);
  const router = useRouter();
  const search = useSearchParams();

  useEffect(() => {
    const projectId = search.get("p") || "";
    const url = search.get("u") || "";
    // Set by the connector prompt when it sent a guest through the bundled
    // sign-in: the resumed conversation opens by checking what got connected.
    const kickoff = search.get("kickoff") || "";
    if (!isTokenValid(authToken())) {
      try {
        sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, `${window.location.pathname}${window.location.search}`);
      } catch {
        /* private mode: they land on the desk after sign-in instead */
      }
      router.replace("/");
      return;
    }
    if (projectId) setActiveProjectId(projectId);
    startAuditResume(router, { conversationId, projectId, url, kickoff });
  }, [conversationId, router, search]);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background" id="main-content" tabIndex={-1}>
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner className="size-4" />
        Opening the report…
      </p>
    </main>
  );
}
