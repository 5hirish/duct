"use client";

// Step 2 of onboarding: connect a model, on the user's own account.
//
// Two paths. "Continue with ChatGPT" (desktop only) runs on the plan the user
// already pays for — the shell signs them in and the token rides as the
// OpenAI credential (lib/chatgpt.js). "Use an API key" is the choice-card
// list beneath it, OpenAI first.
//
// Either way the credential is verified by spending it — one tiny completion
// — because the common failure on a fresh account is not a wrong key but an
// unfunded one, and the person is about to wait three minutes for an audit
// that would end in that error. Every failure code maps to something they
// can act on, with the vendor's page linked; "try again" is the wrong advice
// for most of them.
//
// Skip is a first-class exit, not a dead end: the session opens with the
// project already drafted and a "connect a model to start" card where the
// first turn would be.

import { useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, Eye, EyeOff, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { LOGOS } from "@/components/connections/logos";
import { cn } from "@/lib/utils";
import { verifyProvider } from "../../lib/onboardingApi";
import { PROVIDERS, getProviderKey, setProviderKey } from "../../lib/providerKeys";
import { rememberProviderKey } from "../../lib/providerKeysRemote";
import { fetchProviderStatus } from "../../lib/modelTiers";
import { chatgptAuthAvailable, chatgptLogin, chatgptLoginCancel, chatgptStatus, isChatgptCancelled } from "../../lib/chatgpt";
import { isDesktopShell } from "../../lib/shell";
import { planLabel } from "../../lib/chatgpt";

const RECOMMENDED_ID = "openai";
const OPENAI_STATUS_ID = "openai";

// The recommended provider leads the list; the rest keep the settings
// page's order so the two surfaces still read as one catalogue.
const CHOICES = [...PROVIDERS].sort((a, b) => (a.id === RECOMMENDED_ID ? -1 : b.id === RECOMMENDED_ID ? 1 : 0));

// One line per provider, in the user's terms — what it runs and what it costs
// them. `PROVIDERS[].description` talks about engines, which is the settings
// page's concern, not a first-run one.
const BLURBS = {
  openai: "GPT-5.6 · about a cent per audit",
  anthropic: "Claude · a few cents per audit",
  gemini: "Gemini · a free tier covers a first audit",
  openrouter: "One key, hundreds of models",
  xai: "Grok · a few cents per audit",
};

// Billing pages, because `no_billing` is the failure that needs one.
const BILLING_URLS = {
  openai: "https://platform.openai.com/settings/organization/billing/overview",
  anthropic: "https://console.anthropic.com/settings/billing",
  gemini: "https://aistudio.google.com/app/apikey",
  openrouter: "https://openrouter.ai/settings/credits",
  xai: "https://console.x.ai",
};

// One sentence of what happened and one of what to do, per verify code.
const FIXES = {
  invalid_key: {
    title: "That key was rejected",
    body: "Keys start with the prefix shown in the field. Copy it again from the console — most consoles show a key only once.",
    link: "console",
  },
  no_billing: {
    title: "The key works, but the account has no credit",
    body: "New accounts start at $0. Add a small amount on the billing page — an audit costs cents — then verify again.",
    link: "billing",
  },
  model_access: {
    title: "This account can't use that model yet",
    body: "Some accounts need verification or a higher usage tier first. Try another provider, or come back once the account is verified.",
    link: "console",
  },
  rate_limited: {
    title: "The provider is rate-limiting right now",
    body: "Nothing is wrong with the key. Give it a moment and verify again.",
  },
  unreachable: {
    title: "Can't reach the provider",
    body: "Check the connection. Behind a corporate proxy, Duct respects HTTPS_PROXY.",
  },
  missing_key: {
    title: "Paste a key first",
    body: "",
  },
  subscription_quota: {
    title: "Your ChatGPT plan's window is used up",
    body: "Plus and Pro meter GPT usage in five-hour windows. Wait for it to reset, or use an API key to keep going.",
  },
  subscription_revoked: {
    title: "The ChatGPT sign-in has lapsed",
    body: "You signed out of ChatGPT or removed Duct from it. Sign in again and Duct picks up where it left off.",
    relogin: true,
  },
  subscription_blocked: {
    title: "ChatGPT sign-in isn't available for this account right now",
    body: "OpenAI has changed what third-party apps may do with this plan. An API key works regardless.",
  },
  unknown: {
    title: "The provider returned something Duct didn't expect",
    body: "The exact message is below. Try again, or use a different provider.",
  },
};

function ProviderMark({ id }) {
  return (
    <span className="start-choice-mark" aria-hidden="true">
      {LOGOS[id]}
    </span>
  );
}

export default function ProviderStep({ onVerified, onSkip, className }) {
  const [providerId, setProviderId] = useState(RECOMMENDED_ID);
  const [value, setValue] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { ok, code, model, detail, latency_ms }
  const [remember, setRemember] = useState(true);
  // The ChatGPT path: null until the shell and the backend have both answered.
  const [chatgpt, setChatgpt] = useState(null); // { status } | null
  const [chatgptBusy, setChatgptBusy] = useState(false);
  const desktop = isDesktopShell();

  const provider = useMemo(() => PROVIDERS.find((p) => p.id === providerId) || PROVIDERS[0], [providerId]);

  // Offered only when the shell can run the sign-in AND the backend allows
  // the path. An older shell has no command; a backend with the switch off
  // has no reason to let the button exist.
  useEffect(() => {
    let cancelled = false;
    chatgptAuthAvailable().then(async (available) => {
      if (!available || cancelled) return;
      const [status, providers] = await Promise.all([chatgptStatus(), fetchProviderStatus()]);
      if (cancelled || !providers.chatgptAuthEnabled) return;
      setChatgpt({ status });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // A key already in this browser (or the keychain) pre-fills, so someone who
  // came back does not paste it twice.
  useEffect(() => {
    let cancelled = false;
    getProviderKey(provider.id).then((existing) => {
      if (!cancelled) setValue(existing || "");
    });
    setResult(null);
    return () => {
      cancelled = true;
    };
  }, [provider.id]);

  function report(verdict, extra) {
    setResult(verdict);
    onVerified?.({
      providerId: extra.providerId,
      statusId: extra.statusId,
      model: verdict.model,
      latencyMs: verdict.latency_ms,
      ok: verdict.ok !== false,
      code: verdict.ok ? "" : verdict.code,
      ...extra,
    });
  }

  async function verify() {
    const trimmed = value.trim();
    if (!trimmed) {
      setResult({ ok: false, code: "missing_key" });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      await setProviderKey(provider.id, trimmed);
      const verdict = await verifyProvider(provider.statusId);
      if (verdict.ok && remember && !desktop) {
        // A guest is a real user, so remembering works before sign-in; on
        // the desktop the keychain already has it and the server copy is
        // not offered.
        try {
          await rememberProviderKey(provider.statusId, trimmed);
        } catch {
          /* the session copy still funds this run */
        }
      }
      report(verdict, { providerId: provider.id, statusId: provider.statusId });
    } catch (err) {
      setResult({ ok: false, code: "unreachable", detail: err?.message || "" });
    } finally {
      setBusy(false);
    }
  }

  // Sign in (if needed), then verify exactly as a key is verified: the
  // access token is already in the OpenAI header by the time the call goes
  // out (lib/providerKeys.js), so the backend sees a credential, not a path.
  async function continueWithChatgpt() {
    setChatgptBusy(true);
    setResult(null);
    try {
      let status = chatgpt?.status;
      if (!status?.connected) {
        status = await chatgptLogin();
        setChatgpt({ status });
      }
      // A pasted key would win over the sign-in; the user just chose the plan.
      await setProviderKey(RECOMMENDED_ID, "");
      setValue("");
      const verdict = await verifyProvider(OPENAI_STATUS_ID);
      report(verdict, { providerId: RECOMMENDED_ID, statusId: OPENAI_STATUS_ID, subscription: true });
    } catch (err) {
      // Cancelled is the user's own Cancel below, not a failure to explain.
      if (!isChatgptCancelled(err)) {
        setResult({ ok: false, code: "unreachable", detail: String(err?.message || err) });
      }
    } finally {
      setChatgptBusy(false);
    }
  }

  const fix = result && !result.ok ? FIXES[result.code] || FIXES.unknown : null;
  const fixHref = fix?.link === "billing" ? BILLING_URLS[provider.id] : fix?.link === "console" ? provider.consoleUrl : "";
  const connectedPlan = chatgpt?.status?.connected ? chatgpt.status : null;
  const anyBusy = busy || chatgptBusy;

  return (
    <div className={cn("grid gap-5", className)}>
      {chatgpt && (
        <div className="start-plan">
          <div className="start-plan-text">
            <p className="text-sm font-semibold">
              <Sparkles className="mr-1.5 inline size-4 text-primary" aria-hidden />
              {connectedPlan ? `Signed in to ${planLabel(connectedPlan.plan_type)}` : "Use the plan you already pay for"}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {connectedPlan
                ? `${connectedPlan.email || "Your ChatGPT account"} — no API key, no extra bill.`
                : "Runs on your ChatGPT Plus or Pro plan. Duct never sees your ChatGPT password or history."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="lg" onClick={continueWithChatgpt} disabled={anyBusy}>
              {chatgptBusy && <Spinner className="size-4" />}
              {chatgptBusy
                ? connectedPlan
                  ? "Checking…"
                  : "Finish in your browser…"
                : connectedPlan
                  ? "Use this plan"
                  : "Continue with ChatGPT"}
            </Button>
            {/* A closed browser tab tells the shell nothing; this is the way
                back short of the sign-in's own five-minute timeout. */}
            {chatgptBusy && !connectedPlan && (
              <Button type="button" variant="ghost" size="lg" onClick={() => chatgptLoginCancel()}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}

      {chatgpt && (
        <div className="start-or" aria-hidden="true">
          <span>or paste an API key</span>
        </div>
      )}

      <div className="start-choices" role="radiogroup" aria-label="Model provider">
        {CHOICES.map((p) => {
          const active = p.id === provider.id;
          return (
            <div key={p.id} className={cn("start-choice", active && "is-active")}>
              <button
                type="button"
                role="radio"
                aria-checked={active}
                className="start-choice-head"
                onClick={() => setProviderId(p.id)}
              >
                <ProviderMark id={p.id} />
                <span className="start-choice-text">
                  <span className="start-choice-title">
                    {p.label}
                    {p.id === RECOMMENDED_ID && <span className="start-choice-tag">Recommended</span>}
                  </span>
                  <span className="start-choice-desc">{BLURBS[p.id] || p.description}</span>
                </span>
                <span className="start-choice-radio" aria-hidden="true" />
              </button>

              {active && (
                <div className="start-choice-body">
                  <Label htmlFor="provider-key" className="sr-only">
                    {p.label} API key
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id="provider-key"
                      type={revealed ? "text" : "password"}
                      autoComplete="off"
                      spellCheck={false}
                      autoFocus
                      placeholder={p.placeholder || "Paste your key"}
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") verify();
                      }}
                      aria-invalid={result && !result.ok ? true : undefined}
                      aria-describedby="provider-key-hint"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={revealed ? "Hide key" : "Show key"}
                      onClick={() => setRevealed((v) => !v)}
                    >
                      {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </Button>
                  </div>
                  <p id="provider-key-hint" className="mt-2 text-xs text-muted-foreground">
                    Sent with each request, never stored by Duct unless you ask.{" "}
                    <a
                      href={p.consoleUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 font-medium text-foreground underline underline-offset-2"
                    >
                      Get a key <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </p>
                  {!desktop && (
                    <label className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={remember}
                        onChange={(e) => setRemember(e.target.checked)}
                      />
                      <span>Remember it on Duct, encrypted, so it survives a refresh and can fund scheduled checks.</span>
                    </label>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {fix && (
        <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm">
          <p className="font-semibold">{fix.title}</p>
          {fix.body && <p className="mt-1 text-muted-foreground">{fix.body}</p>}
          {fixHref && (
            <a
              href={fixHref}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 font-medium underline underline-offset-2"
            >
              {fix.link === "billing" ? "Open billing" : "Open the console"}{" "}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          )}
          {fix.relogin && chatgpt && (
            <Button type="button" size="sm" variant="outline" className="mt-2" onClick={continueWithChatgpt} disabled={anyBusy}>
              Sign in with ChatGPT again
            </Button>
          )}
          {result?.detail && (
            <p className="mt-2 break-words font-mono text-xs text-muted-foreground">{result.detail}</p>
          )}
        </div>
      )}

      {result?.ok && (
        <p className="flex items-center gap-2 text-sm text-foreground" role="status">
          <Check className="size-4 text-success" aria-hidden />
          Connected · {result.model} · {result.latency_ms} ms
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={verify} disabled={anyBusy}>
          {busy && <Spinner className="size-4" />}
          {busy ? "Checking…" : "Verify & continue"}
        </Button>
        <Button type="button" variant="ghost" onClick={onSkip} disabled={anyBusy}>
          Skip for now
        </Button>
      </div>
    </div>
  );
}
