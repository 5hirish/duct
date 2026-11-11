"use client";

// The agent wants to run a tool on an MCP server the user connected, and either
// the server does not mark the tool read-only or it is a server added by
// address, whose "read-only" Duct does not take on trust. The run is parked
// until someone says yes or no; `why` says which rule stopped it (backend
// agents/core/mcp_tools.py). Two content tools park on the same card, each
// with its own words: the TikTok search, because it spends the project's
// Apify credits (agents/content/discover.py), and every publish, because a
// post in front of people is the one thing the agent cannot take back
// (agents/content/publishing.publish_card).
//
// A publish card shows every word that goes out, whole, and carries a
// fingerprint of it; Approve sends the fingerprint back, so an edit made
// after the card appeared is shown again instead of sent.
//
// The card shows what the person needs to decide and nothing else: whose tool,
// which tool, the agent's one-sentence reason, and exactly what would be sent.
// The arguments start folded, because most of the time the reason is enough,
// and are one click away when it is not. They arrive whole: the backend
// refuses a call too long to show rather than cutting it, so what is approved
// is what was shown. Skip is a real button: the agent is told, carries on
// without the call and says what it could not do.

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Trans } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import EntityAvatar from "@/components/connections/EntityAvatar";
import { serverSite } from "@/lib/mcpServers";

const EMPTY_ARGUMENTS = new Set(["", "{}"]);
// Backend WHY_ADDED_BY_ADDRESS and WHY_ALWAYS_ASKS (agents/core/mcp_tools.py).
const WHY_ADDED_BY_ADDRESS = "added_by_address";
const WHY_ALWAYS_ASKS = "always_asks";
// Backend WHY_SPENDS_CREDITS (agents/content/discover.py).
const WHY_SPENDS_CREDITS = "spends_credits";
// Backend WHY_PUBLISHES (agents/content/publishing.py).
const WHY_PUBLISHES = "publishes";

export default function ToolApproval({ request, onAnswer, disabled }) {
  // A publish opens with what goes out showing: where and when are the
  // decision, not a detail behind a click.
  const [open, setOpen] = useState(request.why === WHY_PUBLISHES);
  const serverName = request.server_name || request.server || "";
  const toolName = request.tool_title || request.tool || "";
  const preview = String(request.arguments || "").trim();
  const hasArguments = !EMPTY_ARGUMENTS.has(preview);
  const spends = request.why === WHY_SPENDS_CREDITS;
  const publishes = request.why === WHY_PUBLISHES;

  return (
    <div className="my-3 space-y-3 rounded-xl border border-warning/30 bg-warning/5 p-4">
      <div className="flex items-start gap-2.5">
        <EntityAvatar url={serverSite(request.server_url)} name={serverName} />
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-semibold break-words">
            {publishes ? (
              <Trans>Publish this post through {serverName}?</Trans>
            ) : spends ? (
              <Trans>Search TikTok with {serverName}?</Trans>
            ) : (
              <Trans>Run {toolName} on {serverName}?</Trans>
            )}
          </p>
          {/* The agent's own sentence, in the language it is writing to them
              in, or for a publish the post's own topic. Not translated: it
              was never ours. */}
          {request.reason && <p className="text-xs text-muted-foreground">{request.reason}</p>}
        </div>
      </div>

      {hasArguments && (
        <div className="pl-7.5">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="inline-flex min-h-6 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronRight className={`size-3 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden="true" />
            {publishes ? <Trans>What goes out, and when</Trans> : <Trans>What it will send</Trans>}
          </button>
          {open && (
            <pre className="mt-1.5 max-h-56 overflow-auto rounded-md border border-border bg-card p-2.5 font-mono text-2xs leading-relaxed whitespace-pre-wrap break-words">
              {preview}
            </pre>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pl-7.5">
        {/* A card that carries a fingerprint (a publish) sends it back with the
            yes: the backend sends only the version this card showed. */}
        <Button
          size="sm"
          onClick={() => onAnswer(request.fingerprint ? { approved: true, fingerprint: request.fingerprint } : { approved: true })}
          disabled={disabled}
        >
          <Trans>Approve</Trans>
        </Button>
        <Button size="sm" variant="secondary" onClick={() => onAnswer({ approved: false })} disabled={disabled}>
          <Trans>Skip</Trans>
        </Button>
      </div>
      <p className="pl-7.5 text-2xs text-pretty text-muted-foreground">
        {publishes ? (
          <Trans>
            Publishing puts this post in front of people, so Duct asks every time. Skip and nothing is sent; the
            post stays as it is.
          </Trans>
        ) : spends ? (
          <Trans>
            Each search uses this project&rsquo;s {serverName} credits, so Duct asks first. Skip and the agent
            carries on from what you saved.
          </Trans>
        ) : request.why === WHY_ADDED_BY_ADDRESS ? (
          <Trans>
            You added {serverName} by address, so Duct asks before every call to it. Skip and the agent
            carries on without it.
          </Trans>
        ) : request.why === WHY_ALWAYS_ASKS ? (
          <Trans>
            {serverName} can reach your account&rsquo;s secrets, so Duct asks before every call to it. Skip and
            the agent carries on without it.
          </Trans>
        ) : (
          <Trans>
            {serverName} doesn’t mark this tool as read-only, so Duct asks first. Skip and the agent
            carries on without it.
          </Trans>
        )}
      </p>
    </div>
  );
}
