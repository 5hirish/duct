"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Clapperboard,
  Hash,
  Layers,
  Pencil,
  Plus,
  Save,
  Trash2,
  Type,
} from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button, buttonVariants } from "@/components/ui/button";
import EmptyState from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAutoSlug } from "@/lib/slug";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { relativeTime } from "@/lib/format";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import {
  listFormats,
  listStyles,
  upsertFormat,
  patchFormat,
  deleteFormat,
} from "@/lib/contentApi";
import MarkdownSpec from "@/components/content/MarkdownSpec";
import LoadError from "@/components/LoadError";

const SLIDE_MIN = 1;
const SLIDE_MAX = 12;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function specOf(f)  { return f?.data?.spec_markdown || ""; }
function slidesOf(f){ return f?.data?.default_slide_count ?? null; }
/** Styles this format links to (renamed from caption_classes; reads both). */
function linkedOf(f) {
  const c = f?.data?.linked_styles ?? f?.data?.caption_classes;
  return Array.isArray(c) ? c : [];
}

/** A short human subtitle: the H1 tail after an em dash, else the name. */
function subtitleOf(f) {
  const spec = specOf(f);
  const h1 = spec.match(/^#\s+(.+)$/m)?.[1] || "";
  const tail = h1.split(/\s+[—-]\s+/).slice(1).join(" — ").trim();
  return tail || f?.name || f?.slug || "";
}

/** First readable sentence — skip blockquotes, headings, tables, fences. */
function excerptOf(f) {
  const spec = specOf(f);
  let inFence = false;
  for (const raw of spec.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("```")) { inFence = !inFence; continue; }
    if (inFence) continue;
    if (!line) continue;
    if (line.startsWith("#") || line.startsWith(">") || line.startsWith("|") || line.startsWith("---")) continue;
    const clean = line.replace(/[*_`]/g, "").trim();
    if (clean.length < 12) continue;
    return clean.length > 160 ? clean.slice(0, 157).trimEnd() + "…" : clean;
  }
  return "";
}

const relTime = (iso, locale) => relativeTime(iso, { fallbackAfterDays: 7, locale });

const ACCENTS = [
  "from-destructive/25 to-warning/15 text-destructive",
  "from-primary/25 to-primary/15 text-primary",
  "from-success/25 to-success/15 text-success",
  "from-info/25 to-info/15 text-info",
  "from-warning/25 to-warning/15 text-warning",
];
function accentFor(f) {
  const key = (f?.slug || "?").toString();
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return ACCENTS[h % ACCENTS.length];
}
function glyphFor(f) {
  const slug = (f?.slug || "").replace(/^format-/, "");
  return (slug || f?.name || "·").slice(0, 2).toUpperCase();
}

// ---------------------------------------------------------------------------
// FormatLibrary — list + CRUD orchestration
// ---------------------------------------------------------------------------

export default function FormatLibrary({ projectId }) {
  const { t } = useLingui();
  const [formats, setFormats] = useState([]);
  const [loading, setLoading] = useState(true);
  // Two failures, kept apart: `loadError` means the list never arrived and the
  // section is empty behind it (LoadError, with a retry); `error` is an action
  // that failed against a list still on screen.
  const [error,   setError]   = useState("");
  const [loadError, setLoadError] = useState("");

  const [viewing, setViewing] = useState(null);   // format being viewed
  const [editing, setEditing] = useState(null);   // format being edited, or {} for new
  const [deleting, setDeleting] = useState(null);  // format pending delete
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setError("");
      setLoadError("");
      const list = await listFormats(projectId);
      setFormats(Array.isArray(list) ? list : []);
    } catch (e) {
      setLoadError(e.message || "");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (projectId) { setLoading(true); refresh(); } }, [projectId]);

  async function handleSaved() {
    setEditing(null);
    await refresh();
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await deleteFormat(deleting.id);
      setDeleting(null);
      setViewing(null);
      await refresh();
    } catch (e) {
      setError(e.message || t`That format could not be deleted — it is still in the library.`);
    } finally {
      setBusy(false);
    }
  }

  const deletingName = deleting?.name || deleting?.slug;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Layers className="h-4 w-4 text-primary" />
            <Trans>Formats</Trans>
            <span className="text-xs font-normal tabular-nums text-muted-foreground">
              {formats.length}
            </span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            <Trans>Reusable post recipes the drafting agent pulls at generation time.</Trans>
          </p>
        </div>
        <Button size="sm" onClick={() => setEditing({})}>
          <Plus className="h-4 w-4" /> <Trans>New format</Trans>
        </Button>
      </div>

      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}

      {loadError && (
        <LoadError
          what={t`your formats`}
          detail={loadError}
          onRetry={() => { setLoading(true); refresh(); }}
        />
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @2xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      ) : formats.length === 0 ? (
        <EmptyState
          icon={Layers}
          title={t`No formats yet`}
          actions={
            <Button size="sm" onClick={() => setEditing({})}>
              <Plus className="size-4" aria-hidden="true" /> <Trans>Create your first format</Trans>
            </Button>
          }
        >
          <Trans>
            A reusable recipe — slide structure, caption styles, image prompt rules — that the
            drafting agent follows.
          </Trans>
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @2xl:grid-cols-3">
          {formats.map((f) => (
            <FormatCard
              key={f.id}
              format={f}
              onView={() => setViewing(f)}
              onEdit={() => setEditing(f)}
              onDelete={() => setDeleting(f)}
            />
          ))}
        </div>
      )}

      <FormatDetailSheet
        format={viewing}
        open={!!viewing}
        onOpenChange={(o) => !o && setViewing(null)}
        onEdit={() => { const f = viewing; setViewing(null); setEditing(f); }}
        onDelete={() => setDeleting(viewing)}
      />

      <FormatEditorSheet
        key={editing?.id || (editing ? "new" : "closed")}
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        projectId={projectId}
        initial={editing}
        onSaved={handleSaved}
      />

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle><Trans>Delete this format?</Trans></AlertDialogTitle>
            <AlertDialogDescription>
              <Trans>
                <span className="font-medium text-foreground">{deletingName}</span> will
                be removed. Posts already drafted with it are unaffected, but the agent can no longer pull it.
                This can’t be undone.
              </Trans>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}><Trans>Cancel</Trans></AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); confirmDelete(); }}
              disabled={busy}
              // Was `bg-destructive text-white`, which is off canon twice: DESIGN.md
              // makes the destructive action tinted rather than filled, and a
              // hardcoded white does not follow `--destructive-foreground` into dark,
              // where it measured 2.89:1 on the lifted coral.
              className={buttonVariants({ variant: "destructive" })}
            >
              {busy ? <Trans>Deleting…</Trans> : <Trans>Delete format</Trans>}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Format card
// ---------------------------------------------------------------------------

function FormatCard({ format, onView, onEdit, onDelete }) {
  const { t, i18n } = useLingui();
  const slides = slidesOf(format);
  const linked = linkedOf(format);
  const excerpt = excerptOf(format);
  const updated = relTime(format.updated_at, i18n.locale);
  const linkedCount = linked.length;

  return (
    <article className="group relative flex flex-col rounded-xl border border-border/70 bg-card p-4 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-ring/50">
      <div className="flex items-start gap-3">
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-sm font-bold ${accentFor(format)}`}>
          {glyphFor(format)}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">
            {/* after:inset-0 stretches the hit area over the whole card, so the
                mouse keeps its big target and the keyboard gets one real control. */}
            <button
              type="button"
              onClick={onView}
              className="block w-full cursor-pointer truncate text-left after:absolute after:inset-0 after:rounded-xl after:content-[''] outline-none"
            >
              {format.name || format.slug}
            </button>
          </h3>
          <p className="truncate text-xs text-muted-foreground">{subtitleOf(format)}</p>
        </div>
        <div className="relative z-10 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            title={t`Edit`}
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title={t`Delete`}
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {excerpt && (
        <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{excerpt}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="gap-1 font-mono text-2xs">
          <Hash className="h-3 w-3" />{format.slug}
        </Badge>
        {slides != null && (
          <Badge variant="secondary" className="gap-1 text-2xs">
            <Clapperboard className="h-3 w-3" /><Plural value={slides} one="# slide" other="# slides" />
          </Badge>
        )}
        {linked.length > 0 && (
          <Badge variant="secondary" className="gap-1 text-2xs">
            <Type className="h-3 w-3" /><Plural value={linkedCount} one="# linked style" other="# linked styles" />
          </Badge>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border/40 pt-2.5 text-2xs text-muted-foreground">
        <span><Trans>Updated {updated}</Trans></span>
        <span className="text-primary opacity-0 transition-opacity group-hover:opacity-100"><Trans>View →</Trans></span>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Detail sheet — read view
// ---------------------------------------------------------------------------

function FormatDetailSheet({ format, open, onOpenChange, onEdit, onDelete }) {
  const { i18n } = useLingui();
  const slides = slidesOf(format);
  const linked = linkedOf(format);
  const updated = format ? relTime(format.updated_at, i18n.locale) : "";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 !max-w-[min(840px,100vw)]">
        {format && (
          <>
            <SheetHeader className="space-y-0 border-b border-border/60 p-5">
              <div className="flex items-start gap-3 pr-8">
                <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-base font-bold ${accentFor(format)}`}>
                  {glyphFor(format)}
                </div>
                <div className="min-w-0 flex-1">
                  <SheetTitle className="truncate text-base">{format.name || format.slug}</SheetTitle>
                  <p className="truncate text-xs text-muted-foreground">{subtitleOf(format)}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="gap-1 font-mono text-2xs"><Hash className="h-3 w-3" />{format.slug}</Badge>
                {slides != null && <Badge variant="secondary" className="text-2xs"><Plural value={slides} one="# slide" other="# slides" /></Badge>}
                {linked.map((c) => (
                  <Badge key={c} variant="ghost" className="border border-border/60 font-mono text-2xs">{c}</Badge>
                ))}
              </div>

              <div className="mt-3 flex items-center gap-2">
                <Button size="sm" onClick={onEdit}><Pencil className="h-3.5 w-3.5" /> <Trans>Edit</Trans></Button>
                <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={onDelete}>
                  <Trash2 className="h-3.5 w-3.5" /> <Trans>Delete</Trans>
                </Button>
                <span className="ml-auto text-2xs text-muted-foreground"><Trans>Updated {updated}</Trans></span>
              </div>
            </SheetHeader>

            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              {specOf(format)
                ? <MarkdownSpec>{specOf(format)}</MarkdownSpec>
                : <p className="text-sm text-muted-foreground"><Trans>This format has no spec document yet. Click <strong className="text-foreground">Edit</strong> to add one.</Trans></p>}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Editor sheet — create / edit
// ---------------------------------------------------------------------------

function FormatEditorSheet({ open, onOpenChange, projectId, initial, onSaved }) {
  const { t, i18n } = useLingui();
  const isNew = !initial?.id;

  const [name, setName]               = useState("");
  const { slug, setSlug, reset: resetSlug, syncFromName } = useAutoSlug("", "-");
  const [slideCount, setSlideCount]   = useState(7);
  const [linked, setLinked]           = useState([]);
  const [spec, setSpec]               = useState("");
  const [saving, setSaving]           = useState(false);
  const [err, setErr]                 = useState("");

  // Available base styles to link (shared registry).
  const [available, setAvailable] = useState([]);
  useEffect(() => {
    let cancelled = false;
    listStyles()
      .then((d) => { if (!cancelled) setAvailable(Array.isArray(d?.styles) ? d.styles : []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name || "");
    resetSlug(initial?.slug || "");
    const sc = slidesOf(initial);
    setSlideCount(sc == null ? 7 : Math.min(SLIDE_MAX, Math.max(SLIDE_MIN, sc)));
    setLinked(linkedOf(initial));
    setSpec(specOf(initial));
    setErr("");
  }, [open, initial]);

  const slugValid = useMemo(() => /^[a-z0-9-]+$/.test(slug), [slug]);
  const charCount = spec.length;

  function toggleLinked(key) {
    setLinked((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  }

  async function save() {
    if (!slug.trim()) { setErr(t`Slug is required.`); return; }
    if (!slugValid)   { setErr(t`Slug must be lowercase letters, numbers, and hyphens only.`); return; }
    setSaving(true);
    setErr("");

    const data = {
      ...(initial?.data || {}),
      default_slide_count: slideCount,
      linked_styles: linked,
      spec_markdown: spec,
    };
    delete data.format_style;     // removed — posts link by format_id
    delete data.caption_classes;  // renamed → linked_styles

    try {
      if (isNew) {
        await upsertFormat({ projectId, slug: slug.trim(), name: name.trim(), data });
      } else {
        await patchFormat(initial.id, { projectId, slug: slug.trim(), name: name.trim(), data });
      }
      onSaved();
    } catch (e) {
      setErr(e.message || t`Save failed.`);
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 !max-w-[min(760px,100vw)]">
        <SheetHeader className="border-b border-border/60 p-5">
          <SheetTitle className="text-base">{isNew ? <Trans>New format</Trans> : <Trans>Edit format</Trans>}</SheetTitle>
          <p className="text-xs text-muted-foreground">
            {isNew
              ? <Trans>Define a reusable post recipe. The spec doc is what the drafting agent reads.</Trans>
              : <Trans>Changes apply to future drafts that pull this format.</Trans>}
          </p>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-1 gap-4 @lg:grid-cols-2">
            <Field label={t`Name`} hint={t`Human-friendly title`}>
              <Input value={name} onChange={(e) => setName(e.target.value)} onBlur={() => syncFromName(name)} placeholder={t`Format D — UGC / Raw Authentic`} />
            </Field>
            <Field label={t`Slug`} hint={t`Stable key — lowercase, hyphens`} error={slug && !slugValid ? t`Lowercase, numbers, hyphens only` : ""}>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder={t`format-d`} className="font-mono" />
            </Field>
          </div>

          {/* Slide count — slider 1..12 */}
          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between">
              <Label className="text-xs"><Trans>Default slides</Trans></Label>
              <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">{slideCount}</span>
            </div>
            <input
              type="range"
              min={SLIDE_MIN}
              max={SLIDE_MAX}
              step={1}
              value={slideCount}
              aria-label={t`Default slides`}
              onChange={(e) => setSlideCount(Number(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
            />
            <div className="mt-1 flex justify-between text-2xs text-muted-foreground">
              <span>{SLIDE_MIN}</span><span>{SLIDE_MAX}</span>
            </div>
          </div>

          {/* Linked styles — pick from the shared base styles */}
          <div className="mt-5">
            <Label className="text-xs"><Trans>Linked styles</Trans></Label>
            <p className="mb-2 text-2xs text-muted-foreground">
              <Trans>Base styles the slide builder inlines for this format. Browse them in Library → Styles.</Trans>
            </p>
            {available.length === 0 ? (
              <p className="rounded-md border border-dashed border-border/60 px-3 py-3 text-center text-2xs text-muted-foreground">
                <Trans>No base styles available.</Trans>
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {available.map((s) => {
                  const on = linked.includes(s.key);
                  return (
                    <button
                      key={s.key}
                      type="button"
                      title={s.description}
                      onClick={() => toggleLinked(s.key)}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors ${
                        on
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {on ? <Check className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                      {s.name}
                      <span className="font-mono opacity-60">.{s.key}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="mt-5">
            <Label className="text-xs"><Trans>Spec document (Markdown)</Trans></Label>
            <p className="mb-1.5 text-2xs text-muted-foreground">
              <Trans>The full recipe — slide structure, image prompt rules, failure modes. GFM tables supported.</Trans>
            </p>
            <Tabs defaultValue="edit" className="w-full">
              <TabsList>
                <TabsTrigger value="edit"><Trans>Edit</Trans></TabsTrigger>
                <TabsTrigger value="preview"><Trans>Preview</Trans></TabsTrigger>
              </TabsList>
              <TabsContent value="edit">
                <textarea
                  value={spec}
                  aria-label={t`Format spec`}
                  onChange={(e) => setSpec(e.target.value)}
                  spellCheck={false}
                  placeholder={t`# My Format\n\n## Slide Structure\n\n| Slide | Type |\n|-------|------|\n| 1 | Hook |`}
                  className="h-[48vh] w-full resize-y rounded-md border border-border/70 bg-background p-3 font-mono text-xs leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                />
                <p className="mt-1 text-right text-2xs tabular-nums text-muted-foreground"><Plural value={charCount} one="# char" other="# chars" /></p>
              </TabsContent>
              <TabsContent value="preview">
                <div className="h-[48vh] overflow-y-auto rounded-md border border-border/70 bg-background px-4 py-3">
                  {spec.trim()
                    ? <MarkdownSpec>{spec}</MarkdownSpec>
                    : <p className="text-sm text-muted-foreground"><Trans>Nothing to preview yet.</Trans></p>}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </div>

        <div className="flex items-center gap-2 border-t border-border/60 p-4">
          {err && <p className="mr-auto text-xs text-destructive">{err}</p>}
          {!err && <span className="mr-auto" />}
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}><Trans>Cancel</Trans></Button>
          <Button onClick={save} disabled={saving || !slug.trim() || !slugValid}>
            <Save className="h-4 w-4" />
            {saving ? <Trans>Saving…</Trans> : isNew ? <Trans>Create format</Trans> : <Trans>Save changes</Trans>}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, hint, error, children }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      {hint && <p className="mb-1.5 text-2xs text-muted-foreground">{hint}</p>}
      {children}
      {error && <p className="mt-1 text-2xs text-destructive">{error}</p>}
    </div>
  );
}
