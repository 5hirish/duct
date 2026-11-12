"use client";

/**
 * Connect your AI agent: pick the agent, add Duct to it, allow it in the
 * browser, ask it the first thing.
 *
 * The agent is chosen first, by its logo, because everything after depends on
 * it: the line to paste, the name the browser will show, the logo beside the
 * prompt. People recognise a mark before they read a tab label, and the person
 * doing this is glancing between this page and a terminal.
 *
 * The steps track the person rather than just listing: copying step 1 (or the
 * one-click install) checks it off and asks the page to watch for a sign-in
 * (`onWatch`); a connected agent the page did not know about when it loaded
 * checks off step 2 by name. That second check is the server's word, not a
 * guess, which is the only reason it is worth a poll. There is no secret in
 * any step: the agent finds Duct's sign-in from the server's first answer and
 * opens the browser itself, onto Duct's own consent page (`app/authorize`),
 * which step 2 draws in miniature so it is recognised when it appears.
 *
 * Below the steps, the agents that signed in, each disconnectable, and the
 * older way in, a pasted token, for an agent that cannot open a browser. On
 * the desktop sidecar the token is the only way (`signInAvailable`): its
 * address changes every launch, and the browser cannot reach its app.
 *
 * Presentational: the page owns the requests and the polling, so /preview can
 * render every state from fixtures.
 */

import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, Bot, Check, ChevronRight, Copy, FolderGit2, KeyRound } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { AGENT_LOGOS, AgentLogoTile } from "@/components/connections/logos";
import AgentAbilities from "@/components/settings/AgentAbilities";
import { cn } from "@/lib/utils";
import { formatDate, relativeTime } from "@/lib/format";
import {
  AGENTS,
  AGENT_NAMES,
  KIND_AGENT,
  agentDisplayName,
  agentFromName,
  agentSetup,
  installLinks,
  tokenSetup,
} from "@/lib/mcpTokensApi";

const COPIED_MS = 1600;

// The wordmark is a name, not copy, set as the consent page sets it.
const WORDMARK = "duct";

const BAND = "mt-10 border-t border-border pt-8";

const STEP_DONE = "done";
const STEP_CURRENT = "current";
const STEP_NEXT = "next";

function CopyBox({ value, label, mono = true, leading = null, onCopy }) {
  const { t } = useLingui();
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative flex items-start gap-3 rounded-lg border border-border bg-muted/50">
      {leading && <div className="shrink-0 py-2.5 pl-3">{leading}</div>}
      <pre
        className={cn(
          "min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap py-2.5 pr-11 leading-relaxed text-foreground",
          leading ? "self-center" : "pl-3",
          mono ? "font-mono text-xs break-all" : "font-sans text-sm break-words",
        )}
        aria-label={label}
      >
        {value}
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn("absolute right-1 size-8", leading ? "inset-y-0 my-auto" : "top-1")}
        aria-label={copied ? t`Copied` : t`Copy`}
        onClick={() => {
          navigator.clipboard?.writeText(value).catch(() => {});
          setCopied(true);
          setTimeout(() => setCopied(false), COPIED_MS);
          onCopy?.();
        }}
      >
        {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
      </Button>
    </div>
  );
}

/** One logo tile per agent, as radio buttons: arrow keys move between them and
 *  a screen reader hears "Claude Code, radio button, 1 of 5". */
