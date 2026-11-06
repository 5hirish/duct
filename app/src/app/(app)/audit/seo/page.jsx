"use client";

import { useCallback, useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { loadPreferences } from "@/lib/userPreferences";
import { getActiveProject } from "@/lib/projects";
import { ReportMode, DEFAULT_AUDIT_TEMPLATE_ID } from "@/lib/audit";
import { archiveAgentConversation, listAgentConversations } from "@/lib/api";
import { hasAuthToken } from "@/lib/authFetch";
import { startAuditResume } from "@/lib/auditResume";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Page, PageHeader, Section } from "@/components/ui/page";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronDown } from "lucide-react";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CONTENT_TYPES = [
  { value: "blog", label: msg`Blog / Articles` },
  { value: "landing_pages", label: msg`Landing Pages` },
  { value: "product_pages", label: msg`Product Pages` },
  { value: "docs", label: msg`Docs / Help` },
];

const EFFORT_OPTIONS = [
  { value: "low",    label: msg`Low`,    hint: msg`Faster, lighter` },
  { value: "medium", label: msg`Medium`, hint: msg`Balanced` },
  { value: "high",   label: msg`High`,   hint: msg`Deeper analysis` },
];

/** What a past audit's run is doing, from the list route — so one stuck on a
 *  question or a failure says so before it is opened. Idle says nothing. */
function auditBadge(conv) {
  switch (conv.run_status) {
    case "running": return { label: msg`Working…`, className: "text-brand" };
    case "paused": return { label: msg`Needs you`, className: "text-warning" };
    case "failed": return { label: msg`Failed`, className: "text-destructive" };
    case "cancelled": return { label: msg`Stopped`, className: "text-muted-foreground" };
    default: return null;
  }
}

