"use client";

/**
 * Connect your AI agent: how to add Duct's MCP server to an agent, the agents
 * that signed in, and personal tokens for the ones that cannot.
 *
 * The requests live here and the drawing in AgentAccess, so /preview can show
 * every state. That includes the watch for a sign-in: AgentAccess asks for it
 * (`onWatch`) when step 1 is copied, and this page polls the list until it
 * says stop or the cap runs out. A minted token is held in this page's state only: it is shown
 * once, never written to storage, and gone on reload, which is the promise
 * the page makes ("Duct shows a token once").
 */

import { useCallback, useEffect, useState } from "react";
import { Trans, useLingui } from "@lingui/react/macro";
import AgentAccess from "@/components/settings/AgentAccess";
import LoadError from "@/components/LoadError";
import { hasAuthToken } from "@/lib/authFetch";
import { isLocalBackendActive } from "@/lib/localBackend";
import { createMcpToken, listMcpTokens, mcpServerUrl, revokeMcpToken } from "@/lib/mcpTokensApi";
import { isDesktopShell } from "@/lib/shell";
import { pollWhileVisible } from "@/lib/visibility";
import { Page, PageHeader } from "@/components/ui/page";

// Watching for an agent to sign in starts when the person copies step 1 and
// ends when one appears. The cap is for the person who copied and walked
// away: past it, the page offers "Check again" instead of polling all day.
const WATCH_EVERY_MS = 4000;
const WATCH_FOR_MS = 10 * 60_000;

export default function AgentsSettingsPage() {
  const { t } = useLingui();
  const [tokens, setTokens] = useState(null);
  const [minted, setMinted] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState(null);
  const [signedIn, setSignedIn] = useState(true);
  // Read after mount: BASE is repointed at boot in the desktop shell, and a
  // sidecar has no browser sign-in (backend service/mcp_server/oauth.py).
  const [serverUrl, setServerUrl] = useState("");
  const [signInAvailable, setSignInAvailable] = useState(true);
  // The desktop shell opens only http(s) links outside itself, so a
  // `cursor://` or `vscode:` install link would be a button that does nothing.
  const [deepLinks, setDeepLinks] = useState(true);
  const [watching, setWatching] = useState(false);

  const load = useCallback(() => {
    setLoadError(null);
    listMcpTokens().then(setTokens, setLoadError);
  }, []);

  useEffect(() => {
    const ok = hasAuthToken();
    setSignedIn(ok);
    setServerUrl(mcpServerUrl());
    setSignInAvailable(!isLocalBackendActive());
    setDeepLinks(!isDesktopShell());
    if (ok) load();
  }, [load]);

  // A failed refresh keeps the list on screen: the next tick tries again,
  // and the first load already said whether the server can be reached.
  useEffect(() => {
    if (!watching) return undefined;
    const stop = pollWhileVisible(() => listMcpTokens().then(setTokens, () => {}), WATCH_EVERY_MS);
    const cap = setTimeout(() => setWatching(false), WATCH_FOR_MS);
    return () => {
      stop();
      clearTimeout(cap);
    };
  }, [watching]);

  async function create(name) {
    setCreating(true);
    setError("");
    try {
      const row = await createMcpToken(name);
      setMinted(row);
      setTokens((prev) => [row, ...(prev || [])]);
    } catch (err) {
      setError(err?.message || t`That didn't go through. Try again in a moment.`);
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id) {
    try {
      await revokeMcpToken(id);
      setTokens((prev) => (prev || []).filter((row) => row.id !== id));
      setMinted((prev) => (prev?.id === id ? null : prev));
    } catch (err) {
      setError(err?.message || t`That didn't go through. Try again in a moment.`);
    }
  }

  return (
    <Page width="narrow">
      <PageHeader
        title={<Trans>Connect your AI agent</Trans>}
        status={<Trans>Let the coding agent in your repo describe your product to Duct.</Trans>}
        help={
          <Trans>
            Add it once and it works in every repo. Your agent does the reading on its own subscription, so
            Duct spends none of your model keys on it. Running it again is safe: a draft never replaces what
            you typed or confirmed.
          </Trans>
        }
      />
      {!signedIn ? (
        <p className="text-sm text-muted-foreground">
          <Trans>Sign in first. Your agent works on your account, so there has to be one.</Trans>
        </p>
      ) : loadError ? (
        <LoadError what={t`your agents and tokens`} detail={loadError?.message} onRetry={load} />
      ) : (
        <AgentAccess
          serverUrl={serverUrl}
          tokens={tokens}
          minted={minted}
          creating={creating}
          error={error}
          signInAvailable={signInAvailable}
          watching={watching}
          deepLinks={deepLinks}
          onCreate={create}
          onRevoke={revoke}
          onWatch={setWatching}
        />
      )}
    </Page>
  );
}
