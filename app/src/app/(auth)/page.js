"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BASE } from "../../lib/api";
import { Button } from "@/components/ui/button";

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

/* Google "G" logo as inline SVG */
function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
  );
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

  useEffect(() => {
    // Handle token from OAuth callback
    const token = searchParams.get("token");
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      window.history.replaceState({}, "", "/");
      router.replace("/reports");
      return;
    }

    // Already authenticated? Redirect.
    const existing = localStorage.getItem(TOKEN_KEY);
    if (isTokenValid(existing)) {
      router.replace("/reports");
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
        if (turnstileWidgetIdRef.current) {
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
      if (window.turnstile && turnstileWidgetIdRef.current) {
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
    if (requiresTurnstile && !turnstileToken) {
      return;
    }
    setIsSigningIn(true);
    let url = `${BASE}/auth/signin/google/authorize`;
    if (turnstileToken) {
      url += `?turnstile_token=${encodeURIComponent(turnstileToken)}`;
    }
    window.location.href = url;
  }, [isSigningIn, requiresTurnstile, turnstileToken]);

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

          <Button
            type="button"
            variant="outline"
            size="lg"
            className="h-12 w-full justify-center gap-3 rounded-4xl border-border bg-card font-medium shadow-sm hover:bg-muted/60"
            onClick={handleSignIn}
            disabled={isSigningIn || (requiresTurnstile && !turnstileToken)}
          >
            <GoogleLogo />
            {isSigningIn ? "Signing in..." : "Sign in with Google"}
          </Button>
          {requiresTurnstile && !turnstileToken && (
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
