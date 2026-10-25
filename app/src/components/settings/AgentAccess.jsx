"use client";

/**
 * Connect your AI agent: a token, the line to paste, the sentence to type.
 *
 * Three numbered steps because that is the whole job, and the person doing it
 * is in a terminal with this page beside it. The token is shown once, right
 * where it is made, and dropped into every snippet so one copy is enough; the
 * placeholder before that keeps the snippets readable, never copyable as
 * something that would half-work.
 *
 * The first thing on the page is what an agent cannot do. The person this is
 * for is handing a program write access to Duct, and "it can only draft, and
 * never replaces what you typed" is the sentence that makes that reasonable.
 *
 * Presentational: the page owns the requests, so /preview can render every
 * state from fixtures.
 */

import { useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { formatDate, relativeTime } from "@/lib/format";
import { agentSnippets } from "@/lib/mcpTokensApi";

const COPIED_MS = 1600;
const TOKEN_PLACEHOLDER = "duct_mcp_…";

function CopyBox({ value, label, mono = true, disabled = false }) {
  const { t } = useLingui();
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative rounded-lg border border-border bg-muted/50">
      <pre
        className={`overflow-x-auto whitespace-pre-wrap py-2.5 pl-3 pr-11 leading-relaxed text-foreground ${mono ? "font-mono text-xs break-all" : "font-sans text-sm break-words"}`}
        aria-label={label}
      >
        {value}
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="absolute right-1 top-1 size-8"
        disabled={disabled}
        aria-label={copied ? t`Copied` : t`Copy`}
        onClick={() => {
          navigator.clipboard?.writeText(value).catch(() => {});
          setCopied(true);
          setTimeout(() => setCopied(false), COPIED_MS);
        }}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </Button>
    </div>
  );
}

function Step({ number, title, children }) {
  // The body sits under the title once the column is 28rem wide, and under
  // the number below that, where an indent costs a quarter of the width the
  // snippets need. A container query, because the sidebar and resizable panes
  // decide this column's width, not the window.
  return (
    <li className="grid grid-cols-[1.75rem_1fr] gap-x-3 gap-y-2.5">
      <span
        aria-hidden="true"
        className="flex size-7 items-center justify-center rounded-full border border-border text-xs font-semibold text-muted-foreground"
      >
        {number}
      </span>
      <h2 className="self-center text-sm font-semibold text-foreground">{title}</h2>
      <div className="col-span-2 min-w-0 space-y-2.5 @md:col-span-1 @md:col-start-2">{children}</div>
    </li>
  );
}

function TokenRow({ token, onRevoke }) {
  const { t } = useLingui();
  const tokenName = token.name;
  const used = relativeTime(token.last_used_at, { fallbackAfterDays: 7 });
  const expires = formatDate(token.expires_at);
  return (
    <li className="flex items-start gap-3 border-b border-border/60 py-2.5 last:border-b-0">
      <KeyRound className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-foreground">{token.name}</p>
        <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
          <span className="font-mono">…{token.hint}</span>
          <span>{token.last_used_at ? <Trans>Used {used}</Trans> : <Trans>Never used</Trans>}</span>
          <span><Trans>Expires {expires}</Trans></span>
        </p>
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={() => onRevoke(token)} aria-label={t`Revoke ${tokenName}`}>
        <Trans>Revoke</Trans>
      </Button>
    </li>
  );
}

