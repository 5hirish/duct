"use client";

// The configure sheet behind every connector tile. Repeats the tile's identity
// (logo + name + purpose) so the dialog stands on its own, then hands the rest
// of the body to whichever connector opened it.

import {
  Dialog,
  DialogContent,
  DialogDescription,
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
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
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
              <DialogDescription style={{ marginTop: 4, fontSize: 12.5, lineHeight: 1.45 }}>
                {description}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div style={{ marginTop: 18 }}>{children}</div>
      </DialogContent>
    </Dialog>
  );
}
