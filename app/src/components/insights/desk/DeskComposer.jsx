"use client";

// The composer. One chip of context, one box, two controls.
//
// It shows the PROJECT and nothing else. Making someone declare which sources
// and which dates to consider is the wizard we deleted, in miniature: working
// that out is the agent's job, and the headline above reports what it decided.
//
// The two controls are the two real dials — how freely Duct may act, and how
// hard the model thinks. Both are persisted settings, not per-message
// decoration: the posture writes to the project, the thinking level to your
// preferences.
//
// The thinking picker is server-driven. Every provider sells this dial under a
// different name with a different ladder, so Duct names four rungs and
// backend/agents/thinking.py maps them per model. The menu shows the resolved
// native value under each rung, which is the honesty clause: the abstraction
// saves you from learning five dialects, it does not hide which one is in use.
// A model with no dial (Gemini 2.5, Haiku 4.5, gpt-4o) shows no control.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { CornerDownLeft, KeyRound, Sparkles } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { faviconUrl } from "@/lib/favicon";
import { AUTONOMY_OPTIONS, setProjectAutonomy } from "@/lib/projectsApi";
import { loadPreferences, savePreferences } from "@/lib/userPreferences";
import { DEFAULT_ENGINE } from "@/lib/engines";
import { fetchProviderStatus } from "@/lib/modelTiers";
import { NO_THINKING, fetchThinking, levelHint } from "@/lib/thinking";
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

// Both controls read as chips — the same object as the project chip above the
// box, because they are the same kind of thing: what this message will run with.
// Height comes from the trigger's own size="sm" (h-8) — a bare h-7 here loses
// to the component's data-[size] variant, which is a fight not worth having.
const CHIP =
  "gap-1.5 rounded-full border bg-transparent px-2.5 text-[12px] text-muted-foreground " +
  "shadow-none hover:bg-accent hover:text-foreground focus-visible:ring-0";

// The stored value for "let the model decide" is "", which a Select cannot
// hold — Radix treats an empty string as no selection.
const AUTO = "auto";

export default function DeskComposer({ project, autonomy, onAutonomyChange, placeholder }) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(() => loadPreferences().thinking || "");
  // Which rungs exist depends on the model the engine resolves to, so the
  // server answers it. Until it does — or when the model has no dial — the
  // control simply isn't there.
  const [dial, setDial] = useState(NO_THINKING);
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
    fetchThinking(DEFAULT_ENGINE).then((d) => alive && setDial(d));
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
  const name = project?.company?.name || project?.name || "This project";

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

  const autonomyLabel =
    AUTONOMY_OPTIONS.find((o) => o.value === autonomy)?.label || "Ask";
  // The chip says the Duct word; the menu says which provider word it becomes.
  const thinkingLabel =
    dial.levels.find((l) => l.level === thinking)?.label.toLowerCase() || "auto";

  function pickThinking(value) {
    const next = value === AUTO ? "" : value;
    setThinking(next);
    savePreferences({ ...loadPreferences(), thinking: next });
  }

  async function pickAutonomy(value) {
    onAutonomyChange(value);
    if (!project?.id) return;
    try {
      await setProjectAutonomy(project.id, value);
    } catch {
      /* the picker is a hint; the backend is the authority on next request */
    }
  }

  return (
    <div className="mx-auto w-full max-w-[720px]">
      <div className="mb-2.5 flex">
        <span className="inline-flex items-center gap-2 rounded-lg border bg-card py-1 pl-[7px] pr-3 text-[12.5px]">
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
          aria-label="Ask Duct"
          className="w-full resize-none bg-transparent px-4 py-3.5 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
          <div className="flex items-center gap-1.5">
            <Select value={autonomy} onValueChange={pickAutonomy}>
              <SelectTrigger size="sm" className={CHIP} aria-label="How freely Duct may act">
                <span>{autonomyLabel}</span>
              </SelectTrigger>
              <SelectContent position="popper" align="start" className="max-w-[320px]">
                {AUTONOMY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    <span className="flex flex-col items-start gap-0.5">
                      <span>{o.label}</span>
                      <span className="text-[11px] leading-snug text-muted-foreground">
                        {o.blurb}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Absent, not disabled, when the model has no such dial. */}
            {dial.supported && (
              <Select value={thinking || AUTO} onValueChange={pickThinking}>
                <SelectTrigger
                  size="sm"
                  className={CHIP}
                  aria-label="How hard the model should think"
                >
                  <Sparkles className="size-3" aria-hidden />
                  <span>Thinking: {thinkingLabel}</span>
                </SelectTrigger>
                <SelectContent position="popper" align="start" className="max-w-[320px]">
                  {/* "Auto" is not a fifth rung — it sends nothing, so the model
                      does whatever it would have done. */}
                  <SelectItem value={AUTO}>
                    <span className="flex flex-col items-start gap-0.5">
                      <span>Auto</span>
                      <span className="text-[11px] leading-snug text-muted-foreground">
                        {dial.dial} {dial.default_native} · whatever this model does anyway
                      </span>
                    </span>
                  </SelectItem>
                  {dial.levels.map((level) => (
                    <SelectItem key={level.level} value={level.level}>
                      <span className="flex flex-col items-start gap-0.5">
                        <span>{level.label}</span>
                        <span className="text-[11px] leading-snug text-muted-foreground">
                          {level.blurb}
                        </span>
                        {/* The honesty clause: which provider word this becomes. */}
                        <span className="text-[10.5px] font-mono text-muted-foreground/70">
                          {levelHint(level, dial.dial)}
                        </span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* A new thread starts empty — the ring fills once there is a
                conversation to spend the window on. */}
            <ContextRing used={0} label="New thread" />
            <button
              type="button"
              onClick={send}
              disabled={!draft.trim() || sending}
              aria-label={sending ? "Opening session…" : "Send"}
              className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-35"
            >
              {sending ? <Spinner className="size-3.5" /> : <CornerDownLeft className="size-3.5" />}
            </button>
          </div>
        </div>

        {needsProvider && (
          <div className="flex items-start gap-2.5 border-t border-amber-400/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-600 dark:text-amber-400">
            <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <p className="leading-relaxed">
              No model provider is connected, so this can&apos;t run yet.{" "}
              {/* Straight to the tab with the key fields. The banner's whole
                  complaint is that no key is set, and landing on Tiers made
                  the reader find the one control this sentence is about. */}
              <Link
                href="/settings/models?tab=providers"
                className="font-medium underline underline-offset-2"
              >
                Connect one in Settings → Models &amp; providers →
              </Link>{" "}
              — what you typed is still here when you come back.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
