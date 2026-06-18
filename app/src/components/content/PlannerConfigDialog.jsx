"use client";

import { useEffect, useState } from "react";
import {
  Eye, Users, Bookmark, MousePointerClick, Sparkles, DollarSign,
  Target, Globe, CalendarClock, CalendarDays, Link2, Heart,
  Plus, Minus, X, Check, ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getPlannerConfig, savePlannerConfig } from "@/lib/contentApi";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";

const OBJECTIVES = [
  { id: "awareness",       label: "Awareness",       icon: Eye,               hint: "Reach new people" },
  { id: "followers",       label: "Followers",        icon: Users,             hint: "Grow the audience" },
  { id: "saves",           label: "Saves / shares",   icon: Bookmark,          hint: "High-value, saveable" },
  { id: "website_traffic", label: "Website traffic",  icon: MousePointerClick, hint: "Clicks to the link" },
  { id: "trial_signups",   label: "Trial signups",    icon: Sparkles,          hint: "Start the product" },
  { id: "sales",           label: "Sales",            icon: DollarSign,        hint: "Drive revenue" },
];

const GEO_SUGGESTIONS = ["United States", "United Kingdom", "India", "Canada", "Australia", "Germany", "Brazil"];

const CONVERSION_OBJECTIVES = new Set(["website_traffic", "trial_signups", "sales"]);

/**
 * Planner configuration modal. Sectioned, icon-led, with a live summary so the
 * user sees exactly what the agent will plan. On save it persists the config and
 * fires onSaved(config) so the workspace can ask the agent to re-plan.
 *
 * Props: { open, projectId, onClose, onSaved }
 */
