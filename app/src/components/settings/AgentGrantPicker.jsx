"use client";

/**
 * What an agent may do, as two choices a person can read in a glance:
 * "Help set up my projects" or "Work alongside me". Then which projects, as
 * one line. The detail is there for whoever wants it (Customise, Change) and
 * closed for everyone else, so the screen reads as an invitation rather than
 * a permissions form. Two levels of disclosure, never three (DESIGN.md).
 *
 * The consent page and the token form both render it, with the words from
 * `lib/agentScopes.js`, so an agent that signs in and one given a token are
 * offered the same things in the same terms.
 *
 * Controlled and presentational: the parent holds the grant
 * (`initialGrant` / `grantBody`) and sends it. The three extras act on the
 * person's accounts, content or money: they are never on unless the person
 * turns them on, and each one's hint carries its own reassurance ("you
 * approve every one"), which is what the warning pills used to shout. An
 * extra the agent asked for is named in one line, never pre-ticked.
 */

import { useId, useState } from "react";
import { Brain, ChartLine, ChevronDown, FileText, FolderOpen, ImageIcon, PenLine, SlidersHorizontal } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { plural } from "@lingui/core/macro";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import {
  DEFAULT_WORK_SCOPES,
  DELIBERATE_SCOPES,
  SCOPE_DATA,
  SCOPE_CHANGES,
  SCOPE_CONTENT,
  SCOPE_HINTS,
  SCOPE_MEDIA,
  SCOPE_MEMORY,
  SCOPE_NAMES,
  SCOPE_REPORTS,
  askedExtras,
  asksForWork,
  grantProblem,
  toggleScope,
} from "@/lib/agentScopes";

const ICONS = {
  [SCOPE_DATA]: ChartLine,
  [SCOPE_MEMORY]: Brain,
  [SCOPE_REPORTS]: FileText,
  [SCOPE_CHANGES]: SlidersHorizontal,
  [SCOPE_CONTENT]: PenLine,
  [SCOPE_MEDIA]: ImageIcon,
};

