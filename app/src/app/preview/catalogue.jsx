"use client";

// One live example per canon row in DESIGN.md.
//
// The rule text is NOT here — it is parsed out of DESIGN.md by `canon.js`, and
// joined to these by `id`. This file only answers "what does the rule look
// like", using the real components with real props.
//
// A row with no entry here is a GAP, and the catalogue says so rather than
// quietly listing twelve of thirteen. That is the same move as the type-scale
// ratchet: make the shortfall a number on screen, and closing it becomes a
// task instead of a good intention.
//
// Every example must be the pattern as DESIGN.md states it, not an
// approximation. An example that drifts is worse than a missing one — a
// missing one is honest.

import { CircleAlert, FileText, Inbox } from "lucide-react";

import DeskDayOne from "@/components/insights/desk/DeskDayOne";
import PipelineProgress from "@/components/PipelineProgress";
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
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { StepStatus } from "@/lib/agentSteps";

import { canonId } from "./canon";

/** A labelled specimen, so several variants of one rule read as one rule. */
function Specimen({ label, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

const EXAMPLES = {
  Card: () => (
    <div className="rounded-xl border bg-card p-5">
      <p className="text-sm font-medium">Organic Growth</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Nine sources connected. Last brief two days ago.
      </p>
    </div>
  ),

  "Busy indicator": () => (
    <div className="flex flex-wrap items-center gap-6">
      <Specimen label="On its own">
        <Spinner label="Loading connectors" />
      </Specimen>
      <Specimen label="Inheriting currentColor in a button">
        <Button size="sm" variant="secondary" disabled>
          <Spinner />
          Checking…
        </Button>
      </Specimen>
    </div>
  ),

  "Long-running agent work": () => (
    <PipelineProgress
      stages={[
        { id: "collect", label: "Collecting data" },
        { id: "check", label: "Checking the numbers" },
        { id: "synthesise", label: "Synthesising", virtual: true },
      ]}
      steps={[
        { step_id: "collect", status: StepStatus.SUCCESS },
        { step_id: "check", status: StepStatus.RUNNING },
      ]}
      activeId="synthesise"
      synthesising
      lines={[
        "Reading Search Console…",
        "Reconciling spend against conversions…",
        "Looking for the number that moved…",
      ]}
      estimate="~3 min"
    />
  ),

  "Status badge": () => (
    <div className="flex flex-wrap gap-2">
      <Badge>Connected</Badge>
      <Badge variant="secondary">Draft</Badge>
      <Badge variant="destructive">Failed</Badge>
      <Badge variant="outline">Coming soon</Badge>
    </div>
  ),

  "Destructive confirm": () => (
    // Always open: a confirm nobody can see is not a specimen. The anatomy is
    // the rule — title quotes the object, body states scope and
    // irreversibility, action is verb + noun.
    <AlertDialog open>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Disconnect &ldquo;Google Search Console&rdquo;?</AlertDialogTitle>
          <AlertDialogDescription>
            Duct forgets these credentials. Reports and scheduled runs that read from
            Search Console stop working until you connect it again, and reconnecting
            means signing in with Google once more.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel type="button">Keep it</AlertDialogCancel>
          <AlertDialogAction type="button" className={buttonVariants({ variant: "destructive" })}>
            Disconnect
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ),

  "Destructive action (the button that opens that confirm)": () => (
    <div className="flex flex-wrap items-center gap-6">
      <Specimen label="Button">
        <Button size="sm" variant="destructive">
          Delete project
        </Button>
      </Specimen>
      <Specimen label="AlertDialogAction, which defaults to primary">
        <button type="button" className={buttonVariants({ variant: "destructive" })}>
          Disconnect
        </button>
      </Specimen>
    </div>
  ),

  "Dialog actions": () => (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-sm font-medium">Rename project</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Everyone on the project sees the new name.
      </p>
      {/* Destructive/secondary left, primary rightmost — and it reverses to
          primary-first when the row stacks, which the phone frame shows. */}
      <DialogFooter className="mt-4">
        <Button size="sm" variant="secondary">
          Cancel
        </Button>
        <Button size="sm">Save name</Button>
      </DialogFooter>
    </div>
  ),

  "Empty state (whole surface)": () => (
    <div className="rounded-xl border border-dashed p-10 text-center">
      <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-muted">
        <Inbox className="size-5 text-muted-foreground" aria-hidden="true" />
      </div>
      <p className="mt-3 text-sm font-medium">No briefs yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Connect a source and Duct writes the first one for you.
      </p>
      <Button size="sm" className="mt-4">
        Connect a source
      </Button>
    </div>
  ),

  "Empty state (inside a stable layout)": () => (
    <div className="rounded-xl border bg-card p-5">
      <p className="text-sm font-medium">Needs you</p>
      {/* One muted line in place, so the surrounding layout does not jump
          between the empty and the loaded state. */}
      <p className="mt-2 text-xs text-muted-foreground">Nothing needs you right now.</p>
    </div>
  ),

  "First-run": () => (
    <DeskDayOne hasProject sourceCount={0} hasThread={false} onAsk={() => {}} />
  ),

  "Inline error": () => (
    <div className="flex flex-col gap-4">
      <Specimen label="Field or row level">
        <p role="alert" className="text-sm text-destructive">
          That project name is already taken.
        </p>
      </Specimen>
      <Specimen label="Section level">
        <div
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
          <CircleAlert className="mb-1.5 size-4" aria-hidden="true" />
          Search Console rejected the credentials. Reconnect it to keep this report running.
        </div>
      </Specimen>
    </div>
  ),

  "Corner notification": () => (
    // Rendered in place rather than fixed to the corner, so it can be measured
    // beside the others. The `toast` SURFACE puts it where it really sits.
    <div className="w-[min(24rem,100%)] rounded-xl border bg-card p-4 shadow-lg" role="status">
      <p className="text-sm font-medium">Update ready</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Restart Duct to pick up version 1.4.
      </p>
      <div className="mt-3 flex gap-2">
        <Button size="sm">Restart now</Button>
        <Button size="sm" variant="ghost">
          Later
        </Button>
      </div>
    </div>
  ),

  "Loading a page": () => (
    <div className="flex flex-col gap-4">
      <Specimen label="Skeleton mirroring the loaded layout">
        <div className="rounded-xl border bg-card p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex flex-1 flex-col gap-1.5">
              <Skeleton className="h-3.5 w-1/3" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          </div>
          <Skeleton className="mt-4 h-24 w-full rounded-lg" />
        </div>
      </Specimen>
      <Specimen label="Sub-second fetch">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <FileText className="size-3.5" aria-hidden="true" />
          Loading…
        </p>
      </Specimen>
    </div>
  ),
};

/**
 * Scene-shaped entries, so the frame resolves `?scene=canon-…` with no special
 * case and every device, theme, lens and inspection call works unchanged.
 */
export const CATALOGUE = Object.entries(EXAMPLES).map(([job, render]) => ({
  id: canonId(job),
  group: "Canon",
  title: job,
  state: "canonical",
  render,
}));

export const CATALOGUE_BY_ID = new Map(CATALOGUE.map((c) => [c.id, c]));