function AgentPicker({ value, onChange, connected }) {
  const { t } = useLingui();
  return (
    <fieldset className="mb-9">
      <legend className="mb-3 text-sm font-semibold text-foreground">
        <Trans>Which agent do you use?</Trans>
      </legend>
      <div className="grid grid-cols-3 gap-2 @md:grid-cols-5">
        {AGENTS.map((id) => (
          <label
            key={id}
            className={cn(
              "relative flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-border bg-background px-2 pb-2.5 pt-3 text-center transition-colors",
              "hover:border-foreground/30 has-checked:border-primary has-checked:bg-primary/5 has-checked:ring-1 has-checked:ring-primary",
              "has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50",
            )}
          >
            <input
              type="radio"
              name="duct-agent"
              value={id}
              checked={value === id}
              onChange={() => onChange(id)}
              className="sr-only"
            />
            <AgentLogoTile id={id} />
            <span className="text-xs font-medium leading-tight text-foreground">{AGENT_NAMES[id]}</span>
            {connected.has(id) && (
              <span className="absolute right-1.5 top-1.5 flex size-4 items-center justify-center rounded-full bg-success text-success-foreground">
                <Check className="size-2.5" strokeWidth={3.5} aria-hidden="true" />
                <span className="sr-only">{t`Connected`}</span>
              </span>
            )}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

const MARKER = {
  [STEP_DONE]: "border-primary bg-primary text-primary-foreground",
  [STEP_CURRENT]: "border-primary bg-background text-brand ring-4 ring-primary/15",
  [STEP_NEXT]: "border-border bg-background text-muted-foreground",
};

function Step({ number, title, state, last = false, children }) {
  // The body sits under the title once the column is 28rem wide, and under
  // the number below that, where an indent costs a quarter of the width the
  // snippets need; the rail between markers only exists in the first layout,
  // since below it the body would cover it. A container query, because the
  // sidebar and resizable panes decide this column's width, not the window.
  return (
    <li
      className="relative grid grid-cols-[1.75rem_1fr] gap-x-3 gap-y-3 pb-9 last:pb-0"
      aria-current={state === STEP_CURRENT ? "step" : undefined}
    >
      {!last && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute bottom-1.5 left-[0.8125rem] top-9 hidden w-0.5 rounded-full transition-colors duration-500 @md:block",
            state === STEP_DONE ? "bg-primary" : "bg-border",
          )}
        />
      )}
      <span
        aria-hidden="true"
        className={cn(
          "flex size-7 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
          MARKER[state],
        )}
      >
        {state === STEP_DONE ? <Check className="size-3.5" strokeWidth={3} /> : number}
      </span>
      <h2 className="self-center text-sm font-semibold text-foreground">
        {title}
        {state === STEP_DONE && (
          <span className="sr-only">
            {" "}
            <Trans>(done)</Trans>
          </span>
        )}
      </h2>
      <div className="col-span-2 min-w-0 space-y-3 @md:col-span-1 @md:col-start-2">{children}</div>
    </li>
  );
}

function Lead({ children }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function Hint({ children }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

function Code({ children }) {
  return <code className="rounded bg-muted px-1 font-mono text-foreground">{children}</code>;
}

/** The vendor's own "add this server?" screen, one click away. The paste
 *  route stays, folded, for anyone who keeps their config by hand. */
function OneClick({ href, onClick, children, manual }) {
  return (
    <>
      <Button asChild size="lg" className="w-full @md:w-auto">
        <a href={href} onClick={onClick}>
          {children}
          <ArrowUpRight data-icon="inline-end" className="size-4" aria-hidden="true" />
        </a>
      </Button>
      <details className="group">
        <summary className="flex w-fit cursor-pointer list-none items-center gap-1 text-xs text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
          <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />
          <Trans>Or add it by hand</Trans>
        </summary>
        <div className="mt-2.5 space-y-2.5">{manual}</div>
      </details>
    </>
  );
}

function InstallSteps({ agent, serverUrl, deepLinks, onDone }) {
  const { t } = useLingui();
  const setup = agentSetup(serverUrl);
  const links = installLinks(serverUrl);

  if (agent === "claude") {
    return (
      <>
        <Lead><Trans>Run this in your terminal.</Trans></Lead>
        <CopyBox value={setup.claude} label={t`Command for Claude Code`} onCopy={onDone} />
        <Hint>
          <Trans>
            Then, in Claude Code, run <Code>/mcp</Code>, pick duct and choose Authenticate.
          </Trans>
        </Hint>
      </>
    );
  }
  if (agent === "codex") {
    return (
      <>
        <Lead><Trans>Run these in your terminal. The second one opens your browser.</Trans></Lead>
        <CopyBox value={setup.codex} label={t`Commands for Codex`} onCopy={onDone} />
      </>
    );
  }
  if (agent === "cursor") {
    const manual = (
      <>
        <Hint>
          <Trans>Add this to <Code>~/.cursor/mcp.json</Code>.</Trans>
        </Hint>
        <CopyBox value={setup.cursor} label={t`Settings for Cursor`} onCopy={onDone} />
      </>
    );
    return (
      <>
        {deepLinks ? (
          <OneClick href={links.cursor} onClick={onDone} manual={manual}>
            <Trans>Add to Cursor</Trans>
          </OneClick>
        ) : (
          manual
        )}
        <Hint><Trans>Then sign in from duct&apos;s entry in Cursor&apos;s MCP settings.</Trans></Hint>
      </>
    );
  }
  if (agent === "vscode") {
    const manual = (
      <>
        <Hint>
          <Trans>
            Run <strong className="font-medium text-foreground">MCP: Add Server</strong> from the Command
            Palette, choose HTTP, paste this address, name it duct and choose Global.
          </Trans>
        </Hint>
        <CopyBox value={setup.vscode} label={t`Address for VS Code`} onCopy={onDone} />
      </>
    );
    return deepLinks ? (
      <OneClick href={links.vscode} onClick={onDone} manual={manual}>
        <Trans>Install in VS Code</Trans>
      </OneClick>
    ) : (
      manual
    );
  }
  return (
    <>
      <Lead><Trans>Run these in your terminal. The second one opens your browser.</Trans></Lead>
      <CopyBox value={setup.opencode} label={t`Commands for OpenCode`} onCopy={onDone} />
    </>
  );
}

/** Duct's consent page in miniature, so it is recognised when it opens.
 *  Decorative: the sentence above it says the same thing in words. */
function ConsentPreview({ agentId }) {
  const agent = AGENT_NAMES[agentId];
  return (
    <div
      aria-hidden="true"
      className="w-full max-w-xs overflow-hidden rounded-lg border border-border bg-background shadow-xs"
    >
      <div className="flex items-center gap-1 border-b border-border bg-muted/60 px-2.5 py-1.5">
        <span className="size-1.5 rounded-full bg-muted-foreground/40" />
        <span className="size-1.5 rounded-full bg-muted-foreground/40" />
        <span className="size-1.5 rounded-full bg-muted-foreground/40" />
      </div>
      <div className="space-y-3 p-3.5">
        <div className="flex items-center gap-2">
          <AgentLogoTile id={agentId} className="size-7 rounded-md [&_img]:size-4 [&_svg]:size-4" />
          <span className="h-px w-5 bg-border" />
          <span className="flex items-center gap-1">
            <span className="font-serif text-sm tracking-tight text-foreground">{WORDMARK}</span>
            <span className="size-1.5 rounded-full bg-[var(--orange)]" />
          </span>
        </div>
        <p className="font-serif text-sm leading-snug text-foreground">
          <Trans>
            Allow <em className="text-brand">{agent}</em> to use your Duct account?
          </Trans>
        </p>
        <div className="flex justify-end gap-1.5 text-xs">
          <span className="rounded-md border border-border px-2.5 py-1 text-muted-foreground">
            <Trans>Cancel</Trans>
          </span>
          <span className="rounded-md bg-primary px-2.5 py-1 font-semibold text-primary-foreground ring-2 ring-primary/30 ring-offset-2 ring-offset-background">
            <Trans>Allow</Trans>
          </span>
        </div>
      </div>
    </div>
  );
}

/** What the page knows about the sign-in, in one line: waiting for it, done,
 *  or stopped waiting with a way to look again. Nothing before step 1. */
function SignInStatus({ agentId, fresh, watching, started, onWatch }) {
  const { t } = useLingui();
  const name = AGENT_NAMES[agentId];
  if (fresh) {
    const rowName = agentDisplayName(fresh.name);
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-foreground">
        <span className="flex size-5 items-center justify-center rounded-full bg-success text-success-foreground">
          <Check className="size-3" strokeWidth={3} aria-hidden="true" />
        </span>
        {/* One span, so the flex gap does not split the sentence at the name. */}
        <span>
          <Trans>
            <strong className="font-medium">{rowName}</strong> is connected.
          </Trans>
        </span>
      </p>
    );
  }
  if (watching) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner className="size-4 text-brand" />
        {t`Waiting for ${name} to sign in…`}
      </p>
    );
  }
  if (!started) return null;
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
      <Trans>Not signed in yet.</Trans>
      <Button type="button" variant="link" size="sm" className="h-auto px-0" onClick={() => onWatch?.(true)}>
        <Trans>Check again</Trans>
      </Button>
    </p>
  );
}