// A native radio, visually replaced: arrow keys, the group's name and the
// checked state come from the browser, and the ring follows keyboard focus
// on the row that holds it.
function ChoiceRow({ name, value, checked, onSelect, title, description, tag, children }) {
  return (
    <div
      className={cn(
        "rounded-lg border transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
        checked ? "border-primary bg-primary/5" : "border-border bg-background hover:bg-muted/50",
      )}
    >
      <label className="flex min-h-11 cursor-pointer items-start gap-3 px-3.5 py-3">
        <input type="radio" name={name} value={value} checked={checked} onChange={onSelect} className="sr-only" />
        <span
          aria-hidden="true"
          className={cn(
            "mt-0.5 size-4 shrink-0 rounded-full",
            checked ? "border-5 border-primary" : "border border-control bg-background",
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-medium text-foreground">{title}</span>
            {tag && (
              <Badge variant="secondary" className="font-normal">
                {tag}
              </Badge>
            )}
          </span>
          <span className="mt-0.5 block text-xs text-pretty text-muted-foreground">{description}</span>
        </span>
      </label>
      {children && <div className="px-3.5 pb-3.5 pl-10.5">{children}</div>}
    </div>
  );
}

function ScopeRow({ scope, grant, idPrefix, asked, agent, onChange }) {
  const { i18n, t } = useLingui();
  const Icon = ICONS[scope];
  const id = `${idPrefix}-scope-${scope}`;
  return (
    <div className="flex items-start gap-2.5">
      <Checkbox
        id={id}
        className="mt-0.5"
        checked={grant.scopes.includes(scope)}
        onCheckedChange={(on) => onChange({ ...grant, scopes: toggleScope(grant.scopes, scope, on === true) })}
      />
      <label htmlFor={id} className="min-w-0 text-sm leading-snug text-foreground">
        <span className="flex items-center gap-1.5 font-medium">
          <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          {i18n._(SCOPE_NAMES[scope])}
        </span>
        <span className="block text-xs text-pretty text-muted-foreground">
          {i18n._(SCOPE_HINTS[scope])}
          {asked && <span className="text-brand">{" · "}{agent ? t`${agent} asked for this` : t`Asked for`}</span>}
        </span>
      </label>
    </div>
  );
}

function WorkDetails({ grant, idPrefix, requested, agent, defaultCustomise, onChange }) {
  const { i18n } = useLingui();
  const extrasAsked = askedExtras(requested);
  const [open, setOpen] = useState(defaultCustomise);
  const askedNames = extrasAsked.map((scope) => i18n._(SCOPE_NAMES[scope])).join(", ");
  const panelId = useId();
  const included = grant.scopes;
  return (
    <div className="space-y-3">
      {/* The summary while Customise is closed; open, the Included list
          below says the same thing with its switches. */}
      {!open && (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {included.length === 0 ? (
          <span className="text-xs text-muted-foreground">
            <Trans>Nothing extra yet: turn something on in Customise.</Trans>
          </span>
        ) : (
          included.map((scope) => {
            const Icon = ICONS[scope];
            return (
              <span key={scope} className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Icon className="size-3.5 text-brand" aria-hidden="true" />
                {i18n._(SCOPE_NAMES[scope])}
              </span>
            );
          })
        )}
      </div>
      )}
      {/* An extra the agent asked for stays off; one line says so, so the
          ask is seen without opening the whole list. */}
      {!open && extrasAsked.length > 0 && (
        <p className="text-xs text-pretty text-muted-foreground">
          {agent ? (
            <Trans>
              {agent} also asked for <span className="font-medium text-foreground">{askedNames}</span>. Turn it on
              in Customise if you want it.
            </Trans>
          ) : (
            <Trans>
              It also asked for <span className="font-medium text-foreground">{askedNames}</span>. Turn it on in
              Customise if you want it.
            </Trans>
          )}
        </p>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Trans>Customise</Trans>
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden="true" />
      </button>
      {open && (
        <div id={panelId} className="space-y-4">
          <fieldset className="min-w-0 space-y-2.5">
            <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">
              <Trans>Included</Trans>
            </legend>
            {DEFAULT_WORK_SCOPES.map((scope) => (
              <ScopeRow key={scope} scope={scope} grant={grant} idPrefix={idPrefix} onChange={onChange} />
            ))}
          </fieldset>
          <fieldset className="min-w-0 space-y-2.5">
            <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">
              <Trans>Extras, off until you turn them on</Trans>
            </legend>
            {DELIBERATE_SCOPES.map((scope) => (
              <ScopeRow
                key={scope}
                scope={scope}
                grant={grant}
                idPrefix={idPrefix}
                asked={extrasAsked.includes(scope)}
                agent={agent}
                onChange={onChange}
              />
            ))}
          </fieldset>
        </div>
      )}
    </div>
  );
}

// Every fieldset here is min-w-0: a fieldset's default minimum width is its
// content's, so one long project name widened the whole page at 390px even
// though the name itself truncates.
function ProjectLine({ grant, projects, idPrefix, onChange }) {
  const { t } = useLingui();
  const only = Array.isArray(grant.projectIds);
  const [open, setOpen] = useState(only);
  const chosen = new Set(grant.projectIds || []);
  const set = (projectIds) => onChange({ ...grant, projectIds });
  const panelId = useId();
  const count = grant.projectIds?.length ?? 0;
  const summary = only ? plural(count, { one: "# project you picked", other: "# projects you picked" }) : t`All your projects`;
  return (
    <div className="min-w-0">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-foreground">
        <FolderOpen className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="min-w-0">
          <Trans>
            On: <strong className="font-medium">{summary}</strong>
          </Trans>
        </span>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="rounded text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {open ? <Trans>Done</Trans> : <Trans>Change</Trans>}
        </button>
      </p>
      {open && (
        <fieldset id={panelId} className="mt-2.5 min-w-0 space-y-2 pl-6">
          <legend className="sr-only">
            <Trans>Which projects</Trans>
          </legend>
          <label className="flex items-start gap-2.5 text-sm text-foreground">
            <input
              type="radio"
              name={`${idPrefix}-projects`}
              className="mt-0.5 size-4 shrink-0 accent-primary"
              checked={!only}
              onChange={() => set(null)}
            />
            <span><Trans>All, including ones you add later</Trans></span>
          </label>
          <label className="flex items-start gap-2.5 text-sm text-foreground">
            <input
              type="radio"
              name={`${idPrefix}-projects`}
              className="mt-0.5 size-4 shrink-0 accent-primary"
              checked={only}
              onChange={() => set(projects?.length === 1 ? [projects[0].id] : [])}
            />
            <span><Trans>Only the ones I pick</Trans></span>
          </label>
          {only && (
            <div className="ml-6.5 max-h-48 min-w-0 space-y-2 overflow-y-auto">
              {projects == null ? (
                <p className="text-xs text-muted-foreground"><Trans>Loading your projects…</Trans></p>
              ) : projects.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  <Trans>You have no projects yet. Choose All, and it can set up your first one.</Trans>
                </p>
              ) : (
                projects.map((project) => {
                  const id = `${idPrefix}-project-${project.id}`;
                  return (
                    <div key={project.id} className="flex min-w-0 items-center gap-2.5">
                      <Checkbox
                        id={id}
                        checked={chosen.has(project.id)}
                        onCheckedChange={(on) =>
                          set(
                            on === true
                              ? [...(grant.projectIds || []), project.id]
                              : (grant.projectIds || []).filter((p) => p !== project.id),
                          )
                        }
                      />
                      <label htmlFor={id} className="min-w-0 truncate text-sm text-foreground">
                        {project.name || t`Untitled project`}
                      </label>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </fieldset>
      )}
      {grantProblem(grant) === "no_projects" && (
        <p className="mt-1.5 pl-6 text-xs text-destructive" role="alert">
          <Trans>Pick at least one project, or choose All.</Trans>
        </p>
      )}
    </div>
  );
}

export default function AgentGrantPicker({
  grant,
  onChange,
  projects = null,
  requested = [],
  agent = "",
  idPrefix = "grant",
  // Open Customise on the first render. For /preview's scene of it; the
  // real pages always start closed.
  defaultCustomise = false,
  className,
}) {
  const { t } = useLingui();
  const name = `${idPrefix}-tier`;
  const asked = asksForWork(requested);
  return (
    <div className={cn("space-y-4", className)}>
      <div role="radiogroup" aria-label={t`What it can do`} className="space-y-2">
        <ChoiceRow
          name={name}
          value="setup"
          checked={!grant.work}
          onSelect={() => onChange({ ...grant, work: false })}
          title={t`Help set up my projects`}
          description={t`Reads and drafts your projects' details.`}
        />
        <ChoiceRow
          name={name}
          value="work"
          checked={grant.work}
          onSelect={() => onChange({ ...grant, work: true })}
          title={t`Work alongside me`}
          description={t`Also reads your connected tools, remembers what matters, and writes briefs with Duct's method.`}
          tag={asked ? (agent ? t`Asked for by ${agent}` : t`Asked for`) : null}
        >
          {grant.work && (
            <WorkDetails
              grant={grant}
              idPrefix={idPrefix}
              requested={requested}
              agent={agent}
              defaultCustomise={defaultCustomise}
              onChange={onChange}
            />
          )}
        </ChoiceRow>
      </div>
      <ProjectLine grant={grant} projects={projects} idPrefix={idPrefix} onChange={onChange} />
    </div>
  );
}
