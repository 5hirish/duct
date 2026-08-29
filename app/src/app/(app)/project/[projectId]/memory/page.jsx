"use client";

// Project memory — the timeline of what Duct knows about this project.
//
// One row per remembered fact, newest first: goals and decisions, incidents
// with when they started and ended, metrics for a period, actions taken on the
// account, artifacts produced. Superseded entries stay visible but greyed with
// their validity range, so "we thought X, then learned Y" reads as history
// rather than as an error.
//
// Everything here is the user's to control: confirm what an agent proposed,
// correct it, pin it so it is always in the agent's context, archive it, or
// delete it outright. See docs/engineering/agent-memory-research.html §06–07.

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Pin, Plus, Search, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDate, relativeTime } from "@/lib/format";
import { hasAuthToken } from "@/lib/authFetch";
import { getProjectById } from "@/lib/projects";
import {
  MEMORY_KINDS,
  MEMORY_KIND_ICONS,
  createMemory,
  deleteMemory,
  listMemory,
  updateMemory,
} from "@/lib/memoryApi";

const SOURCE_BADGES = {
  user: { label: "you", className: "status-pill grey" },
  agent: { label: "agent", className: "status-pill green" },
  connector: { label: "connector", className: "status-pill grey" },
  artifact: { label: "artifact", className: "status-pill grey" },
  system: { label: "system", className: "status-pill yellow" },
};

/** "1 Jul 2026 – present" / "14 – 21 Aug 2026" / a period string / a bare date. */
function validity(entry) {
  if (entry.period) return entry.period;
  const from = formatDate(entry.valid_from || entry.observed_at);
  if (["milestone", "event", "decision"].includes(entry.kind)) return from;
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
          return (
            <Link
              key={i}
              href={`/activity?conversation_id=${encodeURIComponent(ref.conversation_id)}`}
              className="underline underline-offset-2 hover:text-foreground"
            >
              conversation
            </Link>
          );
        }
        if (ref.project_profile) return <span key={i}>project settings · {ref.project_profile}</span>;
        if (ref.connector) return <span key={i}>{ref.connector}</span>;
        return <span key={i}>{ref.source || "recorded"}</span>;
      })}
    </p>
  );
}

function MemoryRow({ entry, onPatch, onDelete, busy }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(null);
  const superseded = entry.status === "superseded";
  const archived = entry.status === "archived";
  const badge = SOURCE_BADGES[entry.source_type] || SOURCE_BADGES.agent;

  return (
    <li
      className={`border-b border-border/40 px-3 py-3 last:border-b-0 ${
        superseded || archived ? "opacity-55" : ""
      }`}
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
                <Button size="sm" disabled={busy} onClick={() => onPatch(entry, draft).then(() => setDraft(null))}>
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

function RememberForm({ onCreate, busy, onClose }) {
  const [kind, setKind] = useState("decision");
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
          {MEMORY_KINDS.filter((k) => k !== "artifact").map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="The fact in one line — with its number or date if it has one."
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

export default function ProjectMemoryPage({ params }) {
  const { projectId } = use(params);
  const [projectName, setProjectName] = useState("");
  const [signedIn, setSignedIn] = useState(true);
  const [items, setItems] = useState(null); // null = loading
  const [kinds, setKinds] = useState([]);
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [showSuperseded, setShowSuperseded] = useState(true);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setProjectName(getProjectById(projectId)?.name || "");
    setSignedIn(hasAuthToken());
  }, [projectId]);

  const load = useCallback(() => {
    if (!signedIn) {
      setItems([]);
      return;
    }
    setError("");
    listMemory({ projectId, q: query, kind, includeSuperseded: showSuperseded })
      .then((body) => {
        setItems(body.items);
        // Keep the widest set of chips we have seen, so filtering to one kind
        // does not remove the chips you need to filter back out of it.
        setKinds((prev) => Array.from(new Set([...prev, ...body.kinds])).sort());
      })
      .catch((err) => {
        setItems([]);
        setError(err.message || "Failed to load memory.");
      });
  }, [projectId, query, kind, showSuperseded, signedIn]);

  useEffect(() => {
    setItems(null);
    load();
  }, [load]);

  async function handlePatch(entry, patch) {
    setBusy(true);
    try {
      await updateMemory({ projectId, memoryId: entry.id, ...patch });
      load();
    } catch (err) {
      setError(err.message || "Update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(entry) {
    setBusy(true);
    try {
      await deleteMemory({ projectId, memoryId: entry.id });
      load();
    } catch (err) {
      setError(err.message || "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(entry) {
    setBusy(true);
    try {
      await createMemory({ projectId, ...entry });
      setAdding(false);
      load();
    } catch (err) {
      setError(err.message || "Could not save that.");
    } finally {
      setBusy(false);
    }
  }

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
    <section>
      <div className="page-toolbar">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
          {projectName ? `${projectName} · Memory` : "Memory"}
        </h1>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setAdding((v) => !v)}>
            <Plus className="size-4" /> Remember something
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href="/projects">
              <ArrowLeft className="size-4" /> All projects
            </Link>
          </Button>
        </div>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 14 }}>
        What Duct knows about this project, and where each fact came from. Agents read this
        before every run — confirm what they propose, correct what they got wrong, pin what
        should always be in view.
      </p>

      {adding && <RememberForm onCreate={handleCreate} busy={busy} onClose={() => setAdding(false)} />}

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

      {!signedIn && <p className="app-subtle">Sign in to see this project&apos;s memory.</p>}
      {signedIn && items === null && <p className="app-subtle">Loading…</p>}

      {signedIn && items && items.length === 0 && (
        <p className="app-subtle">
          {query || kind
            ? "Nothing matches that filter."
            : "Nothing remembered yet. Run an audit, apply a change, or set your targets in project settings — everything an agent concludes lands here with its evidence."}
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
                    onPatch={handlePatch}
                    onDelete={handleDelete}
                    busy={busy}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
