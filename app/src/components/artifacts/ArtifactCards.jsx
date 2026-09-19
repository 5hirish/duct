"use client";

/**
 * A thread's documents as cards, when it has more than one.
 *
 * A conversation that ran for a week has several briefs behind it, and the
 * right pane can only show one. The desk's row list answers "which briefs
 * exist" but not "which one was that" — for a document, the page itself is
 * the best label. So each card is a portrait rectangle with the top of the
 * real document drawn small inside it, the way a file browser shows a
 * thumbnail, with the title, the version and how long ago it was written
 * underneath. Clicking one opens it in the pane.
 *
 * The preview is the real renderer scaled down, not a screenshot and not a
 * summary: a markdown brief goes through `MarkdownView`, an HTML brief into
 * a script-less iframe, both inside a clipped box. That costs one content
 * fetch per card, which is the price of the thumbnail being true.
 */

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { MarkdownView, svgDataUrl } from "@/components/artifacts/ArtifactRenderer";
import { Skeleton } from "@/components/ui/skeleton";
import { getArtifactContent } from "@/lib/artifactsApi";
import { relativeTime } from "@/lib/format";
import { useLingui } from "@lingui/react/macro";
import { cn } from "@/lib/utils";

// How much of the document a thumbnail draws. The scale is what makes a
// page's shape recognisable; the byte cap keeps a long brief from parsing
// in full for a picture that shows its first screen.
const PREVIEW_SCALE = 0.4;
const PREVIEW_CHARS = 6_000;

/** Whether a stored row renders as HTML; anything else is treated as markdown. */
export function isHtmlArtifact(row) {
  return (row?.content_type || "").toLowerCase().includes("html");
}

/** Whether a stored row is a vector figure, shown as a picture rather than as source. */
export function isSvgArtifact(row) {
  return (row?.content_type || "").toLowerCase() === "image/svg+xml";
}

/**
 * Whether the thumbnail can draw this row at all. A structured report or a
 * JSON table is bytes the document renderers would show as source, which
 * is a wall of braces at 40% scale; those rows get the icon instead.
 */
export function hasThumbnail(row) {
  const ct = (row?.content_type || "").toLowerCase();
  return ct === "text/markdown" || ct === "text/html" || ct === "image/svg+xml";
}

/**
 * The top of a document, drawn at thumbnail scale inside a clipped box.
 * `html` picks the renderer; `content` is the whole document or a prefix.
 */
export function DocumentThumbnail({ content, html = false, svg = false, className = "" }) {
  const { t } = useLingui();

  return (
    <div
      className={cn("relative overflow-hidden bg-card", className)}
      aria-hidden="true"
    >
      <div
        className="pointer-events-none absolute left-0 top-0 origin-top-left select-none"
        style={{ width: `${100 / PREVIEW_SCALE}%`, transform: `scale(${PREVIEW_SCALE})` }}
      >
        {html ? (
          <iframe
            title={t`Document preview`}
            srcDoc={content}
            sandbox=""
            tabIndex={-1}
            className="block h-[60rem] w-full border-0 bg-white"
          />
        ) : svg ? (
          <img src={svgDataUrl(content)} alt="" className="block w-full bg-white p-6" />
        ) : (
          <div className="px-4 pt-3">
            <MarkdownView source={content.slice(0, PREVIEW_CHARS)} />
          </div>
        )}
      </div>
      {/* The page fades out rather than ending on a cut line, so the card
          reads as "the top of a document" instead of a broken layout. The
          fade is the document's own ground: an HTML brief is a light page
          whatever the app's theme (generated reports declare
          `color-scheme: light`), so fading it to the dark card colour drew a
          smear across it. */}
      <div
        className={cn(
          "absolute inset-x-0 bottom-0 h-1/4 bg-gradient-to-t to-transparent",
          html ? "from-white" : "from-card"
        )}
      />
    </div>
  );
}

/**
 * One document. `doc` is a row from the artifacts list (the latest version
 * of its group, with `version_count`); `loadContent` fetches its bytes for
 * the thumbnail and is a prop so /preview can hand in a fixture.
 */
export function ArtifactCard({ doc, onOpen, loadContent = getArtifactContent, label = "" }) {
  const [content, setContent] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setFailed(false);
    if (!doc.has_content || !hasThumbnail(doc)) {
      setFailed(true);
      return undefined;
    }
    loadContent(doc.id)
      .then((text) => { if (!cancelled) setContent(text); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [doc.id, doc.has_content, loadContent]);

  const title = doc.title || doc.filename || "Untitled";
  const versionLabel = doc.version_count > 1 ? `v${doc.version} of ${doc.version_count}` : `v${doc.version}`;

  return (
    <div className="group relative flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-ring">
      <div className="aspect-[3/4] w-full border-b border-border/60">
        {content !== null ? (
          <DocumentThumbnail content={content} html={isHtmlArtifact(doc)} svg={isSvgArtifact(doc)} className="h-full w-full" />
        ) : failed ? (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <FileText className="size-6" aria-hidden="true" />
          </div>
        ) : (
          <Skeleton className="h-full w-full rounded-none" />
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-0.5 px-3 py-2.5">
        {/* The whole card is the target: the button carries the name and
            stretches over the thumbnail, so there is one tab stop and no
            <div onClick>. */}
        <button
          type="button"
          onClick={() => onOpen(doc)}
          className="truncate text-left text-sm font-medium text-foreground outline-none after:absolute after:inset-0 after:content-['']"
          title={title}
        >
          {title}
        </button>
        <span className="flex items-center gap-2 text-2xs text-muted-foreground">
          {label && (
            <>
              <span className="rounded-full border border-border px-1.5 py-px capitalize">{label}</span>
              <span aria-hidden="true">·</span>
            </>
          )}
          <span>{versionLabel}</span>
          <span aria-hidden="true">·</span>
          <span>{relativeTime(doc.created_at)}</span>
        </span>
      </div>
    </div>
  );
}

/** The cards, on a responsive grid sized by the pane rather than the window.
 * `labelFor` gives a card its small pill (the library shows the kind; a
 * thread's pane, where every card is a brief, shows none). */
export function ArtifactGallery({ docs, onOpen, loadContent = getArtifactContent, labelFor, className = "p-4" }) {
  return (
    <div className={cn("grid grid-cols-2 gap-4 @lg:grid-cols-3 @2xl:grid-cols-4", className)}>
      {docs.map((doc) => (
        <ArtifactCard
          key={doc.group_id || doc.id}
          doc={doc}
          onOpen={onOpen}
          loadContent={loadContent}
          label={labelFor ? labelFor(doc) : ""}
        />
      ))}
    </div>
  );
}
