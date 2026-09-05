"use client";

// The project-memory rows in a transcript: what a turn remembered (with undo),
// what it was primed with (with forget), and the user's own "remember this".
// Agent-neutral — memory belongs to the project, not to the agent that wrote
// it — so every chat shell renders the same three.

import { useState } from "react";
import { Brain } from "lucide-react";
import { MEMORY_KIND_ICONS, createMemory, deleteMemory } from "@/lib/memoryApi";
import { trackEvent } from "../../lib/analytics-client";
import { getActiveProject } from "@/lib/projects";

/** Deep link to one entry in the project timeline, which fetches and highlights
 * it regardless of the filters in force there. */
function memoryHref(projectId, memory) {
  return `/project/${projectId}/memory?m=${encodeURIComponent(memory.memory_id)}`;
}

/** Chip click-through — whether anyone follows a citation back to its source is
 * the one honest signal that the attribution loop is worth its cost. The id is
 * the short, non-identifying one; no memory text leaves the page. */
function trackChip(surface, memory) {
  trackEvent("memory_chip_opened", { surface, memory_id: memory.id, kind: memory.kind });
}

/** The quiet "Remembered: …" line under a turn that wrote project memory.
 * Deliberately understated — memory should feel like a side effect the user can
 * see and undo, not an announcement. Each entry links to its timeline row, and
 * Undo deletes what this turn just wrote: the cheapest possible off-ramp, right
 * where the surprise happens. */
export function MemoryNote({ memories }) {
  const projectId = getActiveProject()?.id;
  const [undone, setUndone] = useState(() => new Set());

  async function undo(memory) {
    try {
      await deleteMemory({ projectId, memoryId: memory.memory_id });
    } catch {
      /* Already gone, or offline — either way it should stop claiming it. */
    }
    setUndone((prev) => new Set(prev).add(memory.memory_id));
  }

  const live = (memories || []).filter((m) => !undone.has(m.memory_id));
  if (!memories?.length) return null;

  return (
    <div className="my-1.5 flex flex-wrap items-center gap-1.5 px-1 text-xs text-muted-foreground">
      <Brain size={13} aria-hidden="true" />
      {live.length === 0 ? (
        <span>Forgotten.</span>
      ) : (
        <>
          <span>Remembered:</span>
          {live.map((m, i) => (
            <span key={m.memory_id || m.id || i} className="inline-flex items-center gap-1">
              {projectId && m.memory_id ? (
                <a
                  href={memoryHref(projectId, m)}
                  onClick={() => trackChip("written", m)}
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  {m.title}
                </a>
              ) : (
                m.title
              )}
              {i < live.length - 1 ? "," : ""}
            </span>
          ))}
          {projectId && live.some((m) => m.memory_id) && (
            <button
              type="button"
              onClick={() => live.forEach((m) => m.memory_id && undo(m))}
              className="underline underline-offset-2 hover:text-foreground"
            >
              Undo
            </button>
          )}
        </>
      )}
    </div>
  );
}

/** "Recalled N memories" — what this turn was primed with, opening to a chip per
 * entry: what it remembered, a link to its row, and Forget. An answer should
 * always be traceable to the facts behind it, and forgetting one should not
 * require going looking for it. */
export function MemoryRecall({ memories }) {
  const projectId = getActiveProject()?.id;
  const [forgotten, setForgotten] = useState(() => new Set());
  if (!memories?.length) return null;

  async function forget(memory) {
    if (!window.confirm(`Forget "${memory.title}"? The agents stop seeing it from the next turn.`)) {
      return;
    }
    try {
      await deleteMemory({ projectId, memoryId: memory.memory_id });
      setForgotten((prev) => new Set(prev).add(memory.memory_id));
    } catch {
      /* Leave the chip in place — a failed delete should not look like one. */
    }
  }

  return (
    <details className="my-1.5 px-1 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none hover:text-foreground">
        <Brain size={13} className="mr-1 inline-block align-[-2px]" aria-hidden="true" />
        Recalled {memories.length} {memories.length === 1 ? "memory" : "memories"}
      </summary>
      <ul className="mt-1 flex flex-col gap-1">
        {memories.map((m) => (
          <li
            key={m.memory_id || m.id}
            className={`flex items-start gap-1.5 ${forgotten.has(m.memory_id) ? "opacity-50 line-through" : ""}`}
          >
            <span aria-hidden="true">{MEMORY_KIND_ICONS[m.kind] || "•"}</span>
            {projectId && m.memory_id ? (
              <a
                href={memoryHref(projectId, m)}
                onClick={() => trackChip("recalled", m)}
                className="min-w-0 flex-1 underline underline-offset-2 hover:text-foreground"
              >
                {m.title}
              </a>
            ) : (
              <span className="min-w-0 flex-1">{m.title}</span>
            )}
            <span className="font-mono text-[11px] opacity-70">{m.id}</span>
            {projectId && m.memory_id && !forgotten.has(m.memory_id) && (
              <button
                type="button"
                onClick={() => forget(m)}
                className="shrink-0 underline underline-offset-2 hover:text-foreground"
              >
                Forget
              </button>
            )}
          </li>
        ))}
      </ul>
      {projectId && (
        <a href={`/project/${projectId}/memory`} className="mt-1 inline-block underline underline-offset-2 hover:text-foreground">
          Open the project timeline
        </a>
      )}
    </details>
  );
}

/** "Remember this" under a finished agent turn — or under a selection inside it.
 *
 * The agent decides what to remember on its own; this is the other half, where
 * the user overrules that judgement. What it writes is a user statement, so it
 * lands confirmed rather than as a proposal awaiting its own approval. */
export function RememberThis({ text }) {
  const [state, setState] = useState("idle"); // idle | saving | saved | error
  const projectId = getActiveProject()?.id;
  if (!projectId) return null;

  async function save() {
    // A selection inside this turn beats the whole turn — the user pointing at
    // one sentence is a much better title than 400 words of analysis.
    const selected = String(window.getSelection?.() || "").trim();
    const title = (selected || text).replace(/\s+/g, " ").trim().slice(0, 200);
    if (!title) return;
    setState("saving");
    try {
      await createMemory({
        projectId,
        kind: "conclusion",
        title,
        source_refs: [{ source: "user", from: "chat" }],
      });
      setState("saved");
    } catch {
      setState("error");
    }
  }

  return (
    <button
      type="button"
      onClick={save}
      disabled={state === "saving" || state === "saved"}
      className="mt-1 ml-1 text-[11px] text-muted-foreground hover:text-foreground disabled:hover:text-muted-foreground"
    >
      {state === "saved" ? (
        <a href={`/project/${projectId}/memory`} className="underline underline-offset-2">
          Remembered — open the timeline
        </a>
      ) : state === "error" ? (
        "Could not remember that"
      ) : state === "saving" ? (
        "Remembering…"
      ) : (
        "+ Remember this"
      )}
    </button>
  );
}
