"use client";

import {
  BookOpen, Brain, CircleCheckBig, CircleDot, FileText, GitCommitHorizontal, GitPullRequest, NotebookText, ShieldCheck, Tag,
} from "lucide-react";
import { cn } from "@/lib/utils";

// One glyph per kind of source, so a stone reads without its colour: a
// release, a pull request, a change Duct applied. Unknown kinds get the page.
export const KIND_ICONS = {
  release: Tag,
  pull_request: GitPullRequest,
  commit: GitCommitHorizontal,
  docs_change: BookOpen,
  issue: CircleDot,
  change_set: ShieldCheck,
  artifact: FileText,
  memory: Brain,
  linear_issue: CircleCheckBig,
  notion_page: NotebookText,
};

const SIZES = {
  xs: { box: "size-4 rounded", icon: "size-2.5" },
  sm: { box: "size-5 rounded-md", icon: "size-3" },
  md: { box: "size-7 rounded-lg", icon: "size-3.5" },
};

/**
 * A source's kind as a stone: its colour from `styles/feed.css` (the mosaic
 * palette), its glyph from KIND_ICONS. Decorative: the title beside it names
 * the source, so the stone is hidden from readers.
 */
export function KindStone({ kind, size = "sm", className }) {
  const Icon = KIND_ICONS[kind] || FileText;
  const s = SIZES[size] || SIZES.sm;
  return (
    <span data-kind={kind} className={cn("feed-kind inline-flex shrink-0 items-center justify-center", s.box, className)} aria-hidden>
      <Icon className={s.icon} strokeWidth={2.25} />
    </span>
  );
}
