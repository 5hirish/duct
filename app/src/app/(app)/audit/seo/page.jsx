"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { loadPreferences } from "@/lib/userPreferences";
import { getActiveProject } from "@/lib/projects";

const CONTENT_TYPES = [
  { value: "", label: "Select type…" },
  { value: "blog", label: "Blog / Articles" },
  { value: "landing_pages", label: "Landing Pages" },
  { value: "product_pages", label: "Product Pages" },
  { value: "docs", label: "Docs / Help" },
];

const EFFORT_OPTIONS = [
  { value: "low",    label: "Low",    hint: "Faster, lighter" },
  { value: "medium", label: "Medium", hint: "Balanced" },
  { value: "high",   label: "High",   hint: "Deeper analysis" },
];

const INPUT = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

export default function SeoAuditSetupPage() {
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

  useEffect(() => {
    const project = getActiveProject();
    if (!project) return;
    setActiveProject(project);
    applyProjectContext(project);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The durable competitor field users actually fill in onboarding is
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
    if (!url.trim()) { setError("Website URL is required."); return; }
    setLoading(true);
    try {
      const params = {
        url: url.trim(),
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
        user_preferences: loadPreferences(),
      };
      const sessionId = crypto.randomUUID();
      sessionStorage.setItem(`audit_session_${sessionId}`, JSON.stringify(params));
      router.push(`/audit/seo/${sessionId}`);
    } catch (err) {
      setError(err.message || "Failed to start audit.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">SEO Audit</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Crawl your site, surface issues, and get an AI-generated report with actionable recommendations.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* URL */}
        <div>
          <label className="block text-sm font-medium mb-1.5" htmlFor="url">
            Website URL <span className="text-destructive">*</span>
          </label>
          <input
            id="url" type="url" placeholder="https://yoursite.com"
            value={url} onChange={e => setUrl(e.target.value)} required
            className={INPUT}
          />
        </div>

        {/* Business context */}
        <div className="rounded-lg border border-border/60 p-4 space-y-4">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Optional — improves report quality
          </p>

          {activeProject && (
            <div className="flex items-start justify-between gap-4 rounded-md bg-muted/30 px-3 py-2.5">
              <div>
                <p className="text-sm font-medium">
                  Use {activeProject.name || "this project"}&apos;s business context
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Turn off to audit a different business or competitor — only the fields below are used.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={useProjectContext}
                onClick={() => toggleProjectContext(!useProjectContext)}
                className={`relative shrink-0 mt-0.5 h-5 w-9 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 ${
                  useProjectContext ? "bg-primary" : "bg-input"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow transition-transform ${
                    useProjectContext ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="biz-name">Business name</label>
              <input id="biz-name" type="text" placeholder="Duct" value={businessName}
                onChange={e => setBusinessName(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5" htmlFor="content-type">Primary content type</label>
              <select id="content-type" value={contentType} onChange={e => setContentType(e.target.value)}
                className="w-full rounded-md border border-input bg-background pl-3 pr-10 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
                {CONTENT_TYPES.map(ct => <option key={ct.value} value={ct.value}>{ct.label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="description">Business description</label>
            <input id="description" type="text" placeholder="One-sentence description of what you do"
              value={description} onChange={e => setDescription(e.target.value)} className={INPUT} />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="keywords">Target keywords</label>
            <input id="keywords" type="text"
              placeholder="analytics reporting, growth intelligence, SEO audit (comma-separated)"
              value={keywords} onChange={e => setKeywords(e.target.value)} className={INPUT} />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="competitors">Competitors</label>
            <input id="competitors" type="text"
              placeholder="competitor1.com, competitor2.com (comma-separated)"
              value={competitors} onChange={e => setCompetitors(e.target.value)} className={INPUT} />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" htmlFor="goals">Primary SEO goal</label>
            <textarea id="goals" rows={2} placeholder="e.g. Increase trial signups from organic search"
              value={goals} onChange={e => setGoals(e.target.value)}
              className={`${INPUT} resize-none`} />
          </div>
        </div>

        {/* Advanced */}
        <div className="rounded-lg border border-border/60 overflow-hidden">
          <button
            type="button"
            onClick={() => setAdvancedOpen(o => !o)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-muted/40 transition-colors"
          >
            <span className="font-medium">Advanced</span>
            <span className={`text-muted-foreground transition-transform duration-150 ${advancedOpen ? "rotate-90" : ""}`}>›</span>
          </button>

          <div
            className="overflow-hidden transition-all duration-200"
            style={{ maxHeight: advancedOpen ? "300px" : "0px" }}
          >
            <div className="px-4 pb-4 space-y-5 border-t border-border/40">

              {/* Effort */}
              <div className="pt-4">
                <p className="text-sm font-medium mb-1">Analysis effort</p>
                <p className="text-xs text-muted-foreground mb-2.5">
                  Controls how deeply the AI reasons about your site before writing findings.
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
                      <span className="block text-sm font-medium">{opt.label}</span>
                      <span className="block text-[11px] text-muted-foreground mt-0.5">{opt.hint}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Adaptive thinking */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">Adaptive thinking</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Lets the AI reason internally before responding. Improves accuracy on complex sites.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={adaptiveThinking}
                  onClick={() => setAdaptiveThinking(v => !v)}
                  className={`relative shrink-0 mt-0.5 h-5 w-9 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 ${
                    adaptiveThinking ? "bg-primary" : "bg-input"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow transition-transform ${
                      adaptiveThinking ? "translate-x-4" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>

            </div>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Starting audit…" : "Run SEO Audit →"}
        </Button>
      </form>
    </div>
  );
}
