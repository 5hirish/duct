"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { BASE } from "../../lib/api";
import { isDesktopShell, getShellInfo, openExternal } from "../../lib/shell";
import { isLocalBackendActive } from "../../lib/localBackend.js";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import FrontDoor from "@/components/onboarding/FrontDoor";
import { Checkbox } from "@/components/ui/checkbox";
import {
  POST_SIGNIN_REDIRECT_KEY,
  SIGNIN_REASON_EXPIRED,
  SIGNIN_REASON_KEY,
  authToken,
  decodeJwtPayload,
  isTokenValid,
  setAuthToken,
} from "@/lib/authFetch";
import { analytics, trackEvent, AnalyticsEvent, AnalyticsParam } from "@/lib/analytics";
import { isGuestToken } from "@/lib/guest";
import { guestLinkCode } from "@/lib/onboardingApi";
import { consumeSignInSources, peekSignInSources } from "@/lib/signInSources";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";
const DEFAULT_LANDING = "/insights/organic-growth";

/**
 * Where to go once signed in. The invite page parks its own path here before
 * sending the recipient through Google, so an emailed invitation survives the
 * OAuth round trip; authFetch parks the page a rejected session was on, so
 * signing back in returns you to it. Only same-origin paths are honoured — an
 * attacker-supplied value must never turn sign-in into an open redirect.
 */
/**
 * True when the backend refused the last session and bounced the user here.
 * Read once and cleared: without it they arrive at a login screen with no idea
 * why they left the page they were on.
 *
 * Memoised because it is destructive and effects are not: StrictMode runs the
 * mount effect twice in dev, and the second read of an already-cleared key
 * would answer "no" and silently drop the notice.
 */
let expiredSessionFlag = null;

