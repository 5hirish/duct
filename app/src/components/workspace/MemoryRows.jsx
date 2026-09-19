"use client";

// The project-memory rows in a transcript: what a turn remembered (with undo)
// and what it was primed with (with forget). Agent-neutral — memory belongs to
// the project, not to the agent that wrote it — so every chat shell renders
// the same two.
//
// There is deliberately no "remember this" button under a reply. The agent
// decides what is durable (RememberFact, under the discipline in
// agents/core/prompts.py) and the row below says what it kept, with undo —
// the same shape ChatGPT's "Memory updated" takes. A per-reply save button
// asked the user to do the agent's job and, once pressed, sat under every
// answer as a permanent link.

import { useState } from "react";
import { Brain } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { MEMORY_KIND_ICONS, deleteMemory } from "@/lib/memoryApi";
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
        <span><Trans>Forgotten.</Trans></span>
      ) : (
        <>
          <span><Trans>Remembered:</Trans></span>
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
              <Trans>Undo</Trans>
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
  const { t } = useLingui();
  const projectId = getActiveProject()?.id;
  const [forgotten, setForgotten] = useState(() => new Set());
  const { confirm, dialog } = useConfirm();
  if (!memories?.length) return null;
  const recalledCount = memories.length;

  async function forget(memory) {
    const title = memory.title;
    const ok = await confirm({
      title: t`Forget "${title}"?`,
      description: t`The agents stop seeing it from the next turn.`,
      action: t`Forget`,
      destructive: true,
    });
    if (!ok) return;
    try {
      await deleteMemory({ projectId, memoryId: memory.memory_id });
      setForgotten((prev) => new Set(prev).add(memory.memory_id));
    } catch {
      /* Leave the chip in place — a failed delete should not look like one. */
    }
  }

  return (
    <>
      {dialog}
      <details className="my-1.5 px-1 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none hover:text-foreground">
        <Brain size={13} className="mr-1 inline-block align-[-2px]" aria-hidden="true" />
        <Plural value={recalledCount} one="Recalled # memory" other="Recalled # memories" />
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
            <span className="font-mono text-2xs opacity-70">{m.id}</span>
            {projectId && m.memory_id && !forgotten.has(m.memory_id) && (
              <button
                type="button"
                onClick={() => forget(m)}
                className="shrink-0 underline underline-offset-2 hover:text-foreground"
              >
                <Trans>Forget</Trans>
              </button>
            )}
          </li>
        ))}
      </ul>
      {projectId && (
        <a href={`/project/${projectId}/memory`} className="mt-1 inline-block underline underline-offset-2 hover:text-foreground">
          <Trans>Open the project timeline</Trans>
        </a>
      )}
    </details>
    </>
  );
}
