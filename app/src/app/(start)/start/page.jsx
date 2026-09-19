"use client";

// Onboarding: the audit is the onboarding.
//
//   I    Your site   one field → the root page read back in a second, the
//                    crawl continuing in the background while the user moves on
//   II   Your model  a key verified by spending it, or the ChatGPT plan they
//                    already pay for — or skipped
//   III  The audit   the session, inside the real app, crawl already done
//
// The first submit mints a guest (lib/guest.js); there is no "start" click
// that does nothing visible. Design in docs/engineering/2026-09-08-smart-onboarding-plan.md.
// The water in the aqueduct strip is the state: it reaches an arch when that
// step's data does.

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowRight, Check, ClipboardCheck, FolderOpen, Globe, Sparkles } from "lucide-react";
import { plural } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import MosaicPanel, { MOSAIC } from "@/components/MosaicPanel";
import { AnalyticsEvent, AnalyticsParam, trackEvent } from "@/lib/analytics";
import { DEFAULT_AUDIT_TEMPLATE_ID, ReportMode } from "@/lib/audit";
import { loadPreferences } from "@/lib/userPreferences";
import { modelPayload } from "@/lib/modelTiers";
import { PROJECT_EXISTING, PROJECT_NEW, openAuditSession } from "@/lib/auditSession";
import { hydrateProjectsFromBackend, projectsForSite } from "@/lib/projects";
import { ensureGuest, isSignedInUser } from "../../../lib/guest";
import { prefetchSite, prefetchStatus } from "../../../lib/onboardingApi";
import { applyProjectDraft } from "../../../lib/projectDraft";
import Aqueduct, { STEP_ACTIVE, STEP_DONE, STEP_DRY, STEP_TODO } from "../../../components/onboarding/Aqueduct";
import ProviderStep from "../../../components/onboarding/ProviderStep";
import TesseraBurst from "../../../components/onboarding/TesseraBurst";

const STEP = Object.freeze({ URL: 1, PROVIDER: 2 });
const POLL_MS = 2000;
// Long enough for the water to reach the arch before the page changes.
const LEAVE_AFTER_VERIFY_MS = 1100;
const LEAVE_AFTER_SKIP_MS = 600;

