"use client";

// Where a component is mounted changes what is wrong with it.
//
// The same card is a different problem inline in a 320px pane, inside a dialog
// that centres and caps its width, and inside a bottom sheet that takes the
// full width and pins itself to an edge. Reviewing only the placement it
// happens to ship in today is how a component acquires a second placement and
// breaks — so the harness hosts one scene in any of them, and the scene does
// not know which it is in.
//
// Every host here is the app's real primitive. None of them is a mock: a
// re-implementation of `DialogContent` would be a copy that stops matching,
// which is the whole failure this route exists to end.

import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

/** Opens an overlay host, since an overlay has to be opened to be looked at. */
function Trigger({ label, children }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        {label}
      </Button>
      {children(open, setOpen)}
    </>
  );
}

export const SURFACES = [
  {
    id: "inline",
    label: "In place",
    // The default, and the only one where the width control means anything —
    // every overlay below sets its own.
    host: (node) => node,
  },
  {
    id: "dialog",
    label: "Dialog",
    host: (node, scene) => (
      <Trigger label="Open dialog">
        {(open, setOpen) => (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{scene.title}</DialogTitle>
                <DialogDescription>Hosted in ui/dialog by the preview route.</DialogDescription>
              </DialogHeader>
              <div className="mt-4">{node}</div>
            </DialogContent>
          </Dialog>
        )}
      </Trigger>
    ),
  },
  {
    id: "sheet",
    label: "Bottom sheet",
    // The mobile surface. A component that assumes a centred, width-capped box
    // finds out here: the sheet is full width and edge-pinned.
    host: (node, scene) => (
      <Trigger label="Open sheet">
        {(open, setOpen) => (
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto">
              <SheetHeader>
                <SheetTitle>{scene.title}</SheetTitle>
                <SheetDescription>Hosted in ui/sheet by the preview route.</SheetDescription>
              </SheetHeader>
              <div className="px-4 pb-6">{node}</div>
            </SheetContent>
          </Sheet>
        )}
      </Trigger>
    ),
  },
  {
    id: "alert",
    label: "Alert",
    // The destructive-confirm anatomy from DESIGN.md, so copy written for it
    // can be read at the width it will actually be read at.
    host: (node, scene) => (
      <Trigger label="Open alert">
        {(open, setOpen) => (
          <AlertDialog open={open} onOpenChange={setOpen}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{scene.title}</AlertDialogTitle>
                <AlertDialogDescription>
                  Hosted in ui/alert-dialog by the preview route.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div>{node}</div>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction>Confirm</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </Trigger>
    ),
  },
  {
    id: "drawer",
    label: "Drawer",
    // The same primitive as the bottom sheet, pinned to the side instead. A
    // component that is fine full-width at the bottom can still be wrong in a
    // ~24rem column, which is what this catches.
    host: (node, scene) => (
      <Trigger label="Open drawer">
        {(open, setOpen) => (
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetContent side="right" className="w-[min(26rem,90vw)] overflow-y-auto">
              <SheetHeader>
                <SheetTitle>{scene.title}</SheetTitle>
                <SheetDescription>Hosted in ui/sheet (side) by the preview route.</SheetDescription>
              </SheetHeader>
              <div className="px-4 pb-6">{node}</div>
            </SheetContent>
          </Sheet>
        )}
      </Trigger>
    ),
  },
  {
    id: "page",
    label: "Full page",
    // The `.app-main` container the authenticated routes render into, so a
    // component sees the width and the measure it will really get — without
    // the sidebar, the auth guard or a backend.
    host: (node) => (
      <div className="app-main mx-auto w-full max-w-5xl py-6">{node}</div>
    ),
  },
  {
    id: "toolbar",
    label: "Toolbar",
    // A sticky page header. Puts the component in a short, wide box where
    // vertical growth is what breaks the layout rather than width.
    host: (node) => (
      <div className="rounded-xl border">
        <div className="flex min-h-14 flex-wrap items-center gap-3 border-b px-4 py-2">
          <span className="text-sm font-semibold">Page title</span>
          <div className="ml-auto flex items-center gap-2">{node}</div>
        </div>
        <div className="p-4 text-xs text-muted-foreground">Page body, for scale.</div>
      </div>
    ),
  },
  {
    id: "toast",
    label: "Notification",
    // The `UpdateToast` anatomy, which DESIGN.md makes canon and which is
    // deliberately not a library. Reproduced as a position, not as a
    // component, because there is no shared primitive to import.
    host: (node) => (
      <div className="pointer-events-none fixed right-4 bottom-4 z-50 w-[min(24rem,calc(100vw-2rem))]">
        <div
          role="status"
          className="pointer-events-auto rounded-xl border bg-card p-4 shadow-lg"
        >
          {node}
        </div>
      </div>
    ),
  },
];

export const DEFAULT_SURFACE = "inline";
