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

const CONTENT_TYPES = [
  { value: "", label: msg`Select type…` },
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

// Kept for the one control the primitive does not cover (`<textarea>`), and
// written the way the primitive writes it: `text-base md:text-sm` so iOS
// Safari does not zoom the page when a field under 16px takes focus, and
// `focus-visible` so a mouse click does not light the ring up.
const FIELD = "w-full rounded-3xl border border-control bg-input/50 px-3 py-2 text-base placeholder:text-muted-foreground outline-none transition-[color,box-shadow,background-color] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 md:text-sm";

/** What a past audit's run is doing, from the list route — so one stuck on a
 *  question or a failure says so before it is opened. Idle says nothing. */
function auditBadge(conv) {
  switch (conv.run_status) {
    case "running": return { label: msg`Working…`, className: "text-primary" };
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

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight"><Trans>SEO Audit</Trans></h1>
        <p className="text-muted-foreground mt-1 text-sm">
          <Trans>Crawl your site, surface issues, and get an AI-generated report with actionable recommendations.</Trans>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* URL */}
        <div>
          <label className="block text-sm font-medium mb-1.5" htmlFor="url">
            <Trans>Website URL <span className="text-destructive">*</span></Trans>
          </label>
          <Input
            id="url" type="url" placeholder={t`https://yoursite.com`}
            value={url} onChange={e => setUrl(e.target.value)} required
            className="border-control"
          />
        </div>

        {/* Business context */}
        <div className="rounded-lg border border-border/60 p-4 space-y-4">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            <Trans>Optional — improves report quality</Trans>
          </p>

          {activeProject && (
            <div className="flex items-start justify-between gap-4 rounded-md bg-muted/30 px-3 py-2.5">
              <div>
                <p className="text-sm font-medium">
                  <Trans>Use {projectName}&apos;s business context</Trans>
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  <Trans>Turn off to audit a different business or competitor — only the fields below are used.</Trans>
                </p>
              </div>
              <Switch
                className="mt-0.5 shrink-0"
                checked={useProjectContext}
                onCheckedChange={(next) => toggleProjectContext(next)}
              />
            </div>
          )}

          {activeProject && useProjectContext && (
            <div className="flex items-start justify-between gap-4 rounded-md bg-muted/30 px-3 py-2.5">
              <div>
                <p className="text-sm font-medium"><Trans>Remember this session</Trans></p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {remember
                    ? <Trans>This run reads project memory, and what it concludes is written back.</Trans>
                    : <Trans>A one-off: project memory is neither read nor written. The report is still saved.</Trans>}
                </p>
              </div>
              <Switch
                className="mt-0.5 shrink-0"
                checked={remember}
                aria-label={t`Remember this session`}
                onCheckedChange={(next) => setRemember(next)}
              />
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 @md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="biz-name"><Trans>Business name</Trans></label>
              <Input id="biz-name" type="text" placeholder="Duct" value={businessName}
                onChange={e => setBusinessName(e.target.value)} className="border-control" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="content-type"><Trans>Primary content type</Trans></label>
              <select id="content-type" value={contentType} onChange={e => setContentType(e.target.value)}
                className={FIELD}>
                {CONTENT_TYPES.map(ct => <option key={ct.value} value={ct.value}>{i18n._(ct.label)}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="description"><Trans>Business description</Trans></label>
            <Input id="description" type="text" placeholder={t`One-sentence description of what you do`}
              value={description} onChange={e => setDescription(e.target.value)} className="border-control" />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="keywords"><Trans>Target keywords</Trans></label>
            <Input id="keywords" type="text"
              placeholder={t`analytics reporting, growth intelligence, SEO audit (comma-separated)`}
              value={keywords} onChange={e => setKeywords(e.target.value)} className="border-control" />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="competitors"><Trans>Competitors</Trans></label>
            <Input id="competitors" type="text"
              placeholder={t`competitor1.com, competitor2.com (comma-separated)`}
              value={competitors} onChange={e => setCompetitors(e.target.value)} className="border-control" />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="goals"><Trans>Primary SEO goal</Trans></label>
            <textarea id="goals" rows={2} placeholder={t`e.g. Increase trial signups from organic search`}
              value={goals} onChange={e => setGoals(e.target.value)}
              className={`${FIELD} resize-none`} />
          </div>
        </div>

        {/* Advanced */}
        <div className="rounded-lg border border-border/60 overflow-hidden">
          <button
            type="button"
            onClick={() => setAdvancedOpen(o => !o)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-muted/40 transition-colors"
          >
            <span className="font-medium"><Trans>Advanced</Trans></span>
            <span className={`text-muted-foreground transition-transform duration-150 ${advancedOpen ? "rotate-90" : ""}`}>›</span>
          </button>

          <div
            className="overflow-hidden transition-all duration-200"
            style={{ maxHeight: advancedOpen ? "300px" : "0px" }}
          >
            <div className="px-4 pb-4 space-y-5 border-t border-border/40">

              {/* Effort */}
              <div className="pt-4">
                <p className="text-sm font-medium mb-1"><Trans>Analysis effort</Trans></p>
                <p className="text-xs text-muted-foreground mb-2.5">
                  <Trans>Controls how deeply the AI reasons about your site before writing findings.</Trans>
                </p>
                <div className="flex gap-2">
                  {EFFORT_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setEffort(opt.value)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-left transition-colors ${
                        effort === opt.value
                          ? "border-primary bg-primary/8 text-foreground"
                          : "border-border hover:border-border/80 text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <span className="block text-sm font-medium">{i18n._(opt.label)}</span>
                      <span className="block text-2xs text-muted-foreground mt-0.5">{i18n._(opt.hint)}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Adaptive thinking */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium"><Trans>Adaptive thinking</Trans></p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    <Trans>Lets the AI reason internally before responding. Improves accuracy on complex sites.</Trans>
                  </p>
                </div>
                <Switch
                  className="mt-0.5 shrink-0"
                  checked={adaptiveThinking}
                  aria-label={t`Adaptive thinking`}
                  onCheckedChange={setAdaptiveThinking}
                />
              </div>

            </div>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? <Trans>Starting audit…</Trans> : <Trans>Run SEO Audit →</Trans>}
        </Button>
      </form>

      {prevAudits.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            <Trans>Previous audits</Trans>
          </h2>
          <div className="grid gap-2">
            {prevAudits.slice(0, 5).map((conv) => {
              const badge = auditBadge(conv);
              const eventCount = conv.last_seq;
              return (
              <div
                key={conv.id}
                className="flex items-center justify-between gap-3 rounded-md border border-input px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {conv.title || t`SEO audit`}
                    {badge && (
                      <span className={`ml-2 text-2xs font-medium ${badge.className}`}>{i18n._(badge.label)}</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {conv.last_active_at ? new Date(conv.last_active_at).toLocaleString() : ""}
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
          </div>
        </div>
      )}
    </div>
  );
}
