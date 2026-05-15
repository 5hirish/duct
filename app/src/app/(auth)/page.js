"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BASE } from "../../lib/api";
import GoogleSignInButton from "@/components/GoogleSignInButton";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";
const TOKEN_KEY = "duct_auth_token";

function decodeJwtPayload(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

function isTokenValid(token) {
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  if (!payload || !payload.exp) return false;
  return payload.exp * 1000 > Date.now();
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
  const [turnstileError, setTurnstileError] = useState("");
  const requiresTurnstile = Boolean(TURNSTILE_SITE_KEY);
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
            localStorage.setItem(TOKEN_KEY, token);
            router.replace("/insights");
          }
        })
        .catch(() => {});
      return;
    }

    // Already authenticated? Redirect.
    const existing = localStorage.getItem(TOKEN_KEY);
    if (isTokenValid(existing)) {
      router.replace("/insights");
      return;
    }

    setReady(true);
  }, [searchParams, router]);

  // Load and render Turnstile explicitly so remounts always work.
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !ready) return;
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
  }, [ready]);

  const handleSignIn = useCallback(() => {
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
    let url = `${BASE}/auth/signin/google/authorize`;
    if (resolvedTurnstileToken) {
      url += `?turnstile_token=${encodeURIComponent(resolvedTurnstileToken)}`;
    }
    window.location.href = url;
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

          {TURNSTILE_SITE_KEY && <div ref={turnstileContainerRef} className="cf-turnstile" aria-label="Security verification" />}

          <GoogleSignInButton
            onClick={handleSignIn}
            disabled={isSigningIn || (requiresTurnstile && !hasTurnstileToken)}
            isLoading={isSigningIn}
          />
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
