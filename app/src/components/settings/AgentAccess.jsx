"use client";

/**
 * Connect your AI agent: the line to paste, the sign-in, the sentence to type.
 *
 * Three numbered steps because that is the whole job, and the person doing it
 * is in a terminal with this page beside it. There is no secret in any of
 * them: the agent finds Duct's sign-in from the server's first answer and
 * opens the browser itself, so step 1 is the same line for everyone and step 2
 * happens on Duct's own consent page (`app/authorize`).
 *
 * The first thing on the page is what an agent cannot do. The person this is
 * for is handing a program write access to Duct, and "it can only draft, and
 * never replaces what you typed" is the sentence that makes that reasonable.
 *
 * Below the steps, the agents that signed in, each disconnectable, and the
 * older way in, a pasted token, for an agent that cannot open a browser. On
 * the desktop sidecar the token is the only way (`signInAvailable`): its
 * address changes every launch, and the browser cannot reach its app.
 *
 * Presentational: the page owns the requests, so /preview can render every
 * state from fixtures.
 */

import { useState } from "react";
import { Bot, Check, Copy, KeyRound } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { formatDate, relativeTime } from "@/lib/format";
import { KIND_AGENT, agentSetup, tokenSetup } from "@/lib/mcpTokensApi";

const COPIED_MS = 1600;

function CopyBox({ value, label, mono = true }) {
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

function Hint({ children }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

/** One connected agent or one pasted token. An agent's access token changes
 *  every hour, so it shows no hint; a token's last four tell two apart. */
function CredentialRow({ row, onRemove }) {
  const { t } = useLingui();
  const rowName = row.name;
  const agent = row.kind === KIND_AGENT;
  const used = relativeTime(row.last_used_at, { fallbackAfterDays: 7 });
  const created = formatDate(row.created_at);
  const expires = formatDate(row.expires_at);
  const Icon = agent ? Bot : KeyRound;
  return (
    <li className="flex items-start gap-3 border-b border-border/60 py-2.5 last:border-b-0">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-foreground">{row.name}</p>
        <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
          {agent ? <span><Trans>Connected {created}</Trans></span> : <span className="font-mono">…{row.hint}</span>}
          <span>{row.last_used_at ? <Trans>Used {used}</Trans> : <Trans>Never used</Trans>}</span>
          {!agent && <span><Trans>Expires {expires}</Trans></span>}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => onRemove(row)}
        aria-label={agent ? t`Disconnect ${rowName}` : t`Revoke ${rowName}`}
      >
        {agent ? <Trans>Disconnect</Trans> : <Trans>Revoke</Trans>}
      </Button>
    </li>
  );
}

function CredentialList({ rows, empty, onRemove }) {
  if (rows == null) return <p className="text-sm text-muted-foreground"><Trans>Loading…</Trans></p>;
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul>
      {rows.map((row) => (
        <CredentialRow key={row.id} row={row} onRemove={onRemove} />
      ))}
    </ul>
  );
}

function SignInSteps({ serverUrl }) {
  const { t } = useLingui();
  const setup = agentSetup(serverUrl);
  return (
    <ol className="space-y-8">
      <Step number={1} title={t`Add Duct to your agent`}>
        <Tabs defaultValue="claude">
          {/* Five names do not fit one pill in a narrow column; underlined
              tabs wrap onto a second row and still read as one set. */}
          <TabsList variant="line" className="flex-wrap justify-start group-data-horizontal/tabs:h-auto">
            <TabsTrigger value="claude">Claude Code</TabsTrigger>
            <TabsTrigger value="codex">Codex</TabsTrigger>
            <TabsTrigger value="cursor">Cursor</TabsTrigger>
            <TabsTrigger value="vscode">VS Code</TabsTrigger>
            <TabsTrigger value="opencode">OpenCode</TabsTrigger>
          </TabsList>
          <TabsContent value="claude" className="space-y-1.5">
            <Hint><Trans>Run this in your terminal.</Trans></Hint>
            <CopyBox value={setup.claude} label={t`Command for Claude Code`} />
            <Hint>
              <Trans>
                Then, in Claude Code, run <code className="font-mono">/mcp</code>, pick duct and choose
                Authenticate.
              </Trans>
            </Hint>
          </TabsContent>
          <TabsContent value="codex" className="space-y-1.5">
            <Hint><Trans>Run these in your terminal. The second one opens your browser.</Trans></Hint>
            <CopyBox value={setup.codex} label={t`Commands for Codex`} />
          </TabsContent>
          <TabsContent value="cursor" className="space-y-1.5">
            <Hint>
              <Trans>Add this to <code className="font-mono">~/.cursor/mcp.json</code>.</Trans>
            </Hint>
            <CopyBox value={setup.cursor} label={t`Settings for Cursor`} />
            <Hint><Trans>Then sign in from duct&apos;s entry in Cursor&apos;s MCP settings.</Trans></Hint>
          </TabsContent>
          <TabsContent value="vscode" className="space-y-1.5">
            <Hint>
              <Trans>
                Run <strong className="font-medium text-foreground">MCP: Add Server</strong> from the Command
                Palette, choose HTTP, paste this address and name it duct.
              </Trans>
            </Hint>
            <CopyBox value={setup.vscode} label={t`Address for VS Code`} />
          </TabsContent>
          <TabsContent value="opencode" className="space-y-1.5">
            <Hint>
              <Trans>Add this to <code className="font-mono">opencode.json</code>.</Trans>
            </Hint>
            <CopyBox value={setup.opencode} label={t`Settings for OpenCode`} />
            <Hint>
              <Trans>Then run <code className="font-mono">opencode mcp auth duct</code>.</Trans>
            </Hint>
          </TabsContent>
        </Tabs>
      </Step>

      <Step number={2} title={t`Sign in when your browser opens`}>
        <Hint>
          <Trans>
            Your agent opens Duct in your browser. Check it names your agent, then choose Allow. No token to copy,
            and it shows up under Connected agents below.
          </Trans>
        </Hint>
      </Step>

      <Step number={3} title={t`Ask it to set up your project`}>
        {/* In the reader's language: the agent understands any of them,
            and a prompt is easier to trust when you can read it. */}
        <CopyBox value={t`Set up this product in Duct.`} label={t`First prompt`} mono={false} />
        <Hint>
          <Trans>
            It reads your README and docs, shows you what it will send, then drafts the project. Review it in
            Duct afterwards; every field says where it came from.
          </Trans>
        </Hint>
      </Step>
    </ol>
  );
}