function normaliseUrl(raw) {
  const trimmed = (raw || "").trim();
  if (!trimmed) return "";
  return /^[a-z]+:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function Eyebrow({ children }) {
  return <p className="start-eyebrow">{children}</p>;
}

export default function StartPage() {
  return (
    <Suspense fallback={null}>
      <StartPageContent />
    </Suspense>
  );
}

function StartPageContent() {
  const { t } = useLingui();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(STEP.URL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [crawl, setCrawl] = useState(null); // the prefetch status
  // The newest draft the crawl has produced, held rather than written: which
  // project it belongs to is the user's call when they already have one for
  // this site, and a merge cannot be taken back.
  const [draft, setDraft] = useState(null);
  // { mode: "new" } | { mode: "existing", project } | { mode: "ambiguous", options }
  const [target, setTarget] = useState({ mode: PROJECT_NEW });
  const [project, setProject] = useState(null);
  const [verified, setVerified] = useState(null); // provider verdict, or { skipped: true }
  const [signedIn, setSignedIn] = useState(false);
  const pollRef = useRef(null);
  // StrictMode double-invokes mount effects in dev; without this a `?url=`
  // hand-off from the landing page would mint two guests and prefetch twice.
  const autoStartedRef = useRef(false);

  useEffect(() => {
    setSignedIn(isSignedInUser());
  }, []);

  // The landing page's own URL field hands off here instead of duplicating
  // the guest+crawl logic — prefill and continue exactly as if the visitor
  // had typed it on this page.
  useEffect(() => {
    const prefill = searchParams.get("url");
    if (!prefill || autoStartedRef.current) return;
    autoStartedRef.current = true;
    setUrl(prefill);
    readSite(undefined, prefill);
    // Intentionally run once on mount, off the raw param — not `readSite`,
    // which is recreated whenever `url` changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // ── Background crawl: keep the status fresh until it settles ───────────
  useEffect(() => {
    clearInterval(pollRef.current);
    if (!crawl?.crawl_id || crawl.state !== "running") return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const next = await prefetchStatus(crawl.crawl_id);
        setCrawl(next);
        if (next.draft) setDraft(next.draft);
        if (next.state !== "running") {
          clearInterval(pollRef.current);
          // The full crawl knows more than the root page did — pillars,
          // channels, a better name. Same merge, same rules. Only once the
          // project is settled; before that the draft is just held.
          if (next.draft && project?.id) setProject(applyProjectDraft(next.draft, { projectId: project.id }));
        }
      } catch {
        clearInterval(pollRef.current);
      }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [crawl?.crawl_id, crawl?.state, project?.id]);

  // ── Step I: read the site ──────────────────────────────────────────────
  // `rawSite` lets the landing page's own URL field hand off straight into
  // this step (via `?url=`, read below) without waiting on a state update —
  // the manual submit path still just reads `url`.
  const readSite = useCallback(
    async (event, rawSite) => {
      event?.preventDefault();
      const site = normaliseUrl(rawSite ?? url);
      if (!site) {
        setError(t`Enter your website address.`);
        return;
      }
      setBusy(true);
      setError("");
      try {
        // The first thing the audit makes needs an owner; a guest is one.
        const { guest, created } = await ensureGuest();
        trackEvent(AnalyticsEvent.OnboardingStarted, {
          [AnalyticsParam.Method]: guest ? (created ? "guest_new" : "guest_returning") : "signed_in",
        });
        let status;
        try {
          status = await prefetchSite(site);
        } catch (err) {
          // A token the browser trusts and the backend does not: mint a new
          // guest and try once more before telling the user anything.
          if (err?.status !== 401) throw err;
          await ensureGuest({ fresh: true });
          status = await prefetchSite(site);
        }
        setCrawl(status);
        setDraft(status.draft);
        setTarget(await resolveTarget(status.site?.url || site));
        trackEvent(AnalyticsEvent.OnboardingSiteFound, {
          [AnalyticsParam.Reason]: status.site?.blocked ? "blocked" : status.site?.is_spa_suspected ? "spa" : "ok",
        });
      } catch (err) {
        trackEvent(AnalyticsEvent.OnboardingSiteFailed, { [AnalyticsParam.Reason]: err?.reason || String(err?.status || "error") });
        setError(err?.message || t`Couldn't read that site.`);
      } finally {
        setBusy(false);
      }
    },
    [t, url],
  );

  function tryAnother() {
    clearInterval(pollRef.current);
    setCrawl(null);
    setDraft(null);
    setTarget({ mode: PROJECT_NEW });
    setError("");
  }

  /**
   * Which project this site's audit should write to.
   *
   * A guest has no projects, so the question only arises for someone signed
   * in — and for them it matters a great deal: the draft rewrites a project's
   * name, pitch, industry, personas and competitors, and before this it went
   * into whichever project happened to be active. Hydrating first is what
   * makes the answer right on a machine they have not used before, where the
   * local store is empty and every site would look new.
   */
  async function resolveTarget(siteUrl) {
    if (!isSignedInUser()) return { mode: PROJECT_NEW };
    try {
      await hydrateProjectsFromBackend();
    } catch {
      /* offline: match against whatever this browser already knows */
    }
    const matches = projectsForSite(siteUrl);
    if (matches.length === 1) return { mode: PROJECT_EXISTING, project: matches[0] };
    if (matches.length > 1) return { mode: "ambiguous", options: matches };
    return { mode: PROJECT_NEW };
  }

  /**
   * The user has settled which project this is. Write the draft, then move on.
   *
   * This is the first write of the whole flow — everything before it is a
   * read of their site — so it is also the last point at which "not that
   * project" costs nothing.
   */
  function commitProject({ projectId = null, createNew = false } = {}) {
    if (!draft) return;
    setProject(applyProjectDraft(draft, { projectId, createNew }));
    setStep(STEP.PROVIDER);
  }

  // What the run turned out to be, once committed: adding to a project that
  // already existed, or filling a new one.
  const committedMode = project && target.mode === PROJECT_EXISTING && project.id === target.project?.id
    ? PROJECT_EXISTING
    : PROJECT_NEW;

  // ── Step II → the session ──────────────────────────────────────────────
  const startAudit = useCallback(
    ({ skipped = false } = {}) => {
      if (!crawl?.site?.url) return;
      const params = {
        url: crawl.site.url,
        project_id: project?.id || null,
        business_context: {},
        remember: true,
        user_preferences: loadPreferences(),
        report_mode: ReportMode.TEMPLATE,
        template_id: DEFAULT_AUDIT_TEMPLATE_ID,
        crawl_id: crawl.crawl_id,
        draft_project: true,
        ...(modelPayload()?.tiers ? { tiers: modelPayload().tiers } : {}),
      };
      // Client-only, never sent: the card to show first, and whether this run
      // is adding to a project that already existed — which is the thing the
      // workspace has to tell the user about while they read the report.
      const sessionId = openAuditSession(params, {
        pendingProvider: skipped,
        projectMode: committedMode,
        projectName: project?.name || "",
      });
      trackEvent(AnalyticsEvent.OnboardingAuditStarted, { [AnalyticsParam.Ok]: skipped ? "false" : "true" });
      router.push(`/audit/seo/${sessionId}`);
    },
    [committedMode, crawl, project, router],
  );

  function onVerified(verdict) {
    trackEvent(AnalyticsEvent.ProviderVerified, {
      [AnalyticsParam.Provider]: verdict.subscription ? "chatgpt" : verdict.providerId,
      [AnalyticsParam.Ok]: verdict.ok === false ? "false" : "true",
      [AnalyticsParam.Code]: verdict.code || "",
    });
    if (verdict.ok === false) return;
    setVerified(verdict);
    setTimeout(() => startAudit(), LEAVE_AFTER_VERIFY_MS);
  }

  function onSkip() {
    trackEvent(AnalyticsEvent.ProviderSkipped, {});
    setVerified({ skipped: true });
    setTimeout(() => startAudit({ skipped: true }), LEAVE_AFTER_SKIP_MS);
  }

  // ── The aqueduct's reading of all that ─────────────────────────────────
  const site = crawl?.site;
  const siteFound = Boolean(site);
  // Plain identifiers for the catalogue: a member expression inside <Trans>
  // becomes an anonymous {0} the translator cannot place.
  const httpStatus = site?.http_status;
  const targetProjectName = target.project?.name;
  const crawlDone = crawl?.state === "done";
  const water = verified?.skipped
    ? 1.9
    : verified
      ? 3
      : siteFound
        ? crawlDone
          ? 1.6
          : 1.25
        : busy
          ? 0.35
          : 0;
  const steps = [
    { key: "site", label: t`Your site`, state: siteFound ? STEP_DONE : STEP_ACTIVE },
    {
      key: "model",
      label: t`Your model`,
      state: verified?.skipped ? STEP_DRY : verified ? STEP_DONE : step === STEP.PROVIDER ? STEP_ACTIVE : STEP_TODO,
    },
    { key: "audit", label: t`The audit`, state: verified && !verified.skipped ? STEP_ACTIVE : STEP_TODO },
  ];

  // Before the commit there is no project to read a name from, so the draft
  // itself supplies it — the same value the merge would have written.
  const siteName =
    project?.company?.name || draft?.fields?.name?.value || site?.title || site?.url || "";
  const pages = crawl?.pages ?? 0;
  const pagesLine =
    crawl?.state === "running"
      ? t`Reading the rest of the site…`
      : crawl?.state === "done"
        ? plural(pages, { one: "Read # page", other: "Read # pages" })
        : crawl?.state === "failed"
          ? t`Could only read the front page — the audit will use that`
          : "";

  return (
    <div className="start-frame">
      {/* ── The threshold ─────────────────────────────────────────────── */}
      <aside className="start-threshold">
        <div className="start-threshold-inner">
          <MosaicPanel name={MOSAIC.salve} size={280} className="start-mosaic" />
          <h2 className="start-headline">
            <Trans>Duct checks a number before it trusts it.</Trans>
          </h2>
          <p className="start-lede">
            <Trans>
              Start with your website. Duct reads it, audits it, and builds your project from what it
              finds. An account can wait until there is something worth keeping.
            </Trans>
          </p>
          <ul className="start-promises" aria-label={t`What happens next`}>
            <li>
              <Globe className="size-4" aria-hidden />
              <span><Trans>Reads what a search engine sees</Trans></span>
            </li>
            <li>
              <Sparkles className="size-4" aria-hidden />
              <span><Trans>Drafts your project from what it finds</Trans></span>
            </li>
            <li>
              <ClipboardCheck className="size-4" aria-hidden />
              <span><Trans>Audits it in about three minutes</Trans></span>
            </li>
          </ul>
        </div>
        <Aqueduct steps={steps} water={water} className="start-aqueduct" />
      </aside>

      {/* ── The stage ─────────────────────────────────────────────────── */}
      <section className="start-stage">
        <div className="start-stage-inner">
          {step === STEP.URL && !siteFound && (
            <form onSubmit={readSite} className="grid gap-5">
              <div>
                <Eyebrow><Trans>Step I of III · Your site</Trans></Eyebrow>
                <h1 className="start-title"><Trans>Where does the data come from?</Trans></h1>
                <p className="start-sub">
                  <Trans>
                    Your website is enough to start. Duct reads it now and keeps reading while you set up the rest.
                  </Trans>
                </p>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="site-url"><Trans>Your website</Trans></Label>
                <div className="start-url">
                  <Globe className="start-url-icon size-4" aria-hidden />
                  <Input
                    id="site-url"
                    inputMode="url"
                    autoComplete="url"
                    autoFocus
                    placeholder={t`acme.com`}
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? "site-url-error" : "site-url-hint"}
                    className="start-url-input"
                  />
                </div>
                {error ? (
                  <p id="site-url-error" className="text-sm text-destructive" role="alert">
                    {error}
                  </p>
                ) : (
                  <p id="site-url-hint" className="text-xs text-muted-foreground">
                    <Trans>No account needed. Nothing is sent anywhere but your own model provider.</Trans>
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" size="lg" disabled={busy}>
                  {busy ? <Spinner className="size-4" /> : <ArrowRight className="size-4" aria-hidden />}
                  {busy ? <Trans>Reading…</Trans> : <Trans>Read my site</Trans>}
                </Button>
                {signedIn ? (
                  <Button asChild variant="ghost" size="lg">
                    <Link href="/insights/organic-growth">
                      <Trans>Open Duct</Trans>
                    </Link>
                  </Button>
                ) : (
                  <Link href="/" className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
                    <Trans>I have an account</Trans>
                  </Link>
                )}
              </div>
            </form>
          )}

          {step === STEP.URL && siteFound && (
            <div className="grid gap-5">
              <div>
                <Eyebrow><Trans>Step I of III · Your site</Trans></Eyebrow>
                <h1 className="start-title"><Trans>Found it.</Trans></h1>
              </div>

              <div className="start-site">
                <div className="start-site-icon" aria-hidden="true">
                  {site.favicon ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={site.favicon} alt="" />
                  ) : (
                    <Globe className="size-5 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold tracking-tight">{siteName}</p>
                  {site.description && <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{site.description}</p>}
                  {pagesLine && (
                    <p className="start-site-pages" role="status">
                      {crawl.state === "running" ? (
                        <Spinner className="size-3 text-muted-foreground" />
                      ) : (
                        <Check className="size-3.5 text-success" aria-hidden />
                      )}
                      <span>{pagesLine}</span>
                    </p>
                  )}
                </div>
              </div>

              {site.blocked && (
                <p className="start-warn">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                  <span>
                    <Trans>
                      The site answered <code>{httpStatus}</code> to our crawler, so this audit will be
                      thin — it may sit behind a bot wall.
                    </Trans>
                  </span>
                </p>
              )}
              {!site.blocked && site.is_spa_suspected && (
                <p className="start-warn">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                  <span>
                    <Trans>
                      This looks like a client-rendered app, so the crawler may see very little — the same
                      as a search engine.
                    </Trans>
                  </span>
                </p>
              )}

              {target.mode === PROJECT_EXISTING && (
                <div className="start-project" role="status">
                  <FolderOpen className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0">
                    <p>
                      <Trans>
                        This will update <strong>{targetProjectName}</strong>, the project you already
                        have for this site. Anything you filled in yourself stays as it is.
                      </Trans>
                    </p>
                    <button type="button" className="start-project-alt" onClick={() => commitProject({ createNew: true })}>
                      <Trans>Keep it separate — start a new project instead</Trans>
                    </button>
                  </div>
                </div>
              )}

              {target.mode === "ambiguous" && (
                <div className="start-project" role="status">
                  <FolderOpen className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0">
                    <p>
                      <Trans>You have more than one project for this site. Which should this audit update?</Trans>
                    </p>
                    <div className="start-project-picks">
                      {target.options.map((option) => (
                        <Button
                          key={option.id}
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => commitProject({ projectId: option.id })}
                        >
                          {option.name}
                        </Button>
                      ))}
                      <button type="button" className="start-project-alt" onClick={() => commitProject({ createNew: true })}>
                        <Trans>None of these — start a new one</Trans>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {/* An unanswered "which project?" has no continue — but a wrong
                    site always has a way back, or the only exit is a reload. */}
                {target.mode !== "ambiguous" && (
                  <Button
                    type="button"
                    size="lg"
                    onClick={() =>
                      commitProject({ projectId: target.mode === PROJECT_EXISTING ? target.project.id : null })
                    }
                  >
                    <Trans>That&apos;s us — continue</Trans> <ArrowRight className="size-4" aria-hidden />
                  </Button>
                )}
                <Button type="button" variant="ghost" size="lg" onClick={tryAnother}>
                  <Trans>Not it — try another</Trans>
                </Button>
              </div>
            </div>
          )}

          {step === STEP.PROVIDER && (
            <div className="relative grid gap-5">
              {verified && !verified.skipped && <TesseraBurst />}
              <div>
                <Eyebrow><Trans>Step II of III · Your model</Trans></Eyebrow>
                <h1 className="start-title"><Trans>Connect a model</Trans></h1>
                <p className="start-sub">
                  <Trans>
                    Duct runs on your own account, so an audit costs you cents — and Duct never sees your data twice.
                  </Trans>
                </p>
                {pagesLine && (
                  <p className="start-site-pages" role="status">
                    {crawl.state === "running" ? (
                      <Spinner className="size-3 text-muted-foreground" />
                    ) : (
                      <Check className="size-3.5 text-success" aria-hidden />
                    )}
                    <span>{pagesLine}</span>
                  </p>
                )}
              </div>
              <ProviderStep onVerified={onVerified} onSkip={onSkip} />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
