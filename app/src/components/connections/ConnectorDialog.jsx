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
              <DialogTitle>{title}</DialogTitle>
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
