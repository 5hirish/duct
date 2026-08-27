"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BASE } from "../../lib/api";
import { isDesktopShell, getShellInfo, openExternal } from "../../lib/shell";
import { isLocalBackendActive } from "../../lib/localBackend.js";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { AUTH_TOKEN_KEY, isTokenValid } from "@/lib/authFetch";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";
const POST_SIGNIN_REDIRECT_KEY = "duct_post_signin_redirect";
const DEFAULT_LANDING = "/insights/organic-growth";

/**
 * Where to go once signed in. The invite page parks its own path here before
 * sending the recipient through Google, so an emailed invitation survives the
 * OAuth round trip. Only same-origin paths are honoured — an attacker-supplied
 * value must never turn sign-in into an open redirect.
 */
function consumePostSignInRedirect() {
  let target = "";
  try {
    target = sessionStorage.getItem(POST_SIGNIN_REDIRECT_KEY) || "";
    sessionStorage.removeItem(POST_SIGNIN_REDIRECT_KEY);
  } catch {
    return DEFAULT_LANDING;
  }
  if (!target.startsWith("/") || target.startsWith("//")) return DEFAULT_LANDING;
  return target;
}

function SignInSuspenseFallback() {
  return (
    <div
      className="flex min-h-dvh items-center justify-center bg-background"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<SignInSuspenseFallback />}>
      <SignInContent />
    </Suspense>
  );
}

function SignInContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [turnstileToken, setTurnstileToken] = useState("");
  const [ready, setReady] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [awaitingBrowser, setAwaitingBrowser] = useState(false);
  const [turnstileError, setTurnstileError] = useState("");
  // Turnstile site keys are locked to their registered hostnames, so the widget
  // can never render on the desktop shell's origin (`tauri://localhost`, or a
  // loopback dev server) — it just fails with "Security check failed to load".
  // Nothing is lost by skipping it: the sidecar is bound to 127.0.0.1 and gated
  // by a per-install API key, so there is no bot surface to protect, and
  // `verify_turnstile` already no-ops when the sidecar has no secret configured.
  const requiresTurnstile = Boolean(TURNSTILE_SITE_KEY) && !isLocalBackendActive();
  const turnstileContainerRef = useRef(null);
  const turnstileWidgetIdRef = useRef(null);
  const getTurnstileResponseToken = useCallback(() => {
    if (
      typeof window === "undefined" ||
      !window.turnstile ||
      turnstileWidgetIdRef.current === null
    ) {
      return "";
    }
    try {
      return window.turnstile.getResponse(turnstileWidgetIdRef.current) || "";
    } catch {
      return "";
    }
  }, []);

  useEffect(() => {
    // Handle auth_code from OAuth callback — exchange it for the JWT server-side
    // so the token itself never appears in the URL (browser history / Referer leak).
    const authCode = searchParams.get("auth_code");
    if (authCode) {
      window.history.replaceState({}, "", "/");
      fetch(`${BASE}/auth/exchange?code=${encodeURIComponent(authCode)}`)
        .then((r) => r.json())
        .then(({ token }) => {
          if (token) {
            localStorage.setItem(AUTH_TOKEN_KEY, token);
            router.replace(consumePostSignInRedirect());
          }
        })
        .catch(() => {});
      return;
    }

    // Already authenticated? Redirect.
    const existing = localStorage.getItem(AUTH_TOKEN_KEY);
    if (isTokenValid(existing)) {
      router.replace(consumePostSignInRedirect());
      return;
    }

    setReady(true);
  }, [searchParams, router]);

  // Load and render Turnstile explicitly so remounts always work.
  useEffect(() => {
    if (!requiresTurnstile || !ready) return;
    let cancelled = false;

    const renderWidget = () => {
      if (cancelled || !window.turnstile || !turnstileContainerRef.current) return;
      try {
        if (turnstileWidgetIdRef.current !== null) {
          window.turnstile.remove(turnstileWidgetIdRef.current);
          turnstileWidgetIdRef.current = null;
        }
        setTurnstileError("");
        setTurnstileToken("");
        turnstileWidgetIdRef.current = window.turnstile.render(
          turnstileContainerRef.current,
          {
            sitekey: TURNSTILE_SITE_KEY,
            callback: (token) => {
              setTurnstileToken(token);
              setTurnstileError("");
            },
            "expired-callback": () => setTurnstileToken(""),
            "error-callback": () => {
              setTurnstileToken("");
              setTurnstileError("Security check failed to load. Please refresh and try again.");
            },
            theme: "light",
            appearance: "always",
          }
        );
      } catch {
        setTurnstileError("Security check failed to load. Please refresh and try again.");
      }
    };

    window.onTurnstileLoad = renderWidget;

    if (window.turnstile) {
      renderWidget();
    } else if (!document.getElementById("cf-turnstile-script")) {
      const script = document.createElement("script");
      script.id = "cf-turnstile-script";
      script.src =
        "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad&render=explicit";
      script.async = true;
      script.defer = true;
      script.onerror = () => {
        setTurnstileError("Security check failed to load. Please refresh and try again.");
      };
      document.head.appendChild(script);
    }

    return () => {
      cancelled = true;
      setTurnstileToken("");
      if (window.turnstile && turnstileWidgetIdRef.current !== null) {
        window.turnstile.remove(turnstileWidgetIdRef.current);
        turnstileWidgetIdRef.current = null;
      }
      if (window.onTurnstileLoad === renderWidget) {
        delete window.onTurnstileLoad;
      }
    };
  }, [ready, requiresTurnstile]);

  const handleSignIn = useCallback(async () => {
    if (isSigningIn) return;
    if (!BASE) {
      window.alert(
        "Sign-in is temporarily unavailable: API endpoint is not configured. Please set NEXT_PUBLIC_API_BASE for this deployment."
      );
      return;
    }
    const resolvedTurnstileToken = turnstileToken || getTurnstileResponseToken();
    if (requiresTurnstile && !resolvedTurnstileToken) {
      return;
    }
    if (resolvedTurnstileToken && resolvedTurnstileToken !== turnstileToken) {
      setTurnstileToken(resolvedTurnstileToken);
    }
    setIsSigningIn(true);
    const params = new URLSearchParams();
    if (resolvedTurnstileToken) {
      params.set("turnstile_token", resolvedTurnstileToken);
    }
    // Desktop shell: Google disallows OAuth inside embedded webviews, so
    // capable shells run the flow in the system browser. The backend routes
    // the auth code back through the shell's deep link, which reloads this
    // page with ?auth_code=. Shells without the browserAuth capability (and
    // plain browsers) keep the in-page redirect below.
    if (isDesktopShell()) {
      const info = await getShellInfo();
      if (info?.capabilities?.browserAuth) {
        params.set("client", "desktop");
        try {
          await openExternal(
            `${BASE}/auth/signin/google/authorize?${params.toString()}`
          );
          setAwaitingBrowser(true);
          return;
        } catch {
          params.delete("client"); // shell refused to open — fall back
        }
      }
    }
    const query = params.toString();
    window.location.href = `${BASE}/auth/signin/google/authorize${query ? `?${query}` : ""}`;
  }, [
    getTurnstileResponseToken,
    isSigningIn,
    requiresTurnstile,
    turnstileToken,
  ]);

  const hasTurnstileToken = Boolean(turnstileToken || getTurnstileResponseToken());

  if (!ready) {
    return (
      <div
        className="flex min-h-dvh items-center justify-center bg-background"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <main id="main-content" className="signin-split" aria-labelledby="signin-heading" tabIndex={-1}>
      {/* ── Left: Hero ── */}
      <div className="signin-hero">
        <div className="signin-hero-inner">
          <div className="signin-logo">
            <span className="signin-logo-text">duct</span>
            <span className="logo-mark" aria-hidden="true" />
          </div>

          <h1>Your tools have the answers.<br /><em>Duct connects them.</em></h1>

          <p className="signin-hero-sub">
            Automated intelligence across your ad platforms, analytics, and
            search data. Stop guessing what&rsquo;s working&mdash;start knowing.
          </p>

          <div className="signin-tools">
            <span className="signin-tool-pill">Google Ads</span>
            <span className="signin-tool-pill">GA4</span>
            <span className="signin-tool-pill">Search Console</span>
            <span className="signin-tool-pill">Meta Ads</span>
          </div>

          <p className="signin-trust">
            Free during beta &middot; No credit card &middot; 10 minutes to
            first insight
          </p>
        </div>
      </div>

      {/* ── Right: Sign-In Form ── */}
      <div className="signin-form-side">
        <div className="signin-form">
          <h2 id="signin-heading">Sign in to Duct</h2>
          <p className="signin-form-sub">
            Get started with your Google account
          </p>

          {requiresTurnstile && <div ref={turnstileContainerRef} className="cf-turnstile" aria-label="Security verification" />}

          <GoogleSignInButton
            onClick={handleSignIn}
            disabled={isSigningIn || (requiresTurnstile && !hasTurnstileToken)}
            isLoading={isSigningIn}
            loadingLabel={awaitingBrowser ? "Continue in your browser…" : "Signing in..."}
          />
          {awaitingBrowser && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Finish signing in with Google in your browser — this window will
              continue automatically.{" "}
              <button
                type="button"
                className="underline underline-offset-2"
                onClick={() => window.location.reload()}
              >
                Start over
              </button>
            </p>
          )}
          {requiresTurnstile && !hasTurnstileToken && (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Complete security check to continue.
            </p>
          )}
          {turnstileError && (
            <p className="mt-2 text-center text-xs text-destructive">{turnstileError}</p>
          )}

          <p className="signin-legal">
            By signing in, you agree to our{" "}
            <a href="https://getduct.ai/terms" target="_blank" rel="noopener noreferrer">
              Terms of Service
            </a>{" "}
            and{" "}
            <a href="https://getduct.ai/privacy" target="_blank" rel="noopener noreferrer">
              Privacy Policy
            </a>
          </p>
        </div>
      </div>
    </main>
  );
}
