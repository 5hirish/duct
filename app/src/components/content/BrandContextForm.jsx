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
  Quote,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CONTENT_LANGUAGES } from "@/lib/userProfile";
import { getBrandContext, putBrandContext } from "@/lib/contentApi";
import { RULES_KEY, SAMPLES_KEY, cleanSamples } from "@/lib/voiceRules";
import WritingSamples from "@/components/content/WritingSamples";
import VoiceRulesFields from "@/components/content/VoiceRulesFields";
import { getActiveProject, hydrateProjectsFromBackend } from "@/lib/projects";
import { slugify } from "@/lib/slug";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";

/**
 * Structured form for editing a project's content brand context.
 *
 * Replaces the placeholder JSON editor on the Brand tab. Mirrors the
 * project-context page's Field/Input/Label pattern.
 *
 * Sections:
 *   - Identity (tagline, url, description)
 *   - Audience + voice (who + how)
 *   - Value proposition + content goal
 *   - Writing samples + voice rules — the text writer's own voice (#271)
 *   - Audience personas — the project's one persona list, which the
 *     pre-publish review role-plays
 *   - Pillars — repeating-row editor (add/remove)
 *   - Visual identity (primary/secondary color, style)
 */
// The project keeps up to three personas (service/project_draft.py
// MAX_DRAFT_PERSONAS), and the route holds the same field lengths.
const MAX_PERSONAS = 3;
const PERSONA_NAME_MAX = 80;
const PERSONA_DESCRIPTION_MAX = 400;
const BLANK_PERSONA = Object.freeze({ name: "", description: "" });

