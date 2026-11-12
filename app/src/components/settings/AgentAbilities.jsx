"use client";

/**
 * What an agent connected to Duct's MCP server can and can never do, said the
 * same way in the two places a person decides: the settings page that
 * explains why to connect one, and the consent page the agent opens. One
 * component so the promise cannot drift between them; when the server gains
 * a tool (backend `service/mcp_server/tools.py`), this is the line to change.
 * The edit line is the maintainer's own wording (issue #512): editing on
 * request is a promise only because every edit can be undone from Activity.
 *
 * Two labelled lists, not one: a check and a cross are the only difference
 * otherwise, and a skim reads every line as a grant.
 */

import { Check, X } from "lucide-react";
import { Trans } from "@lingui/react/macro";
import { cn } from "@/lib/utils";

function Ability({ allowed, children }) {
  const Icon = allowed ? Check : X;
  return (
    <li className="flex items-start gap-2.5 text-sm text-foreground">
      <Icon
        className={cn("mt-0.5 size-4 shrink-0", allowed ? "text-success" : "text-muted-foreground")}
        aria-hidden="true"
      />
      <span>{children}</span>
    </li>
  );
}

export default function AgentAbilities({ className }) {
  return (
    <div className={cn("grid gap-4", className)}>
      <div>
        <p className="mb-1.5 text-xs font-semibold text-muted-foreground"><Trans>It will be able to</Trans></p>
        <ul className="space-y-2">
          <Ability allowed><Trans>See your projects and what Duct knows about each</Trans></Ability>
          <Ability allowed><Trans>Draft a project&apos;s description, audience and competitors</Trans></Ability>
          <Ability allowed>
            <Trans>Edit your project when you ask, and every edit can be undone in Duct</Trans>
          </Ability>
        </ul>
      </div>
      <div>
        <p className="mb-1.5 text-xs font-semibold text-muted-foreground"><Trans>It can never</Trans></p>
        <ul className="space-y-2">
          <Ability allowed={false}><Trans>Approve or apply changes to your tools, or connect new ones</Trans></Ability>
          <Ability allowed={false}><Trans>See your keys or passwords</Trans></Ability>
        </ul>
      </div>
    </div>
  );
}
