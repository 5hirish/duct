"use client";

/**
 * The page an agent opens in the browser to sign in to Duct's MCP server:
 * "Allow Claude Code to use your Duct account?"
 *
 * It is the one place the person decides, so it says three things before the
 * button and nothing else: what the agent will be able to do, what it never
 * can, and where the browser goes next. The agent's name is whatever it
 * registered as, which anyone can choose, so the page says so and names the
 * destination: an agent on this computer, a website, or an app. That line is
 * what tells a real "Claude Code" from a page pretending to be one.
 *
 * Presentational, like AgentAccess: `app/authorize/page.jsx` owns the
 * requests, so /preview can draw every state.
 */

import { AppWindow, Check, Globe, Laptop, X } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { DESTINATION_APP, DESTINATION_DEVICE } from "@/lib/mcpTokensApi";

export const CONSENT_LOADING = "loading";
export const CONSENT_ASK = "ask";
export const CONSENT_SIGN_IN = "sign-in";
export const CONSENT_ALLOWED = "allowed";
export const CONSENT_DECLINED = "declined";
export const CONSENT_INVALID = "invalid";
export const CONSENT_EXPIRED = "expired";
export const CONSENT_FAILED = "failed";

// The wordmark is a name, not copy: the literal-string check lets "Duct"
// through by name and this is the same word set in the logo's lowercase.
const WORDMARK = "duct";

function Shell({ children }) {
  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-background px-4 py-10"
      tabIndex={-1}
    >
      <div className="w-full max-w-md rounded-3xl border border-border bg-card p-7 shadow-sm ring-1 ring-foreground/5">
        <div className="mb-6 flex items-center gap-1.5">
          <span className="font-serif text-lg tracking-tight text-foreground">{WORDMARK}</span>
          <span className="size-2 rounded-full bg-[var(--orange)]" aria-hidden />
        </div>
        {children}
      </div>
    </main>
  );
}

function Notice({ title, children }) {
  return (
    <>
      <h1 className="mb-2 font-serif text-xl text-foreground">{title}</h1>
      <div className="space-y-2 text-sm text-muted-foreground">{children}</div>
    </>
  );
}

function Ability({ allowed, children }) {
  const Icon = allowed ? Check : X;
  return (
    <li className="flex items-start gap-2.5 text-sm text-foreground">
      <Icon className={`mt-0.5 size-4 shrink-0 ${allowed ? "text-success" : "text-muted-foreground"}`} aria-hidden="true" />
      <span>{children}</span>
    </li>
  );
}

function Destination({ kind, name, agent }) {
  const Icon = kind === DESTINATION_DEVICE ? Laptop : kind === DESTINATION_APP ? AppWindow : Globe;
  return (
    <p className="flex items-start gap-2.5 text-sm text-muted-foreground">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>
        {kind === DESTINATION_DEVICE ? (
          <Trans>After you allow it, Duct hands {agent} its sign-in on this computer.</Trans>
        ) : kind === DESTINATION_APP ? (
          <Trans>
            After you allow it, your browser opens the <strong className="font-medium text-foreground">{name}</strong> app.
          </Trans>
        ) : (
          <Trans>
            After you allow it, you go to <strong className="font-medium text-foreground">{name}</strong>.
          </Trans>
        )}
      </span>
    </p>
  );
}

