"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getBrandContext, putBrandContext } from "@/lib/contentApi";

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

  // Identity
  const [tagline, setTagline] = useState("");
  const [url, setUrl]         = useState("");
  const [description, setDescription] = useState("");
  // Brand
  const [audience, setAudience] = useState("");
  const [voice, setVoice]       = useState("");
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
        setTagline(b.tagline || "");
        setUrl(b.url || "");
        setDescription(b.description || "");
        setAudience(b.content_brand?.audience || "");
        setVoice(b.content_brand?.brand_voice || "");
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
          id:          slugify(p.id || p.name || ""),
          name:        (p.name || "").trim(),
          description: (p.description || "").trim(),
          ...(p.research_hint ? { research_hint: p.research_hint } : {}),
        }));
      const updated = await putBrandContext(projectId, {
        tagline:     tagline.trim(),
        url:         url.trim(),
        description: description.trim(),
        content_brand: {
          audience:     audience.trim(),
          brand_voice:  voice.trim(),
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
    <div className="max-w-3xl space-y-6 pb-8">
      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/8 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      <Section title="Identity" hint="Who you are at a glance.">
        <Field label="Tagline">
          <Input value={tagline} onChange={e => setTagline(e.target.value)} placeholder="One memorable line" />
        </Field>
        <Field label="Website">
          <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.com" />
        </Field>
        <Field label="Short description">
          <Textarea value={description} onChange={e => setDescription(e.target.value)}
            rows={2} placeholder="One sentence on what you do." />
        </Field>
      </Section>

      <Section title="Audience & voice" hint="Who you're talking to and how.">
        <Field label="Audience" hint="Who is this content for?">
          <Textarea value={audience} onChange={e => setAudience(e.target.value)}
            rows={2} placeholder="e.g. women 16-35, beauty enthusiasts, looking for science-backed style advice" />
        </Field>
        <Field label="Brand voice" hint="Comma-separated adjectives.">
          <Input value={voice} onChange={e => setVoice(e.target.value)}
            placeholder="e.g. confident, warm, educational" />
        </Field>
        <Field label="Tone">
          <Input value={tone} onChange={e => setTone(e.target.value)} placeholder="e.g. casual" />
        </Field>
      </Section>

      <Section title="Value & goals" hint="What you offer and what you want the content to drive.">
        <Field label="Value proposition" hint="What you uniquely offer.">
          <Textarea value={valueProp} onChange={e => setValueProp(e.target.value)}
            rows={2} placeholder="e.g. Real-time AI analysis of YOUR actual selfie — not a static quiz." />
        </Field>
        <Field label="Content goal" hint="What does success look like?">
          <Input value={contentGoal} onChange={e => setContentGoal(e.target.value)}
            placeholder="e.g. Drive trial signups via saveable beauty education" />
        </Field>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Always say">
            <Textarea value={doSay} onChange={e => setDoSay(e.target.value)} rows={2}
              placeholder="e.g. knowledgeable friend, science-backed, real results" />
          </Field>
          <Field label="Never say">
            <Textarea value={doNotSay} onChange={e => setDoNotSay(e.target.value)} rows={2}
              placeholder="e.g. medical claims, perfect, flawless" />
          </Field>
        </div>
      </Section>

      <Section
        title="Pillars"
        hint="Your top content themes. The agent dispatches one research sub-agent per pillar."
      >
        <div className="space-y-2">
          {pillars.map((p, i) => (
            <div key={i} className="rounded-md border border-border bg-background p-2.5 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Pillar {i + 1}</span>
                <button
                  type="button"
                  onClick={() => removePillar(i)}
                  className="text-xs text-muted-foreground hover:text-destructive"
                  title="Remove this pillar"
                >
                  Remove
                </button>
              </div>
              <Input value={p.name || ""}
                onChange={e => updatePillar(i, { name: e.target.value })}
                placeholder="Pillar name (e.g. Face Shape Analysis)" />
              <Input value={p.id || ""}
                onChange={e => updatePillar(i, { id: e.target.value })}
                placeholder="Pillar id (e.g. face_shape — auto-slugged from name on save)" />
              <Textarea value={p.description || ""}
                onChange={e => updatePillar(i, { description: e.target.value })}
                rows={2}
                placeholder="One-line description — what this pillar covers." />
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={addPillar} disabled={pillars.length >= 8}>
            + Add pillar
          </Button>
        </div>
      </Section>

      <Section title="Visual identity" hint="Colors and style the agent applies to images and slides.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Primary color">
            <Input value={primaryColor} onChange={e => setPrimaryColor(e.target.value)}
              placeholder="#8B1A4A" />
          </Field>
          <Field label="Secondary color">
            <Input value={secondaryColor} onChange={e => setSecondaryColor(e.target.value)}
              placeholder="#C9A96E" />
          </Field>
          <Field label="Style">
            <Input value={style} onChange={e => setStyle(e.target.value)}
              placeholder="editorial / minimal / bold" />
          </Field>
        </div>
      </Section>

      <div className="flex items-center gap-3 sticky bottom-0 bg-background/95 backdrop-blur border-t border-border/60 py-3 -mx-2 px-2">
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save brand"}</Button>
        {savedAt && <span className="text-xs text-green-600">Saved {savedAt.toLocaleTimeString()}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Form primitives
// ---------------------------------------------------------------------------

function Section({ title, hint, children }) {
  return (
    <section className="space-y-2.5">
      <header>
        <h2 className="text-sm font-semibold">{title}</h2>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </header>
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

function Textarea(props) {
  return (
    <textarea
      {...props}
      className="flex w-full rounded-3xl border border-input bg-input/50 px-4 py-2.5 text-sm transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 resize-y"
    />
  );
}

function slugify(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}
