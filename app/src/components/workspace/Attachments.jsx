"use client";

import { useState } from "react";
import { FileText, Paperclip, X } from "lucide-react";
import { useLingui } from "@lingui/react/macro";

import { Button } from "@/components/ui/button";
import { Lightbox } from "@/components/ui/lightbox";
import { AttachmentKind, attachmentLabel } from "@/lib/attachments";
import { cn } from "@/lib/utils";

/**
 * A file on a message, drawn the same way before it goes (the composer,
 * with a remove button) and after (the user's row, read-only). An image is
 * its own thumbnail and opens full size; anything else is a small card with
 * the name and a badge saying what it is — a PDF, a CSV, a pasted block of
 * JSON. One tile so the person sees the same object in both places.
 *
 * `attachment` is the shape lib/attachments.js describes: { name, mediaType,
 * kind, preview? }.
 */
export function AttachmentTile({ attachment, onRemove, className }) {
  const { t } = useLingui();
  const [open, setOpen] = useState(false);
  const name = attachment.name || t`Attachment`;
  const badge = attachmentLabel(attachment.mediaType, attachment.name);
  const isImage = attachment.kind === AttachmentKind.IMAGE && attachment.preview;
  return (
    <div className={cn("group/tile relative shrink-0", className)}>
      {isImage ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          title={t`View full screen`}
          className="block size-20 overflow-hidden rounded-lg border border-border/60 bg-muted/40 transition-opacity hover:opacity-90"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={attachment.preview} alt={name} className="size-full object-cover" />
        </button>
      ) : (
        <div
          className="flex h-20 w-36 flex-col justify-between rounded-lg border border-border/60 bg-muted/40 p-2.5"
          title={name}
        >
          <span className="line-clamp-2 break-all text-xs leading-snug text-foreground">{name}</span>
          <span className="flex items-center gap-1 text-2xs text-muted-foreground">
            <FileText className="size-3" aria-hidden="true" />
            {badge}
          </span>
        </div>
      )}
      {onRemove && (
        <Button
          type="button"
          variant="secondary"
          size="icon-xs"
          onClick={onRemove}
          aria-label={t`Remove ${name}`}
          className="absolute -right-1.5 -top-1.5 rounded-full border border-border bg-background shadow-sm hover:bg-muted"
        >
          <X aria-hidden="true" />
        </Button>
      )}
      {isImage && <Lightbox open={open} onOpenChange={setOpen} src={attachment.preview} alt={name} />}
    </div>
  );
}

/**
 * The tiles in a row that scrolls sideways rather than wrapping: three
 * screenshots and a PDF must not push the text box off the bottom of the
 * composer. `onRemove(index)` puts the remove button on every tile.
 */
export function AttachmentStrip({ attachments = [], onRemove, className }) {
  if (!attachments.length) return null;
  return (
    <div className={cn("flex gap-2.5 overflow-x-auto p-1.5", className)}>
      {attachments.map((att, i) => (
        <AttachmentTile
          key={`${att.name}-${i}`}
          attachment={att}
          onRemove={onRemove ? () => onRemove(i) : undefined}
        />
      ))}
    </div>
  );
}

/** What the composer shows while a file is held over it. */
export function DropHint() {
  const { t } = useLingui();
  return (
    <div
      className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-ring bg-background/90 text-sm text-foreground"
      aria-hidden="true"
    >
      <Paperclip className="size-4" aria-hidden="true" />
      {t`Drop to attach`}
    </div>
  );
}
