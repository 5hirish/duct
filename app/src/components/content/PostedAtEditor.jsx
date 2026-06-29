"use client";

import { useState } from "react";
import { Check, Pencil } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { patchPost } from "@/lib/contentApi";

// Local "YYYY-MM-DDTHH:mm" (wall-clock) — the shape a datetime-local input wants.
function toLocalInput(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * Inline editor for a posted post's publish time. Renders the "Posted {date}"
 * chip as a button; clicking opens a small popover with a datetime field and
 * persists via PATCH /content/posts/{id} { posted_at }, then bubbles the fresh
 * post up via onUpdated.
 *
 * Props:
 *   - post      : { id, posted_at }
 *   - label     : the chip text to show (e.g. "Posted Jun 27, 2026")
 *   - onUpdated : (updatedPost) => void
 */
export default function PostedAtEditor({ post, label, onUpdated }) {
  const [open, setOpen]     = useState(false);
  const [value, setValue]   = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr]       = useState("");

  function onOpenChange(next) {
    if (next) {
      // Seed from the post's current publish time (or now if somehow unset).
      setValue(post?.posted_at ? toLocalInput(new Date(post.posted_at)) : toLocalInput(new Date()));
      setErr("");
    }
    setOpen(next);
  }

  async function save() {
    if (!value) { setErr("Pick a date."); return; }
    setSaving(true); setErr("");
    try {
      const iso = new Date(value).toISOString();   // wall-clock → UTC instant
      const updated = await patchPost(post.id, { posted_at: iso });
      onUpdated?.(updated);
      setOpen(false);
    } catch (e) {
      setErr(e?.message || "Couldn't update the date.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          title="Edit the published date"
          className="inline-flex items-center gap-1 rounded text-muted-foreground transition-colors hover:text-foreground"
        >
          {label} <Pencil className="size-2.5 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-2 p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Published date
        </p>
        <input
          type="datetime-local"
          value={value}
          max={toLocalInput(new Date())}
          onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-lg border border-input bg-input/40 px-2 py-1.5 text-sm outline-none [color-scheme:light] transition-[box-shadow,border-color] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25 dark:[color-scheme:dark]"
        />
        {err && <p className="text-[11px] text-destructive">{err}</p>}
        <div className="flex justify-end gap-2 pt-0.5">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={saving}>
            Cancel
          </Button>
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? "Saving…" : <><Check className="size-3.5" /> Save</>}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
