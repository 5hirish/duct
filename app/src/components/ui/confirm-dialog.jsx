"use client";

import { useCallback, useRef, useState } from "react";

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
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * "Are you sure?", once.
 *
 * There were two ways to ask in this app: four hand-written `AlertDialog`
 * blocks, and four `window.confirm` calls. The native one is not a styling
 * problem — it is an OS modal in a system font that blocks the whole tab, has
 * no room to say what will happen, cannot say it destructively, and on the
 * desktop shell's webview looks like the browser accusing the user of
 * something. It is also invisible to `/preview`, which is how four of them
 * survived a design pass.
 *
 * The API is deliberately shaped like the thing it replaces, because that is
 * what makes replacing it a one-line change at the call site:
 *
 *   const { confirm, dialog } = useConfirm();
 *   if (!(await confirm({ title: "Forget this?", action: "Forget" }))) return;
 *   …
 *   return (<>{…}{dialog}</>);
 *
 * `destructive` tints the action rather than filling it, which is the canon
 * for anything that removes something (DESIGN.md) — a wall of solid red on the
 * one screen where the user is being asked to think is the opposite of help.
 */
export function useConfirm() {
  const [request, setRequest] = useState(null);
  const resolveRef = useRef(null);

  const settle = useCallback((answer) => {
    const resolve = resolveRef.current;
    resolveRef.current = null;
    setRequest(null);
    resolve?.(answer);
  }, []);

  const confirm = useCallback((options) => {
    // A second ask while one is open would strand the first promise forever;
    // the pending one resolves false, which is the safe answer to a question
    // nobody is looking at any more.
    resolveRef.current?.(false);
    setRequest(options || {});
    return new Promise((resolve) => {
      resolveRef.current = resolve;
    });
  }, []);

  const dialog = (
    <ConfirmDialog
      open={request != null}
      onOpenChange={(next) => {
        if (!next) settle(false);
      }}
      onConfirm={() => settle(true)}
      {...(request || {})}
    />
  );

  return { confirm, dialog };
}

/**
 * The dialog on its own, for a caller that already tracks what is being
 * confirmed in state (a row being deleted, say) and wants that value in the
 * copy. `useConfirm` is the shorter road when the question is self-contained.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  title = "Are you sure?",
  description = null,
  action = "Confirm",
  cancel = "Cancel",
  destructive = false,
  busy = false,
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description ? <AlertDialogDescription>{description}</AlertDialogDescription> : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{cancel}</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={(e) => {
              e.preventDefault();
              onConfirm?.();
            }}
            className={destructive ? cn(buttonVariants({ variant: "destructive" })) : undefined}
          >
            {action}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default ConfirmDialog;
