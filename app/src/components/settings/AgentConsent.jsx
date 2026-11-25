"use client";

/**
 * The page an agent opens in the browser to sign in to Duct's MCP server:
 * "Claude Code would like to work with Duct".
 *
 * It is the one place the person decides, and it should read as an
 * invitation, not a permissions form. So: who is asking, two choices in
 * plain words (AgentGrantPicker), which projects as one line, one calm
 * reassurance row for what it can never do, and the two buttons. Everything
 * finer (the six capabilities, the project list) is one click away and
 * closed until wanted.
 *
 * The agent's name is whatever it registered as, which anyone can choose,
 * so one small line by the buttons names where the browser goes next and
 * says to allow it only if you just added Duct. That line is what tells a
 * real "Claude Code" from a page pretending to be one; it stays, quietly.
 *
 * Presentational, like AgentAccess: `app/authorize/page.jsx` owns the
 * requests, so /preview can draw every state.
 */

import { useEffect, useState } from "react";
import { AppWindow, Globe, Laptop, ShieldCheck } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import AgentGrantPicker from "@/components/settings/AgentGrantPicker";
import { grantBody, grantProblem, initialGrant } from "@/lib/agentScopes";
import { AgentLogoTile } from "@/components/connections/logos";
import { DESTINATION_APP, DESTINATION_DEVICE, agentDisplayName, agentFromName } from "@/lib/mcpTokensApi";

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

function Shell({ children, mark = null }) {
  return (
    <main
      id="main-content"
      className="flex min-h-dvh items-center justify-center bg-background px-4 py-10"
      tabIndex={-1}
    >
      <Card size="lg" className="w-full max-w-md gap-0">
        {mark || (
          <div className="mb-6 flex items-center gap-1.5">
            <span className="font-serif text-lg tracking-tight text-foreground">{WORDMARK}</span>
            <span className="size-2 rounded-full bg-[var(--orange)]" aria-hidden />
          </div>
        )}
        {children}
      </Card>
    </main>
  );
}

/** The two marks are joined by a short channel with water running in it,
 *  the aqueduct of /start: blue is water and water is data, and this is the
 *  one place a person watches their data meet an agent. It runs once the
 *  page is open and stands still under reduced motion (styles/agent-consent.css). */
function Channel() {
  return (
    <svg className="consent-channel" viewBox="0 0 48 12" width="48" height="12" aria-hidden="true">
      <path className="consent-channel-bed" d="M2 6 H46" />
      <path className="consent-channel-water" d="M2 6 H46" />
    </svg>
  );
}

/** The agent's mark joined to Duct's: who is asking, at a glance. A known
 *  name gets its owner's logo, anything else a generic agent; the name in
 *  the heading below is still the thing to check. */
function Pairing({ agentId }) {
  return (
    <div className="mb-6 flex items-center gap-2" aria-hidden="true">
      <AgentLogoTile id={agentId} className="size-11 rounded-xl [&_img]:size-6 [&_svg]:size-6" />
      <Channel />
      <span className="flex size-11 items-center justify-center rounded-xl border border-border bg-background">
        <span className="flex items-baseline gap-0.5">
          <span className="font-serif text-lg leading-none text-foreground">{WORDMARK.charAt(0)}</span>
          <span className="size-1.5 rounded-full bg-[var(--orange)]" />
        </span>
      </span>
    </div>
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

function Destination({ kind, name, agent }) {
  const Icon = kind === DESTINATION_DEVICE ? Laptop : kind === DESTINATION_APP ? AppWindow : Globe;
  return (
    <p className="flex items-start gap-2 text-xs text-muted-foreground">
      <Icon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      <span>
        {kind === DESTINATION_DEVICE ? (
          <Trans>Then back to {agent} on this computer.</Trans>
        ) : kind === DESTINATION_APP ? (
          <Trans>
            Then to the <strong className="font-medium text-foreground">{name}</strong> app.
          </Trans>
        ) : (
          <Trans>
            Then to <strong className="font-medium text-foreground">{name}</strong>.
          </Trans>
        )}{" "}
        <Trans>Only allow this if you just added Duct to {agent}.</Trans>
      </span>
    </p>
  );
}

export default function AgentConsent({
  state,
  request = null,
  viewerEmail = "",
  projects = null,
  defaultGrant = null,
  defaultCustomise = false,
  busy = false,
  error = "",
  onAllow,
  onDecline,
  onSignIn,
  onSwitchAccount,
}) {
  const { t } = useLingui();
  const agent = agentDisplayName(request?.client_name) || t`An AI agent`;
  const agentId = agentFromName(request?.client_name);
  const requested = request?.requested_scopes || [];
  const requestedKey = requested.join(" ");
  const [grant, setGrant] = useState(() => defaultGrant || initialGrant(requested));
  // The request arrives after the first render on the real page; start the
  // choice from what it asked for once it does.
  useEffect(() => {
    if (!defaultGrant) setGrant(initialGrant(requestedKey ? requestedKey.split(" ") : []));
  }, [requestedKey, defaultGrant]);

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
      <Shell mark={<Pairing agentId={agentId} />}>
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
      <Shell mark={<Pairing agentId={agentId} />}>
        <h1 className="mb-2 font-serif text-2xl leading-snug text-foreground">
          <Trans>
            <em className="text-brand">{agent}</em> would like to work with Duct
          </Trans>
        </h1>
        <p className="mb-6 text-sm text-muted-foreground">
          <Trans>Sign in, then you choose what it can do.</Trans>
        </p>
        <GoogleSignInButton onClick={onSignIn} />
      </Shell>
    );
  }

  return (
    <Shell mark={<Pairing agentId={agentId} />}>
      <h1 className="mb-1.5 font-serif text-2xl leading-snug text-foreground">
        <Trans>
          <em className="text-brand">{agent}</em> would like to work with Duct
        </Trans>
      </h1>
      <p className="text-sm text-muted-foreground">
        <Trans>You choose what it can do. Change it any time in Settings.</Trans>
      </p>
      <p className="mb-6 mt-1 text-xs text-muted-foreground">
        <Trans>
          Signed in as <strong className="font-medium text-foreground">{viewerEmail}</strong>.
        </Trans>{" "}
        <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={onSwitchAccount}>
          <Trans>Switch account</Trans>
        </button>
      </p>

      <AgentGrantPicker
        grant={grant}
        onChange={setGrant}
        projects={projects}
        requested={requested}
        agent={agent}
        idPrefix="consent"
        defaultCustomise={defaultCustomise}
      />

      <p className="mt-5 flex items-start gap-2.5 rounded-lg bg-muted/60 px-3.5 py-3 text-xs text-pretty text-muted-foreground">
        <ShieldCheck className="mt-px size-4 shrink-0 text-success" aria-hidden="true" />
        <span>
          <Trans>
            It can&apos;t approve changes, publish, or see your passwords and keys. Everything it does shows in
            Activity, and edits can be undone.
          </Trans>
        </span>
      </p>

      {error && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mt-6 flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={onDecline} disabled={busy}>
          <Trans>Not now</Trans>
        </Button>
        <Button
          type="button"
          className="flex-1"
          onClick={() => onAllow?.(grantBody(grant))}
          disabled={busy || Boolean(grantProblem(grant))}
        >
          {busy && <Spinner className="size-4" />}
          <Trans>Allow</Trans>
        </Button>
      </div>
      <div className="mt-3">
        <Destination kind={request?.destination} name={request?.destination_name} agent={agent} />
      </div>
    </Shell>
  );
}
