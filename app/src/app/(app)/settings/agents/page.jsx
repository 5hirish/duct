"use client";

/**
 * Connect your AI agent: how to add Duct's MCP server to an agent, the agents
 * that signed in, and personal tokens for the ones that cannot.
 *
 * The requests live here and the drawing in AgentAccess, so /preview can show
 * every state. A minted token is held in this page's state only: it is shown
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
import { Page, PageHeader } from "@/components/ui/page";

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

  const load = useCallback(() => {
    setLoadError(null);
    listMcpTokens().then(setTokens, setLoadError);
  }, []);

  useEffect(() => {
    const ok = hasAuthToken();
    setSignedIn(ok);
    setServerUrl(mcpServerUrl());
    setSignInAvailable(!isLocalBackendActive());
    if (ok) load();
  }, [load]);

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
        status={<Trans>Use Duct from Claude Code, Codex, Cursor, VS Code or OpenCode, in the repo you are working in.</Trans>}
        help={
          <Trans>
            Your agent can read your projects and draft their profile. It can&apos;t approve changes,
            connect tools, or replace anything you typed or confirmed.
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
          onCreate={create}
          onRevoke={revoke}
        />
      )}
    </Page>
  );
}
