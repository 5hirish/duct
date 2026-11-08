"use client";

// The memory timeline — one component for both scopes.
//
// Project memory (shared with every member) and your memory (private to you)
// are the same surface over different rows, so the caller passes an `api`
// adapter bound to one scope plus that scope's kind groups, and everything
// else lives here rather than being forked twice and drifting.
// components/memory/MemoryPage.jsx is the one caller that switches between
// them.
//
// The surface is a list first and an editor second. A row is a title and one
// muted line: who said it, when, and what it replaced. What an agent proposed
// carries Keep and Dismiss on the row itself, because reviewing what the
// agents learned is the job this page earns its place with. Body, evidence
// and the rest of the verbs wait behind a click.
//
// See docs/engineering/2026-08-28-agent-memory-research.md §06 for what each
// affordance is for.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import {
  CalendarRange,
  ChartLine,
  Check,
  ChevronDown,
  Ellipsis,
  Building2,
  FileText,
  Flag,
  Globe,
  History,
  Lightbulb,
  MessageSquare,
  Pause,
  Pin,
  Plus,
  Scale,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Tag,
  Target,
  Trash2,
  TrendingUp,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonList } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import LoadError from "@/components/LoadError";
import { isSessionExpired } from "@/lib/authFetch";
import { dayKey, formatDate, relativeTime } from "@/lib/format";

// One glyph per group, so a row's icon and its filter chip always agree.
const GROUP_ICONS = {
  rules: ShieldCheck,
  goals: Target,
  facts: Tag,
  numbers: TrendingUp,
  findings: Lightbulb,
  outcomes: ChartLine,
  decisions: Scale,
  feedback: MessageSquare,
  reports: FileText,
  about: User,
  style: MessageSquare,
  methods: SlidersHorizontal,
  corrections: Flag,
};

const SOURCE_LABELS = {
  user: msg`You`,
  agent: msg`Agent`,
  connector: msg`Connector`,
  artifact: msg`Report`,
  system: msg`Duct`,
};

// Presets cover how people actually ask ("what changed this week"); the
// custom range is there for the rare "between the redirect and the fix".
const DATE_PRESETS = [
  { id: "any", label: msg`Any time`, days: 0 },
  { id: "7", label: msg`Last 7 days`, days: 7 },
  { id: "30", label: msg`Last 30 days`, days: 30 },
  { id: "90", label: msg`Last 90 days`, days: 90 },
];

function groupOf(groups, kind) {
  return groups.find((g) => g.kinds.includes(kind));
}

function GroupIcon({ id, className = "size-4" }) {
  const Icon = GROUP_ICONS[id] || Tag;
  return <Icon className={className} aria-hidden="true" />;
}

/** "Project settings" beats "You" for a value mirrored from a form: it says where to change it. */
function sourceLabel(entry, i18n) {
  const refs = entry.source_refs || [];
  if (refs.some((r) => r.project_profile)) return i18n._(msg`Project settings`);
  if (refs.some((r) => r.user_preferences)) return i18n._(msg`Your preferences`);
  return i18n._(SOURCE_LABELS[entry.source_type] || SOURCE_LABELS.agent);
}

function daysAgoIso(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return dayKey(d);
}

/** Evidence pointers, rendered as the links the design calls chips. */
function EvidenceLinks({ entry }) {
  const { t } = useLingui();
  const refs = entry.source_refs || [];
  if (!refs.length) return null;
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span><Trans>from</Trans></span>
      {refs.map((ref, i) => {
        if (ref.artifact_id) {
          return (
            <Link
              key={i}
              href={`/artifacts/${ref.artifact_id}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              {ref.slug || t`artifact`}
              {ref.version ? ` v${ref.version}` : ""}
              {ref.section ? ` §${ref.section}` : ""}
            </Link>
          );
        }
        if (ref.change_set_id) {
          const id = String(ref.change_set_id).slice(0, 8);
          return (
            <Link key={i} href="/execute" className="underline underline-offset-2 hover:text-foreground">
              <Trans>change set {id}</Trans>
            </Link>
          );
        }
        if (ref.conversation_id) {
          return (
            <Link
              key={i}
              href={`/activity?conversation_id=${encodeURIComponent(ref.conversation_id)}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              <Trans>the conversation</Trans>
            </Link>
          );
        }
        if (ref.project_profile) return <span key={i}><Trans>project settings</Trans></span>;
        if (ref.user_preferences) return <span key={i}><Trans>your preferences</Trans></span>;
        if (ref.connector) return <span key={i}>{ref.connector}</span>;
        if (ref.edited_by) return <span key={i}><Trans>edited by you</Trans></span>;
        return <span key={i}>{ref.source || t`recorded`}</span>;
      })}
    </p>
  );
}

