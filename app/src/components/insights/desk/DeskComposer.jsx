"use client";

// The composer. One chip of context, one box, two controls.
//
// It shows the PROJECT and nothing else. Making someone declare which sources
// and which dates to consider is the wizard we deleted, in miniature: working
// that out is the agent's job, and the headline above reports what it decided.
//
// The controls are the real dials — how freely Duct may act, how hard the
// model thinks, which tier it starts on — and they are the same chips the
// session composer shows once the conversation is open (ComposerDials), so
// what was chosen here is still visible and changeable there.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CornerDownLeft, KeyRound } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { faviconUrl } from "@/lib/favicon";
import { fetchProviderStatus } from "@/lib/modelTiers";
import ComposerDials from "../../workspace/ComposerDials";
import ContextRing from "../../workspace/ContextRing";

const SESSION_ROUTE = "/insights/session";

// Nothing has been sent yet, so this is worth a network round trip up front
// rather than folding into the reactive 402 the session route already
// handles (server.py's ProviderKeyRequired -> ErrorCode.AUTH) — that one
// only fires after a session exists, which is exactly the "opened a session
// that couldn't run" experience this avoids. `reachable` already unions the
// customer's own keys with Duct's (lib/modelTiers.js), so this only trips
// when literally nothing could serve the request.
async function anyProviderReachable() {
  const status = await fetchProviderStatus();
  return status.providers.some((p) => p.reachable);
}

// One draft, one project, restored once. A blocked send stashes the text
// here right before sending the user to Settings — the only reason this
// composer's local state wouldn't survive is that route change unmounting
// it — and the mount effect below claims and clears it the moment the
// project is known, so returning from Settings picks up mid-sentence
// instead of asking for it again.
const DRAFT_KEY_PREFIX = "duct_desk_draft:";

function draftKeyFor(projectId) {
  return `${DRAFT_KEY_PREFIX}${projectId || "_"}`;
}

function stashDraft(projectId, text) {
  try {
    localStorage.setItem(draftKeyFor(projectId), text);
  } catch {
    /* private mode / storage full — the prompt still shows, just won't survive the trip */
  }
}

function claimDraft(projectId) {
  try {
    const key = draftKeyFor(projectId);
    const value = localStorage.getItem(key);
    if (value) localStorage.removeItem(key);
    return value || "";
  } catch {
    return "";
  }
}

export default function DeskComposer({ project, autonomy, onAutonomyChange, placeholder }) {
  const { t } = useLingui();
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // null = still checking; true/false once the round trip answers. Send
  // stays enabled while this is null — a slow /providers/status is not a
  // reason to hold the button hostage, only a confirmed "nothing reachable"
  // is worth stopping the click for.
  const [providerReachable, setProviderReachable] = useState(null);
  const [needsProvider, setNeedsProvider] = useState(false);
  const restoredDraft = useRef(false);

  useEffect(() => {
    let alive = true;
    anyProviderReachable().then((ok) => alive && setProviderReachable(ok));
    // Warms the route so Send doesn't wait on a chunk fetch on top of the
    // session round trip — the actual network work still happens on the
    // destination page, this just removes the blank beat before it.
    router.prefetch(SESSION_ROUTE);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Claimed once the project id is known (it may arrive after this project's
  // own fetch resolves) — never again, so a later re-render can't stomp on
  // what the person is now typing.
  useEffect(() => {
    if (restoredDraft.current) return;
    restoredDraft.current = true;
    const restored = claimDraft(project?.id);
    if (restored) setDraft(restored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const website = project?.company?.website_url || "";
  const icon = faviconUrl(website);
  const name = project?.company?.name || project?.name || t`This project`;

  function send() {
    const q = draft.trim();
    if (!q || sending) return;

    if (providerReachable === false) {
      // Stash rather than clear: the box keeps what was typed, and the
      // stash is only so it still has it after the trip to Settings unmounts
      // this component — same text, same place, once they're back.
      stashDraft(project?.id, q);
      setNeedsProvider(true);
      return;
    }

    setNeedsProvider(false);
    setSending(true);
    const params = new URLSearchParams({ q });
    if (project?.id) params.set("project", project.id);
    router.push(`${SESSION_ROUTE}?${params}`);
  }

  return (
    <div className="mx-auto w-full max-w-[720px]">
      <div className="mb-2.5 flex">
        <span className="inline-flex items-center gap-2 rounded-lg border bg-card py-1 pl-[7px] pr-3 text-xs">
          <span className="flex size-[18px] shrink-0 items-center justify-center overflow-hidden rounded border bg-background">
            {icon ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={icon} alt="" width={14} height={14} className="size-3.5" />
            ) : (
              <span className="size-[7px] rounded-full bg-[var(--orange)]" />
            )}
          </span>
          {name}
        </span>
      </div>

      <div className="rounded-xl border bg-card focus-within:border-ring">
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder}
          aria-label={t`Ask Duct`}
          className="w-full resize-none bg-transparent px-4 py-3.5 text-base leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
          <ComposerDials projectId={project?.id} autonomy={autonomy} onAutonomyChange={onAutonomyChange} />

          <div className="flex items-center gap-3">
            {/* A new thread starts empty — the ring fills once there is a
                conversation to spend the window on. */}
            <ContextRing used={0} label={t`New thread`} />
            <Button
              type="button"
              size="icon-xs"
              onClick={send}
              disabled={!draft.trim() || sending}
              aria-label={sending ? t`Opening session…` : t`Send`}
            >
              {sending ? <Spinner className="size-3.5" /> : <CornerDownLeft className="size-3.5" />}
            </Button>
          </div>
        </div>

        {needsProvider && (
          <div className="flex items-start gap-2.5 border-t border-warning/30 bg-warning/10 px-4 py-2.5 text-xs text-warning">
            <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {/* Straight to the tab with the key fields. The banner's whole
                complaint is that no key is set, and landing on Tiers made
                the reader find the one control this sentence is about. */}
            <p className="leading-relaxed">
              <Trans>
                No model provider is connected, so this can’t run yet.{" "}
                <Link
                  href="/settings/models?tab=providers"
                  className="font-medium underline underline-offset-2"
                >
                  Connect one in Settings → Models & providers →
                </Link>{" "}
                — what you typed is still here when you come back.
              </Trans>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
