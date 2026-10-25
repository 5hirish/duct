"use client";

/**
 * Connect your AI agent — tokens for Duct's MCP server, and how to use one.
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
import { createMcpToken, listMcpTokens, mcpServerUrl, revokeMcpToken } from "@/lib/mcpTokensApi";

export default function AgentsSettingsPage() {
  const { t } = useLingui();
  const [tokens, setTokens] = useState(null);
  const [minted, setMinted] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState(null);
  const [signedIn, setSignedIn] = useState(true);
  // Read after mount: BASE is repointed at boot in the desktop shell.
  const [serverUrl, setServerUrl] = useState("");

  const load = useCallback(() => {
    setLoadError(null);
    listMcpTokens().then(setTokens, setLoadError);
  }, []);

  useEffect(() => {
    const ok = hasAuthToken();
    setSignedIn(ok);
    setServerUrl(mcpServerUrl());
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
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          <Trans>Connect your AI agent</Trans>
        </h1>
      </div>
      {!signedIn ? (
        <p className="app-subtle" style={{ marginTop: 0 }}>
          <Trans>Sign in first. A token works on your account, so there has to be one.</Trans>
        </p>
      ) : loadError ? (
        <LoadError what={t`your tokens`} detail={loadError?.message} onRetry={load} />
      ) : (
        <AgentAccess
          serverUrl={serverUrl}
          tokens={tokens}
          minted={minted}
          creating={creating}
          error={error}
          onCreate={create}
          onRevoke={revoke}
        />
      )}
    </section>
  );
}
