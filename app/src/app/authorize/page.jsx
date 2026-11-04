"use client";

// Where an agent's browser sign-in lands (backend routes/mcp_oauth.py). The
// backend has already checked the agent and parked its request; this page
// asks the person and sends the browser back to the agent with their answer.
//
// The request code is the only thing in the URL. It names a request that
// lasts ten minutes, grants nothing by itself, and is spent by the answer.

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLingui } from "@lingui/react/macro";
import AgentConsent, {
  CONSENT_ALLOWED,
  CONSENT_ASK,
  CONSENT_DECLINED,
  CONSENT_EXPIRED,
  CONSENT_FAILED,
  CONSENT_INVALID,
  CONSENT_LOADING,
  CONSENT_SIGN_IN,
} from "@/components/settings/AgentConsent";
import {
  POST_SIGNIN_REDIRECT_KEY,
  authToken,
  clearAuthToken,
  decodeJwtPayload,
  isSessionExpired,
} from "@/lib/authFetch";
import { allowSignInRequest, declineSignInRequest, fetchSignInRequest } from "@/lib/mcpTokensApi";

/** The signed-in person, or "" for nobody. A guest is an install, not a
 *  person, and cannot connect an agent, so it counts as nobody. */
function signedInEmail() {
  const payload = decodeJwtPayload(authToken());
  if (!payload?.exp || payload.exp * 1000 <= Date.now() || payload.guest === true) return "";
  return payload.sub || "";
}

export default function AuthorizePage({ searchParams }) {
  const { request: code = "", error: backendError = "" } = use(searchParams);
  const router = useRouter();
  const { t } = useLingui();
  const [state, setState] = useState(CONSENT_LOADING);
  const [request, setRequest] = useState(null);
  const [viewerEmail, setViewerEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    // The backend sends `error` instead of a request when it could not check
    // the agent or its redirect (routes/mcp_oauth.py, CONSENT_ERROR_INVALID).
    if (backendError || !code) {
      setState(CONSENT_INVALID);
      return;
    }
    const email = signedInEmail();
    setViewerEmail(email);
    fetchSignInRequest(code).then(
      (found) => {
        setRequest(found);
        setState(email ? CONSENT_ASK : CONSENT_SIGN_IN);
      },
      (err) => {
        setError(err?.message || "");
        setState(err?.status === 404 ? CONSENT_EXPIRED : CONSENT_FAILED);
      },
    );
  }, [code, backendError]);

  const goSignIn = useCallback(() => {
    try {
      sessionStorage.setItem(POST_SIGNIN_REDIRECT_KEY, `/authorize?request=${encodeURIComponent(code)}`);
    } catch {
      // Storage refused (private mode): they land on the app after signing
      // in, and the agent's sign-in can be started again.
    }
    router.push("/");
  }, [code, router]);

  const answer = useCallback(
    async (allow) => {
      setBusy(true);
      setError("");
      try {
        const { redirect_to: next } = await (allow ? allowSignInRequest(code) : declineSignInRequest(code));
        setState(allow ? CONSENT_ALLOWED : CONSENT_DECLINED);
        // The agent's own address, checked by the backend when it parked the
        // request: a loopback listener, the client's site or its app.
        window.location.assign(next);
      } catch (err) {
        setBusy(false);
        if (isSessionExpired(err) || err?.status === 403) {
          setState(CONSENT_SIGN_IN);
        } else if (err?.status === 404) {
          setState(CONSENT_EXPIRED);
        } else {
          setError(err?.message || t`That didn't go through. Try again in a moment.`);
        }
      }
    },
    [code, t],
  );

  return (
    <AgentConsent
      state={state}
      request={request}
      viewerEmail={viewerEmail}
      busy={busy}
      error={error}
      onAllow={() => answer(true)}
      onDecline={() => answer(false)}
      onSignIn={goSignIn}
      onSwitchAccount={() => {
        clearAuthToken();
        goSignIn();
      }}
    />
  );
}