export default function SeoAuditSetupPage() {
  const { t, i18n } = useLingui();
  const router = useRouter();
  const [url, setUrl]                   = useState("");
  const [businessName, setBusinessName] = useState("");
  const [description, setDescription]   = useState("");
  const [goals, setGoals]               = useState("");
  const [keywords, setKeywords]         = useState("");
  const [competitors, setCompetitors]   = useState("");
  const [contentType, setContentType]   = useState("");
  const [effort, setEffort]             = useState("medium");
  const [adaptiveThinking, setAdaptiveThinking] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [activeProject, setActiveProject] = useState(null);
  const [useProjectContext, setUseProjectContext] = useState(true);
  // "Don't remember this session" — the one-off counterpart to the standing
  // pause switch on /project/[id]/memory.
  const [remember, setRemember] = useState(true);
  const [prevAudits, setPrevAudits] = useState([]);

  // Previous audits for this project (persisted conversations) — signed-in only.
  const loadPrevAudits = useCallback(() => {
    if (!activeProject?.id || !hasAuthToken()) return;
    listAgentConversations("audit_seo", { projectId: activeProject.id })
      .then((rows) => setPrevAudits((rows || []).filter((c) => c.last_seq > 0)))
      .catch(() => {});
  }, [activeProject]);

  useEffect(() => {
    loadPrevAudits();
  }, [loadPrevAudits]);

  // Archive a past audit conversation: it leaves this list (and resume), but
  // its report artifacts stay in the library untouched.
  async function archivePrevAudit(conversationId) {
    setPrevAudits((rows) => rows.filter((c) => c.id !== conversationId)); // optimistic
    try {
      await archiveAgentConversation("audit_seo", conversationId);
    } catch {
      loadPrevAudits(); // restore on failure
    }
  }

  useEffect(() => {
    const project = getActiveProject();
    if (!project) return;
    setActiveProject(project);
    applyProjectContext(project);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The durable competitor field users actually fill in project context is
  // `compare_against` (a comma-joined string). `competitors` is a richer
  // [{ name, differentiator }] list with no editor yet, so fall back to its
  // names only when present — never join the raw objects (that prints
  // "[object Object]").
  function projectCompetitors(project) {
    const competition = project.competition || {};
    if (typeof competition.compare_against === "string" && competition.compare_against.trim()) {
      return competition.compare_against.trim();
    }
    return (Array.isArray(competition.competitors) ? competition.competitors : [])
      .map((entry) => (typeof entry === "string" ? entry : entry?.name || ""))
      .filter(Boolean)
      .join(", ");
  }

  // Pre-fill the business-context fields from the saved project profile. Only
  // maps fields with a genuine project equivalent — there's no target-keywords
  // field in the profile, so keywords stay empty rather than borrowing the
  // unrelated competitor list.
  function applyProjectContext(project) {
    setUrl(project.company?.website_url || "");
    setBusinessName(project.company?.name || "");
    setDescription(project.company?.pitch || "");
    setGoals(project.targets?.north_star_metric || "");
    setCompetitors(projectCompetitors(project));
  }

  function toggleProjectContext(next) {
    setUseProjectContext(next);
    if (next && activeProject) {
      applyProjectContext(activeProject);
    } else {
      // Auditing a different business / competitor — drop everything sourced
      // from our own project (including our own site URL) so only what the user
      // types is used.
      setUrl("");
      setBusinessName("");
      setDescription("");
      setGoals("");
      setCompetitors("");
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (!url.trim()) { setError(t`Website URL is required.`); return; }
    setLoading(true);
    try {
      const params = {
        url: url.trim(),
        // Project scoping: report versions persist to the artifact library when
        // the audit belongs to the active project and the user is signed in.
        project_id: useProjectContext && activeProject?.id ? activeProject.id : null,
        business_context: {
          business_name:         businessName.trim(),
          business_description:  description.trim(),
          business_goals:        goals.trim(),
          target_keywords:       keywords.split(",").map(k => k.trim()).filter(Boolean),
          competitors:           competitors.split(",").map(c => c.trim()).filter(Boolean),
          primary_content_type:  contentType,
          // Richer fields from the saved project profile — only appended when the
          // audit is for this project. Skipped when auditing another business so
          // we don't leak our own context into someone else's report.
          ...(useProjectContext && activeProject ? {
            industry:              activeProject.company?.industry || "",
            business_model:        activeProject.company?.business_model || "",
            positioning_statement: activeProject.competition?.positioning_statement || "",
            audience_segment:      activeProject.audience?.primary_segment || "",
            brand_voice:           activeProject.brand_channels?.brand_voice || "",
            growth_stage:          activeProject.targets?.growth_stage_milestone || "",
          } : {}),
        },
        effort,
        adaptive_thinking: adaptiveThinking,
        remember,
        user_preferences: loadPreferences(),
        // Structured template report (matches the lead-magnet flow): the agent
        // calls SubmitAuditReport instead of streaming freeform <duct_artifact>
        // HTML. Backend default is "freehand"; this opts the app audit into the
        // same template the public audit uses.
        report_mode: ReportMode.TEMPLATE,
        template_id: DEFAULT_AUDIT_TEMPLATE_ID,
      };
      const sessionId = crypto.randomUUID();
      sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify(params));
      router.push(`/audit/seo/${sessionId}`);
    } catch (err) {
      setError(err.message || t`The audit didn't start. Check the address and try again.`);
      setLoading(false);
    }
  }

  const projectName = activeProject?.name || t`this project`;

  const field = "flex flex-col gap-2";
  const label = "text-sm font-medium";

  return (
    <Page width="narrow">
      <PageHeader
        title={<Trans>SEO Audit</Trans>}
        status={<Trans>Duct reads your site the way a search engine does, in about three minutes.</Trans>}
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* The field and its button are one row, like the front door: a
            single-field form over a full-width button reads as two steps. */}
        <Card size="lg" className="gap-3">
          <label className={label} htmlFor="url">
            <Trans>Site to audit</Trans>
          </label>
          <div className="flex flex-col gap-2 @md:flex-row">
            <Input
              id="url" type="url" placeholder={t`https://yoursite.com`}
              value={url} onChange={e => setUrl(e.target.value)} required
              className="h-10"
            />
            <Button type="submit" size="lg" disabled={loading} className="shrink-0">
              {loading ? <Trans>Starting…</Trans> : <Trans>Run audit</Trans>}
            </Button>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </Card>

        {/* Everything else is optional, so it waits behind one disclosure
            (NN/g: progressive disclosure, one level). It was seven fields,
            two switches and an "Advanced" fold, all open above the button. */}
        <Card variant="quiet" size="sm" className="gap-0">
          <button
            type="button"
            onClick={() => setAdvancedOpen(o => !o)}
            aria-expanded={advancedOpen}
            className="flex w-full items-center justify-between gap-3 rounded-md text-left text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          >
            <span>
              <Trans>Context and settings</Trans>
              <span className="ml-2 font-normal text-muted-foreground">
                {activeProject && useProjectContext
                  ? <Trans>Using {projectName}</Trans>
                  : <Trans>Optional</Trans>}
              </span>
            </span>
            <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", advancedOpen && "rotate-180")} aria-hidden />
          </button>

          {advancedOpen && (
            <div className="mt-5 flex flex-col gap-5">
              {activeProject && (
                <label className="flex items-start justify-between gap-4">
                  <span className="flex flex-col gap-0.5">
                    <span className={label}><Trans>Use {projectName}&apos;s context</Trans></span>
                    <span className="text-sm text-muted-foreground">
                      <Trans>Off to audit a competitor or another business.</Trans>
                    </span>
                  </span>
                  <Switch
                    className="mt-0.5 shrink-0"
                    checked={useProjectContext}
                    onCheckedChange={(next) => toggleProjectContext(next)}
                  />
                </label>
              )}

              {activeProject && useProjectContext && (
                <label className="flex items-start justify-between gap-4">
                  <span className="flex flex-col gap-0.5">
                    <span className={label}><Trans>Remember this audit</Trans></span>
                    <span className="text-sm text-muted-foreground">
                      {remember
                        ? <Trans>Reads project memory and writes back what it learns.</Trans>
                        : <Trans>A one-off. The report is still saved.</Trans>}
                    </span>
                  </span>
                  <Switch
                    className="mt-0.5 shrink-0"
                    checked={remember}
                    aria-label={t`Remember this audit`}
                    onCheckedChange={(next) => setRemember(next)}
                  />
                </label>
              )}

              <div className="grid grid-cols-1 gap-5 @md:grid-cols-2">
                <div className={field}>
                  <label className={label} htmlFor="biz-name"><Trans>Business name</Trans></label>
                  <Input id="biz-name" type="text" placeholder={activeProject?.name || t`Your business`} value={businessName}
                    onChange={e => setBusinessName(e.target.value)} />
                </div>
                <div className={field}>
                  <label className={label} htmlFor="content-type"><Trans>Primary content type</Trans></label>
                  <Select value={contentType || undefined} onValueChange={setContentType}>
                    <SelectTrigger id="content-type" className="w-full">
                      <SelectValue placeholder={t`Choose one`} />
                    </SelectTrigger>
                    <SelectContent position="popper">
                      {CONTENT_TYPES.map(ct => (
                        <SelectItem key={ct.value} value={ct.value}>{i18n._(ct.label)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className={field}>
                <label className={label} htmlFor="description"><Trans>What the business does</Trans></label>
                <Input id="description" type="text" placeholder={t`One sentence`}
                  value={description} onChange={e => setDescription(e.target.value)} />
              </div>

              <div className={field}>
                <label className={label} htmlFor="keywords"><Trans>Target keywords</Trans></label>
                <Input id="keywords" type="text"
                  placeholder={t`Comma-separated`}
                  value={keywords} onChange={e => setKeywords(e.target.value)} />
              </div>

              <div className={field}>
                <label className={label} htmlFor="competitors"><Trans>Competitors</Trans></label>
                <Input id="competitors" type="text"
                  placeholder={t`rival.com, other.com`}
                  value={competitors} onChange={e => setCompetitors(e.target.value)} />
              </div>

              <div className={field}>
                <label className={label} htmlFor="goals"><Trans>Primary SEO goal</Trans></label>
                <Textarea id="goals" rows={2} placeholder={t`e.g. More trial signups from organic search`}
                  value={goals} onChange={e => setGoals(e.target.value)} />
              </div>

              <div className={field}>
                <p className={label}><Trans>Analysis effort</Trans></p>
                <div role="radiogroup" aria-label={t`Analysis effort`} className="grid grid-cols-3 gap-2">
                  {EFFORT_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      role="radio"
                      aria-checked={effort === opt.value}
                      onClick={() => setEffort(opt.value)}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-left transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                        effort === opt.value
                          ? "border-primary bg-primary/5 text-foreground"
                          : "border-border bg-card text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <span className="block text-sm font-medium">{i18n._(opt.label)}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{i18n._(opt.hint)}</span>
                    </button>
                  ))}
                </div>
              </div>

              <label className="flex items-start justify-between gap-4">
                <span className="flex flex-col gap-0.5">
                  <span className={label}><Trans>Adaptive thinking</Trans></span>
                  <span className="text-sm text-muted-foreground">
                    <Trans>Reasons before answering. Better on complex sites.</Trans>
                  </span>
                </span>
                <Switch
                  className="mt-0.5 shrink-0"
                  checked={adaptiveThinking}
                  aria-label={t`Adaptive thinking`}
                  onCheckedChange={setAdaptiveThinking}
                />
              </label>
            </div>
          )}
        </Card>
      </form>

      {prevAudits.length > 0 && (
        <Section title={<Trans>Previous audits</Trans>} count={prevAudits.length}>
          <Card className="gap-0 overflow-hidden p-0">
            {prevAudits.slice(0, 5).map((conv) => {
              const badge = auditBadge(conv);
              const eventCount = conv.last_seq;
              return (
              <div
                key={conv.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3 last:border-0"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {conv.title || t`SEO audit`}
                    {badge && (
                      <span className={`ml-2 text-2xs font-medium ${badge.className}`}>{i18n._(badge.label)}</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {conv.last_active_at ? relativeTime(conv.last_active_at, { fallbackAfterDays: 7, locale: i18n.locale }) : ""}
                    {eventCount ? <> · <Plural value={eventCount} one="# event" other="# events" /></> : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button asChild type="button" size="sm" variant="ghost">
                    {/* Everything this chat did — proposals, auto-applies,
                        rollbacks, artifact versions — as one timeline. */}
                    <Link href={`/activity?conversation_id=${conv.id}`}><Trans>Activity</Trans></Link>
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="text-muted-foreground"
                    title={t`Archive this conversation (its report artifacts stay in the library)`}
                    onClick={() => archivePrevAudit(conv.id)}
                  >
                    <Trans>Archive</Trans>
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      startAuditResume(router, {
                        conversationId: conv.id,
                        projectId: conv.project_id,
                        url: conv.meta?.url || "",
                        reportMode: conv.mode || "",
                      })
                    }
                  >
                    <Trans>Continue chat</Trans>
                  </Button>
                </div>
              </div>
              );
            })}
          </Card>
        </Section>
      )}
    </Page>
  );
}
