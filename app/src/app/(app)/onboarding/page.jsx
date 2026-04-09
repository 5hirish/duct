"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  getBusinessProfileDraft,
  saveBusinessProfileDraft,
} from "../../../lib/businessProfile";

const INDUSTRIES = [
  "E-commerce & Retail",
  "SaaS & Software",
  "Financial Services",
  "Healthcare",
  "Education",
  "Professional Services",
  "Marketing & Advertising",
  "Real Estate",
  "Travel & Hospitality",
  "Other",
];

const KPI_OPTIONS = ["Revenue", "Signups", "Leads", "Purchases", "Bookings", "Calls"];
const BRAND_VOICES = ["Professional", "Friendly", "Bold", "Technical", "Playful"];
const CHANNELS = ["Paid Search", "Paid Social", "SEO", "Email", "Content", "Display", "Video", "Referral"];
const TOTAL_STEPS = 5;
const STEP_DEFINITIONS = [
  {
    label: "Company basics",
    shortLabel: "Company",
    fields: [
      { weight: 3, check: (profile) => profile.company.name.trim().length > 0 },
      { weight: 3, check: (profile) => profile.company.industry.trim().length > 0 },
      { weight: 1, check: (profile) => profile.company.website_url.trim().length > 0 },
    ],
  },
  {
    label: "Targets",
    shortLabel: "Targets",
    fields: [
      { weight: 3, check: (profile) => profile.targets.primary_kpi.trim().length > 0 },
      { weight: 2, check: (profile) => Number(profile.targets.monthly_budget) > 0 },
      { weight: 2, check: (profile) => Number(profile.targets.target_cpa) > 0 },
      { weight: 2, check: (profile) => Number(profile.targets.target_roas) > 0 },
    ],
  },
  {
    label: "Audience",
    shortLabel: "Audience",
    fields: [
      { weight: 3, check: (profile) => (profile.audience.personas[0]?.name || "").trim().length > 0 },
      { weight: 2, check: (profile) => (profile.audience.personas[0]?.description || "").trim().length > 0 },
    ],
  },
  {
    label: "Competition",
    shortLabel: "Competition",
    fields: [
      { weight: 2, check: (profile) => (profile.competition.competitors[0]?.name || "").trim().length > 0 },
      {
        weight: 2,
        check: (profile) => (profile.competition.competitors[0]?.differentiator || "").trim().length > 0,
      },
      { weight: 1, check: (profile) => profile.competition.positioning_statement.trim().length > 0 },
    ],
  },
  {
    label: "Brand & channels",
    shortLabel: "Brand",
    fields: [
      { weight: 2, check: (profile) => profile.brand_channels.brand_voice.trim().length > 0 },
      { weight: 2, check: (profile) => profile.brand_channels.active_channels.length > 0 },
      { weight: 1, check: (profile) => profile.brand_channels.seasonality_notes.trim().length > 0 },
    ],
  },
];