export default function AgentAccess({
  serverUrl,
  tokens,
  minted = null,
  creating = false,
  error = "",
  signInAvailable = true,
  onCreate,
  onRevoke,
}) {
  const { t } = useLingui();
  const [name, setName] = useState("");
  const { confirm, dialog } = useConfirm();
  const agents = tokens?.filter((row) => row.kind === KIND_AGENT) ?? null;
  const pasted = tokens?.filter((row) => row.kind !== KIND_AGENT) ?? null;
  const withToken = minted ? tokenSetup(serverUrl, minted.token) : null;

  async function remove(row) {
    const rowName = row.name;
    const agent = row.kind === KIND_AGENT;
    const ok = await confirm(
      agent
        ? {
            title: t`Disconnect “${rowName}”?`,
            description: t`It loses access to Duct on its next request. Your projects stay as they are, and you can add it again any time.`,
            action: t`Disconnect`,
            destructive: true,
          }
        : {
            title: t`Revoke “${rowName}”?`,
            description: t`Any agent using this token loses access to Duct right away. Your projects stay as they are.`,
            action: t`Revoke`,
            destructive: true,
          },
    );
    if (ok) onRevoke(row.id);
  }

  return (
    <div className="max-w-2xl">
      <p className="mb-1 text-sm text-foreground">
        <Trans>Use Duct from Claude Code, Codex, Cursor, VS Code or OpenCode, in the repo you are working in.</Trans>
      </p>
      <p className="mb-8 text-sm text-muted-foreground">
        <Trans>
          Your agent can read your projects and draft their profile. It can&apos;t approve changes,
          connect tools, or replace anything you typed or confirmed.
        </Trans>
      </p>

      {signInAvailable ? (
        <>
          <SignInSteps serverUrl={serverUrl} />
          <h2 className="mb-1 mt-10 text-sm font-semibold text-foreground"><Trans>Connected agents</Trans></h2>
          <CredentialList
            rows={agents}
            empty={t`None yet. An agent shows up here once you allow it.`}
            onRemove={remove}
          />
        </>
      ) : (
        <p className="mb-2 rounded-lg border border-border bg-muted/50 p-3 text-sm text-foreground">
          <Trans>
            Browser sign-in works with Duct&apos;s hosted service. This Duct runs on your computer, so connect your
            agent with a token below.
          </Trans>
        </p>
      )}

      <section aria-labelledby="agent-token-heading" className="mt-10 border-t border-border pt-6">
        <h2 id="agent-token-heading" className="mb-1 text-sm font-semibold text-foreground">
          {signInAvailable ? <Trans>No browser? Use a token</Trans> : <Trans>Use a token</Trans>}
        </h2>
        <p className="mb-3 text-xs text-muted-foreground">
          <Trans>
            For an agent that can&apos;t open a browser, such as CI or a remote machine. Duct shows a token once, and
            it works for a year.
          </Trans>
        </p>
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
            placeholder={t`Name it, e.g. CI on GitHub Actions`}
            onChange={(e) => setName(e.target.value)}
          />
          <Button type="submit" variant="outline" disabled={creating || !name.trim()}>
            {creating ? <Trans>Creating…</Trans> : <Trans>Create token</Trans>}
          </Button>
        </form>
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {withToken && (
          <div className="mt-4 space-y-2.5" role="status">
            <p className="text-sm text-foreground">
              <Trans>Copy it now. Duct shows a token once.</Trans>
            </p>
            <CopyBox value={minted.token} label={t`Your new token`} />
            <Hint><Trans>Add Duct to Claude Code with it:</Trans></Hint>
            <CopyBox value={withToken.claude} label={t`Command for Claude Code with a token`} />
            <Hint><Trans>Or have any other agent send this header to the same address:</Trans></Hint>
            <CopyBox value={withToken.header} label={t`Header for any agent`} />
          </div>
        )}
        <h3 className="mb-1 mt-6 text-xs font-semibold text-muted-foreground"><Trans>Your tokens</Trans></h3>
        <CredentialList rows={pasted} empty={t`No tokens yet.`} onRemove={remove} />
      </section>
      {dialog}
    </div>
  );
}
