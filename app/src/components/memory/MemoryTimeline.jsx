"use client";

// The memory timeline — one component, two scopes.
//
// Project memory (/project/[id]/memory) and user memory (/memory) are the same
// surface over different rows: entries grouped by day, superseded ones greyed
// with their validity range, each expanding to its body and evidence, with
// confirm / edit / pin / not-relevant / delete and the pause and reset
// controls. The scope only differs in *which* API the calls go to, so the page
// passes an `api` adapter and everything else lives here rather than being
// forked twice and drifting.
//
// The surface is deliberately quiet. A row is a title and one muted line; the
// kind is an icon with its name on hover, the source is a word, the validity a
// range. Everything else — body, evidence, recall count, the actions — waits
// behind a click, because "what does Duct know about this account" is read as
// a list first and edited one row at a time.
//
// See docs/engineering/2026-08-28-agent-memory-research.md §06 for what each
// affordance is for, and 2026-08-29-agent-memory-taxonomy-and-ux-patterns.md
// Part B for why.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CalendarRange,
  Check,
  Ellipsis,
  Eye,
  EyeOff,
  FileText,
  Flag,
  Flame,
  Lightbulb,
  MessageSquare,
  Pause,
  Pin,
  Plus,
  Scale,
  Search,
  Tag,
  Target,
  Trash2,
  TrendingUp,
  User,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import LoadError from "@/components/LoadError";
import { isSessionExpired } from "@/lib/authFetch";
import { formatDate, relativeTime, titleCase } from "@/lib/format";

// One lucide glyph per kind, for both vocabularies (project and user memory).
// Anything unmapped gets the tag, which is what "some fact" looks like.
const KIND_ICONS = {
  goal: Target,
  decision: Scale,
  incident: Flame,
  status: Pin,
  metric: TrendingUp,
  milestone: Flag,
  event: Zap,
  conclusion: Lightbulb,
  action: Wrench,
  watch: Eye,
  entity: Tag,
  artifact: FileText,
  identity: User,
  communication: MessageSquare,
  method: Wrench,
  tooling: Wrench,
  process: Flag,
  feedback: MessageSquare,
};

const SOURCE_LABELS = {
  user: "You",
  agent: "Agent",
  connector: "Connector",
  artifact: "Artifact",
  system: "System",
};

const EVENT_KINDS = ["milestone", "event", "decision"];

function KindIcon({ kind, className = "size-3.5" }) {
  const Icon = KIND_ICONS[kind] || Tag;
  return <Icon className={className} aria-hidden="true" />;
}

/** "1 Jul 2026 – present" / "14 – 21 Aug 2026" / a period string / a bare date. */
function validity(entry) {
  if (entry.period) return entry.period;
  const from = formatDate(entry.valid_from || entry.observed_at);
  if (EVENT_KINDS.includes(entry.kind)) return from;
  return `${from} – ${entry.valid_to ? formatDate(entry.valid_to) : "present"}`;
}

/** Evidence pointers, rendered as the links the design calls chips. */
function EvidenceLinks({ entry }) {
  const refs = entry.source_refs || [];
  if (!refs.length) return null;
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span>from</span>
      {refs.map((ref, i) => {
        if (ref.artifact_id) {
          return (
            <Link
              key={i}
              href={`/artifacts/${ref.artifact_id}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              {ref.slug || "artifact"}
              {ref.version ? ` v${ref.version}` : ""}
              {ref.section ? ` §${ref.section}` : ""}
            </Link>
          );
        }
        if (ref.change_set_id) {
          return (
            <Link key={i} href="/execute" className="underline underline-offset-2 hover:text-foreground">
              change set {String(ref.change_set_id).slice(0, 8)}
            </Link>
          );
        }
        if (ref.conversation_id) {
          const turns = ref.seq ? ` turns ${ref.seq[0]}–${ref.seq[1]}` : "";
          return (
            <Link
              key={i}
              href={`/activity?conversation_id=${encodeURIComponent(ref.conversation_id)}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              conversation{turns}
            </Link>
          );
        }
        if (ref.project_profile) return <span key={i}>project settings · {ref.project_profile}</span>;
        if (ref.user_preferences) return <span key={i}>preferences · {ref.user_preferences}</span>;
        if (ref.connector) return <span key={i}>{ref.connector}</span>;
        if (ref.edited_by) return <span key={i}>edited by you</span>;
        return <span key={i}>{ref.source || "recorded"}</span>;
      })}
    </p>
  );
}