function FlowNode({ tile, title, caption }) {
  return (
    <li className="flex min-w-0 items-center gap-3 @xl:flex-1">
      <span
        aria-hidden="true"
        className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-foreground [&_img]:size-6 [&_svg]:size-6"
      >
        {tile}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{title}</span>
        <span className="block text-xs text-muted-foreground">{caption}</span>
      </span>
    </li>
  );
}

function FlowArrow() {
  return (
    <li aria-hidden="true" className="flex w-10 shrink-0 justify-center text-muted-foreground @xl:w-auto @xl:self-center">
      <ArrowRight className="size-4 rotate-90 @xl:rotate-0" />
    </li>
  );
}

/**
 * Why connect one, before how: what flows where, what the person gets out of
 * it, and the same can / can never the consent page will show. Without this
 * the page was a set of instructions for a reason it never gave. The middle
 * node follows the picker, so the drawing names the reader's own agent.
 */
function WhyConnect({ agentId }) {
  const { t } = useLingui();
  const agentName = agentId ? AGENT_NAMES[agentId] : t`Your agent`;
  return (
    <section aria-label={t`What your agent does with Duct`} className="space-y-5">
      <Card variant="quiet" size="sm" className="gap-4">
        <ol className="flex flex-col gap-2 @xl:flex-row @xl:items-center @xl:gap-3">
          <FlowNode
            tile={<FolderGit2 strokeWidth={1.75} />}
            title={t`Your repo`}
            caption={t`README, docs, landing copy`}
          />
          <FlowArrow />
          <FlowNode
            tile={agentId ? AGENT_LOGOS[agentId] : <Bot strokeWidth={1.75} />}
            title={agentName}
            caption={t`Reads it, drafts the profile`}
          />
          <FlowArrow />
          <FlowNode
            tile={
              <span className="flex items-baseline gap-0.5">
                <span className="font-serif text-base leading-none">{WORDMARK.charAt(0)}</span>
                <span className="size-1.5 rounded-full bg-[var(--orange)]" />
              </span>
            }
            title={t`Your Duct project`}
            caption={t`Audience, competitors, positioning`}
          />
        </ol>
        <p className="text-sm text-foreground">
          <Trans>
            Duct&apos;s briefs, audits and posts all start from this profile. Your repo knows things your
            homepage doesn&apos;t: who it&apos;s for, who it&apos;s up against, what&apos;s new.
          </Trans>
        </p>
      </Card>
      <AgentAbilities className="@xl:grid-cols-2" />
    </section>
  );
}

