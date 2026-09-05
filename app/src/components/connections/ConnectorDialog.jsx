"use client";

// The configure sheet behind every connector tile. Repeats the tile's identity
// (logo + name + purpose) so the dialog stands on its own, then hands the rest
// of the body to whichever connector opened it.

import { useRef } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function ConnectorDialog({
  open,
  onOpenChange,
  logo,
  title,
  description,
  // Status glyphs, rendered beside the title.
  //
  // They used to sit in the action row, which measured 312px of empty space
  // between them and the buttons — one row, but far enough apart to read as
  // unrelated. State is a property of the thing, not of the buttons that act
  // on it, so it belongs with the identity; the action row is then left with
  // one job.
  status,
  children,
  // What acts on this connection — Reconnect, Disconnect, Save.
  //
  // A footer, because that is where a dialog's actions go: shadcn ships
  // `DialogFooter` for it and every other confirm in this app already uses
  // one. These sat at the TOP of the body instead, directly under the
  // description, which cost twice — a measured 32px of dead space above them
  // (nothing else was there to fill it) and an action row read before the
  // permissions and account it acts on.
  footer,
}) {
  const contentRef = useRef(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        ref={contentRef}
        onOpenAutoFocus={(event) => {
          // Radix focuses the first focusable descendant when a dialog opens.
          // Here that is the storage glyph in the header — and Radix's tooltip
          // opens on ANY focus, not just keyboard focus (`onFocus: if
          // (!isPointerDownRef.current) onOpen()`), so the dialog appeared with
          // a tooltip already showing, every single time.
          //
          // Focus the content box instead. It carries `tabIndex={-1}`, so the
          // focus trap still holds, Escape still closes, and Tab still reaches
          // every control in order — the only thing lost is a tooltip nobody
          // asked for.
          event.preventDefault();
          contentRef.current?.focus();
        }}
      >
        <DialogHeader>
          <div className="conn-dialog-head">
            <span className="conn-tile-logo" aria-hidden="true">
              {logo}
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="conn-dialog-title-row">
                <DialogTitle>{title}</DialogTitle>
                {status}
              </div>
              <DialogDescription className="conn-dialog-desc">
                {description}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="conn-dialog-body">{children}</div>

        {footer && <DialogFooter className="conn-dialog-footer">{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  );
}
