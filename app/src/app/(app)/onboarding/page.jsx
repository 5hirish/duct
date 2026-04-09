"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
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
        <h1>Profile setup</h1>
        <p className="app-subtle">Loading your saved progress...</p>
      </section>
    );
  }

  return (
    <section>
      <div className="onboarding-progress-shell">
        <div className="page-toolbar" style={{ marginBottom: 8 }}>
          <h1 className="page-toolbar-title">Profile setup</h1>
          <span className="app-subtle">{inputProgressPercent}% complete</span>
        </div>

        <div className="onboarding-progress-track-wrap">
          <div
            className="onboarding-progress-track"
            role="progressbar"
            aria-label="Onboarding completion progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={inputProgressPercent}
          >
            <span
              className="onboarding-progress-fill"
              style={{ width: `${inputProgressPercent}%` }}
            />
          </div>
        </div>

        <div className="onboarding-stepper-minimal" role="list" aria-label="Onboarding steps">
          {stepProgress.map((stepItem, index) => {
            const stepNumber = index + 1;
            const isActive = step === stepNumber;
            const isDone = stepItem.percent === 100;
            return (
              <div
                key={stepItem.shortLabel}
                role="listitem"
                className={`onboarding-step-inline${isActive ? " active" : ""}${isDone ? " done" : ""}`}
              >
                <button
                  type="button"
                  className="onboarding-step-inline-button"
                  disabled={stepNumber > maxVisitedStep}
                  onClick={() => goToStep(stepNumber)}
                >
                  <span className="onboarding-step-inline-title">{stepItem.shortLabel}</span>
                </button>
                {isDone && <Check className="onboarding-step-check" aria-hidden="true" />}
              </div>
            );
          })}
        </div>
      </div>

      {step === 1 && (
        <div>
          <div style={{ display: "grid", gap: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Company name</span>
              <input
                className="app-input onboarding-input"
                value={profile.company.name}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    company: { ...prev.company, name: event.target.value },
                  }))
                }
                placeholder="Acme Inc."
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">Industry</span>
              <select
                className="app-input onboarding-input"
                value={profile.company.industry}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    company: { ...prev.company, industry: event.target.value },
                  }))
                }
              >
                <option value="">Select industry...</option>
                {INDUSTRIES.map((industry) => (
                  <option key={industry} value={industry}>
                    {industry}
                  </option>
                ))}
              </select>
            </label>
            <label className="generate-field">
              <span className="app-subtle">Website (optional)</span>
              <input
                className="app-input onboarding-input"
                value={profile.company.website_url}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    company: { ...prev.company, website_url: event.target.value },
                  }))
                }
                placeholder="https://example.com"
              />
            </label>
          </div>
        </div>
      )}

      {step === 2 && (
        <div>
          <div style={{ display: "grid", gap: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Primary KPI</span>
              <select
                className="app-input onboarding-input"
                value={profile.targets.primary_kpi}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    targets: { ...prev.targets, primary_kpi: event.target.value },
                  }))
                }
              >
                <option value="">Select KPI...</option>
                {KPI_OPTIONS.map((kpi) => (
                  <option key={kpi} value={kpi}>
                    {kpi}
                  </option>
                ))}
              </select>
            </label>
            <div className="connections-date-row">
              <label className="generate-field">
                <span className="app-subtle">Monthly budget</span>
                <input
                  className="app-input onboarding-input"
                  type="number"
                  min="0"
                  value={profile.targets.monthly_budget}
                  onChange={(event) =>
                    setProfile((prev) => ({
                      ...prev,
                      targets: { ...prev.targets, monthly_budget: event.target.value },
                    }))
                  }
                  placeholder="5000"
                />
              </label>
              <label className="generate-field">
                <span className="app-subtle">Target CPA</span>
                <input
                  className="app-input onboarding-input"
                  type="number"
                  min="0"
                  value={profile.targets.target_cpa}
                  onChange={(event) =>
                    setProfile((prev) => ({
                      ...prev,
                      targets: { ...prev.targets, target_cpa: event.target.value },
                    }))
                  }
                  placeholder="50"
                />
              </label>
            </div>
            <label className="generate-field">
              <span className="app-subtle">Target ROAS</span>
              <input
                className="app-input onboarding-input"
                type="number"
                min="0"
                step="0.1"
                value={profile.targets.target_roas}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    targets: { ...prev.targets, target_roas: event.target.value },
                  }))
                }
                placeholder="3.0"
              />
            </label>
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          <div style={{ display: "grid", gap: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Primary persona name</span>
              <input
                className="app-input onboarding-input"
                value={profile.audience.personas[0]?.name || ""}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    audience: {
                      personas: [
                        {
                          ...(prev.audience.personas[0] || {}),
                          name: event.target.value,
                          description: prev.audience.personas[0]?.description || "",
                          priority: prev.audience.personas[0]?.priority || "primary",
                        },
                      ],
                    },
                  }))
                }
                placeholder="Marketing managers at SaaS startups"
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">Persona description</span>
              <textarea
                className="app-input app-textarea onboarding-input onboarding-textarea"
                rows={3}
                value={profile.audience.personas[0]?.description || ""}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    audience: {
                      personas: [
                        {
                          ...(prev.audience.personas[0] || {}),
                          description: event.target.value,
                          name: prev.audience.personas[0]?.name || "",
                          priority: prev.audience.personas[0]?.priority || "primary",
                        },
                      ],
                    },
                  }))
                }
                placeholder="Pain points, goals, motivations..."
              />
            </label>
          </div>
        </div>
      )}

      {step === 4 && (
        <div>
          <div style={{ display: "grid", gap: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Top competitor</span>
              <input
                className="app-input onboarding-input"
                value={profile.competition.competitors[0]?.name || ""}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    competition: {
                      ...prev.competition,
                      competitors: [
                        {
                          ...(prev.competition.competitors[0] || {}),
                          name: event.target.value,
                          differentiator: prev.competition.competitors[0]?.differentiator || "",
                        },
                      ],
                    },
                  }))
                }
                placeholder="Competitor name"
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">Your differentiator</span>
              <input
                className="app-input onboarding-input"
                value={profile.competition.competitors[0]?.differentiator || ""}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    competition: {
                      ...prev.competition,
                      competitors: [
                        {
                          ...(prev.competition.competitors[0] || {}),
                          differentiator: event.target.value,
                          name: prev.competition.competitors[0]?.name || "",
                        },
                      ],
                    },
                  }))
                }
                placeholder="What makes you different?"
              />
            </label>
            <label className="generate-field">
              <span className="app-subtle">Positioning statement</span>
              <textarea
                className="app-input app-textarea onboarding-input onboarding-textarea"
                rows={2}
                value={profile.competition.positioning_statement}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    competition: { ...prev.competition, positioning_statement: event.target.value },
                  }))
                }
                placeholder="One-line value proposition"
              />
            </label>
          </div>
        </div>
      )}

      {step === 5 && (
        <div>
          <div style={{ display: "grid", gap: 12 }}>
            <label className="generate-field">
              <span className="app-subtle">Brand voice</span>
              <select
                className="app-input onboarding-input"
                value={profile.brand_channels.brand_voice}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    brand_channels: { ...prev.brand_channels, brand_voice: event.target.value },
                  }))
                }
              >
                <option value="">Select voice...</option>
                {BRAND_VOICES.map((voice) => (
                  <option key={voice} value={voice}>
                    {voice}
                  </option>
                ))}
              </select>
            </label>

            <div className="generate-field">
              <span className="app-subtle">Active channels</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
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

            <label className="generate-field">
              <span className="app-subtle">Seasonality notes</span>
              <textarea
                className="app-input app-textarea onboarding-input onboarding-textarea"
                rows={2}
                value={profile.brand_channels.seasonality_notes}
                onChange={(event) =>
                  setProfile((prev) => ({
                    ...prev,
                    brand_channels: { ...prev.brand_channels, seasonality_notes: event.target.value },
                  }))
                }
                placeholder="Any seasonal pattern to keep in mind?"
              />
            </label>
          </div>

          <div style={{ marginTop: 20, display: "flex", gap: 10, flexWrap: "wrap" }}>
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
