"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  Check,
  Layers,
  Megaphone,
  Palette,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getBrandContext, putBrandContext } from "@/lib/contentApi";
import { getActiveProject } from "@/lib/projects";
import { slugify } from "@/lib/slug";

/**
 * Structured form for editing a project's content brand context.
 *
 * Replaces the placeholder JSON editor on the Brand tab. Mirrors the
 * onboarding flow's Field/Input/Label pattern.
 *
 * Sections:
 *   - Identity (tagline, url, description)
 *   - Audience + voice (who + how)
 *   - Value proposition + content goal
 *   - Pillars — repeating-row editor (add/remove)
 *   - Visual identity (primary/secondary color, style)
 */
export default function BrandContextForm({ projectId, onSaved }) {
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError]   = useState("");

  // Inherited (read-only) project context — single source of truth for the
  // shared business fields (company, website, industry, audience, voice).
  const [project, setProject] = useState(null);
  // Identity
  const [tagline, setTagline] = useState("");
  const [description, setDescription] = useState("");
  // Brand (content-specific)
  const [tone, setTone]         = useState("");
  const [valueProp, setValueProp] = useState("");
  const [contentGoal, setContentGoal] = useState("");
  const [doSay, setDoSay]       = useState("");
  const [doNotSay, setDoNotSay] = useState("");
  // Pillars
  const [pillars, setPillars]   = useState([]);
  // Visual
  const [primaryColor, setPrimaryColor]     = useState("");
  const [secondaryColor, setSecondaryColor] = useState("");
  const [style, setStyle]                   = useState("");

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      try {
        const b = await getBrandContext(projectId);
        if (cancelled) return;
        setProject(getActiveProject());
        setTagline(b.tagline || "");
        setDescription(b.description || "");
        setTone(b.content_brand?.tone || "");
        setValueProp(b.content_brand?.value_prop || "");
        setContentGoal(b.content_brand?.content_goal || "");
        setDoSay(b.content_brand?.do_say || "");
        setDoNotSay(b.content_brand?.do_not_say || "");
        const items = Array.isArray(b.content_pillars?.items) ? b.content_pillars.items : [];
        setPillars(items.length ? items : [{ id: "", name: "", description: "" }]);
        setPrimaryColor(b.content_visual_assets?.primary_color || "");
        setSecondaryColor(b.content_visual_assets?.secondary_color || "");
        setStyle(b.content_visual_assets?.style || "");
        setLoaded(true);
      } catch (e) {
        if (!cancelled) setError(e.message || "Couldn't load brand context.");
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  function updatePillar(idx, patch) {
    setPillars(prev => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }
  function addPillar() {
    setPillars(prev => [...prev, { id: "", name: "", description: "" }].slice(0, 8));
  }
  function removePillar(idx) {
    setPillars(prev => prev.filter((_, i) => i !== idx));
  }

  async function save() {
    setSaving(true); setError(""); setSavedAt(null);
    try {
      const cleanedPillars = pillars
        .filter(p => (p.name || "").trim() || (p.id || "").trim())
        .map(p => ({
          id:          pillarSlug(p.id || p.name || ""),
          name:        (p.name || "").trim(),
          description: (p.description || "").trim(),
          ...(p.research_hint ? { research_hint: p.research_hint } : {}),
        }));
      const updated = await putBrandContext(projectId, {
        tagline:     tagline.trim(),
        description: description.trim(),
        content_brand: {
          tone:         tone.trim(),
          value_prop:   valueProp.trim(),
          content_goal: contentGoal.trim(),
          do_say:       doSay.trim(),
          do_not_say:   doNotSay.trim(),
        },
        content_pillars:       { items: cleanedPillars },
        content_visual_assets: {
          primary_color:   primaryColor.trim(),
          secondary_color: secondaryColor.trim(),
          style:           style.trim(),
        },
      });
      setSavedAt(new Date());
      onSaved?.(updated);
    } catch (e) {
      setError(e.message || "Couldn't save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (!loaded && !error) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Loading brand context…</p>;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 pb-24">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Brand context</h2>
        <p className="text-sm text-muted-foreground">
          The tone, messaging, pillars, and visual identity the content agent uses. Core
          business details are inherited from your project setup.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/8 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Inherited from project context — single source of truth for shared fields */}
      <section className="rounded-2xl border border-dashed border-border bg-muted/20 p-5 md:p-6">
        <div className="grid gap-x-8 gap-y-4 md:grid-cols-[240px_1fr]">
          <header className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Building2 className="size-4 text-muted-foreground" />
              From project context
            </h3>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Company, website, audience, and brand voice live in your project setup so they
              stay consistent across audit, insights, and content.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link href={`/onboarding?project_id=${projectId}`}>
                <Pencil className="size-3.5" /> Edit in project setup
              </Link>
            </Button>
          </header>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ReadOnly label="Company" value={project?.company?.name} />
            <ReadOnly label="Industry" value={project?.company?.industry} />
            <ReadOnly label="Website" value={project?.company?.website_url} />
            <ReadOnly label="Brand voice" value={project?.brand_channels?.brand_voice} />
            <ReadOnly label="Audience" value={project?.audience?.primary_segment} className="sm:col-span-2" />
          </dl>
        </div>
      </section>

      <Section icon={Building2} title="Identity" hint="Tagline and description used across posts.">
        <Field label="Tagline" hint="One memorable line.">
          <Input value={tagline} onChange={e => setTagline(e.target.value)} placeholder="One memorable line" />
        </Field>
        <Field label="Short description" hint="One sentence on what you do.">
          <Textarea value={description} onChange={e => setDescription(e.target.value)}
            rows={2} placeholder="One sentence on what you do." />
        </Field>
      </Section>

      <Section icon={Megaphone} title="Voice & messaging" hint="How posts sound and what they must (or must not) say.">
        <Field label="Tone" hint="Brand voice is inherited; tone fine-tunes it for content.">
          <Input value={tone} onChange={e => setTone(e.target.value)} placeholder="casual, punchy" />
        </Field>
        <Field label="Value proposition" hint="What you uniquely offer.">
          <Textarea value={valueProp} onChange={e => setValueProp(e.target.value)}
            rows={2} placeholder="e.g. Real-time AI analysis of YOUR actual selfie — not a static quiz." />
        </Field>
        <Field label="Content goal" hint="What does success look like?">
          <Input value={contentGoal} onChange={e => setContentGoal(e.target.value)}
            placeholder="e.g. Drive trial signups via saveable beauty education" />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label={<span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-green-500" /> Always say</span>}
          >
            <Textarea value={doSay} onChange={e => setDoSay(e.target.value)} rows={3}
              placeholder="knowledgeable friend, science-backed, real results" />
          </Field>
          <Field
            label={<span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-rose-500" /> Never say</span>}
          >
            <Textarea value={doNotSay} onChange={e => setDoNotSay(e.target.value)} rows={3}
              placeholder="medical claims, perfect, flawless" />
          </Field>
        </div>
      </Section>

      <Section
        icon={Layers}
        title="Content pillars"
        hint="Your core themes. The agent runs one research sub-agent per pillar."
      >
        <div className="space-y-3">
          {pillars.map((p, i) => (
            <div key={i} className="rounded-xl border border-border bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary tabular-nums">
                    {i + 1}
                  </span>
                  Pillar
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => removePillar(i)}
                  title="Remove this pillar"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Input value={p.name || ""}
                  onChange={e => updatePillar(i, { name: e.target.value })}
                  onBlur={() => { if (!p.id && p.name) updatePillar(i, { id: pillarSlug(p.name) }); }}
                  placeholder="Name — e.g. Face Shape Analysis" />
                <Input value={p.id || ""}
                  onChange={e => updatePillar(i, { id: e.target.value })}
                  placeholder="id — auto-slugged from name" />
              </div>
              <Textarea value={p.description || ""}
                onChange={e => updatePillar(i, { description: e.target.value })}
                rows={2}
                className="mt-2"
                placeholder="One-line description — what this pillar covers." />
            </div>
          ))}
          <button
            type="button"
            onClick={addPillar}
            disabled={pillars.length >= 8}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="size-4" /> Add pillar
            <span className="text-xs text-muted-foreground/70">({pillars.length}/8)</span>
          </button>
        </div>
      </Section>

      <Section icon={Palette} title="Visual identity" hint="Colors and style applied to images and slides.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <ColorField label="Primary color" value={primaryColor} onChange={setPrimaryColor} placeholder="#8B1A4A" />
          <ColorField label="Secondary color" value={secondaryColor} onChange={setSecondaryColor} placeholder="#C9A96E" />
        </div>
        <Field label="Style" hint="A few words the agent applies to visuals.">
          <Input value={style} onChange={e => setStyle(e.target.value)}
            placeholder="editorial / minimal / bold" />
        </Field>
      </Section>

      {/* Sticky save bar */}
      <div className="sticky bottom-0 -mx-2 flex items-center justify-end gap-3 border-t border-border/60 bg-background/90 px-2 py-3 backdrop-blur">
        {savedAt && (
          <span className="inline-flex items-center gap-1.5 text-xs text-green-600">
            <Check className="size-3.5" /> Saved {savedAt.toLocaleTimeString()}
          </span>
        )}
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save brand"}</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Form primitives
// ---------------------------------------------------------------------------

/** Two-column settings section: label + description on the left, fields on the right. */
function Section({ icon: Icon, title, hint, children }) {
  return (
    <section className="rounded-2xl border border-border bg-card p-5 md:p-6">
      <div className="grid gap-x-8 gap-y-4 md:grid-cols-[240px_1fr]">
        <header className="space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            {Icon && <Icon className="size-4 text-muted-foreground" />}
            {title}
          </h3>
          {hint && <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>}
        </header>
        <div className="space-y-4">{children}</div>
      </div>
    </section>
  );
}

function ReadOnly({ label, value, className = "" }) {
  return (
    <div className={className}>
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`mt-0.5 truncate text-sm ${value ? "text-foreground" : "text-muted-foreground/60"}`}>
        {value || "Not set"}
      </dd>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs font-medium">{label}</Label>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

/** Normalize a hex string (with or without a leading #) to "#rrggbb", or "" if invalid. */
function normalizeHex(v) {
  const s = String(v || "").trim().replace(/^#/, "");
  return /^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s) ? `#${s}` : "";
}

function ColorField({ label, value, onChange, placeholder }) {
  const hex = normalizeHex(value);
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <label
          className="relative size-9 shrink-0 overflow-hidden rounded-xl border border-border bg-[conic-gradient(at_50%_50%,#0001_25%,transparent_0_50%,#0001_0_75%,transparent_0)] bg-[length:10px_10px] cursor-pointer"
          title="Pick a color"
        >
          {hex && <span className="absolute inset-0" style={{ backgroundColor: hex }} />}
          <input
            type="color"
            value={hex || "#000000"}
            onChange={(e) => onChange(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
            aria-label={typeof label === "string" ? label : "color"}
          />
        </label>
        <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      </div>
    </Field>
  );
}

function Textarea({ className = "", ...props }) {
  return (
    <textarea
      {...props}
      className={`flex w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y ${className}`}
    />
  );
}

// Pillar ids use underscores (face_shape) — the shared slugify takes a separator.
function pillarSlug(s) {
  return slugify(s, "_");
}