export default function AgentConsent({
  state,
  request = null,
  viewerEmail = "",
  busy = false,
  error = "",
  onAllow,
  onDecline,
  onSignIn,
  onSwitchAccount,
}) {
  const { t } = useLingui();
  const agent = request?.client_name || t`An AI agent`;

  if (state === CONSENT_LOADING) {
    return (
      <Shell>
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Spinner className="size-4" />
          <Trans>Checking the request…</Trans>
        </p>
      </Shell>
    );
  }

  if (state === CONSENT_INVALID || state === CONSENT_EXPIRED) {
    return (
      <Shell>
        <Notice title={state === CONSENT_EXPIRED ? t`This request has expired` : t`This sign-in link doesn't work`}>
          <p>
            {state === CONSENT_EXPIRED
              ? t`A sign-in request lasts ten minutes. Start again from your agent.`
              : t`Start again from your agent, so it can send a fresh one.`}
          </p>
          <p>
            <Trans>
              In Claude Code, run <code className="font-mono">/mcp</code> and choose Authenticate. In Codex, run{" "}
              <code className="font-mono">codex mcp login duct</code>.
            </Trans>
          </p>
        </Notice>
      </Shell>
    );
  }

  if (state === CONSENT_FAILED) {
    return (
      <Shell>
        <Notice title={t`Something went wrong`}>
          <p>{error || t`Duct couldn't read this request. Try again in a moment.`}</p>
        </Notice>
      </Shell>
    );
  }

  if (state === CONSENT_ALLOWED || state === CONSENT_DECLINED) {
    return (
      <Shell>
        <Notice title={state === CONSENT_ALLOWED ? t`${agent} is connected` : t`${agent} wasn't connected`}>
          <p role="status">
            {state === CONSENT_ALLOWED
              ? t`You can close this tab and go back to your agent.`
              : t`Nothing changed. You can close this tab.`}
          </p>
        </Notice>
      </Shell>
    );
  }

  if (state === CONSENT_SIGN_IN) {
    return (
      <Shell>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand">
          <Trans>Connect an agent</Trans>
        </p>
        <h1 className="mb-3 font-serif text-2xl leading-snug text-foreground">
          <Trans>
            <em className="text-brand">{agent}</em> wants to use your Duct account
          </Trans>
        </h1>
        <p className="mb-6 text-sm text-muted-foreground">
          <Trans>Sign in, and Duct asks you whether to allow it.</Trans>
        </p>
        <GoogleSignInButton onClick={onSignIn} />
      </Shell>
    );
  }

  return (
    <Shell>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand">
        <Trans>Connect an agent</Trans>
      </p>
      <h1 className="mb-2 font-serif text-2xl leading-snug text-foreground">
        <Trans>
          Allow <em className="text-brand">{agent}</em> to use your Duct account?
        </Trans>
      </h1>
      <p className="mb-5 text-xs text-muted-foreground">
        <Trans>
          Signed in as <strong className="font-medium text-foreground">{viewerEmail}</strong>.
        </Trans>{" "}
        <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={onSwitchAccount}>
          <Trans>Switch account</Trans>
        </button>
      </p>

      {/* Two labelled lists, not one: a check and a cross are the only
          difference otherwise, and a skim reads four lines as four grants. */}
      <p className="mb-1.5 text-xs font-semibold text-muted-foreground"><Trans>It will be able to</Trans></p>
      <ul className="mb-4 space-y-2">
        <Ability allowed><Trans>See your projects and what Duct knows about each</Trans></Ability>
        <Ability allowed><Trans>Draft a project&apos;s description, audience and competitors</Trans></Ability>
      </ul>
      <p className="mb-1.5 text-xs font-semibold text-muted-foreground"><Trans>It can never</Trans></p>
      <ul className="mb-4 space-y-2">
        <Ability allowed={false}><Trans>Approve or apply changes, or connect tools</Trans></Ability>
        <Ability allowed={false}><Trans>See your keys, or replace anything you typed</Trans></Ability>
      </ul>

      <div className="mb-6 space-y-2 border-t border-border pt-4">
        <Destination kind={request?.destination} name={request?.destination_name} agent={agent} />
        <p className="text-xs text-muted-foreground">
          <Trans>
            {agent} is the name the agent gave itself. Allow it only if you just added Duct to an agent.
          </Trans>
        </p>
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={onDecline} disabled={busy}>
          <Trans>Cancel</Trans>
        </Button>
        <Button type="button" className="flex-1" onClick={onAllow} disabled={busy}>
          {busy && <Spinner className="size-4" />}
          <Trans>Allow</Trans>
        </Button>
      </div>
    </Shell>
  );
}