export default function PlannerConfigDialog({ open, projectId, onClose, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [accounts, setAccounts] = useState([]);
  const [platforms, setPlatforms] = useState([]);
  const [postsPerDay, setPostsPerDay] = useState(1);
  const [geos, setGeos] = useState([]);
  const [geoInput, setGeoInput] = useState("");
  const [objective, setObjective] = useState("");
  const [cta, setCta] = useState("");
  const [upcoming, setUpcoming] = useState("");
  const [pains, setPains] = useState("");
  const [desires, setDesires] = useState("");
  const [objections, setObjections] = useState("");

  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    getPlannerConfig(projectId)
      .then((data) => {
        if (cancelled) return;
        const accs = data?.connected_accounts || [];
        const cfg = data?.config || {};
        setAccounts(accs);
        const uniq = [...new Set(accs.map((a) => a.platform))];
        setPlatforms(cfg.platforms?.length ? cfg.platforms : uniq.slice(0, 1));
        setPostsPerDay(cfg.posts_per_day || 1);
        setGeos((cfg.geographies || []).slice(0, 3));
        setObjective(cfg.primary_objective || "");
        setCta(cfg.cta_destination || "");
        setUpcoming(cfg.upcoming || "");
        setPains(cfg.audience_pains || "");
        setDesires(cfg.audience_desires || "");
        setObjections(cfg.audience_objections || "");
      })
      .catch((e) => { if (!cancelled) setError(e.message || "Failed to load config."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, projectId]);

  // Escape to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const uniquePlatforms = [...new Set(accounts.map((a) => a.platform))];

  function togglePlatform(p) {
    setPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }
  function addGeo(v) {
    const g = (v || "").trim();
    if (!g) return;
    setGeos((prev) => (prev.length >= 3 || prev.some((x) => x.toLowerCase() === g.toLowerCase()) ? prev : [...prev, g]));
    setGeoInput("");
  }
  function removeGeo(i) {
    setGeos((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function save() {
    if (!platforms.length) { setError("Pick at least one platform."); return; }
    if (!geos.length) { setError("Add at least one geography."); return; }
    if (!objective) { setError("Pick a primary objective."); return; }
    setSaving(true);
    setError("");
    try {
      const cfg = {
        platforms,
        posts_per_day: Number(postsPerDay) || 1,
        geographies: geos.slice(0, 3),
        primary_objective: objective,
        cta_destination: cta.trim(),
        upcoming: upcoming.trim(),
        audience_pains: pains.trim(),
        audience_desires: desires.trim(),
        audience_objections: objections.trim(),
      };
      await savePlannerConfig(projectId, cfg);
      onSaved?.(cfg);
      onClose?.();
    } catch (e) {
      setError(e.message || "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  const objMeta = OBJECTIVES.find((o) => o.id === objective);
  const summary = [
    platforms.length ? `${postsPerDay}×/day on ${platforms.map((p) => platformMeta(p).label).join(" + ")}` : null,
    geos.length ? geos[0] + (geos.length > 1 ? ` +${geos.length - 1}` : "") : null,
    objMeta ? `for ${objMeta.label.toLowerCase()}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in-0 duration-150"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl animate-in fade-in-0 zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-border/60 px-6 py-4">
          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Target className="size-4" />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-semibold">Planner configuration</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Tell the strategist what to plan for. Saving asks the agent to update the plan.
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="space-y-3 py-6">
              {[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-lg bg-muted/40" />)}
            </div>
          ) : (
            <>
              {/* Goal */}
              <Section icon={Target} title="Primary objective" desc="Anchors the funnel mix — what every post drives toward.">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {OBJECTIVES.map((o) => (
                    <ObjectiveCard key={o.id} objective={o} active={objective === o.id} onClick={() => setObjective(o.id)} />
                  ))}
                </div>
                {CONVERSION_OBJECTIVES.has(objective) && (
                  <div className="mt-3 animate-in fade-in-0 slide-in-from-top-1 duration-200">
                    <FieldLabel icon={Link2} label="CTA destination" hint="Where the bio link / offer points" />
                    <Input value={cta} onChange={(e) => setCta(e.target.value)} placeholder="e.g. maxaura.app/try" className="mt-1.5" />
                  </div>
                )}
              </Section>

              {/* Where & how often */}
              <Section icon={CalendarClock} title="Where & how often">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <FieldLabel label="Platforms" />
                    {uniquePlatforms.length === 0 ? (
                      <p className="mt-1.5 text-xs text-muted-foreground">No connected accounts — add one in the Accounts tab.</p>
                    ) : (
                      <div className="mt-1.5 flex flex-wrap gap-2">
                        {uniquePlatforms.map((p) => (
                          <PlatformChip key={p} platform={p} active={platforms.includes(p)} onClick={() => togglePlatform(p)} />
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <FieldLabel label="Posts per day" />
                    <div className="mt-1.5 flex items-center gap-3">
                      <Stepper value={postsPerDay} onChange={setPostsPerDay} min={1} max={10} />
                      <span className="text-xs text-muted-foreground">≈ {(Number(postsPerDay) || 1) * 7} / week</span>
                    </div>
                  </div>
                </div>
              </Section>

              {/* Audience focus */}
              <Section icon={Globe} title="Audience focus" desc="Up to 3 priority geographies — drives timing, language, and relevance.">
                <div className="flex flex-wrap gap-2">
                  {geos.map((g, i) => (
                    <span key={g} className="inline-flex items-center gap-1 rounded-full bg-primary/10 py-1 pl-3 pr-1.5 text-xs text-foreground">
                      {g}
                      <button type="button" onClick={() => removeGeo(i)} className="rounded-full p-0.5 text-muted-foreground hover:text-foreground" aria-label={`Remove ${g}`}>
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                  {geos.length < 3 && (
                    <input
                      value={geoInput}
                      onChange={(e) => setGeoInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addGeo(geoInput); } }}
                      placeholder={geos.length ? "Add another…" : "e.g. United States"}
                      className="min-w-[8rem] flex-1 rounded-full border border-dashed border-input bg-transparent px-3 py-1 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-primary"
                    />
                  )}
                </div>
                {geos.length < 3 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {GEO_SUGGESTIONS.filter((s) => !geos.some((g) => g.toLowerCase() === s.toLowerCase())).slice(0, 5).map((s) => (
                      <button key={s} type="button" onClick={() => addGeo(s)}
                        className="inline-flex items-center gap-0.5 rounded-full border border-border/60 px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
                        <Plus className="size-2.5" /> {s}
                      </button>
                    ))}
                  </div>
                )}
              </Section>

              {/* Context */}
              <Section icon={CalendarDays} title="Anything upcoming?" desc="Launches, promos, events, seasonal moments to plan around.">
                <Textarea value={upcoming} onChange={(e) => setUpcoming(e.target.value)} placeholder="Optional — e.g. summer sale starts Jul 1, new feature launch next week" />
              </Section>

              {/* Audience deep-dive */}
              <details className="group rounded-xl border border-border/60">
                <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  <Heart className="size-3.5" />
                  Audience deep-dive
                  <span className="text-muted-foreground/60">(optional — sharpens the hooks)</span>
                  <ChevronRight className="ml-auto size-3.5 transition-transform group-open:rotate-90" />
                </summary>
                <div className="grid grid-cols-1 gap-3 border-t border-border/50 px-4 py-3 sm:grid-cols-3">
                  <div><FieldLabel label="Pains" /><Textarea className="mt-1.5" value={pains} onChange={(e) => setPains(e.target.value)} placeholder="What frustrates them?" /></div>
                  <div><FieldLabel label="Desires" /><Textarea className="mt-1.5" value={desires} onChange={(e) => setDesires(e.target.value)} placeholder="What do they want?" /></div>
                  <div><FieldLabel label="Objections" /><Textarea className="mt-1.5" value={objections} onChange={(e) => setObjections(e.target.value)} placeholder="Why hesitate?" /></div>
                </div>
              </details>

              {error && (
                <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive animate-in fade-in-0">{error}</p>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 border-t border-border/60 px-6 py-3">
          <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            {summary ? <><span className="text-foreground/70">Planning</span> {summary}</> : "Set platforms, an objective, and a geography to start."}
          </p>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button size="sm" onClick={save} disabled={saving || loading}>
            {saving ? "Saving…" : "Save & update plan"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function Section({ icon: Icon, title, desc, children }) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">{title}</h3>
      </div>
      {desc && <p className="-mt-1.5 ml-6 text-xs text-muted-foreground">{desc}</p>}
      <div className="ml-6">{children}</div>
    </section>
  );
}

function FieldLabel({ icon: Icon, label, hint }) {
  return (
    <div className="flex items-center gap-1.5">
      {Icon && <Icon className="size-3.5 text-muted-foreground" />}
      <span className="text-xs font-medium">{label}</span>
      {hint && <span className="text-[11px] text-muted-foreground">· {hint}</span>}
    </div>
  );
}

function ObjectiveCard({ objective, active, onClick }) {
  const Icon = objective.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`group relative flex flex-col items-start gap-1 rounded-xl border p-2.5 text-left transition-all ${
        active
          ? "border-primary bg-primary/10 shadow-sm"
          : "border-border bg-card hover:border-primary/40 hover:bg-muted/40"
      }`}
    >
      {active && <Check className="absolute right-2 top-2 size-3.5 text-primary" />}
      <Icon className={`size-4 ${active ? "text-primary" : "text-muted-foreground"}`} />
      <span className="text-xs font-medium leading-tight">{objective.label}</span>
      <span className="text-[10px] leading-tight text-muted-foreground">{objective.hint}</span>
    </button>
  );
}

function PlatformChip({ platform, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border py-1 pl-2 pr-3 text-xs transition-colors ${
        active ? "border-primary bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:text-foreground"
      }`}
    >
      <PlatformGlyph platform={platform} className="size-3.5" />
      {platformMeta(platform).label}
      {active && <Check className="size-3 text-primary" />}
    </button>
  );
}

function Stepper({ value, onChange, min = 1, max = 10 }) {
  const n = Number(value) || min;
  const set = (v) => onChange(Math.max(min, Math.min(max, v)));
  return (
    <div className="inline-flex items-center rounded-lg border border-border">
      <button type="button" onClick={() => set(n - 1)} disabled={n <= min}
        className="flex size-8 items-center justify-center text-muted-foreground transition-colors hover:text-foreground disabled:opacity-30" aria-label="Decrease">
        <Minus className="size-3.5" />
      </button>
      <span className="w-9 text-center text-sm font-semibold tabular-nums">{n}</span>
      <button type="button" onClick={() => set(n + 1)} disabled={n >= max}
        className="flex size-8 items-center justify-center text-muted-foreground transition-colors hover:text-foreground disabled:opacity-30" aria-label="Increase">
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}

function Textarea({ className = "", ...props }) {
  return (
    <textarea
      rows={2}
      {...props}
      className={`w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring ${className}`}
    />
  );
}
