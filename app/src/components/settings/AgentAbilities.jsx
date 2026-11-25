"use client";

/**
 * What an agent connected to Duct's MCP server can and can never do, in full,
 * on the settings page that explains why to connect one. The consent page
 * says the same promise in fewer words (AgentGrantPicker's two choices and
 * one reassurance row), because a person deciding in a popup reads less than
 * one exploring Settings; both take their capability words from
 * `lib/agentScopes.js`, so they cannot promise different things. When the
 * server gains a tool (backend `service/mcp_server/`), that file and this one
 * are the lines to change. The edit line is the maintainer's own wording
 * (issue #512): editing on request is a promise only because every edit can
 * be undone from Activity.
 *
 * Separate labelled lists, not one: a check and a cross are the only
 * difference otherwise, and a skim reads every line as a grant.
 */

import { Check, Plus, X } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { cn } from "@/lib/utils";
import { SCOPE_ABILITIES, WORK_SCOPES } from "@/lib/agentScopes";

const MARKS = { yes: Check, maybe: Plus, never: X };

function Ability({ mark = "yes", children }) {
  const Icon = MARKS[mark];
  return (
    <li className="flex items-start gap-2.5 text-sm text-foreground">
      <Icon
        className={cn("mt-0.5 size-4 shrink-0", mark === "yes" ? "text-success" : "text-muted-foreground")}
        aria-hidden="true"
      />
      <span>{children}</span>
    </li>
  );
}

function Group({ title, children, className }) {
  return (
    <div className={className}>
      <p className="mb-1.5 text-xs font-semibold text-muted-foreground">{title}</p>
      <ul className="space-y-2">{children}</ul>
    </div>
  );
}

export default function AgentAbilities({ className, workTier = true }) {
  const { i18n } = useLingui();
  return (
    <div className={cn("grid gap-4", className)}>
      <Group title={<Trans>It will be able to set up your project</Trans>}>
        <Ability><Trans>See your projects and what Duct knows about each</Trans></Ability>
        <Ability><Trans>Draft a project&apos;s description, audience and competitors</Trans></Ability>
        <Ability>
          <Trans>Edit your project when you ask, and every edit can be undone in Duct</Trans>
        </Ability>
      </Group>
      <Group title={<Trans>It can never</Trans>}>
        <Ability mark="never"><Trans>Approve or apply changes to your tools, or connect new ones</Trans></Ability>
        <Ability mark="never"><Trans>Publish a post or send anything in your name</Trans></Ability>
        <Ability mark="never"><Trans>See your keys or passwords</Trans></Ability>
      </Group>
      {workTier && (
        <Group
          className="@xl:col-span-2"
          title={<Trans>If you also let it work on your behalf, only what you tick</Trans>}
        >
          {WORK_SCOPES.map((scope) => (
            <Ability key={scope} mark="maybe">{i18n._(SCOPE_ABILITIES[scope])}</Ability>
          ))}
        </Group>
      )}
    </div>
  );
}
