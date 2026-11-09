"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Clapperboard,
  FileText,
  Hash,
  Image as ImageIcon,
  Layers,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  Type,
} from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
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
  upsertFormat,
  patchFormat,
  deleteFormat,
} from "@/lib/contentApi";
import { MEDIA_KIND_LABELS, MediaKind, PLATFORM_LABELS, Platform } from "@/lib/contentEnums";
import { PlatformGlyph } from "@/components/content/platformGlyphs";
import MarkdownSpec from "@/components/content/MarkdownSpec";
import SpecEditor from "@/components/content/SpecEditor";
import LoadError from "@/components/LoadError";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function specOf(f)        { return f?.data?.spec_markdown || ""; }
function descriptionOf(f) { return f?.description || f?.data?.description || ""; }
function mediaOf(f)       { return Array.isArray(f?.media) ? f.media : (Array.isArray(f?.data?.media) ? f.data.media : []); }
function channelsOf(f)    { return Array.isArray(f?.channels) ? f.channels : (Array.isArray(f?.data?.channels) ? f.data.channels : []); }
export function isBuiltin(f) { return f?.source === "builtin"; }

// The media kinds a format can declare, in the order the chips show. Article
// is the long form a blog channel takes; the four others mirror PostType.
const MEDIA_ORDER = [MediaKind.SLIDESHOW, MediaKind.VIDEO, MediaKind.IMAGE, MediaKind.TEXT, MediaKind.ARTICLE];
const MEDIA_ICONS = {
  [MediaKind.SLIDESHOW]: Layers,
  [MediaKind.VIDEO]:     Clapperboard,
  [MediaKind.IMAGE]:     ImageIcon,
  [MediaKind.TEXT]:      Type,
  [MediaKind.ARTICLE]:   FileText,
};
const CHANNEL_ORDER = Object.values(Platform);

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
  "from-primary/25 to-primary/15 text-brand",
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
  const [deleting, setDeleting] = useState(null);  // custom format pending delete / reset
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
  const isReset = !!deleting?.overrides_builtin;

  return (
    <section>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Layers className="h-4 w-4 text-brand" />
            <Trans>Formats</Trans>
            <span className="text-xs font-normal tabular-nums text-muted-foreground">
              {formats.length}
            </span>
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            <Trans>Recipes the drafting agent follows. Each one says which media and channels it is for; the built-ins can be customised.</Trans>
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
            A reusable recipe — structure, hook rules, image prompt rules — that the
            drafting agent follows for the media and channels you pick.
          </Trans>
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @2xl:grid-cols-3">
          {formats.map((f) => (
            <FormatCard
              key={f.id || `builtin:${f.slug}`}
              format={f}
              onView={() => setViewing(f)}
              onEdit={() => setEditing(f)}
              onDelete={isBuiltin(f) ? null : () => setDeleting(f)}
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
        key={editing?.id || editing?.slug || (editing ? "new" : "closed")}
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        projectId={projectId}
        initial={editing}
        onSaved={handleSaved}
      />

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {isReset ? <Trans>Reset to the built-in?</Trans> : <Trans>Delete this format?</Trans>}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {isReset ? (
                <Trans>
                  Your copy of <span className="font-medium text-foreground">{deletingName}</span> will
                  be removed and the built-in version comes back. Posts already drafted with it are unaffected.
                </Trans>
              ) : (
                <Trans>
                  <span className="font-medium text-foreground">{deletingName}</span> will
                  be removed. Posts already drafted with it are unaffected, but the agent can no longer pull it.
                  This can’t be undone.
                </Trans>
              )}
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
              {busy
                ? (isReset ? <Trans>Resetting…</Trans> : <Trans>Deleting…</Trans>)
                : (isReset ? <Trans>Reset format</Trans> : <Trans>Delete format</Trans>)}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Applicability badges — media kinds as words, channels as glyphs
// ---------------------------------------------------------------------------

export function AppliesTo({ format, size = "sm" }) {
  const { i18n, t } = useLingui();
  const media = mediaOf(format);
  const channels = channelsOf(format);
  const glyph = size === "sm" ? "size-3" : "size-3.5";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {media.length === 0 ? (
        <Badge variant="secondary" className="text-2xs"><Trans>Any media</Trans></Badge>
      ) : media.map((m) => {
        const Icon = MEDIA_ICONS[m] || Layers;
        return (
          <Badge key={m} variant="secondary" className="gap-1 text-2xs">
            <Icon className="h-3 w-3" aria-hidden="true" />
            {MEDIA_KIND_LABELS[m] ? i18n._(MEDIA_KIND_LABELS[m]) : m}
          </Badge>
        );
      })}
      <span className="mx-0.5 h-3 w-px bg-border" aria-hidden="true" />
      {channels.length === 0 ? (
        <span className="text-2xs text-muted-foreground"><Trans>Every channel</Trans></span>
      ) : (
        <span className="inline-flex items-center gap-1 text-muted-foreground" aria-label={t`Channels`}>
          {channels.map((c) => (
            <PlatformGlyph key={c} platform={c} className={glyph} title={PLATFORM_LABELS[c] || c} />
          ))}
        </span>
      )}
    </div>
  );
}

function SourceBadge({ format }) {
  if (isBuiltin(format)) {
    return (
      <Badge variant="outline" className="gap-1 border-primary/40 text-2xs text-brand">
        <Sparkles className="h-3 w-3" aria-hidden="true" /><Trans>Built-in</Trans>
      </Badge>
    );
  }
  if (format?.overrides_builtin) {
    return <Badge variant="outline" className="text-2xs"><Trans>Customised built-in</Trans></Badge>;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Format card
// ---------------------------------------------------------------------------

export function FormatCard({ format, onView, onEdit, onDelete }) {
  const { t, i18n } = useLingui();
  const description = descriptionOf(format) || excerptOf(format);
  const builtin = isBuiltin(format);
  const updated = builtin ? "" : relTime(format.updated_at, i18n.locale);

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
          <p className="truncate font-mono text-2xs text-muted-foreground">{format.slug}</p>
        </div>
        <div className="relative z-10 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
          <button
            type="button"
            title={builtin ? t`Customise` : t`Edit`}
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {onDelete && (
            <button
              type="button"
              title={format.overrides_builtin ? t`Reset to built-in` : t`Delete`}
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            >
              {format.overrides_builtin ? <RotateCcw className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>
      </div>

      {description && (
        <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}

      <div className="mt-3">
        <AppliesTo format={format} />
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border/40 pt-2.5 text-2xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <SourceBadge format={format} />
          {updated && <span><Trans>Updated {updated}</Trans></span>}
        </span>
        <span className="text-brand opacity-0 transition-opacity group-hover:opacity-100"><Trans>View →</Trans></span>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Detail sheet — read view
// ---------------------------------------------------------------------------

export function FormatDetailSheet({ format, open, onOpenChange, onEdit, onDelete }) {
  const { i18n } = useLingui();
  const builtin = isBuiltin(format);
  const updated = format && !builtin ? relTime(format.updated_at, i18n.locale) : "";
  const description = descriptionOf(format);

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
                  {description
                    ? <p className="text-xs text-muted-foreground">{description}</p>
                    : <p className="truncate font-mono text-2xs text-muted-foreground">{format.slug}</p>}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="gap-1 font-mono text-2xs"><Hash className="h-3 w-3" />{format.slug}</Badge>
                <SourceBadge format={format} />
                <AppliesTo format={format} size="md" />
              </div>

              <div className="mt-3 flex items-center gap-2">
                <Button size="sm" onClick={onEdit}>
                  <Pencil className="h-3.5 w-3.5" /> {builtin ? <Trans>Customise</Trans> : <Trans>Edit</Trans>}
                </Button>
                {!builtin && (
                  <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={onDelete}>
                    {format.overrides_builtin
                      ? <><RotateCcw className="h-3.5 w-3.5" /> <Trans>Reset to built-in</Trans></>
                      : <><Trash2 className="h-3.5 w-3.5" /> <Trans>Delete</Trans></>}
                  </Button>
                )}
                <span className="ml-auto text-2xs text-muted-foreground">
                  {builtin ? <Trans>Ships with Duct · customising makes your own copy</Trans> : <Trans>Updated {updated}</Trans>}
                </span>
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
// Editor sheet — create / edit / customise a built-in
// ---------------------------------------------------------------------------

/** Chip row for a multi-select; nothing selected reads as "any". */
function ChipPicker({ options, value, onChange, renderLabel, anyLabel }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((key) => {
        const on = value.includes(key);
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((k) => k !== key) : [...value, key])}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors ${
              on
                ? "border-primary bg-primary/10 text-brand"
                : "border-border text-muted-foreground hover:bg-muted"
            }`}
          >
            {on ? <Check className="h-3 w-3" aria-hidden="true" /> : <Plus className="h-3 w-3" aria-hidden="true" />}
            {renderLabel(key)}
          </button>
        );
      })}
      {value.length === 0 && anyLabel && (
        <span className="self-center text-2xs text-muted-foreground">{anyLabel}</span>
      )}
    </div>
  );
}

// `save` is injectable so /preview can open the editor without the API.
async function saveToApi({ isNew, builtin, initial, projectId, slug, name, data }) {
  if (isNew || builtin) {
    return upsertFormat({ projectId, slug, name, data });
  }
  return patchFormat(initial.id, { projectId, slug, name, data });
}

export function FormatEditorSheet({ open, onOpenChange, projectId, initial, onSaved, save = saveToApi }) {
  const { t, i18n } = useLingui();
  const isNew = !initial?.id && !isBuiltin(initial);
  const builtin = isBuiltin(initial);

  const [name, setName]               = useState("");
  const { slug, setSlug, reset: resetSlug, syncFromName } = useAutoSlug("", "-");
  const [description, setDescription] = useState("");
  const [media, setMedia]             = useState([]);
  const [channels, setChannels]       = useState([]);
  const [spec, setSpec]               = useState("");
  const [saving, setSaving]           = useState(false);
  const [err, setErr]                 = useState("");

  useEffect(() => {
    if (!open) return;
    setName(initial?.name || "");
    resetSlug(initial?.slug || "");
    setDescription(descriptionOf(initial));
    setMedia(mediaOf(initial));
    setChannels(channelsOf(initial));
    setSpec(specOf(initial));
    setErr("");
  }, [open, initial]);

  const slugValid = useMemo(() => /^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug), [slug]);

  async function doSave() {
    if (!slug.trim()) { setErr(t`Slug is required.`); return; }
    if (!slugValid)   { setErr(t`Slug must be lowercase letters, numbers, and hyphens only.`); return; }
    setSaving(true);
    setErr("");

    // Only the current shape is sent: the older slider and linked-style keys
    // are dropped here as well as on the server, so a saved row converges.
    const data = {
      description: description.trim(),
      media,
      channels,
      spec_markdown: spec,
    };

    try {
      await save({ isNew, builtin, initial, projectId, slug: slug.trim(), name: name.trim(), data });
      onSaved();
    } catch (e) {
      setErr(e.message || t`Save failed.`);
      setSaving(false);
    }
  }

  const title = isNew ? <Trans>New format</Trans> : builtin ? <Trans>Customise built-in format</Trans> : <Trans>Edit format</Trans>;
  const subtitle = isNew
    ? <Trans>A recipe the drafting agent follows. Say what it applies to, then write the spec.</Trans>
    : builtin
      ? <Trans>Saving makes this project’s own copy, which replaces the built-in here. Reset it later to go back.</Trans>
      : <Trans>Changes apply to future drafts that pull this format.</Trans>;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 !max-w-[min(820px,100vw)]">
        <SheetHeader className="border-b border-border/60 p-5">
          <SheetTitle className="text-base">{title}</SheetTitle>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-1 gap-4 @lg:grid-cols-[1fr_auto]">
            <Field label={t`Name`}>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => { if (!builtin) syncFromName(name); }}
                placeholder={t`Educational carousel`}
              />
            </Field>
            <Field
              label={t`Slug`}
              hint={builtin ? t`Fixed, so your copy stands in for the built-in` : t`Lowercase, hyphens`}
              error={slug && !slugValid ? t`Lowercase, numbers, hyphens only` : ""}
            >
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder={t`educational-carousel`}
                className="font-mono @lg:w-56"
                readOnly={builtin}
                aria-readonly={builtin || undefined}
              />
            </Field>
          </div>

          <div className="mt-4">
            <Field label={t`What it is for`} hint={t`One or two sentences. The agent reads this to pick between formats, so say what it does and when to use it.`}>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t`A swipe-through lesson, one idea per slide. Use when the post teaches or lists; not for a personal story.`}
              />
            </Field>
          </div>

          {/* Applies to — the filters the agent reads the library through. */}
          <fieldset className="mt-5 rounded-lg border border-border/60 p-4">
            <legend className="px-1 text-xs font-semibold"><Trans>Applies to</Trans></legend>
            <div className="space-y-4">
              <div>
                <Label className="text-xs"><Trans>Media</Trans></Label>
                <p className="mb-2 text-2xs text-muted-foreground"><Trans>What kind of post this recipe makes.</Trans></p>
                <ChipPicker
                  options={MEDIA_ORDER}
                  value={media}
                  onChange={setMedia}
                  anyLabel={t`Nothing picked = any media`}
                  renderLabel={(m) => {
                    const Icon = MEDIA_ICONS[m] || Layers;
                    return <><Icon className="h-3 w-3" aria-hidden="true" />{MEDIA_KIND_LABELS[m] ? i18n._(MEDIA_KIND_LABELS[m]) : m}</>;
                  }}
                />
              </div>
              <div>
                <Label className="text-xs"><Trans>Channels</Trans></Label>
                <p className="mb-2 text-2xs text-muted-foreground"><Trans>Where it is offered. The plan only pulls it for posts on these channels.</Trans></p>
                <ChipPicker
                  options={CHANNEL_ORDER}
                  value={channels}
                  onChange={setChannels}
                  anyLabel={t`Nothing picked = every channel`}
                  renderLabel={(c) => <><PlatformGlyph platform={c} className="size-3" />{PLATFORM_LABELS[c] || c}</>}
                />
              </div>
            </div>
          </fieldset>

          <div className="mt-5">
            <Label className="text-xs"><Trans>Spec document</Trans></Label>
            <p className="mb-1.5 text-2xs text-muted-foreground">
              <Trans>The full recipe — structure, hook rules, image prompt rules, failure modes. Write it like a brief to a new hire; headings and tables help the agent find things.</Trans>
            </p>
            <SpecEditor
              value={spec}
              onChange={setSpec}
              placeholder={t`Start with a title, then the structure as a table, then the rules…`}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 border-t border-border/60 p-4">
          {err && <p className="mr-auto text-xs text-destructive">{err}</p>}
          {!err && <span className="mr-auto" />}
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}><Trans>Cancel</Trans></Button>
          <Button onClick={doSave} disabled={saving || !slug.trim() || !slugValid}>
            <Save className="h-4 w-4" />
            {saving ? <Trans>Saving…</Trans> : isNew ? <Trans>Create format</Trans> : builtin ? <Trans>Save my copy</Trans> : <Trans>Save changes</Trans>}
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
