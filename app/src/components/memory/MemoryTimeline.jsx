"use client";

// The memory timeline — one component, two scopes.
//
// Project memory (/project/[id]/memory) and user memory (/memory) are the same
// surface over different rows: entries grouped by day, superseded ones greyed
// with their validity range, each expanding to its body and evidence, with
// confirm / edit / pin / not-relevant / delete and the pause–reset–export
// controls. The scope only differs in *which* API the calls go to, so the page
// passes an `api` adapter and everything else lives here rather than being
// forked twice and drifting.
//
// See docs/engineering/agent-memory-research.html §06 for what each affordance
// is for, and agent-memory-taxonomy-and-ux-patterns.md Part B for why.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, Download, Pin, Plus, Search, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDate, relativeTime } from "@/lib/format";
import { MEMORY_KIND_ICONS, downloadJson } from "@/lib/memoryApi";

const SOURCE_BADGES = {
  user: { label: "you", className: "status-pill grey" },
  agent: { label: "agent", className: "status-pill green" },
  connector: { label: "connector", className: "status-pill grey" },
  artifact: { label: "artifact", className: "status-pill grey" },
  system: { label: "system", className: "status-pill yellow" },
};

const EVENT_KINDS = ["milestone", "event", "decision"];

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
    <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
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
  const badge = SOURCE_BADGES[entry.source_type] || SOURCE_BADGES.agent;

  return (
    <li
      className={`border-b border-border/40 px-3 py-3 last:border-b-0 ${
        superseded || archived ? "opacity-55" : ""
      } ${focused ? "bg-muted/40 ring-1 ring-inset ring-border" : ""}`}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 shrink-0 text-base leading-none" aria-hidden="true">
          {MEMORY_KIND_ICONS[entry.kind] || "•"}
        </span>

        <div className="min-w-0 flex-1">
          {draft === null ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="block w-full text-left text-sm leading-snug hover:underline underline-offset-2"
            >
              {entry.pinned && <Pin size={12} className="mr-1 inline-block align-[-1px]" />}
              {entry.title}
            </button>
          ) : (
            <div className="space-y-2">
              <Input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
              <textarea
                value={draft.body}
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

          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className={badge.className} style={{ fontSize: 11 }}>{badge.label}</span>
            <span>{entry.kind}</span>
            <span>{validity(entry)}</span>
            {entry.status === "proposed" && (
              <span className="status-pill yellow" style={{ fontSize: 11 }}>unconfirmed</span>
            )}
            {superseded && <span>superseded</span>}
            {archived && <span>archived</span>}
            <span className="font-mono text-[11px]">{entry.short_id}</span>
            <span>· recorded {relativeTime(entry.recorded_at)}</span>
          </p>

          {open && draft === null && (
            <div className="mt-2 rounded-md bg-muted/40 p-3">
              {entry.body && <p className="whitespace-pre-wrap text-xs leading-relaxed">{entry.body}</p>}
              {entry.entity_key && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {entry.entity_key}
                  {entry.attribute ? ` · ${entry.attribute}` : ""}
                  {entry.recall_count ? ` · recalled ${entry.recall_count}×` : ""}
                </p>
              )}
              {Object.keys(entry.value || {}).length > 0 && (
                <pre className="mt-2 overflow-x-auto rounded bg-background/60 p-2 text-[11px]">
                  {JSON.stringify(entry.value, null, 2)}
                </pre>
              )}
              <EvidenceLinks entry={entry} />
              <div className="mt-3 flex flex-wrap gap-2">
                {entry.status === "proposed" && (
                  <Button size="sm" variant="outline" disabled={busy}
                    onClick={() => onPatch(entry, { status: "confirmed" })}>
                    <Check className="size-3.5" /> Confirm
                  </Button>
                )}
                <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => setDraft({ title: entry.title, body: entry.body })}>
                  Edit
                </Button>
                <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => onPatch(entry, { pinned: !entry.pinned })}>
                  <Pin className="size-3.5" /> {entry.pinned ? "Unpin" : "Pin"}
                </Button>
                {!archived && !superseded && (
                  <Button size="sm" variant="outline" disabled={busy}
                    onClick={() => onPatch(entry, { status: "archived" })}>
                    <X className="size-3.5" /> Not relevant
                  </Button>
                )}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDelete(entry)}>
                  <Trash2 className="size-3.5" /> Delete
                </Button>
              </div>
            </div>
          )}
        </div>
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
      className="mb-4 space-y-2 rounded-lg border border-border/60 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim()) onCreate({ kind, title: title.trim(), body: body.trim() });
      }}
    >
      <div className="flex flex-wrap gap-2">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          {kinds.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={placeholder}
          className="flex-1 min-w-[16rem]"
        />
      </div>
      <textarea
        value={body}
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

/**
 * @param api      { list, create, patch, remove, get?, setPaused?, reset?,
 *                 exportAll? } — promises bound to one scope. The optional ones
 *                 hide their affordance when absent.
 * @param focusId  A memory id from a deep link (a chip in the chat). The entry
 *                 is opened and highlighted, and fetched on its own if the
 *                 current filters would not have listed it.
 */
export default function MemoryTimeline({
  api,
  kinds: kindVocabulary,
  defaultKind,
  addLabel = "Remember something",
  titlePlaceholder = "The fact in one line — with its number or date if it has one.",
  emptyHint,
  exportFilename = "duct-memory.json",
  resetPrompt = "Delete every memory here? This cannot be undone — export first if you want a copy.",
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
  const [showSuperseded, setShowSuperseded] = useState(true);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [linked, setLinked] = useState(null); // deep-linked entry outside the filters

  const load = useCallback(() => {
    if (!signedIn) {
      setItems([]);
      return;
    }
    setError("");
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
        setItems([]);
        setError(err.message || "Failed to load memory.");
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
        setError(err.message || failure);
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

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => setAdding((v) => !v)}>
          <Plus className="size-4" /> {addLabel}
        </Button>
        {api.setPaused && (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={paused}
              disabled={busy}
              onChange={(e) =>
                run(() => api.setPaused({ paused: e.target.checked }), "Could not change that.")
              }
            />
            Pause — stop remembering anything new
          </label>
        )}
        <span className="ml-auto flex gap-2">
          {api.exportAll && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                run(async () => downloadJson(await api.exportAll(), exportFilename), "Export failed.")
              }
            >
              <Download className="size-4" /> Export
            </Button>
          )}
          {api.reset && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              disabled={busy}
              onClick={() => {
                if (window.confirm(resetPrompt)) run(() => api.reset(), "Reset failed.");
              }}
            >
              Reset
            </Button>
          )}
        </span>
      </div>

      {paused && (
        <p className="mb-3 text-xs text-muted-foreground">
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

      <form
        className="mb-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <div className="relative flex-1 min-w-[14rem]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search memory — an incident, a page, a number…"
            className="pl-8"
          />
        </div>
        <Button type="submit" size="sm" variant="outline">Search</Button>
        {/* The range is what makes this a timeline rather than a list: "what
            happened between the redirect and the recovery" is a date question. */}
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          from
          <input
            type="date"
            value={fromDate}
            max={toDate || undefined}
            onChange={(e) => setFromDate(e.target.value)}
            className="rounded-md border border-input bg-transparent px-2 py-1 text-xs"
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          to
          <input
            type="date"
            value={toDate}
            min={fromDate || undefined}
            onChange={(e) => setToDate(e.target.value)}
            className="rounded-md border border-input bg-transparent px-2 py-1 text-xs"
          />
        </label>
        {(fromDate || toDate) && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setFromDate("");
              setToDate("");
            }}
          >
            Clear dates
          </Button>
        )}
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={showSuperseded}
            onChange={(e) => setShowSuperseded(e.target.checked)}
          />
          Show superseded
        </label>
      </form>

      {kinds.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setKind("")}
            className={`status-pill ${kind === "" ? "green" : "grey"}`}
            style={{ fontSize: 11, cursor: "pointer" }}
          >
            all
          </button>
          {kinds.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k === kind ? "" : k)}
              className={`status-pill ${k === kind ? "green" : "grey"}`}
              style={{ fontSize: 11, cursor: "pointer" }}
            >
              {MEMORY_KIND_ICONS[k] || "•"} {k}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}

      {!signedIn && <p className="app-subtle">Sign in to see this.</p>}
      {signedIn && items === null && <p className="app-subtle">Loading…</p>}

      {linked && (
        <div className="mb-4 rounded-lg border border-border/60">
          <p className="border-b border-border/40 bg-muted/30 px-3 py-1.5 text-xs font-medium text-muted-foreground">
            Linked from chat — outside the filters below
          </p>
          <ul>
            <MemoryRow
              entry={linked}
              busy={busy}
              focused
              onPatch={(row, patch) =>
                run(() => api.patch({ memoryId: row.id, ...patch }), "Update failed.").then(() =>
                  setLinked(null)
                )
              }
              onDelete={(row) =>
                run(() => api.remove({ memoryId: row.id }), "Delete failed.").then(() =>
                  setLinked(null)
                )
              }
            />
          </ul>
        </div>
      )}

      {/* A count first: "what do you know about me?" is a number before it is a
          list, and unconfirmed is the number worth acting on. */}
      {signedIn && items && items.length > 0 && (
        <p className="mb-2 text-xs text-muted-foreground">
          {items.length} {items.length === 1 ? "memory" : "memories"}
          {(() => {
            const proposed = items.filter((e) => e.status === "proposed").length;
            return proposed ? ` · ${proposed} unconfirmed` : "";
          })()}
          {fromDate || toDate
            ? ` · ${fromDate ? formatDate(fromDate) : "the start"} to ${
                toDate ? formatDate(toDate) : "now"
              }`
            : ""}
        </p>
      )}

      {signedIn && items && items.length === 0 && (
        <p className="app-subtle">
          {query || kind || fromDate || toDate ? "Nothing matches that filter." : emptyHint}
        </p>
      )}

      {signedIn && groups.length > 0 && (
        <div className="rounded-lg border border-border/60">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="border-b border-border/40 bg-muted/30 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                {group.label}
              </p>
              <ul>
                {group.entries.map((entry) => (
                  <MemoryRow
                    key={entry.id}
                    entry={entry}
                    busy={busy}
                    focused={entry.id === focusId}
                    onPatch={(row, patch) =>
                      run(() => api.patch({ memoryId: row.id, ...patch }), "Update failed.")
                    }
                    onDelete={(row) => run(() => api.remove({ memoryId: row.id }), "Delete failed.")}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