export default function AgentAccess({
  serverUrl,
  tokens,
  minted = null,
  creating = false,
  error = "",
  onCreate,
  onRevoke,
}) {
  const { t } = useLingui();
  const [name, setName] = useState("Claude Code");
  const { confirm, dialog } = useConfirm();
  const snippets = agentSnippets(serverUrl, minted?.token || TOKEN_PLACEHOLDER);

  async function revoke(token) {
    const tokenName = token.name;
    const ok = await confirm({
      title: t`Revoke “${tokenName}”?`,
      description: t`Any agent using this token loses access to Duct right away. Your projects stay as they are.`,
      action: t`Revoke`,
      destructive: true,
    });
    if (ok) onRevoke(token.id);
  }

  return (
    <div className="max-w-2xl">
      <p className="mb-1 text-sm text-foreground">
        <Trans>Let Claude Code, Codex or Cursor set up your projects from the repo you are working in.</Trans>
      </p>
      <p className="mb-8 text-sm text-muted-foreground">
        <Trans>
          Your agent can read your projects and draft their profile. It can&apos;t approve changes,
          connect tools, or replace anything you typed or confirmed.
        </Trans>
      </p>

      <ol className="space-y-8">
        <Step number={1} title={t`Create a token`}>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) onCreate(name.trim());
            }}
          >
            <label htmlFor="agent-token-name" className="sr-only">
              <Trans>Token name</Trans>
            </label>
            <input
              id="agent-token-name"
              className="h-9 min-w-0 flex-1 rounded-lg border border-input bg-transparent px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              value={name}
              maxLength={60}
              placeholder={t`Claude Code on my laptop`}
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={creating || !name.trim()}>
              {creating ? <Trans>Creating…</Trans> : <Trans>Create token</Trans>}
            </Button>
          </form>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {minted && (
            <div className="space-y-1.5" role="status">
              <p className="text-sm text-foreground">
                <Trans>Copy it now. Duct shows a token once.</Trans>
              </p>
              <CopyBox value={minted.token} label={t`Your new token`} />
            </div>
          )}
        </Step>

        <Step number={2} title={t`Add Duct to your agent`}>
          {!minted && (
            <p className="text-xs text-muted-foreground">
              <Trans>Create a token first. It fills in below, so one copy is all it takes.</Trans>
            </p>
          )}
          <Tabs defaultValue="claude">
            <TabsList>
              <TabsTrigger value="claude">Claude Code</TabsTrigger>
              <TabsTrigger value="codex">Codex</TabsTrigger>
              <TabsTrigger value="cursor">Cursor</TabsTrigger>
            </TabsList>
            <TabsContent value="claude" className="space-y-1.5">
              <p className="text-xs text-muted-foreground"><Trans>Run this in your terminal.</Trans></p>
              <CopyBox value={snippets.claude} label={t`Command for Claude Code`} disabled={!minted} />
            </TabsContent>
            <TabsContent value="codex" className="space-y-1.5">
              <p className="text-xs text-muted-foreground">
                <Trans>Add this to <code className="font-mono">~/.codex/config.toml</code>.</Trans>
              </p>
              <CopyBox value={snippets.codex} label={t`Settings for Codex`} disabled={!minted} />
            </TabsContent>
            <TabsContent value="cursor" className="space-y-1.5">
              <p className="text-xs text-muted-foreground">
                <Trans>Add this to <code className="font-mono">~/.cursor/mcp.json</code>.</Trans>
              </p>
              <CopyBox value={snippets.cursor} label={t`Settings for Cursor`} disabled={!minted} />
            </TabsContent>
          </Tabs>
        </Step>

        <Step number={3} title={t`Ask it to set up your project`}>
          {/* In the reader's language: the agent understands any of them,
              and a prompt is easier to trust when you can read it. */}
          <CopyBox value={t`Set up this product in Duct.`} label={t`First prompt`} mono={false} />
          <p className="text-xs text-muted-foreground">
            <Trans>
              It reads your README and docs, shows you what it will send, then drafts the project. Review
              it in Duct afterwards; every field says where it came from.
            </Trans>
          </p>
        </Step>
      </ol>

      <h2 className="mb-1 mt-10 text-sm font-semibold text-foreground"><Trans>Your tokens</Trans></h2>
      {tokens == null ? (
        <p className="text-sm text-muted-foreground"><Trans>Loading…</Trans></p>
      ) : tokens.length === 0 ? (
        <p className="text-sm text-muted-foreground"><Trans>No tokens yet.</Trans></p>
      ) : (
        <ul>
          {tokens.map((token) => (
            <TokenRow key={token.id} token={token} onRevoke={revoke} />
          ))}
        </ul>
      )}
      {dialog}
    </div>
  );
}