function SignInSteps({ agent, onAgentChange, serverUrl, agents, watching, deepLinks, onWatch }) {
  const { t } = useLingui();
  const [installed, setInstalled] = useState(null);
  const [prompted, setPrompted] = useState(false);
  // The agents already connected when the list first arrived. One that is not
  // among them signed in while this page was open: that is step 2, done.
  const [baseline, setBaseline] = useState(null);
  if (baseline === null && agents) setBaseline(new Set(agents.map((row) => row.id)));
  const fresh = baseline && agents ? agents.find((row) => !baseline.has(row.id)) : null;

  useEffect(() => {
    if (fresh && watching) onWatch?.(false);
  }, [fresh, watching, onWatch]);

  const connected = new Set((agents || []).map((row) => agentFromName(row.name)).filter(Boolean));
  const name = AGENT_NAMES[agent];
  const step1 = installed === agent || fresh ? STEP_DONE : STEP_CURRENT;
  const step2 = fresh ? STEP_DONE : step1 === STEP_DONE ? STEP_CURRENT : STEP_NEXT;
  const step3 = prompted ? STEP_DONE : step2 === STEP_DONE ? STEP_CURRENT : STEP_NEXT;

  function markInstalled() {
    setInstalled(agent);
    if (!fresh) onWatch?.(true);
  }

  return (
    <>
      <AgentPicker value={agent} onChange={onAgentChange} connected={connected} />
      <ol>
        <Step number={1} state={step1} title={t`Add Duct to ${name}`}>
          <InstallSteps agent={agent} serverUrl={serverUrl} deepLinks={deepLinks} onDone={markInstalled} />
        </Step>

        <Step number={2} state={step2} title={t`Allow it in your browser`}>
          <Lead>
            <Trans>{name} opens Duct in your browser. Check the name it shows, then choose Allow.</Trans>
          </Lead>
          <ConsentPreview agentId={agent} />
          <SignInStatus
            agentId={agent}
            fresh={fresh}
            watching={watching}
            started={installed !== null}
            onWatch={onWatch}
          />
        </Step>

        <Step number={3} state={step3} title={t`Ask it to set up your project`} last>
          {/* In the reader's language: the agent understands any of them,
              and a prompt is easier to trust when you can read it. */}
          <CopyBox
            value={t`Set up this product in Duct.`}
            label={t`First prompt`}
            mono={false}
            leading={<AgentLogoTile id={agent} className="size-7 rounded-md [&_img]:size-4 [&_svg]:size-4" />}
            onCopy={() => setPrompted(true)}
          />
          <Hint>
            <Trans>
              It reads your README and docs, shows you what it will send, then drafts the project. Review it in
              Duct afterwards; every field says where it came from.
            </Trans>
          </Hint>
          <Hint>
            <Trans>
              Ask the same in any other repo, or after a launch. It updates that product&apos;s project, or starts
              one. To change something you set, just ask; you can undo it from Activity.
            </Trans>
          </Hint>
        </Step>
      </ol>
    </>
  );
}

