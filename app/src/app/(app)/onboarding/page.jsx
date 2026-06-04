"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  createProject,
  getActiveProject,
  getProjectById,
  pushProjectToBackend,
  saveProject,
  setActiveProjectId,
} from "../../../lib/projects";
import { fetchProjectConfig, getFallbackProjectConfig } from "../../../lib/projectConfig";

const PRIMARY_SEGMENTS = ["Consumer", "SMB", "Mid-market", "Enterprise", "Public sector", "Non-profit", "Other"];
const BRAND_VOICES = ["Professional", "Friendly", "Bold", "Technical", "Playful"];
const GROWTH_MOTIONS = ["Organic", "Paid", "Product-led", "Sales-led", "Partnerships", "Community", "Lifecycle/CRM"];
const TOTAL_STEPS = 5;

function parseComparisonItems(rawValue) {
  return Array.from(
    new Set(
      String(rawValue || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
}

function hasText(value) {
  return String(value ?? "").trim().length > 0;
}

const STEP_DEFINITIONS = [
  {
    label: "Company basics",
    shortLabel: "Company",
    fields: [
      { weight: 3, check: (profile) => hasText(profile.company?.name) },
      { weight: 3, check: (profile) => hasText(profile.company?.industry) },
      { weight: 2, check: (profile) => hasText(profile.company?.business_model) },
      { weight: 1, check: (profile) => hasText(profile.company?.website_url) },
    ],
  },
  {
    label: "Targets",
    shortLabel: "Targets",
    fields: [
      { weight: 2, check: (profile) => hasText(profile.targets?.north_star_metric) },
      { weight: 2, check: (profile) => hasText(profile.targets?.north_star_goal_window) },
      { weight: 2, check: (profile) => hasText(profile.targets?.growth_stage_milestone) },
    ],
  },
  {
    label: "Audience",
    shortLabel: "Audience",
    fields: [
      { weight: 2, check: (profile) => hasText(profile.audience?.primary_segment) },
      { weight: 3, check: (profile) => (profile.audience.personas[0]?.name || "").trim().length > 0 },
      { weight: 2, check: (profile) => (profile.audience.personas[0]?.description || "").trim().length > 0 },
    ],
  },
  {
    label: "Competition",
    shortLabel: "Competition",
    fields: [
      { weight: 1, check: (profile) => hasText(profile.competition?.compare_against) },
    ],
  },
  {
    label: "Business context",
    shortLabel: "Context",
    fields: [
      { weight: 2, check: (profile) => hasText(profile.brand_channels?.brand_voice) },
      { weight: 2, check: (profile) => (profile.brand_channels?.growth_motions || []).length > 0 },
      { weight: 1, check: (profile) => hasText(profile.brand_channels?.context_notes) },
    ],
  },
];

export default function OnboardingPage() {
  const searchParams = useSearchParams();
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState(1);
  const [projectMeta, setProjectMeta] = useState(null);
  const [isNewProjectFlow, setIsNewProjectFlow] = useState(false);
  const [projectLoadError, setProjectLoadError] = useState("");
  const [projectConfig, setProjectConfig] = useState(getFallbackProjectConfig);
  const [projectConfigLoading, setProjectConfigLoading] = useState(false);
  const [projectConfigError, setProjectConfigError] = useState("");
  const [profile, setProfile] = useState({
    company: { name: "", industry: "", business_model: "", website_url: "" },
    targets: {
      monthly_budget: "",
      target_cpa: "",
      target_roas: "",
      primary_kpi: "",
      north_star_metric: "",
      north_star_goal_window: "",
      north_star_constraints: "",
      growth_stage_milestone: "",
      growth_stage_context: "",
    },
    audience: { primary_segment: "", personas: [{ name: "", description: "", priority: "primary" }] },
    competition: { compare_against: "", competitors: [{ name: "", differentiator: "" }], positioning_statement: "" },
    brand_channels: {
      brand_voice: "",
      growth_motions: [],
      context_notes: "",
      active_channels: [],
      seasonality_notes: "",
    },
  });

  useEffect(() => {
    const wantsNewProject = searchParams.get("new") === "1";
    const requestedProjectId = searchParams.get("project_id");
    setIsNewProjectFlow(wantsNewProject);
    setProjectLoadError("");
    let project = null;
    if (wantsNewProject) {
      setProjectMeta(null);
      setReady(true);
      return;
    } else if (requestedProjectId) {
      project = getProjectById(requestedProjectId);
      if (!project) {
        setProjectMeta(null);
        setProjectLoadError("Project not found. It may have been deleted.");
        setReady(true);
        return;
      }
      setActiveProjectId(project.id);
    } else {
      project = getActiveProject();
      if (!project) {
        project = createProject();
        setActiveProjectId(project.id);
      }
    }

    setProjectMeta(project);
    const draft = project || {};
    setProfile((prev) => ({
      ...prev,
      ...draft,
      company: {
        ...prev.company,
        ...(draft.company || {}),
      },
      targets: {
        ...prev.targets,
        ...(draft.targets || {}),
      },
      audience: {
        ...prev.audience,
        ...(draft.audience || {}),
        personas:
          Array.isArray(draft.audience?.personas) && draft.audience.personas.length
            ? draft.audience.personas
            : prev.audience.personas,
      },
      competition: {
        ...prev.competition,
        ...(draft.competition || {}),
        competitors:
          Array.isArray(draft.competition?.competitors) && draft.competition.competitors.length
            ? draft.competition.competitors
            : prev.competition.competitors,
        positioning_statement: draft.competition?.positioning_statement ?? prev.competition.positioning_statement,
      },
      brand_channels: {
        ...prev.brand_channels,
        ...(draft.brand_channels || {}),
      },
    }));
    setReady(true);
  }, [searchParams]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    async function loadProjectConfig() {
      setProjectConfigLoading(true);
      try {
        const config = await fetchProjectConfig({
          industry: profile.company.industry,
          businessModel: profile.company.business_model,
        });
        if (cancelled) return;
        setProjectConfig(config);
        setProjectConfigError("");
      } catch {
        if (cancelled) return;
        setProjectConfig(getFallbackProjectConfig());
        setProjectConfigError("Using fallback options while config service is unavailable.");
      } finally {
        if (!cancelled) {
          setProjectConfigLoading(false);
        }
      }
    }
    loadProjectConfig();
    return () => {
      cancelled = true;
    };
  }, [ready, profile.company.industry, profile.company.business_model]);

  function isStepOneRequiredComplete(currentProfile) {
    return Boolean(
      currentProfile.company?.name?.trim() &&
      currentProfile.company?.industry?.trim() &&
      currentProfile.company?.business_model?.trim()
    );
  }

  useEffect(() => {
    if (!ready) return;
    if (!projectMeta?.id) {
      if (!isNewProjectFlow || !isStepOneRequiredComplete(profile)) return;
      const created = createProject({
        ...profile,
        name: profile.company.name || "Untitled project",
      });
      setProjectMeta(created);
      setActiveProjectId(created.id);
      window.dispatchEvent(new Event("duct:project-changed"));
      return;
    }
    saveProject({
      ...projectMeta,
      ...profile,
      name: projectMeta.name || profile.company.name || "Untitled project",
    });
  }, [profile, projectMeta, ready, isNewProjectFlow]);

  const stepProgress = useMemo(
    () =>
      STEP_DEFINITIONS.map((stepDef) => {
        const totalWeight = stepDef.fields.reduce((sum, field) => sum + field.weight, 0);
        const completedWeight = stepDef.fields.reduce(
          (sum, field) => sum + (field.check(profile) ? field.weight : 0),
          0
        );
        const percent = Math.round((completedWeight / totalWeight) * 100);
        return { ...stepDef, totalWeight, completedWeight, percent };
      }),
    [profile]
  );
  const inputProgressPercent = useMemo(() => {
    const completedWeight = stepProgress.reduce((sum, item) => sum + item.completedWeight, 0);
    const totalWeight = stepProgress.reduce((sum, item) => sum + item.totalWeight, 0);
    return Math.round((completedWeight / totalWeight) * 100);
  }, [stepProgress]);
  const comparisonItems = useMemo(
    () => parseComparisonItems(profile.competition.compare_against),
    [profile.competition.compare_against]
  );
  const [comparisonInput, setComparisonInput] = useState("");
  const industryOptions = projectConfig?.industry_options ?? [];
  const businessModelOptions = projectConfig?.business_model_options ?? [];
  const northStarOptions = projectConfig?.north_star_metric_options ?? [];
  const growthStageOptions = projectConfig?.growth_stage_milestone_options ?? [];
  const hasCompanyContext = Boolean(profile.company.industry && profile.company.business_model);

  function handleIndustryChange(value) {
    setProfile((prev) => ({
      ...prev,
      company: { ...prev.company, industry: value },
      targets: {
        ...prev.targets,
        north_star_metric: "",
        growth_stage_milestone: "",
      },
    }));
  }

  function handleBusinessModelChange(value) {
    setProfile((prev) => ({
      ...prev,
      company: { ...prev.company, business_model: value },
      targets: {
        ...prev.targets,
        north_star_metric: "",
        growth_stage_milestone: "",
      },
    }));
  }

  function goNext() {
    setStep((current) => Math.min(current + 1, TOTAL_STEPS));
  }

  // "Save & Next": the deliberate persistence point. Saves the current profile
  // locally, then upserts it to the backend (fire-and-forget), then advances.
  function saveAndNext() {
    const merged = {
      ...(projectMeta || {}),
      ...profile,
      name: projectMeta?.name || profile.company.name || "Untitled project",
    };
    const saved = projectMeta?.id ? saveProject(merged) : createProject(merged);
    if (saved?.id && saved.id !== projectMeta?.id) {
      setProjectMeta(saved);
      setActiveProjectId(saved.id);
      window.dispatchEvent(new Event("duct:project-changed"));
    }
    pushProjectToBackend(saved);
    goNext();
  }

  // Final step: persist the project (local + backend). Navigation is handled by
  // the separate Back button, so this only saves.
  function saveProjectFinal() {
    const merged = {
      ...(projectMeta || {}),
      ...profile,
      name: projectMeta?.name || profile.company.name || "Untitled project",
    };
    const saved = projectMeta?.id ? saveProject(merged) : createProject(merged);
    if (saved?.id && saved.id !== projectMeta?.id) {
      setProjectMeta(saved);
      setActiveProjectId(saved.id);
    }
    window.dispatchEvent(new Event("duct:project-changed"));
    pushProjectToBackend(saved);
  }

  function goBack() {
    setStep((current) => Math.max(current - 1, 1));
  }

  function skipStep() {
    goNext();
  }

  function goToStep(targetStep) {
    if (targetStep < 1 || targetStep > TOTAL_STEPS) return;
    setStep(targetStep);
  }

  function addCompetitionItems(rawValue) {
    const incoming = parseComparisonItems(rawValue);
    if (!incoming.length) return;
    setProfile((prev) => {
      const existing = parseComparisonItems(prev.competition.compare_against);
      const merged = Array.from(new Set([...existing, ...incoming]));
      return {
        ...prev,
        competition: {
          ...prev.competition,
          compare_against: merged.join(", "),
        },
      };
    });
    setComparisonInput("");
  }

  function removeCompetitionItem(itemToRemove) {
    setProfile((prev) => {
      const next = parseComparisonItems(prev.competition.compare_against).filter((item) => item !== itemToRemove);
      return {
        ...prev,
        competition: {
          ...prev.competition,
          compare_against: next.join(", "),
        },
      };
    });
  }

  if (!ready) {
    return (
      <section>
        <h1 className="text-2xl font-semibold tracking-tight mb-2">Project setup</h1>
        <p className="text-sm text-muted-foreground">Loading your saved progress...</p>
      </section>
    );
  }

  if (projectLoadError) {
    return (
      <section>
        <h1 className="text-2xl font-semibold tracking-tight mb-2">Project setup</h1>
        <p className="text-sm text-muted-foreground mb-4">{projectLoadError}</p>
        <Button asChild>
          <Link href="/projects">Back to manage projects</Link>
        </Button>
      </section>
    );
  }

  return (
    <section>
      {/* Sticky progress shell */}
      <div className="onboarding-progress-shell">
        <div className="page-toolbar" style={{ marginBottom: 8 }}>
          <h1 className="page-toolbar-title text-lg font-semibold tracking-tight">Project setup</h1>
          <span className="text-sm text-muted-foreground">{inputProgressPercent}% complete</span>
        </div>

        <div className="mb-3">
          <Progress value={inputProgressPercent} className="h-1.5" />
        </div>

        <div className="flex items-center gap-3 overflow-x-auto pb-1 scrollbar-thin" role="list" aria-label="Onboarding steps">
          {stepProgress.map((stepItem, index) => {
            const stepNumber = index + 1;
            const isActive = step === stepNumber;
            const isDone = stepItem.percent === 100;
            return (
              <div
                key={stepItem.shortLabel}
                role="listitem"
                className="inline-flex items-center gap-1.5 whitespace-nowrap"
              >
                <button
                  type="button"
                  onClick={() => goToStep(stepNumber)}
                  className={cn(
                    "rounded-xl border px-2.5 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "border-primary/30 bg-primary/8 text-foreground font-semibold"
                      : "border-transparent bg-muted/70 text-muted-foreground hover:border-border hover:bg-muted"
                  )}
                >
                  {stepItem.shortLabel}
                </button>
                {isDone && <Check className="size-3.5 text-primary" aria-hidden="true" />}
                {index < TOTAL_STEPS - 1 && (
                  <span className="inline-block h-px w-3 bg-border" aria-hidden="true" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Step 1: Company */}
      {step === 1 && (
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="company-name">Company name</Label>
            <Input
              id="company-name"
              value={profile.company.name}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, company: { ...prev.company, name: e.target.value } }))
              }
              placeholder="Acme Inc."
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="company-industry">Industry</Label>
            <Select value={profile.company.industry} onValueChange={handleIndustryChange}>
              <SelectTrigger id="company-industry">
                <SelectValue placeholder="Select industry..." />
              </SelectTrigger>
              <SelectContent>
                {industryOptions.map((industry) => (
                  <SelectItem key={industry.value} value={industry.value}>{industry.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="company-business-model">Business model</Label>
            <Select value={profile.company.business_model} onValueChange={handleBusinessModelChange}>
              <SelectTrigger id="company-business-model">
                <SelectValue placeholder="Select business model..." />
              </SelectTrigger>
              <SelectContent>
                {businessModelOptions.map((model) => (
                  <SelectItem key={model.value} value={model.value}>{model.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="company-website">Website <span className="text-muted-foreground">(optional)</span></Label>
            <Input
              id="company-website"
              value={profile.company.website_url}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, company: { ...prev.company, website_url: e.target.value } }))
              }
              placeholder="https://example.com"
            />
          </div>
        </div>
      )}

      {/* Step 2: Targets */}
      {step === 2 && (
        <div className="grid gap-4">
          <p className="text-sm text-muted-foreground">
            Define your North Star metric and current growth stage. Channel-specific KPIs stay in report generation.
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="north-star-metric">North Star metric</Label>
            <Select
              value={profile.targets.north_star_metric}
              disabled={!hasCompanyContext || projectConfigLoading}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, north_star_metric: val } }))
              }
            >
              <SelectTrigger id="north-star-metric">
                <SelectValue placeholder="Select North Star metric..." />
              </SelectTrigger>
              <SelectContent>
                {northStarOptions.map((metric) => (
                  <SelectItem key={metric.value} value={metric.value}>{metric.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!hasCompanyContext ? (
              <p className="text-xs text-muted-foreground">
                Select Industry and Business model first to load relevant North Star options.
              </p>
            ) : null}
            {projectConfigError ? <p className="text-xs text-muted-foreground">{projectConfigError}</p> : null}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="north-star-goal-window">What does success look like in the next 90 days?</Label>
            <textarea
              id="north-star-goal-window"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={3}
              value={profile.targets.north_star_goal_window}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, north_star_goal_window: e.target.value } }))
              }
              placeholder="e.g. Reach 500 weekly active users with at least 40% week-4 retention."
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="growth-stage-milestone">Current growth stage (milestone-based)</Label>
            <Select
              value={profile.targets.growth_stage_milestone}
              disabled={!hasCompanyContext || projectConfigLoading}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, growth_stage_milestone: val } }))
              }
            >
              <SelectTrigger id="growth-stage-milestone">
                <SelectValue placeholder="Select your current milestone..." />
              </SelectTrigger>
              <SelectContent>
                {growthStageOptions.map((stage) => (
                  <SelectItem key={stage.value} value={stage.value}>{stage.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="north-star-constraints">What currently limits this metric most? <span className="text-muted-foreground">(optional)</span></Label>
            <textarea
              id="north-star-constraints"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={3}
              value={profile.targets.north_star_constraints}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, north_star_constraints: e.target.value } }))
              }
              placeholder="e.g. Limited sales capacity, high onboarding drop-off, or long implementation cycles."
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="growth-stage-context">Growth stage context or constraints <span className="text-muted-foreground">(optional)</span></Label>
            <textarea
              id="growth-stage-context"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={2}
              value={profile.targets.growth_stage_context}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, growth_stage_context: e.target.value } }))
              }
              placeholder="e.g. Team of 3, founder-led sales, runway for 8 months."
            />
          </div>
        </div>
      )}

      {/* Step 3: Audience */}
      {step === 3 && (
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="primary-segment">Primary segment</Label>
            <Select
              value={profile.audience.primary_segment}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, audience: { ...prev.audience, primary_segment: val } }))
              }
            >
              <SelectTrigger id="primary-segment">
                <SelectValue placeholder="Select primary segment..." />
              </SelectTrigger>
              <SelectContent>
                {PRIMARY_SEGMENTS.map((segment) => (
                  <SelectItem key={segment} value={segment}>{segment}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="persona-name">Primary persona name</Label>
            <Input
              id="persona-name"
              value={profile.audience.personas[0]?.name || ""}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  audience: {
                    ...prev.audience,
                    personas: [{
                      ...(prev.audience.personas[0] || {}),
                      name: e.target.value,
                      description: prev.audience.personas[0]?.description || "",
                      priority: prev.audience.personas[0]?.priority || "primary",
                    }],
                  },
                }))
              }
              placeholder="Marketing managers at SaaS startups"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="persona-desc">Persona description</Label>
            <textarea
              id="persona-desc"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={3}
              value={profile.audience.personas[0]?.description || ""}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  audience: {
                    ...prev.audience,
                    personas: [{
                      ...(prev.audience.personas[0] || {}),
                      description: e.target.value,
                      name: prev.audience.personas[0]?.name || "",
                      priority: prev.audience.personas[0]?.priority || "primary",
                    }],
                  },
                }))
              }
              placeholder="Pain points, goals, motivations..."
            />
          </div>
        </div>
      )}

      {/* Step 4: Competition */}
      {step === 4 && (
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="compare-against">Who do customers compare you against most often?</Label>
            <Input
              id="compare-against"
              value={comparisonInput}
              onChange={(e) => setComparisonInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addCompetitionItems(comparisonInput);
                }
              }}
              onBlur={() => addCompetitionItems(comparisonInput)}
              placeholder="e.g. Notion, HubSpot, in-house spreadsheets"
            />
            <p className="text-xs text-muted-foreground">
              Add one or more names, separated by commas.
            </p>
            {comparisonItems.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {comparisonItems.map((item) => (
                  <Badge key={item} variant="secondary" className="inline-flex items-center gap-1 pr-1">
                    <span>{item}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-4 rounded-full"
                      onClick={() => removeCompetitionItem(item)}
                      aria-label={`Remove ${item}`}
                    >
                      <X className="size-3" />
                    </Button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 5: Business context */}
      {step === 5 && (
        <div className="grid gap-4">
          <p className="text-sm text-muted-foreground">
            Capture durable business context that applies across paid, organic, and product intelligence use cases.
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="brand-voice">Brand voice</Label>
            <Select
              value={profile.brand_channels.brand_voice}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, brand_channels: { ...prev.brand_channels, brand_voice: val } }))
              }
            >
              <SelectTrigger id="brand-voice">
                <SelectValue placeholder="Select voice..." />
              </SelectTrigger>
              <SelectContent>
                {BRAND_VOICES.map((voice) => (
                  <SelectItem key={voice} value={voice}>{voice}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label>Primary growth motions</Label>
            <div className="flex flex-wrap gap-2">
              {GROWTH_MOTIONS.map((motion) => {
                const active = profile.brand_channels.growth_motions.includes(motion);
                return (
                  <Button
                    key={motion}
                    type="button"
                    variant={active ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      setProfile((prev) => ({
                        ...prev,
                        brand_channels: {
                          ...prev.brand_channels,
                          growth_motions: active
                            ? prev.brand_channels.growth_motions.filter((item) => item !== motion)
                            : [...prev.brand_channels.growth_motions, motion],
                        },
                      }))
                    }
                  >
                    {motion}
                  </Button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="context-notes">Additional business context</Label>
            <textarea
              id="context-notes"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={2}
              value={profile.brand_channels.context_notes}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  brand_channels: { ...prev.brand_channels, context_notes: e.target.value },
                }))
              }
              placeholder="e.g. Strong Q4 seasonality, long enterprise sales cycle, or limited engineering bandwidth."
            />
          </div>

        </div>
      )}

      <div className="onboarding-actions">
        {step > 1 && (
          <Button type="button" variant="outline" onClick={goBack}>
            Back
          </Button>
        )}
        {step < TOTAL_STEPS ? (
          <Button type="button" onClick={saveAndNext}>
            Save & Next
          </Button>
        ) : (
          <Button type="button" onClick={saveProjectFinal}>
            Save Project
          </Button>
        )}
        {step > 1 && step < TOTAL_STEPS && (
          <Button type="button" variant="ghost" onClick={skipStep}>
            I&apos;ll do this later
          </Button>
        )}
      </div>
    </section>
  );
}
