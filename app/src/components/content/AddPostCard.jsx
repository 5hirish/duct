"use client";

import { Plus } from "lucide-react";

/**
 * Pinned CTA at the top of the Kanban PENDING lane (only). Opens the Add-post
 * modal (manual entry / paste a TikTok URL / pick a saved reference). Styled as
 * a dashed tile so it reads as an action, not a real post card.
 */
export default function AddPostCard({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-amber-400/50 bg-amber-50/40 px-3 py-3 text-sm font-medium text-amber-700 transition-colors hover:border-amber-400 hover:bg-amber-50/70 dark:bg-amber-950/10 dark:text-amber-400 dark:hover:bg-amber-950/20"
    >
      <span className="flex size-5 items-center justify-center rounded-full bg-amber-500/15 transition-transform group-hover:scale-110">
        <Plus className="size-3.5" />
      </span>
      Add post
    </button>
  );
}