export default function OnboardingPage() {
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState(1);
  const [maxVisitedStep, setMaxVisitedStep] = useState(1);
  const [profile, setProfile] = useState({
    company: { name: "", industry: "", website_url: "" },
    targets: { monthly_budget: "", target_cpa: "", target_roas: "", primary_kpi: "" },
    audience: { personas: [{ name: "", description: "", priority: "primary" }] },
    competition: { competitors: [{ name: "", differentiator: "" }], positioning_statement: "" },
    brand_channels: { brand_voice: "", active_channels: [], seasonality_notes: "" },
  });

  useEffect(() => {
    const draft = getBusinessProfileDraft();
    setProfile((prev) => ({
      ...prev,
      ...draft,
      audience: {
        personas:
          Array.isArray(draft.audience?.personas) && draft.audience.personas.length
            ? draft.audience.personas
            : prev.audience.personas,
      },
      competition: {
        competitors:
          Array.isArray(draft.competition?.competitors) && draft.competition.competitors.length
            ? draft.competition.competitors
            : prev.competition.competitors,
        positioning_statement: draft.competition?.positioning_statement ?? prev.competition.positioning_statement,
      },
    }));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    saveBusinessProfileDraft(profile);
  }, [profile, ready]);

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

  function goNext() {
    setStep((current) => {
      const nextStep = Math.min(current + 1, TOTAL_STEPS);
      setMaxVisitedStep((visited) => Math.max(visited, nextStep));
      return nextStep;
    });
  }

  function goBack() {
    setStep((current) => Math.max(current - 1, 1));
  }

  function skipStep() {
    goNext();
  }

  function goToStep(targetStep) {
    if (targetStep < 1 || targetStep > TOTAL_STEPS) return;
    if (targetStep <= maxVisitedStep) {
      setStep(targetStep);
    }
  }

  useEffect(() => {
    if (!ready) return;
    const highestTouched = stepProgress.reduce(
      (highest, item, index) => (item.percent > 0 ? Math.max(highest, index + 1) : highest),
      1
    );
    setMaxVisitedStep((current) => Math.max(current, highestTouched));
  }, [ready, stepProgress]);

  if (!ready) {
    return (
      <section>
        <h1 className="text-2xl font-semibold tracking-tight mb-2">Profile setup</h1>
        <p className="text-sm text-muted-foreground">Loading your saved progress...</p>
      </section>
    );
  }

  return (
    <section>
      {/* Sticky progress shell */}
      <div className="onboarding-progress-shell">
        <div className="page-toolbar" style={{ marginBottom: 8 }}>
          <h1 className="page-toolbar-title text-lg font-semibold tracking-tight">Profile setup</h1>
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
                  disabled={stepNumber > maxVisitedStep}
                  onClick={() => goToStep(stepNumber)}
                  className={cn(
                    "rounded-xl border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-default disabled:opacity-60",
                    isActive
                      ? "border-primary/30 bg-primary/8 text-foreground font-semibold"
                      : "border-transparent bg-white/70 text-muted-foreground hover:border-border hover:bg-white"
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
            <Select
              value={profile.company.industry}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, company: { ...prev.company, industry: val } }))
              }
            >
              <SelectTrigger id="company-industry">
                <SelectValue placeholder="Select industry..." />
              </SelectTrigger>
              <SelectContent>
                {INDUSTRIES.map((industry) => (
                  <SelectItem key={industry} value={industry}>{industry}</SelectItem>
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
          <div className="grid gap-1.5">
            <Label htmlFor="primary-kpi">Primary KPI</Label>
            <Select
              value={profile.targets.primary_kpi}
              onValueChange={(val) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, primary_kpi: val } }))
              }
            >
              <SelectTrigger id="primary-kpi">
                <SelectValue placeholder="Select KPI..." />
              </SelectTrigger>
              <SelectContent>
                {KPI_OPTIONS.map((kpi) => (
                  <SelectItem key={kpi} value={kpi}>{kpi}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="monthly-budget">Monthly budget</Label>
              <Input
                id="monthly-budget"
                type="number"
                min="0"
                value={profile.targets.monthly_budget}
                onChange={(e) =>
                  setProfile((prev) => ({ ...prev, targets: { ...prev.targets, monthly_budget: e.target.value } }))
                }
                placeholder="5000"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="target-cpa">Target CPA</Label>
              <Input
                id="target-cpa"
                type="number"
                min="0"
                value={profile.targets.target_cpa}
                onChange={(e) =>
                  setProfile((prev) => ({ ...prev, targets: { ...prev.targets, target_cpa: e.target.value } }))
                }
                placeholder="50"
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="target-roas">Target ROAS</Label>
            <Input
              id="target-roas"
              type="number"
              min="0"
              step="0.1"
              value={profile.targets.target_roas}
              onChange={(e) =>
                setProfile((prev) => ({ ...prev, targets: { ...prev.targets, target_roas: e.target.value } }))
              }
              placeholder="3.0"
            />
          </div>
        </div>
      )}

      {/* Step 3: Audience */}
      {step === 3 && (
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="persona-name">Primary persona name</Label>
            <Input
              id="persona-name"
              value={profile.audience.personas[0]?.name || ""}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  audience: {
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
            <Label htmlFor="competitor-name">Top competitor</Label>
            <Input
              id="competitor-name"
              value={profile.competition.competitors[0]?.name || ""}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  competition: {
                    ...prev.competition,
                    competitors: [{
                      ...(prev.competition.competitors[0] || {}),
                      name: e.target.value,
                      differentiator: prev.competition.competitors[0]?.differentiator || "",
                    }],
                  },
                }))
              }
              placeholder="Competitor name"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="differentiator">Your differentiator</Label>
            <Input
              id="differentiator"
              value={profile.competition.competitors[0]?.differentiator || ""}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  competition: {
                    ...prev.competition,
                    competitors: [{
                      ...(prev.competition.competitors[0] || {}),
                      differentiator: e.target.value,
                      name: prev.competition.competitors[0]?.name || "",
                    }],
                  },
                }))
              }
              placeholder="What makes you different?"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="positioning">Positioning statement</Label>
            <textarea
              id="positioning"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={2}
              value={profile.competition.positioning_statement}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  competition: { ...prev.competition, positioning_statement: e.target.value },
                }))
              }
              placeholder="One-line value proposition"
            />
          </div>
        </div>
      )}

      {/* Step 5: Brand & channels */}
      {step === 5 && (
        <div className="grid gap-4">
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
            <Label>Active channels</Label>
            <div className="flex flex-wrap gap-2">
              {CHANNELS.map((channel) => {
                const active = profile.brand_channels.active_channels.includes(channel);
                return (
                  <Button
                    key={channel}
                    type="button"
                    variant={active ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      setProfile((prev) => ({
                        ...prev,
                        brand_channels: {
                          ...prev.brand_channels,
                          active_channels: active
                            ? prev.brand_channels.active_channels.filter((item) => item !== channel)
                            : [...prev.brand_channels.active_channels, channel],
                        },
                      }))
                    }
                  >
                    {channel}
                  </Button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="seasonality">Seasonality notes</Label>
            <textarea
              id="seasonality"
              className="flex min-h-[80px] w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={2}
              value={profile.brand_channels.seasonality_notes}
              onChange={(e) =>
                setProfile((prev) => ({
                  ...prev,
                  brand_channels: { ...prev.brand_channels, seasonality_notes: e.target.value },
                }))
              }
              placeholder="Any seasonal pattern to keep in mind?"
            />
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            <Button type="button" asChild>
              <Link href="/generate">Go to Generate</Link>
            </Button>
            <Button type="button" variant="outline" asChild>
              <Link href="/reports">Back to Reports</Link>
            </Button>
          </div>
        </div>
      )}

      <div className="onboarding-actions">
        {step > 1 && (
          <Button type="button" variant="outline" onClick={goBack}>
            Back
          </Button>
        )}
        {step < TOTAL_STEPS && (
          <Button type="button" onClick={goNext}>
            Next
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