/** The one muted line under a title: who, when, and what changed. */
function RowMeta({ entry, binding }) {
  const { i18n } = useLingui();
  const onlyHere = Boolean(binding && entry.project_id && entry.project_id === binding.projectId);
  const projectName = binding?.projectName || "";
  const date = formatDate(entry.valid_from || entry.observed_at, { locale: i18n.locale });
  const source = sourceLabel(entry, i18n);
  const replaced = entry.replaced;
  const replacedUntil = replaced?.until ? formatDate(replaced.until, { locale: i18n.locale }) : "";
  const replacedTitle = replaced?.title || "";
  const endedOn = entry.valid_to ? formatDate(entry.valid_to, { locale: i18n.locale }) : "";

  return (
    <p className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
      <span>{source}</span>
      <span aria-hidden="true">·</span>
      <span>{date}</span>
      {onlyHere && (
        <>
          <span aria-hidden="true">·</span>
          <span><Trans>only on {projectName}</Trans></span>
        </>
      )}
      {entry.status === "proposed" && (
        <>
          <span aria-hidden="true">·</span>
          <span className="text-warning"><Trans>needs your review</Trans></span>
        </>
      )}
      {entry.status === "superseded" && (
        <>
          <span aria-hidden="true">·</span>
          <span>{endedOn ? <Trans>replaced on {endedOn}</Trans> : <Trans>replaced</Trans>}</span>
        </>
      )}
      {entry.status === "archived" && (
        <>
          <span aria-hidden="true">·</span>
          <span><Trans>dismissed</Trans></span>
        </>
      )}
      {replaced && (
        <>
          <span aria-hidden="true">·</span>
          <span className="min-w-0 max-w-full truncate" title={replacedTitle}>
            {replacedUntil ? (
              <Trans>was “{replacedTitle}” until {replacedUntil}</Trans>
            ) : (
              <Trans>was “{replacedTitle}”</Trans>
            )}
          </span>
        </>
      )}
    </p>
  );
}