/** One connected agent or one pasted token. An agent's access token changes
 *  every hour, so it shows no hint; a token's last four tell two apart. */
function CredentialRow({ row, onRemove }) {
  const { t } = useLingui();
  const agent = row.kind === KIND_AGENT;
  const rowName = agent ? agentDisplayName(row.name) : row.name;
  const kind = agent ? agentFromName(row.name) : null;
  const used = relativeTime(row.last_used_at, { fallbackAfterDays: 7 });
  const created = formatDate(row.created_at);
  const expires = formatDate(row.expires_at);
  const Icon = agent ? Bot : KeyRound;
  return (
    <li className="flex items-center gap-3 border-b border-border/60 py-2.5 last:border-b-0">
      {kind ? (
        <AgentLogoTile id={kind} className="size-8 rounded-md [&_img]:size-4 [&_svg]:size-4" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-muted/50 text-muted-foreground"
        >
          <Icon className="size-4" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-foreground">{rowName}</p>
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

export default function AgentAccess({
  serverUrl,
  tokens,
  minted = null,
  creating = false,
  error = "",
  signInAvailable = true,
  watching = false,
  deepLinks = true,
  onCreate,
  onRevoke,
  onWatch,
}) {
  const { t } = useLingui();
  const [name, setName] = useState("");
  const [agent, setAgent] = useState(AGENTS[0]);
  const { confirm, dialog } = useConfirm();
  const agents = tokens?.filter((row) => row.kind === KIND_AGENT) ?? null;
  const pasted = tokens?.filter((row) => row.kind !== KIND_AGENT) ?? null;
  const withToken = minted ? tokenSetup(serverUrl, minted.token) : null;

  async function remove(row) {
    const agent = row.kind === KIND_AGENT;
    const rowName = agent ? agentDisplayName(row.name) : row.name;
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
      <WhyConnect agentId={signInAvailable ? agent : null} />
      {/* Three bands, each behind the same rule: why, then setting it up,
          then the token fallback. Whitespace alone read as one long list
          running from the can / can never lines straight into the picker. */}
      <div className={BAND}>
        {signInAvailable ? (
          <>
            <SignInSteps
              agent={agent}
              onAgentChange={setAgent}
              serverUrl={serverUrl}
              agents={agents}
              watching={watching}
              deepLinks={deepLinks}
              onWatch={onWatch}
            />
            <h2 className="mb-1 mt-12 text-sm font-semibold text-foreground"><Trans>Connected agents</Trans></h2>
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
      </div>

      <section aria-labelledby="agent-token-heading" className={BAND}>
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
