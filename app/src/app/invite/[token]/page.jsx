"use client";

// Invitation landing page. Lives outside the (app) route group on purpose: the
// recipient is usually signed out, so it must render without AuthGuard and show
// who invited them before asking them to sign in.

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { acceptInvitation, fetchInvitation } from "@/lib/membersApi";
import { hydrateProjectsFromBackend, setActiveProjectId } from "@/lib/projects";
import { AUTH_TOKEN_KEY, decodeJwtPayload } from "@/lib/authFetch";

// Read by the sign-in page after the OAuth round trip, so the invite survives
// the redirect through Google without ever putting the token in an OAuth param.
const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";

function signedInEmail() {
  if (typeof window === "undefined") return "";
  const payload = decodeJwtPayload(localStorage.getItem(AUTH_TOKEN_KEY) || "");
  if (!payload?.exp || payload.exp * 1000 <= Date.now()) return "";
  return (payload.sub || "").toLowerCase();
}

function Shell({ children }) {
  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-background px-4 py-10"
      tabIndex={-1}
    >
      <div className="w-full max-w-md rounded-3xl border border-border bg-card p-7 shadow-sm ring-1 ring-foreground/5">
        <div className="mb-6 flex items-center gap-1.5">
          <span className="font-serif text-lg tracking-tight text-foreground">duct</span>
          <span className="size-2 rounded-full bg-[var(--orange)]" aria-hidden />
        </div>
        {children}
      </div>
    </main>
  );
}

export default function InvitePage({ params }) {
  const { token } = use(params);
  const router = useRouter();

  const [invitation, setInvitation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [viewerEmail, setViewerEmail] = useState("");

  useEffect(() => {
    setViewerEmail(signedInEmail());
    fetchInvitation(token)
      .then(setInvitation)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [token]);

  const accept = useCallback(async () => {
    setAccepting(true);
    setError("");
    try {
      const result = await acceptInvitation(token);
      // Pull the newly shared project into the local cache and make it active,
      // so the app opens on the project they were invited to.
      await hydrateProjectsFromBackend();
      setActiveProjectId(result.project_id);
      window.dispatchEvent(new Event("duct:project-changed"));
      router.replace(`/project/${result.project_id}/members`);
    } catch (err) {
      setError(err.message);
      setAccepting(false);
    }
  }, [token, router]);

  function goSignIn() {
    try {
      sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, `/invite/${token}`);
    } catch {
      // Private mode with storage disabled — they'll land on the app home and
      // can reopen the emailed link.
    }
    router.push("/");
  }

  if (loading) {
    return (
      <Shell>
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Checking your invitation…
        </p>
      </Shell>
    );
  }

  if (!invitation) {
    return (
      <Shell>
        <h1 className="mb-2 font-serif text-xl text-foreground">Invitation unavailable</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          {error || "This invitation link is invalid, expired, or has already been used."}
        </p>
        <p className="text-sm text-muted-foreground">
          Ask whoever invited you to send a new one, or{" "}
          <a className="underline underline-offset-2" href="/">
            sign in
          </a>{" "}
          if you already have access.
        </p>
      </Shell>
    );
  }

  const inviter = invitation.inviter_name || invitation.inviter_email;
  const signedIn = Boolean(viewerEmail);
  const wrongAccount = signedIn && viewerEmail !== invitation.invited_email;

  return (
    <Shell>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--orange)]">
        Project invitation
      </p>
      <h1 className="mb-3 font-serif text-2xl leading-snug text-foreground">
        {inviter ? `${inviter} invited you to ` : "You've been invited to "}
        <em className="text-[var(--orange)]">{invitation.project_name || "a project"}</em>
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        You&rsquo;ll join as a collaborator — you can open the project, run audits and insights, and
        work on content with the rest of the team.
      </p>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

      {!signedIn && (
        <>
          <GoogleSignInButton onClick={goSignIn} />
          <p className="mt-3 text-center text-xs text-muted-foreground">
            Sign in as <strong>{invitation.invited_email}</strong> to accept. We&rsquo;ll create
            your account if you don&rsquo;t have one.
          </p>
        </>
      )}

      {signedIn && wrongAccount && (
        <>
          <p className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400">
            This invitation was sent to <strong>{invitation.invited_email}</strong>, but
            you&rsquo;re signed in as <strong>{viewerEmail}</strong>.
          </p>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() => {
              localStorage.removeItem(AUTH_TOKEN_KEY);
              goSignIn();
            }}
          >
            Switch account
          </Button>
        </>
      )}

      {signedIn && !wrongAccount && (
        <Button type="button" className="w-full" onClick={accept} disabled={accepting}>
          {accepting && <Loader2 className="size-4 animate-spin" />}
          Accept invitation
        </Button>
      )}
    </Shell>
  );
}