function MemoryRow({ entry, onPatch, onDelete, busy, focused = false }) {
  const [open, setOpen] = useState(focused);
  const [draft, setDraft] = useState(null);
  const superseded = entry.status === "superseded";
  const archived = entry.status === "archived";
  const proposed = entry.status === "proposed";
  const faded = superseded || archived;

  return (
    <li className={`px-4 py-3.5 ${focused ? "bg-muted/40" : ""}`}>
      <div className="flex items-start gap-3">
        <span
          title={titleCase(entry.kind)}
          className={`mt-px flex size-7 shrink-0 items-center justify-center rounded-full bg-muted ${
            faded ? "text-muted-foreground" : "text-muted-foreground"
          }`}
        >
          <KindIcon kind={entry.kind} />
        </span>

        <div className="min-w-0 flex-1">
          {draft === null ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              className={`block w-full text-left text-sm leading-snug hover:underline underline-offset-2 ${
                faded ? "text-muted-foreground" : ""
              }`}
            >
              {entry.title}
            </button>
          ) : (
            <div className="space-y-2">
              <Input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
              <textarea
                value={draft.body}
                aria-label="Memory body"
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                rows={3}
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                placeholder="What was observed, why it matters, how to apply it."
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={() => onPatch(entry, draft).then(() => setDraft(null))}
                >
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span>{SOURCE_LABELS[entry.source_type] || SOURCE_LABELS.agent}</span>
            <span aria-hidden="true">·</span>
            <span>{validity(entry)}</span>
            {proposed && (
              <>
                <span aria-hidden="true">·</span>
                <span className="text-warning">unconfirmed</span>
              </>
            )}
            {superseded && (
              <>
                <span aria-hidden="true">·</span>
                <span>superseded</span>
              </>
            )}
            {archived && (
              <>
                <span aria-hidden="true">·</span>
                <span>not relevant</span>
              </>
            )}
          </p>

          {open && draft === null && (
            <div className="mt-3 space-y-3">
              {entry.body && <p className="whitespace-pre-wrap text-sm leading-relaxed">{entry.body}</p>}
              <p className="text-xs text-muted-foreground">
                Recorded {relativeTime(entry.recorded_at)}
                {entry.recall_count ? ` · recalled ${entry.recall_count}×` : ""}
                {entry.entity_key ? ` · ${entry.entity_key}${entry.attribute ? ` · ${entry.attribute}` : ""}` : ""}
              </p>
              {Object.keys(entry.value || {}).length > 0 && (
                <pre className="overflow-x-auto rounded-md bg-muted/60 p-2 text-xs">
                  {JSON.stringify(entry.value, null, 2)}
                </pre>
              )}
              <EvidenceLinks entry={entry} />
              <div className="flex flex-wrap gap-1">
                {proposed && (
                  <Button size="xs" variant="outline" disabled={busy}
                    onClick={() => onPatch(entry, { status: "confirmed" })}>
                    <Check /> Confirm
                  </Button>
                )}
                <Button size="xs" variant="ghost" disabled={busy}
                  onClick={() => setDraft({ title: entry.title, body: entry.body })}>
                  Edit
                </Button>
                <Button size="xs" variant="ghost" disabled={busy}
                  onClick={() => onPatch(entry, { pinned: !entry.pinned })}>
                  <Pin /> {entry.pinned ? "Unpin" : "Pin"}
                </Button>
                {!archived && !superseded && (
                  <Button size="xs" variant="ghost" disabled={busy}
                    onClick={() => onPatch(entry, { status: "archived" })}>
                    <X /> Not relevant
                  </Button>
                )}
                <Button size="xs" variant="ghost" disabled={busy} onClick={() => onDelete(entry)}>
                  <Trash2 /> Delete
                </Button>
              </div>
            </div>
          )}
        </div>

        {entry.pinned && (
          <Pin className="mt-1 size-3.5 shrink-0 text-muted-foreground" aria-label="Pinned" />
        )}
      </div>
    </li>
  );
}

function RememberForm({ kinds, defaultKind, placeholder, onCreate, busy, onClose }) {
  const [kind, setKind] = useState(defaultKind);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  return (
    <form
      className="space-y-2 rounded-xl border border-border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) onCreate({ kind, title: title.trim(), body: body.trim() });
      }}
    >
      <div className="flex flex-wrap gap-2">
        <select
          value={kind}
          aria-label="Memory kind"
          onChange={(e) => setKind(e.target.value)}
          className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
        >
          {kinds.map((k) => (
            <option key={k} value={k}>{titleCase(k)}</option>
          ))}
        </select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={placeholder}
          className="flex-1 min-w-[16rem]"
          autoFocus
        />
      </div>
      <textarea
        value={body}
        aria-label="Why it matters, and how an agent should apply it"
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        placeholder="Why it matters, and how an agent should apply it. Optional."
        className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !title.trim()}>Remember it</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

