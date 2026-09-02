"use client";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Full-bleed image zoom.
 *
 * Built on the same Radix dialog as every other overlay rather than a second
 * hand-rolled `fixed inset-0`, so it inherits the portal, the focus trap,
 * Escape-to-close and the scroll lock for free. The portal is the part that
 * matters structurally: overlays rendered inline inside an agent pane are at
 * the mercy of every ancestor, and any transform, filter or `container-type`
 * above them silently repositions them.
 *
 * The panel chrome is stripped to nothing — no border, no background, no
 * padding — because the image is the content. Clicking the image closes, which
 * is what a zoom cursor promises.
 *
 * Props:
 *   - open, onOpenChange : controlled, as Radix expects
 *   - src, alt           : the full-size image
 *   - title?             : accessible name; defaults to `alt`, visually hidden
 *     either way since the dialog has no visible heading
 */
export function Lightbox({ open, onOpenChange, src, alt = "", title }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="w-auto max-w-[95vw] cursor-zoom-out border-0 bg-transparent p-0 shadow-none"
      >
        <DialogTitle className="sr-only">{title || alt || "Image"}</DialogTitle>
        <DialogClose asChild>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt}
            className="max-h-[90vh] max-w-full rounded-lg object-contain shadow-2xl"
          />
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}

export default Lightbox;
