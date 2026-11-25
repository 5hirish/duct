"use client";

/**
 * The second tier, "Work on your behalf", as a choice the person makes: off
 * unless they switch it on, then which capabilities and which projects.
 * The consent page and the token form both render it, with the words from
 * `lib/agentScopes.js`, so an agent that signs in and one given a token are
 * offered the same things in the same terms.
 *
 * Controlled and presentational: the parent holds the grant
 * (`initialGrant` / `grantBody` in agentScopes.js) and sends it. Three of
 * the six capabilities act on the person's accounts, content or money, so
 * they carry a mark and are never ticked for them, even when the agent
 * asked; the mark says so where the agent did.
 */

import { Trans, useLingui } from "@lingui/react/macro";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
  DELIBERATE_SCOPES,
  SCOPE_ABILITIES,
  WORK_SCOPES,
  grantProblem,
  toggleScope,
} from "@/lib/agentScopes";

// Every fieldset here is min-w-0: a fieldset's default minimum width is its
// content's, so one long project name widened the whole page at 390px even
// though the name itself truncates.
function ProjectChoice({ grant, projects, idPrefix, onChange }) {
  const { t } = useLingui();
  const only = Array.isArray(grant.projectIds);
  const chosen = new Set(grant.projectIds || []);
  const set = (projectIds) => onChange({ ...grant, projectIds });
  return (
    <fieldset className="min-w-0 space-y-2">
      <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">
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
        <span><Trans>All your projects, including ones you add later</Trans></span>
      </label>
      <label className="flex items-start gap-2.5 text-sm text-foreground">
        <input
          type="radio"
          name={`${idPrefix}-projects`}
          className="mt-0.5 size-4 shrink-0 accent-primary"
          checked={only}
          onChange={() => set(projects?.length === 1 ? [projects[0].id] : [])}
        />
        <span>
          <Trans>Only the ones I pick</Trans>
          <span className="block text-xs text-muted-foreground">
            <Trans>It won&apos;t see or set up any other project.</Trans>
          </span>
        </span>
      </label>
      {only && (
        <div className="ml-6.5 max-h-48 min-w-0 space-y-2 overflow-y-auto">
          {projects == null ? (
            <p className="text-xs text-muted-foreground"><Trans>Loading your projects…</Trans></p>
          ) : projects.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              <Trans>You have no projects yet. Allow all, and it can set up your first one.</Trans>
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
      {grantProblem(grant) === "no_projects" && (
        <p className="ml-6.5 text-xs text-destructive" role="alert">
          <Trans>Pick at least one project, or allow all of them.</Trans>
        </p>
      )}
    </fieldset>
  );
}

export default function AgentGrantPicker({
  grant,
  onChange,
  projects = null,
  requested = [],
  idPrefix = "grant",
  className,
}) {
  const { i18n } = useLingui();
  const asked = new Set(requested);
  return (
    <section
      aria-labelledby={`${idPrefix}-work-title`}
      className={cn("rounded-lg border border-border p-3.5", grant.work && "bg-muted/40", className)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p id={`${idPrefix}-work-title`} className="text-sm font-semibold text-foreground">
            <Trans>Also let it work on your behalf</Trans>
          </p>
          <p className="text-xs text-muted-foreground">
            <Trans>Only what you tick, on the projects you choose.</Trans>
          </p>
        </div>
        <Switch
          checked={grant.work}
          onCheckedChange={(on) => onChange({ ...grant, work: on })}
          aria-labelledby={`${idPrefix}-work-title`}
          className="mt-0.5"
        />
      </div>

      {grant.work && (
        <div className="mt-4 space-y-5">
          <fieldset className="min-w-0 space-y-2.5">
            <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">
              <Trans>What it can do</Trans>
            </legend>
            {WORK_SCOPES.map((scope) => {
              const id = `${idPrefix}-scope-${scope}`;
              const deliberate = DELIBERATE_SCOPES.includes(scope);
              return (
                <div key={scope} className="flex items-start gap-2.5">
                  <Checkbox
                    id={id}
                    className="mt-0.5"
                    checked={grant.scopes.includes(scope)}
                    onCheckedChange={(on) => onChange({ ...grant, scopes: toggleScope(grant.scopes, scope, on === true) })}
                  />
                  <label htmlFor={id} className="text-sm leading-snug text-foreground">
                    {i18n._(SCOPE_ABILITIES[scope])}
                    {deliberate && (
                      <span className="mt-1 flex flex-wrap gap-1.5">
                        <Badge variant="outline" className="font-normal text-muted-foreground">
                          <Trans>Off unless you tick it</Trans>
                        </Badge>
                        {asked.has(scope) && (
                          <Badge variant="outline" className="font-normal text-muted-foreground">
                            <Trans>The agent asked for this</Trans>
                          </Badge>
                        )}
                      </span>
                    )}
                  </label>
                </div>
              );
            })}
          </fieldset>
          <ProjectChoice grant={grant} projects={projects} idPrefix={idPrefix} onChange={onChange} />
        </div>
      )}
    </section>
  );
}