function MemoryRow({ entry, groups, binding, onPatch, onMove, onDelete, busy, focused = false }) {
  const { t, i18n } = useLingui();
  const [open, setOpen] = useState(focused);
  const [draft, setDraft] = useState(null);
  const proposed = entry.status === "proposed";
  const faded = entry.status === "superseded" || entry.status === "archived";
  const group = groupOf(groups, entry.kind);
  const groupName = group ? i18n._(group.label) : entry.kind;
  const recordedAgo = relativeTime(entry.recorded_at, { locale: i18n.locale });
  const recalls = entry.recall_count;
  const bindingName = binding?.projectName || "";

  return (
    <li className={`px-4 py-3 ${focused ? "bg-muted/40" : ""}`}>
      {/* Icon, text, and the review verbs beside them; in a narrow column the
          verbs drop under the text instead of squeezing the title to a word
          per line. */}
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 @lg:grid-cols-[auto_minmax(0,1fr)_auto]">
        <span
          title={groupName}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
        >
          <GroupIcon id={group?.id} />
        </span>

        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className={`block w-full text-left text-sm leading-snug underline-offset-2 hover:underline ${
              faded ? "text-muted-foreground line-through decoration-muted-foreground/60" : ""
            }`}
          >
            {entry.title}
          </button>
          <RowMeta entry={entry} binding={binding} />
        </div>

        {proposed && (
          // The review is the point of the page, so it is on the row, not
          // behind the click: two verbs, the keep one quietly heavier.
          <div className="col-start-2 flex shrink-0 items-center gap-1 @lg:col-start-3">
            <Button size="xs" variant="outline" disabled={busy}
              onClick={() => onPatch(entry, { status: "confirmed" })}>
              <Check /> <Trans>Keep</Trans>
            </Button>
            <Button size="xs" variant="ghost" disabled={busy}
              onClick={() => onPatch(entry, { status: "archived" })}>
              <X /> <Trans>Dismiss</Trans>
            </Button>
          </div>
        )}
        {!proposed && entry.pinned && (
          <Pin className="col-start-3 size-3.5 shrink-0 text-muted-foreground" aria-label={t`Pinned`} />
        )}
      </div>

      {open && (
        // Indented to the title's left edge: the icon (2rem) plus the gap.
        <div className="mt-3 space-y-3 pl-11">
          {draft === null ? (
            <>
              {entry.body && <p className="whitespace-pre-wrap text-sm leading-relaxed">{entry.body}</p>}
              <p className="text-xs text-muted-foreground">
                {groupName}
                {" · "}
                <Trans>Recorded {recordedAgo}</Trans>
                {recalls ? <>{" · "}<Plural value={recalls} one="used in # answer" other="used in # answers" /></> : null}
              </p>
              <EvidenceLinks entry={entry} />
              <div className="flex flex-wrap gap-1">
                <Button size="xs" variant="ghost" disabled={busy}
                  onClick={() => setDraft({ title: entry.title, body: entry.body })}>
                  <Trans>Edit</Trans>
                </Button>
                <Button size="xs" variant="ghost" disabled={busy}
                  onClick={() => onPatch(entry, { pinned: !entry.pinned })}>
                  <Pin /> {entry.pinned ? <Trans>Unpin</Trans> : <Trans>Pin</Trans>}
                </Button>
                {onMove && binding && (
                  entry.project_id ? (
                    <Button size="xs" variant="ghost" disabled={busy} onClick={() => onMove(entry, false)}>
                      <Globe /> <Trans>Use on every project</Trans>
                    </Button>
                  ) : (
                    <Button size="xs" variant="ghost" disabled={busy} onClick={() => onMove(entry, true)}>
                      <Building2 /> <Trans>Only on {bindingName}</Trans>
                    </Button>
                  )
                )}
                <Button size="xs" variant="ghost" disabled={busy} onClick={() => onDelete(entry)}>
                  <Trash2 /> <Trans>Delete</Trans>
                </Button>
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <Input
                value={draft.title}
                aria-label={t`Memory title`}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              />
              <Textarea
                value={draft.body}
                aria-label={t`Memory detail`}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                rows={3}
                placeholder={t`Why it matters, and how an agent should use it.`}
              />
              <div className="flex gap-2">
                <Button size="sm" disabled={busy}
                  onClick={() => onPatch(entry, draft).then(() => setDraft(null))}>
                  <Trans>Save</Trans>
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                  <Trans>Cancel</Trans>
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function RememberForm({ groups, binding, placeholder, onCreate, busy, onClose }) {
  const { t, i18n } = useLingui();
  const choices = groups.filter((g) => g.create !== false);
  const [groupId, setGroupId] = useState(choices[0]?.id || "");
  // Private memory only: everywhere by default, one project when asked.
  const [where, setWhere] = useState("all");
  const bindingName = binding?.projectName || "";
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const kind = choices.find((g) => g.id === groupId)?.kinds[0];

  return (
    <form
      className="space-y-2 rounded-xl border border-border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim() || !kind) return;
        const entry = { kind, title: title.trim(), body: body.trim() };
        if (binding && where === "here") entry.project_id = binding.projectId;
        onCreate(entry);
      }}
    >
      <div className="flex flex-wrap gap-2">
        <Select value={groupId} onValueChange={setGroupId}>
          <SelectTrigger className="w-36" aria-label={t`What kind of memory`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper">
            {choices.map((g) => (
              <SelectItem key={g.id} value={g.id}>{i18n._(g.label)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={placeholder}
          aria-label={t`What to remember`}
          className="min-w-[14rem] flex-1"
          autoFocus
        />
      </div>
      {binding && (
        <Select value={where} onValueChange={setWhere}>
          <SelectTrigger className="w-auto" aria-label={t`Where it applies`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper">
            <SelectItem value="all"><Trans>On every project</Trans></SelectItem>
            <SelectItem value="here"><Trans>Only on {bindingName}</Trans></SelectItem>
          </SelectContent>
        </Select>
      )}
      <Textarea
        value={body}
        aria-label={t`Why it matters`}
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        placeholder={t`Why it matters. Optional.`}
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !title.trim()}><Trans>Save</Trans></Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClose}><Trans>Cancel</Trans></Button>
      </div>
    </form>
  );
}

/** A filter chip's look: one colour when on, none when off. */
function chipClass(active) {
  return `inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-colors [&_svg]:size-3.5 [&_svg]:shrink-0 ${
    active ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"
  }`;
}

function Chip({ active, onClick, children }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={chipClass(active)}>
      {children}
    </button>
  );
}

/** "When": presets first, a custom range behind the last item. */
function DateFilter({ preset, onPreset }) {
  const { i18n } = useLingui();
  const current = DATE_PRESETS.find((p) => p.id === preset);
  const label = current ? i18n._(current.label) : i18n._(msg`Custom range`);
  return (
    <DropdownMenu>
      {/* A menu button, not a toggle, so it borrows the chip's look only. */}
      <DropdownMenuTrigger className={chipClass(preset !== "any")}>
        <CalendarRange aria-hidden="true" /> {label} <ChevronDown aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={preset} onValueChange={onPreset}>
          {DATE_PRESETS.map((p) => (
            <DropdownMenuRadioItem key={p.id} value={p.id}>{i18n._(p.label)}</DropdownMenuRadioItem>
          ))}
          <DropdownMenuRadioItem value="custom"><Trans>Custom range…</Trans></DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * @param api      { list, create, patch, remove, get?, setPaused?, reset? } —
 *                 promises bound to one scope. The optional ones hide their
 *                 affordance when absent.
 * @param groups   The scope's kind groups (lib/memoryApi.js): the filter
 *                 chips, the row icons and the "Remember" form's choices.
 * @param focusId  A memory id from a deep link (a chip in the chat). The entry
 *                 is opened and highlighted, and fetched on its own if the
 *                 current filters would not have listed it.
 */
export default function MemoryTimeline({
  api,
  groups,
  binding = null,
  addPlaceholder,
  emptyHint,
  errorSubject,
  resetPrompt,
  signedIn = true,
  focusId = "",
}) {
  const { t, i18n } = useLingui();
  const titleHint = addPlaceholder ?? t`One line, with its number or date if it has one.`;
  const errorWhat = errorSubject ?? t`your memory`;
  const resetText = resetPrompt ?? t`The agents lose every fact here from their next turn. This cannot be undone.`;
  const [items, setItems] = useState(null); // null = loading
  const [kindsSeen, setKindsSeen] = useState([]);
  const [groupId, setGroupId] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [paused, setPaused] = useState(false);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [datePreset, setDatePreset] = useState("any");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);
  // Two kinds of failure, kept apart on purpose: `error` is a mutation that
  // did not take (shown inline, the list is still trustworthy), `loadError` is
  // a list that never arrived — which must replace the empty state rather than
  // sit above it, because "nothing yet" is a claim we cannot make.
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [linked, setLinked] = useState(null); // deep-linked entry outside the filters
  const [toReview, setToReview] = useState(0);

  const kind = groups.find((g) => g.id === groupId)?.kinds.join(",") || "";
  const preset = DATE_PRESETS.find((p) => p.id === datePreset);
  const since = preset?.days ? daysAgoIso(preset.days) : datePreset === "custom" ? fromDate : "";
  const until = datePreset === "custom" ? toDate : "";

  const load = useCallback(() => {
    if (!signedIn) {
      setItems([]);
      return;
    }
    setError("");
    setLoadError("");
    api
      .list({
        q: query,
        kind,
        status: reviewOnly ? "proposed" : "",
        fromDate: since,
        toDate: until,
        includeSuperseded: showHistory,
      })
      .then((body) => {
        const rows = body?.items || [];
        setItems(rows);
        setPaused(Boolean(body?.memory_paused));
        // Keep the widest set of chips seen, so filtering to one group does
        // not remove the chips you need to filter back out of it.
        setKindsSeen((prev) => Array.from(new Set([...prev, ...(body?.kinds || [])])));
        if (!reviewOnly) setToReview(rows.filter((e) => e.status === "proposed").length);
      })
      .catch((err) => {
        // A retired session is already redirecting to sign-in.
        if (isSessionExpired(err)) return;
        setItems(null);
        setLoadError(err.message || "");
      });
  }, [api, query, kind, reviewOnly, since, until, showHistory, signedIn]);

  useEffect(() => {
    setItems(null);
    load();
  }, [load]);

  // A chip in the chat links straight to one entry. If the list already has it,
  // the row highlights in place; if a filter or the page limit excluded it, it
  // is fetched and shown on its own so the link never dead-ends.
  useEffect(() => {
    if (!focusId || !signedIn || items === null) return;
    if (items.some((entry) => entry.id === focusId)) {
      setLinked(null);
      return;
    }
    if (!api.get) return;
    let alive = true;
    api
      .get({ memoryId: focusId })
      .then((entry) => alive && setLinked(entry))
      .catch(() => alive && setLinked(null));
    return () => {
      alive = false;
    };
  }, [focusId, items, api, signedIn]);

  const run = useCallback(
    async (fn, failure) => {
      setBusy(true);
      try {
        const out = await fn();
        load();
        return out;
      } catch (err) {
        if (!isSessionExpired(err)) setError(err.message || failure);
      } finally {
        setBusy(false);
      }
    },
    [load]
  );

  // Day groups: the timeline reads as dates, not as a flat list.
  const days = useMemo(() => {
    const out = [];
    for (const entry of items || []) {
      const label = formatDate(entry.observed_at, { locale: i18n.locale }) || t`Undated`;
      const last = out[out.length - 1];
      if (last && last.label === label) last.entries.push(entry);
      else out.push({ label, entries: [entry] });
    }
    return out;
  }, [items, t, i18n.locale]);

  const presentGroups = groups.filter((g) => g.kinds.some((k) => kindsSeen.includes(k)));
  const filtered = Boolean(query || kind || since || until || reviewOnly);
  const dateInput = "h-9 rounded-md border border-input bg-transparent px-2 text-xs text-muted-foreground";

  const rowHandlers = (after) => ({
    onPatch: (row, patch) =>
      run(() => api.patch({ memoryId: row.id, ...patch }), t`Update failed.`).then(after),
    onDelete: (row) => run(() => api.remove({ memoryId: row.id }), t`Delete failed.`).then(after),
    onMove: api.move
      ? (row, bound) => run(() => api.move({ memoryId: row.id, bound }), t`Could not move that.`).then(after)
      : undefined,
  });

  return (
    <div className="space-y-4">
      {/* Search is the main control, so it gets the width. */}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <div className="relative min-w-[12rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (!e.target.value.trim()) setQuery("");
            }}
            placeholder={t`Search memory…`}
            aria-label={t`Search memory`}
            className="pl-8"
          />
        </div>
        <Button type="button" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <Plus /> <Trans>Remember</Trans>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" size="icon" variant="ghost" aria-label={t`More`}>
              <Ellipsis />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {/* "Superseded" said nothing to anyone. A current fact already
                says what it replaced; history brings back the old rows
                themselves, and anything dismissed. */}
            <DropdownMenuCheckboxItem checked={showHistory} onCheckedChange={(v) => setShowHistory(Boolean(v))}>
              <History /> <Trans>Show history</Trans>
            </DropdownMenuCheckboxItem>
            {api.setPaused && (
              <DropdownMenuCheckboxItem
                checked={paused}
                disabled={busy}
                onCheckedChange={(next) =>
                  run(() => api.setPaused({ paused: Boolean(next) }), t`Could not change that.`)
                }
              >
                <Pause /> <Trans>Pause remembering</Trans>
              </DropdownMenuCheckboxItem>
            )}
            {api.reset && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  disabled={busy}
                  // Radix closes the menu on select, so the confirm has to be
                  // asked on the next tick or the dialog opens into a closing
                  // popover and inherits its exit animation.
                  onSelect={() => setTimeout(() => setResetting(true), 0)}
                >
                  <Trash2 /> <Trans>Delete everything</Trans>
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </form>

      {(presentGroups.length > 0 || items?.length > 0 || datePreset !== "any") && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!groupId && !reviewOnly} onClick={() => { setGroupId(""); setReviewOnly(false); }}>
            <Trans>All</Trans>
          </Chip>
          {(toReview > 0 || reviewOnly) && (
            <Chip active={reviewOnly} onClick={() => setReviewOnly((v) => !v)}>
              <span className={reviewOnly ? "" : "text-warning"}>
                <Plural value={toReview} one="# to review" other="# to review" />
              </span>
            </Chip>
          )}
          {presentGroups.map((g) => (
            <Chip key={g.id} active={g.id === groupId} onClick={() => setGroupId(g.id === groupId ? "" : g.id)}>
              <GroupIcon id={g.id} /> {i18n._(g.label)}
            </Chip>
          ))}
          <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            {filtered && items && (
              <Plural value={items.length} one="# match" other="# matches" />
            )}
            <DateFilter preset={datePreset} onPreset={setDatePreset} />
          </span>
        </div>
      )}

      {datePreset === "custom" && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span><Trans>From</Trans></span>
          <input
            type="date"
            value={fromDate}
            max={toDate || undefined}
            aria-label={t`From date`}
            onChange={(e) => setFromDate(e.target.value)}
            className={dateInput}
          />
          <span><Trans>to</Trans></span>
          <input
            type="date"
            value={toDate}
            min={fromDate || undefined}
            aria-label={t`To date`}
            onChange={(e) => setToDate(e.target.value)}
            className={dateInput}
          />
        </div>
      )}

      {paused && (
        <p className="text-xs text-muted-foreground">
          <Trans>
            Remembering is paused. Nothing new is saved; everything below stays
            readable and still reaches the agents.
          </Trans>
        </p>
      )}

      {adding && (
        <RememberForm
          groups={groups}
          binding={binding}
          placeholder={titleHint}
          busy={busy}
          onClose={() => setAdding(false)}
          onCreate={(entry) =>
            run(async () => {
              await api.create(entry);
              setAdding(false);
            }, t`Could not save that.`)
          }
        />
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {signedIn && loadError && (
        <LoadError what={errorWhat} detail={loadError} onRetry={load} />
      )}

      {!signedIn && <p className="app-subtle"><Trans>Sign in to see this.</Trans></p>}
      {signedIn && !loadError && items === null && <SkeletonList rows={4} label={t`Loading memories`} />}

      {linked && (
        <div className="overflow-hidden rounded-xl border border-border">
          <p className="border-b border-border/60 bg-muted/30 px-4 py-1.5 text-xs font-medium text-muted-foreground">
            <Trans>Linked from chat, outside the filters below</Trans>
          </p>
          <ul>
            <MemoryRow entry={linked} groups={groups} binding={binding} busy={busy} focused {...rowHandlers(() => setLinked(null))} />
          </ul>
        </div>
      )}

      {signedIn && !loadError && items && items.length === 0 && (
        <p className="app-subtle">{filtered ? <Trans>Nothing matches that filter.</Trans> : emptyHint}</p>
      )}

      {signedIn && days.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border">
          {days.map((day, gi) => (
            <div key={day.label} className={gi > 0 ? "border-t border-border/60" : ""}>
              <p className="bg-muted/30 px-4 py-2 text-xs font-medium text-muted-foreground">
                {day.label}
              </p>
              <ul className="divide-y divide-border/60">
                {day.entries.map((entry) => (
                  <MemoryRow
                    key={entry.id}
                    entry={entry}
                    groups={groups}
                    binding={binding}
                    busy={busy}
                    focused={entry.id === focusId}
                    {...rowHandlers(() => {})}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={resetting}
        onOpenChange={setResetting}
        busy={busy}
        title={t`Delete every memory here?`}
        description={resetText}
        action={t`Delete everything`}
        destructive
        onConfirm={() => {
          setResetting(false);
          run(() => api.reset(), t`Reset failed.`);
        }}
      />
    </div>
  );
}