/** A filter chip: one colour when on, none when off. */
function Chip({ active, onClick, children, className = "", ...rest }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      {...rest}
      className={`inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-colors ${
        active
          ? "bg-foreground text-background"
          : "bg-muted text-muted-foreground hover:text-foreground"
      } ${className}`}
    >
      {children}
    </button>
  );
}

/**
 * @param api      { list, create, patch, remove, get?, setPaused?, reset? } —
 *                 promises bound to one scope. The optional ones hide their
 *                 affordance when absent.
 * @param focusId  A memory id from a deep link (a chip in the chat). The entry
 *                 is opened and highlighted, and fetched on its own if the
 *                 current filters would not have listed it.
 */
export default function MemoryTimeline({
  api,
  kinds: kindVocabulary,
  defaultKind,
  addLabel = "Remember",
  titlePlaceholder = "The fact in one line — with its number or date if it has one.",
  emptyHint,
  // Completes "We couldn't load …" on the error panel.
  errorSubject = "your memory",
  resetPrompt = "The agents lose every fact on this timeline from their next turn. This cannot be undone.",
  signedIn = true,
  focusId = "",
}) {
  const [items, setItems] = useState(null); // null = loading
  const [kinds, setKinds] = useState([]);
  const [kind, setKind] = useState("");
  const [paused, setPaused] = useState(false);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [datesOpen, setDatesOpen] = useState(false);
  const [showSuperseded, setShowSuperseded] = useState(true);
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

  const load = useCallback(() => {
    if (!signedIn) {
      setItems([]);
      return;
    }
    setError("");
    setLoadError("");
    api
      .list({ q: query, kind, fromDate, toDate, includeSuperseded: showSuperseded })
      .then((body) => {
        setItems(body.items);
        setPaused(Boolean(body.memory_paused));
        // Keep the widest set of chips seen, so filtering to one kind does not
        // remove the chips you need to filter back out of it.
        setKinds((prev) => Array.from(new Set([...prev, ...body.kinds])).sort());
      })
      .catch((err) => {
        // A retired session is already redirecting to sign-in.
        if (isSessionExpired(err)) return;
        setItems(null);
        setLoadError(err.message || "");
      });
  }, [api, query, kind, fromDate, toDate, showSuperseded, signedIn]);

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
  const groups = useMemo(() => {
    const out = [];
    for (const entry of items || []) {
      const label = formatDate(entry.observed_at) || "Undated";
      const last = out[out.length - 1];
      if (last && last.label === label) last.entries.push(entry);
      else out.push({ label, entries: [entry] });
    }
    return out;
  }, [items]);

  const unconfirmed = (items || []).filter((e) => e.status === "proposed").length;
  const filtered = Boolean(query || kind || fromDate || toDate);
  const dateInput = "h-9 rounded-md border border-input bg-transparent px-2 text-xs text-muted-foreground";

  const rowHandlers = (after) => ({
    onPatch: (row, patch) =>
      run(() => api.patch({ memoryId: row.id, ...patch }), "Update failed.").then(after),
    onDelete: (row) => run(() => api.remove({ memoryId: row.id }), "Delete failed.").then(after),
  });

  return (
    <div className="space-y-4">
      {/* Search is the timeline's main control, so it gets the width. */}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (!e.target.value.trim()) setQuery("");
            }}
            placeholder="Search memory…"
            aria-label="Search memory"
            className="pl-8"
          />
        </div>
        <Button type="button" size="sm" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <Plus /> {addLabel}
        </Button>
        {(api.setPaused || api.reset) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" size="icon-sm" variant="ghost" aria-label="More">
                <Ellipsis />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {api.setPaused && (
                <DropdownMenuCheckboxItem
                  checked={paused}
                  disabled={busy}
                  onCheckedChange={(next) =>
                    run(() => api.setPaused({ paused: Boolean(next) }), "Could not change that.")
                  }
                >
                  <Pause /> Pause remembering
                </DropdownMenuCheckboxItem>
              )}
              {api.setPaused && api.reset && <DropdownMenuSeparator />}
              {api.reset && (
                <DropdownMenuItem
                  variant="destructive"
                  disabled={busy}
                  // Radix closes the menu on select, so the confirm has to be
                  // asked on the next tick or the dialog opens into a closing
                  // popover and inherits its exit animation.
                  onSelect={() => setTimeout(() => setResetting(true), 0)}
                >
                  <Trash2 /> Delete everything
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </form>

      {(kinds.length > 0 || items?.length > 0) && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={kind === ""} onClick={() => setKind("")}>All</Chip>
          {kinds.map((k) => (
            <Chip key={k} active={k === kind} onClick={() => setKind(k === kind ? "" : k)}>
              <KindIcon kind={k} className="size-3" /> {titleCase(k)}
            </Chip>
          ))}
          <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            {/* A number only when it changes what you do next: unconfirmed
                rows want a look, and a filter should say what it left. */}
            {unconfirmed > 0 && <span className="mr-1 text-warning">{unconfirmed} unconfirmed</span>}
            {!unconfirmed && filtered && items && (
              <span className="mr-1">{items.length} {items.length === 1 ? "match" : "matches"}</span>
            )}
            {/* The range is what makes this a timeline rather than a list:
                "what happened between the redirect and the recovery" is a
                date question — but it is asked rarely, so the inputs wait
                behind the chip. */}
            <Chip active={datesOpen || Boolean(fromDate || toDate)} onClick={() => setDatesOpen((v) => !v)} className="h-6 px-2">
              <CalendarRange className="size-3" /> Dates
            </Chip>
            <Chip active={false} onClick={() => setShowSuperseded((v) => !v)} className="h-6 px-2" aria-label={showSuperseded ? "Hide superseded" : "Show superseded"}>
              {showSuperseded ? <Eye className="size-3" /> : <EyeOff className="size-3" />} Superseded
            </Chip>
          </span>
        </div>
      )}

      {datesOpen && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Between</span>
          <input
            type="date"
            value={fromDate}
            max={toDate || undefined}
            aria-label="From date"
            onChange={(e) => setFromDate(e.target.value)}
            className={dateInput}
          />
          <span>and</span>
          <input
            type="date"
            value={toDate}
            min={fromDate || undefined}
            aria-label="To date"
            onChange={(e) => setToDate(e.target.value)}
            className={dateInput}
          />
          {(fromDate || toDate) && (
            <Button type="button" size="xs" variant="ghost" onClick={() => { setFromDate(""); setToDate(""); }}>
              Clear
            </Button>
          )}
        </div>
      )}

      {paused && (
        <p className="text-xs text-muted-foreground">
          Memory is paused. Nothing new is being remembered; everything below stays
          readable and still reaches the agents.
        </p>
      )}

      {adding && (
        <RememberForm
          kinds={kindVocabulary}
          defaultKind={defaultKind}
          placeholder={titlePlaceholder}
          busy={busy}
          onClose={() => setAdding(false)}
          onCreate={(entry) =>
            run(async () => {
              await api.create(entry);
              setAdding(false);
            }, "Could not save that.")
          }
        />
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {signedIn && loadError && (
        <LoadError what={errorSubject} detail={loadError} onRetry={load} />
      )}

      {!signedIn && <p className="app-subtle">Sign in to see this.</p>}
      {signedIn && !loadError && items === null && <p className="app-subtle">Loading…</p>}

      {linked && (
        <div className="overflow-hidden rounded-xl border border-border">
          <p className="border-b border-border/60 bg-muted/30 px-4 py-1.5 text-xs font-medium text-muted-foreground">
            Linked from chat — outside the filters below
          </p>
          <ul>
            <MemoryRow entry={linked} busy={busy} focused {...rowHandlers(() => setLinked(null))} />
          </ul>
        </div>
      )}

      {signedIn && !loadError && items && items.length === 0 && (
        <p className="app-subtle">{filtered ? "Nothing matches that filter." : emptyHint}</p>
      )}

      {signedIn && groups.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border">
          {groups.map((group, gi) => (
            <div key={group.label} className={gi > 0 ? "border-t border-border/60" : ""}>
              <p className="bg-muted/30 px-4 py-2 text-xs font-medium text-muted-foreground">
                {group.label}
              </p>
              <ul className="divide-y divide-border/60">
                {group.entries.map((entry) => (
                  <MemoryRow
                    key={entry.id}
                    entry={entry}
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
        title="Delete every memory here?"
        description={resetPrompt}
        action="Delete everything"
        destructive
        onConfirm={() => {
          setResetting(false);
          run(() => api.reset(), "Reset failed.");
        }}
      />
    </div>
  );
}