export default function BrandContextForm({ projectId, onSaved }) {
  const { t, i18n } = useLingui();
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
  const [contentLanguage, setContentLanguage] = useState("");
  // Everything content_brand held when it loaded, so a save keeps the keys
  // this form has no field for (features, anything newer) instead of
  // replacing the whole object with the five it knows.
  const [brandBlob, setBrandBlob] = useState({});
  // Voice (#271). A project that never set the rules follows Duct's defaults,
  // and keeps following them across a save until someone changes one.
  const [samples, setSamples] = useState([]);
  const [rules, setRules] = useState(null);
  const [rulesDefault, setRulesDefault] = useState(null);
  const [rulesCustomised, setRulesCustomised] = useState(false);
  // Audience personas (projects.audience.personas)
  const [personas, setPersonas] = useState([]);
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
        setContentLanguage(b.content_brand?.content_language || "");
        setBrandBlob(b.content_brand || {});
        setSamples(Array.isArray(b.content_brand?.[SAMPLES_KEY]) ? b.content_brand[SAMPLES_KEY] : []);
        setRules(b.voice_rules || null);
        setRulesDefault(b.voice_rules_default || null);
        setRulesCustomised(Boolean(b.content_brand?.[RULES_KEY]));
        const people = Array.isArray(b.audience_personas) ? b.audience_personas : [];
        setPersonas(people.length
          ? people.map((p) => ({ name: p.name || "", description: p.description || "" }))
          : [{ ...BLANK_PERSONA }]);
        const items = Array.isArray(b.content_pillars?.items) ? b.content_pillars.items : [];
        setPillars(items.length ? items : [{ id: "", name: "", description: "" }]);
        setPrimaryColor(b.content_visual_assets?.primary_color || "");
        setSecondaryColor(b.content_visual_assets?.secondary_color || "");
        setStyle(b.content_visual_assets?.style || "");
        setLoaded(true);
      } catch (e) {
        if (!cancelled) setError(e.message || t`Couldn't load brand context.`);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  function updatePersona(idx, patch) {
    setPersonas(prev => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }
  function addPersona() {
    setPersonas(prev => [...prev, { ...BLANK_PERSONA }].slice(0, MAX_PERSONAS));
  }
  function removePersona(idx) {
    setPersonas(prev => prev.filter((_, i) => i !== idx));
  }

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
      // Stored rules go out only while customised: "back to defaults" has to
      // clear them, or the project would freeze today's default list.
      const kept = { ...brandBlob };
      delete kept[RULES_KEY];
      const contentBrand = {
        ...kept,
        tone:         tone.trim(),
        value_prop:   valueProp.trim(),
        content_goal: contentGoal.trim(),
        do_say:       doSay.trim(),
        do_not_say:   doNotSay.trim(),
        content_language: contentLanguage,
        [SAMPLES_KEY]: cleanSamples(samples),
        ...(rulesCustomised && rules ? { [RULES_KEY]: rules } : {}),
      };
      const updated = await putBrandContext(projectId, {
        tagline:     tagline.trim(),
        description: description.trim(),
        content_brand: contentBrand,
        content_pillars:       { items: cleanedPillars },
        audience_personas: personas
          .filter(p => (p.name || "").trim())
          .map(p => ({ name: p.name.trim(), description: (p.description || "").trim() })),
        content_visual_assets: {
          primary_color:   primaryColor.trim(),
          secondary_color: secondaryColor.trim(),
          style:           style.trim(),
        },
      });
      setBrandBlob(updated?.content_brand || contentBrand);
      setSavedAt(new Date());
      onSaved?.(updated);
      // The personas live on the project, which the app caches: take the
      // server's copy so project setup shows what was just saved here.
      hydrateProjectsFromBackend().then(() => setProject(getActiveProject())).catch(() => {});
    } catch (e) {
      setError(e.message || t`Couldn't save. Please try again.`);
    } finally {
      setSaving(false);
    }
  }

  const savedAtText = savedAt ? savedAt.toLocaleTimeString(i18n.locale) : "";

  if (!loaded && !error) {
    return <p className="text-sm text-muted-foreground py-8 text-center"><Trans>Loading brand context…</Trans></p>;
  }

  return (
    <div className="max-w-4xl space-y-5 pb-24">
      <div>
        <h2 className="text-lg font-semibold tracking-tight"><Trans>Brand context</Trans></h2>
        <p className="text-sm text-muted-foreground">
          <Trans>The tone, messaging, pillars and visual identity the content agent works from.</Trans>
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/8 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Inherited from project context — single source of truth for shared fields */}
      <Card variant="quiet">
        <div className="grid gap-x-8 gap-y-4 @2xl:grid-cols-[240px_1fr]">
          <header className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Building2 className="size-4 text-muted-foreground" />
              <Trans>From project context</Trans>
            </h3>
            <p className="text-xs leading-relaxed text-muted-foreground">
              <Trans>Set once in project setup, so audit, insights and content agree.</Trans>
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link href={`/project/${projectId}#brand`}>
                <Pencil className="size-3.5" /> <Trans>Edit project context</Trans>
              </Link>
            </Button>
          </header>
          <dl className="grid grid-cols-1 gap-3 @lg:grid-cols-2">
            {/* The product's own name when no separate company is set: most
                projects are both, and "Not set" read as a gap to fill. */}
            <ReadOnly label={t`Company`} value={project?.company?.name || project?.name} />
            <ReadOnly label={t`Industry`} value={project?.company?.industry} />
            <ReadOnly label={t`Website`} value={project?.company?.website_url} />
            <ReadOnly label={t`Brand voice`} value={project?.brand_channels?.brand_voice} />
          </dl>
        </div>
      </Card>

      <Section icon={Building2} title={t`Identity`} hint={t`Tagline and description used across posts.`}>
        <Field label={t`Tagline`} hint={t`One memorable line.`}>
          <Input value={tagline} onChange={e => setTagline(e.target.value)} placeholder={t`e.g. Numbers you can trust`} />
        </Field>
        <Field label={t`Short description`} hint={t`One sentence on what you do.`}>
          <Textarea value={description} onChange={e => setDescription(e.target.value)}
            rows={2} placeholder={t`e.g. Duct reads your marketing data and says what changed.`} />
        </Field>
      </Section>

      <Section icon={Megaphone} title={t`Voice & messaging`} hint={t`How posts sound and what they must (or must not) say.`}>
        <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
          <Field label={t`Tone`} hint={t`Brand voice is inherited; tone fine-tunes it for content.`}>
            <Input value={tone} onChange={e => setTone(e.target.value)} placeholder={t`casual, punchy`} />
          </Field>
          <Field label={t`Content language`} hint={t`Plans, briefs and every post are written in it.`}>
            <Select value={contentLanguage || "auto"} onValueChange={(v) => setContentLanguage(v === "auto" ? "" : v)}>
              <SelectTrigger aria-label={t`Content language`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONTENT_LANGUAGES.map((option) => (
                  <SelectItem key={option.value || "auto"} value={option.value || "auto"}>
                    {i18n._(option.label)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field label={t`Value proposition`} hint={t`What you uniquely offer.`}>
          <Textarea value={valueProp} onChange={e => setValueProp(e.target.value)}
            rows={2} placeholder={t`e.g. Real-time AI analysis of YOUR actual selfie — not a static quiz.`} />
        </Field>
        <Field label={t`Content goal`} hint={t`What does success look like?`}>
          <Input value={contentGoal} onChange={e => setContentGoal(e.target.value)}
            placeholder={t`e.g. Drive trial signups via saveable beauty education`} />
        </Field>
        <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
          <Field
            label={<span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-success" /> <Trans>Always say</Trans></span>}
          >
            <Textarea value={doSay} onChange={e => setDoSay(e.target.value)} rows={3}
              placeholder={t`knowledgeable friend, science-backed, real results`} />
          </Field>
          <Field
            label={<span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-destructive" /> <Trans>Never say</Trans></span>}
          >
            <Textarea value={doNotSay} onChange={e => setDoNotSay(e.target.value)} rows={3}
              placeholder={t`medical claims, perfect, flawless`} />
          </Field>
        </div>
      </Section>

      <Section
        icon={Quote}
        title={t`Writing samples`}
        hint={t`Paste a few posts you wrote. Duct matches their voice on X and LinkedIn, never their topics.`}
      >
        <WritingSamples samples={samples} onChange={setSamples} />
      </Section>

      {rules && (
        <Section
          icon={ShieldCheck}
          title={t`Voice rules`}
          hint={t`What an X or LinkedIn draft never does. Duct's defaults until you change them.`}
        >
          <VoiceRulesFields
            rules={rules}
            customised={rulesCustomised}
            onChange={(next) => { setRules(next); setRulesCustomised(true); }}
            onReset={rulesDefault ? () => { setRules(rulesDefault); setRulesCustomised(false); } : undefined}
          />
        </Section>
      )}

      <Section
        icon={Users}
        title={t`Audience personas`}
        hint={t`Who your posts are for. The pre-publish review plays each one and says whether they'd stop, save or click.`}
      >
        <div className="space-y-3">
          {personas.map((p, i) => (
            <div key={i} className="rounded-xl border border-border bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-2xs font-semibold text-brand tabular-nums">
                    {i + 1}
                  </span>
                  {i === 0 ? <Trans>Primary persona</Trans> : <Trans>Persona</Trans>}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => removePersona(i)}
                  title={t`Remove this persona`}
                  aria-label={t`Remove this persona`}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
              <Input value={p.name}
                onChange={e => updatePersona(i, { name: e.target.value })}
                maxLength={PERSONA_NAME_MAX}
                aria-label={t`Persona name`}
                placeholder={t`Name and role, e.g. Priya, solo founder`} />
              <Textarea value={p.description}
                onChange={e => updatePersona(i, { description: e.target.value })}
                maxLength={PERSONA_DESCRIPTION_MAX}
                rows={3}
                className="mt-2"
                aria-label={t`Who this persona is`}
                placeholder={t`Who they are, what they want, what gets in their way, and the words they use.`} />
            </div>
          ))}
          <button
            type="button"
            onClick={addPersona}
            disabled={personas.length >= MAX_PERSONAS}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="size-4" /> <Trans>Add persona</Trans>
            <span className="text-xs text-muted-foreground">({personas.length}/{MAX_PERSONAS})</span>
          </button>
          <p className="text-xs text-muted-foreground">
            <Trans>The same personas as in project setup: an edit here shows there too.</Trans>
          </p>
        </div>
      </Section>

      <Section
        icon={Layers}
        title={t`Content pillars`}
        hint={t`Your core themes. The agent runs one research sub-agent per pillar.`}
      >
        <div className="space-y-3">
          {pillars.map((p, i) => (
            <div key={i} className="rounded-xl border border-border bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-2xs font-semibold text-brand tabular-nums">
                    {i + 1}
                  </span>
                  <Trans>Pillar</Trans>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => removePillar(i)}
                  title={t`Remove this pillar`}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
              <div className="grid grid-cols-1 gap-2 @lg:grid-cols-2">
                <Input value={p.name || ""}
                  onChange={e => updatePillar(i, { name: e.target.value })}
                  onBlur={() => { if (!p.id && p.name) updatePillar(i, { id: pillarSlug(p.name) }); }}
                  placeholder={t`Name — e.g. Face Shape Analysis`} />
                <Input value={p.id || ""}
                  onChange={e => updatePillar(i, { id: e.target.value })}
                  placeholder={t`id — auto-slugged from name`} />
              </div>
              <Textarea value={p.description || ""}
                onChange={e => updatePillar(i, { description: e.target.value })}
                rows={2}
                className="mt-2"
                placeholder={t`One-line description — what this pillar covers.`} />
            </div>
          ))}
          <button
            type="button"
            onClick={addPillar}
            disabled={pillars.length >= 8}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="size-4" /> <Trans>Add pillar</Trans>
            <span className="text-xs text-muted-foreground">({pillars.length}/8)</span>
          </button>
        </div>
      </Section>

      <Section icon={Palette} title={t`Visual identity`} hint={t`Colors and style applied to images and slides.`}>
        <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
          <ColorField label={t`Primary color`} value={primaryColor} onChange={setPrimaryColor} placeholder="#8B1A4A" />
          <ColorField label={t`Secondary color`} value={secondaryColor} onChange={setSecondaryColor} placeholder="#C9A96E" />
        </div>
        <Field label={t`Style`} hint={t`A few words the agent applies to visuals.`}>
          <Input value={style} onChange={e => setStyle(e.target.value)}
            placeholder={t`editorial / minimal / bold`} />
        </Field>
      </Section>

      {/* Sticky save bar */}
      <div className="sticky bottom-0 -mx-2 flex items-center justify-end gap-3 border-t border-border/60 bg-background/90 px-2 py-3 backdrop-blur">
        {savedAt && (
          <span className="inline-flex items-center gap-1.5 text-xs text-success">
            <Check className="size-3.5" /> <Trans>Saved {savedAtText}</Trans>
          </span>
        )}
        <Button onClick={save} disabled={saving}>{saving ? <Trans>Saving…</Trans> : <Trans>Save brand</Trans>}</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Form primitives
// ---------------------------------------------------------------------------

/** Who the project is for, in one line: its personas by name, primary first. */
/** Two-column settings section: label + description on the left, fields on the right. */
function Section({ icon: Icon, title, hint, children }) {
  return (
    <Card>
      <div className="grid gap-x-8 gap-y-4 @2xl:grid-cols-[240px_1fr]">
        <header className="space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            {Icon && <Icon className="size-4 text-muted-foreground" />}
            {title}
          </h3>
          {hint && <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>}
        </header>
        <div className="space-y-5">{children}</div>
      </div>
    </Card>
  );
}

function ReadOnly({ label, value, className = "" }) {
  return (
    <div className={className}>
      <dt className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`mt-0.5 truncate text-sm ${value ? "text-foreground" : "text-muted-foreground"}`}>
        {value || <Trans>Not set</Trans>}
      </dd>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="grid gap-2">
      <Label className="text-sm font-medium">{label}</Label>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

/** Normalize a hex string (with or without a leading #) to "#rrggbb", or "" if invalid. */
function normalizeHex(v) {
  const s = String(v || "").trim().replace(/^#/, "");
  return /^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s) ? `#${s}` : "";
}

function ColorField({ label, value, onChange, placeholder }) {
  const { t } = useLingui();
  const hex = normalizeHex(value);
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <label
          className="relative size-9 shrink-0 overflow-hidden rounded-xl border border-border bg-[conic-gradient(at_50%_50%,#0001_25%,transparent_0_50%,#0001_0_75%,transparent_0)] bg-[length:10px_10px] cursor-pointer"
          title={t`Pick a color`}
        >
          {hex && <span className="absolute inset-0" style={{ backgroundColor: hex }} />}
          <input
            type="color"
            value={hex || "#000000"}
            onChange={(e) => onChange(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
            aria-label={typeof label === "string" ? label : t`color`}
          />
        </label>
        <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      </div>
    </Field>
  );
}

// Pillar ids use underscores (face_shape) — the shared slugify takes a separator.
function pillarSlug(s) {
  return slugify(s, "_");
}