function consumeExpiredSessionFlag() {
  if (expiredSessionFlag !== null) return expiredSessionFlag;
  try {
    const reason = sessionStorage.getItem(SIGNIN_REASON_KEY);
    sessionStorage.removeItem(SIGNIN_REASON_KEY);
    expiredSessionFlag = reason === SIGNIN_REASON_EXPIRED;
  } catch {
    expiredSessionFlag = false;
  }
  return expiredSessionFlag;
}

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
  const { resolvedTheme } = useTheme();
  const [turnstileToken, setTurnstileToken] = useState("");
  const [ready, setReady] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [awaitingBrowser, setAwaitingBrowser] = useState(false);
  // "" when fine; "outdated" or "browser" when the shell cannot carry a
  // sign-in and the user needs to be told rather than quietly stranded.
  const [shellBlocked, setShellBlocked] = useState("");
  const [turnstileError, setTurnstileError] = useState("");
  // The onboarding connector prompt armed the sign-in to also ask for Search
  // Console + Analytics (lib/signInSources.js). Shown so the extra consent
  // boxes at Google are expected, not a surprise.
  const [sourcesArmed, setSourcesArmed] = useState(false);
  // Read in an effect, not at render: it touches sessionStorage, and clearing
  // it during render would make the notice vanish on the next paint.
  const [sessionExpired, setSessionExpired] = useState(false);
  useEffect(() => setSessionExpired(consumeExpiredSessionFlag()), []);
  // Checked by default: the whole point of the box is fewer forced re-logins,
  // so someone who wants the shorter session has to opt out, not in.
  const [rememberMe, setRememberMe] = useState(true);
  // The audit entry, front and centre on this page: a website, nothing more.
  // Submitting hands off to /start, which does the actual work (mints a
  // guest, reads the site) — this page only decides where a visitor lands.
  const [startUrl, setStartUrl] = useState("");
  const [startError, setStartError] = useState("");
  const handleStartSubmit = useCallback(
    (event) => {
      event.preventDefault();
      const site = startUrl.trim();
      if (!site) {
        setStartError("Enter your website address.");
        return;
      }
      trackEvent(AnalyticsEvent.OnboardingStarted, { [AnalyticsParam.Method]: "landing" });
      router.push(`/start?url=${encodeURIComponent(site)}`);
    },
    [router, startUrl]
  );
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
            setAuthToken(token);
            analytics.identify(decodeJwtPayload(token)?.uid);
            // `new_user` is true only on the sign-in that created the account
            // (routes/signin.py). Fired here rather than wherever the token is
            // read, because it is read on every load for a week.
            if (decodeJwtPayload(token)?.new_user) {
              trackEvent(AnalyticsEvent.SignUp, { method: "google" });
            }
            router.replace(consumePostSignInRedirect());
          }
        })
        .catch(() => {});
      return;
    }

    // Already authenticated? Redirect. A guest is not: this page is where a
    // guest comes to become an account, so their token must not bounce them.
    const existing = authToken();
    if (isTokenValid(existing) && !isGuestToken(existing)) {
      router.replace(consumePostSignInRedirect());
      return;
    }

    setSourcesArmed(Boolean(peekSignInSources()));
    setReady(true);
  }, [searchParams, router]);

  // Load and render Turnstile explicitly so remounts always work.
  useEffect(() => {
    // `resolvedTheme` is undefined until next-themes mounts. Waiting for it
    // costs a tick and saves rendering the widget twice; re-rendering it is
    // not free, because it throws away a token the visitor already solved.
    if (!requiresTurnstile || !ready || !resolvedTheme) return;
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
            theme: resolvedTheme === "dark" ? "dark" : "light",
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
  }, [ready, requiresTurnstile, resolvedTheme]);

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
    setShellBlocked("");
    const params = new URLSearchParams();
    // A guest signing in keeps their work: the callback links the account it
    // creates to this guest, or merges the guest into an existing one. The
    // code travels in the URL instead of the token (lib/onboardingApi.js); a
    // code that fails to mint means an unlinked sign-in, never a blocked one.
    if (isGuestToken()) {
      try {
        params.set("link", await guestLinkCode());
      } catch {
        /* proceed unlinked */
      }
    }
    if (resolvedTurnstileToken) {
      params.set("turnstile_token", resolvedTurnstileToken);
    }
    // Consumed here, at the one point a sign-in actually starts, so a bundle
    // armed for a prompt that was abandoned never rides a later sign-in.
    const sources = consumeSignInSources();
    if (sources) params.set("sources", sources);
    if (rememberMe) params.set("remember", "1");
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
          // The shell can do browser auth but would not open one. Retrying is
          // the only useful advice; falling through is not, for the reason below.
          setShellBlocked("browser");
          setIsSigningIn(false);
          return;
        }
      }
      // No `browserAuth`. Either an old shell, or one where `get_shell_info` is
      // not reachable at all — an unregistered command makes `getShellInfo()`
      // return null, which is indistinguishable from a build that predates the
      // flag, and means the same thing either way.
      //
      // The in-window redirect below is not a fallback for this. It runs Google's
      // consent inside the embedded webview, which Google refuses outright on
      // some platforms; where it does load, the request carries no
      // `client=desktop`, so `signin.py` records the plain web flow and the
      // callback hands the session to the *web* app. The shell never receives a
      // token and the user lands on the hosted app wondering why the desktop
      // window did nothing. Diagnosing that once meant reading strings out of an
      // installed binary. Say what is wrong instead.
      setShellBlocked("outdated");
      setIsSigningIn(false);
      return;
    }
    const query = params.toString();
    window.location.href = `${BASE}/auth/signin/google/authorize${query ? `?${query}` : ""}`;
  }, [
    getTurnstileResponseToken,
    isSigningIn,
    rememberMe,
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
    <main
      id="main-content"
      className={`landing-split${sessionExpired ? " landing-split--auth-first" : ""}`}
      tabIndex={-1}
    >
      {/* ── Sign in: the returning-user path, narrow and secondary ── */}
      <div className="landing-auth">
        <div className="landing-auth-inner">
          <p className="landing-auth-kicker">Already using Duct?</p>
          <h2 id="signin-heading">Sign in</h2>
          <p className="signin-form-sub">
            {sessionExpired
              ? "Your session ended. Sign in again and we'll take you back to where you were."
              : "Continue with your Google account"}
          </p>

          {requiresTurnstile && <div ref={turnstileContainerRef} className="cf-turnstile" aria-label="Security verification" />}

          <label htmlFor="signin-remember-me" className="landing-remember">
            <Checkbox
              id="signin-remember-me"
              checked={rememberMe}
              onCheckedChange={setRememberMe}
              disabled={isSigningIn}
            />
            Keep me signed in for 30 days
          </label>

          <GoogleSignInButton
            onClick={handleSignIn}
            disabled={isSigningIn || (requiresTurnstile && !hasTurnstileToken)}
            isLoading={isSigningIn}
            loadingLabel={awaitingBrowser ? "Continue in your browser…" : "Signing in..."}
          />
          {sourcesArmed && !awaitingBrowser && (
            <p className="landing-auth-note">
              Google will also ask to share Search Console and Analytics with
              Duct &mdash; read-only, and either box can be left unticked.
            </p>
          )}
          {awaitingBrowser && (
            <p className="landing-auth-note">
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
            <p className="landing-auth-note">Complete security check to continue.</p>
          )}
          {turnstileError && (
            <p className="landing-auth-note landing-auth-note-error">{turnstileError}</p>
          )}
          {shellBlocked === "outdated" && (
            <p className="landing-auth-note landing-auth-note-error">
              This version of Duct can&rsquo;t complete sign-in. Update the app
              from{" "}
              <a
                className="underline underline-offset-2"
                href="https://getduct.ai/download"
                target="_blank"
                rel="noopener noreferrer"
              >
                getduct.ai/download
              </a>{" "}
              and try again.
            </p>
          )}
          {shellBlocked === "browser" && (
            <p className="landing-auth-note landing-auth-note-error">
              Duct couldn&rsquo;t open your browser to finish signing in. Check
              that you have a default browser set, then try again.
            </p>
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

      {/* ── The offer: an audit, no account needed — the real first impression ── */}
      <div className="landing-start">
        <FrontDoor
          url={startUrl}
          onUrlChange={(value) => {
            setStartUrl(value);
            if (startError) setStartError("");
          }}
          error={startError}
          onSubmit={handleStartSubmit}
        />
      </div>
    </main>
  );
}
