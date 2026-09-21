"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { Trans, useLingui } from "@lingui/react/macro";
import { BASE } from "../../lib/api";
import { isDesktopShell, getShellInfo, openExternal } from "../../lib/shell";
import { isLocalBackendActive } from "../../lib/localBackend.js";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import FrontDoor from "@/components/onboarding/FrontDoor";
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
      <p className="text-sm text-muted-foreground">
        <Trans>Loading…</Trans>
      </p>
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
  const { t } = useLingui();
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
  // A flag rather than the sentence: the sentence is rendered through the
  // catalogue below, and keeping `t` out of the widget effect means a language
  // switch does not re-render Turnstile and discard a token already solved.
  const [turnstileFailed, setTurnstileFailed] = useState(false);
  // A challenge the visitor has been given and has not solved yet. Distinct
  // from "failed": one says finish the box above, the other says there is no
  // box, and a content blocker produces the second without an error-callback.
  const [turnstilePending, setTurnstilePending] = useState(false);
  // The onboarding connector prompt armed the sign-in to also ask for Search
  // Console + Analytics (lib/signInSources.js). Shown so the extra consent
  // boxes at Google are expected, not a surprise.
  const [sourcesArmed, setSourcesArmed] = useState(false);
  // Read in an effect, not at render: it touches sessionStorage, and clearing
  // it during render would make the notice vanish on the next paint.
  const [sessionExpired, setSessionExpired] = useState(false);
  useEffect(() => setSessionExpired(consumeExpiredSessionFlag()), []);
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
        setStartError(t`Enter your website address.`);
        return;
      }
      trackEvent(AnalyticsEvent.OnboardingStarted, { [AnalyticsParam.Method]: "landing" });
      router.push(`/start?url=${encodeURIComponent(site)}`);
    },
    [router, startUrl, t]
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
        setTurnstileFailed(false);
        setTurnstileToken("");
        turnstileWidgetIdRef.current = window.turnstile.render(
          turnstileContainerRef.current,
          {
            sitekey: TURNSTILE_SITE_KEY,
            callback: (token) => {
              setTurnstileToken(token);
              setTurnstileFailed(false);
              setTurnstilePending(false);
            },
            "expired-callback": () => setTurnstileToken(""),
            "error-callback": () => {
              setTurnstileToken("");
              setTurnstileFailed(true);
            },
            theme: resolvedTheme === "dark" ? "dark" : "light",
            // Not "always". The overwhelming majority of visitors pass
            // silently, and rendering a checkbox for all of them puts a
            // security ritual above the one button on the page — plus the
            // space it reserves shifts that button under a cursor already
            // moving towards it.
            appearance: "interaction-only",
          }
        );
      } catch {
        setTurnstileFailed(true);
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
        setTurnstileFailed(true);
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

  /**
   * Hold the click until the bot check has an answer, rather than greying out
   * the button until it does. A disabled sign-in button on first paint is
   * indistinguishable from a broken one, and the check usually resolves inside
   * a second — so the wait belongs behind the press, where it reads as the
   * sign-in starting, not as the page refusing.
   */
  const awaitTurnstileToken = useCallback(
    async (timeoutMs = 8000) => {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        const token = getTurnstileResponseToken();
        if (token) return token;
        if (Date.now() >= deadline) return "";
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
    },
    [getTurnstileResponseToken]
  );

  const handleSignIn = useCallback(async () => {
    if (isSigningIn) return;
    if (!BASE) {
      // This page already has a place to say a sign-in cannot proceed, and it
      // is under the button the user just pressed. A `window.alert` put the
      // one misconfiguration message the operator needs into an OS modal that
      // reads like a browser warning and vanishes on OK.
      setShellBlocked("unconfigured");
      return;
    }
    setIsSigningIn(true);
    setShellBlocked("");
    setTurnstilePending(false);

    let resolvedTurnstileToken = turnstileToken || getTurnstileResponseToken();
    if (requiresTurnstile && !resolvedTurnstileToken) {
      resolvedTurnstileToken = await awaitTurnstileToken();
      if (!resolvedTurnstileToken) {
        // These are not the same failure and must not share a sentence. A
        // widget that rendered and has no token is a challenge still to solve;
        // one that never rendered was blocked or never loaded, and "finish the
        // check above" points at nothing — which is exactly what a content
        // blocker produces, silently and without an `error-callback`.
        if (turnstileWidgetIdRef.current === null) setTurnstileFailed(true);
        else setTurnstilePending(true);
        setIsSigningIn(false);
        return;
      }
    }
    if (resolvedTurnstileToken && resolvedTurnstileToken !== turnstileToken) {
      setTurnstileToken(resolvedTurnstileToken);
    }
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
    // Always. This was a pre-ticked "Keep me signed in for 30 days" checkbox
    // sitting above the button: a decision demanded before the action it
    // modifies, whose only reachable outcome was a user shortening their own
    // session by mistake. Signing out is the answer to a shared computer.
    params.set("remember", "1");
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
    awaitTurnstileToken,
    getTurnstileResponseToken,
    isSigningIn,
    requiresTurnstile,
    turnstileToken,
  ]);

  if (!ready) {
    return (
      <div
        className="flex min-h-dvh items-center justify-center bg-background"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <p className="text-sm text-muted-foreground">
          <Trans>Loading…</Trans>
        </p>
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
          {/* One line, not three. This was "Already using Duct?" over "Sign in"
              over "Continue with your Google account": a kicker, a heading and
              a sub-line all introducing a single button that says what it does
              on its face. The sub-line earns its place only when it carries
              something the button cannot — why you are back here. */}
          <h2 id="signin-heading">
            <Trans>Sign in</Trans>
          </h2>
          {sessionExpired && (
            <p className="signin-form-sub">
              <Trans>Your session ended. Sign in again and we&rsquo;ll take you back to where you were.</Trans>
            </p>
          )}

          {requiresTurnstile && <div ref={turnstileContainerRef} className="cf-turnstile" aria-label={t`Security verification`} />}

          <GoogleSignInButton
            onClick={handleSignIn}
            disabled={isSigningIn}
            isLoading={isSigningIn}
            loadingLabel={awaitingBrowser ? t`Continue in your browser…` : t`Signing in...`}
          />

          {signInNotice({
            shellBlocked,
            turnstileFailed,
            turnstilePending,
            awaitingBrowser,
            sourcesArmed,
          })}

          <p className="signin-legal">
            <Trans>
              By continuing you agree to the{" "}
              <a href="https://getduct.ai/terms" target="_blank" rel="noopener noreferrer">
                Terms
              </a>{" "}
              and{" "}
              <a href="https://getduct.ai/privacy" target="_blank" rel="noopener noreferrer">
                Privacy Policy
              </a>
              .
            </Trans>
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

/**
 * The one thing worth saying under the button, in the order it matters: a
 * shell that cannot sign in at all, then a bot check in the way, then a flow
 * already running elsewhere, then the extra consent boxes to expect.
 *
 * One slot, never a stack. These were five sibling conditionals, and a panel
 * that can sprout five paragraphs under its only button is how a login screen
 * grows back into a wall of text.
 */
function signInNotice({
  shellBlocked,
  turnstileFailed,
  turnstilePending,
  awaitingBrowser,
  sourcesArmed,
}) {
  const error = (node) => <p className="landing-auth-note landing-auth-note-error">{node}</p>;

  if (shellBlocked === "outdated") {
    return error(
      <Trans>
        This version of Duct can&rsquo;t complete sign-in. Update the app from{" "}
        <a
          className="underline underline-offset-2"
          href="https://getduct.ai/download"
          target="_blank"
          rel="noopener noreferrer"
        >
          getduct.ai/download
        </a>{" "}
        and try again.
      </Trans>
    );
  }
  if (shellBlocked === "unconfigured") {
    return error(
      <Trans>
        Sign-in is unavailable on this deployment: no API endpoint is configured.
        If this is your install, set <code>NEXT_PUBLIC_API_BASE</code> and redeploy.
      </Trans>
    );
  }
  if (shellBlocked === "browser") {
    return error(
      <Trans>
        Duct couldn&rsquo;t open your browser to finish signing in. Check that you
        have a default browser set, then try again.
      </Trans>
    );
  }
  if (turnstileFailed) {
    return error(<Trans>Security check failed to load. Refresh and try again.</Trans>);
  }
  if (turnstilePending) {
    return error(<Trans>Finish the security check above, then try again.</Trans>);
  }
  if (awaitingBrowser) {
    return (
      <p className="landing-auth-note">
        <Trans>
          Finish signing in with Google in your browser — this window will continue
          automatically.
        </Trans>{" "}
        <button
          type="button"
          className="underline underline-offset-2"
          onClick={() => window.location.reload()}
        >
          <Trans>Start over</Trans>
        </button>
      </p>
    );
  }
  if (sourcesArmed) {
    return (
      <p className="landing-auth-note">
        <Trans>
          Google will also ask to share Search Console and Analytics with Duct
          &mdash; read-only, and either box can be left unticked.
        </Trans>
      </p>
    );
  }
  return null;
}
