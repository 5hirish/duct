"use client";

// The Organic Growth desk.
//
// What is front and centre is what changed while you were away — not a blank
// composer. The old page opened on five mode tabs and "No insights yet", which
// asked the user to classify their problem before describing it and then
// admitted it had nothing; both are gone.
//
// Six reads, issued together (lib/deskApi.js), folded into three cards by one
// rule (lib/desk.js). A single GET /projects/{id}/desk is the right end state
// once the shape settles.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { buildDesk, headline } from "@/lib/desk";
import { loadDesk, pinArtifact, pinConversation } from "@/lib/deskApi";
import { getActiveProjectId, getProjectById, PROJECTS_CHANGED } from "@/lib/projects";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal } from "@/components/ui/reveal";
import DeskCards from "./desk/DeskCards";
import DeskLists from "./desk/DeskLists";
import DeskActivity from "./desk/DeskActivity";
import DeskComposer from "./desk/DeskComposer";
import DeskDayOne from "./desk/DeskDayOne";

// How often the desk re-reads its lists while a thread is working.
const DESK_POLL_MS = 30_000;

const EMPTY = {
  memories: [], conversations: [], artifacts: [], activity: [], changeSets: [], sourceCount: 0,
};

export default function Desk({ loadDeskFn = loadDesk, projectIdOverride = null }) {
  const router = useRouter();
  // `null` until the active project has been read, which is not the same as
  // "" — signed in with no project at all, which the desk still has an answer
  // for. Without the distinction, mount fires an account-level load and then a
  // second one the moment the id arrives, and the two race.
  const [projectId, setProjectId] = useState(null);
  const [project, setProject] = useState(null);
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [autonomy, setAutonomy] = useState(AUTONOMY_ASK);

  // The active project can change from the sidebar switcher without a
  // navigation, so this listens rather than reading once.
  useEffect(() => {
    const sync = () => {
      const id = projectIdOverride ?? (getActiveProjectId() || "");
      setProjectId(id);
      const p = id ? getProjectById(id) : null;
      setProject(p);
      setAutonomy(p?.autonomyLevel || AUTONOMY_ASK);
    };
    sync();
    if (projectIdOverride !== null) return undefined;
    window.addEventListener(PROJECTS_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PROJECTS_CHANGED, sync);
      window.removeEventListener("storage", sync);
    };
  }, [projectIdOverride]);

  // Loads overlap — a focus refresh, the status poll and a project switch can
  // all be in flight at once — and they do not answer in the order they were
  // asked. Only the newest answer may be shown; a slow one that started
  // earlier, against the project you have since left, would otherwise land on
  // top of it.
  const latest = useRef(0);

  // Asked even with no project: loadDesk answers the account-level half of the
  // question (which sources are connected) either way, and the day-one
  // checklist would otherwise tell someone with three live connectors to go
  // and connect one.
  const refresh = useCallback(async ({ replaceContent = false } = {}) => {
    const mine = ++latest.current;
    // The first load and a project change have no trustworthy content to keep
    // on screen. Focus and status polling do: hiding it on every re-read makes
    // the desk look as though the app window has reloaded.
    if (replaceContent) setLoading(true);
    try {
      const next = await loadDeskFn({ projectId });
      if (mine !== latest.current) return;
      setData(next);
    } finally {
      // The newest load lowers the skeleton, not whichever load raised it: a
      // background refresh can overtake the first load, and the first load is
      // then the one that must not declare the desk ready.
      if (mine === latest.current) setLoading(false);
    }
  }, [loadDeskFn, projectId]);

  useEffect(() => {
    // Nothing to ask for until the active project has been read once.
    if (projectId === null) return;
    // A project switch is an identity boundary, so do not briefly show the
    // previous project's desk while its replacement loads.
    refresh({ replaceContent: true });
  }, [refresh, projectId]);

  // The list's run badges are read, not pushed: refresh when the user comes
  // back to the tab, and every half minute while any thread is working. These
  // updates keep the current desk visible, so "Working…" becomes "Needs you"
  // without looking like a reload. Idle desks stay quiet.
  const working = data.conversations.some((c) => c.run_status === "running");
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    const timer = working ? setInterval(refresh, DESK_POLL_MS) : null;
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (timer) clearInterval(timer);
    };
  }, [refresh, working]);

  const buckets = useMemo(
    () => buildDesk({
      memories: data.memories,
      changeSets: data.changeSets,
      conversations: data.conversations,
    }),
    [data]
  );

  const lastRunAt = data.activity[0]?.created_at || "";
  const head = headline({
    needsYou: buckets.needsYou.length,
    found: buckets.found.length,
    lastRunAt,
    sourceCount: data.sourceCount,
  });

  // Day one is "this project has produced nothing yet" — not "the fetch was
  // slow" and not "there is no project".
  const isDayOne =
    !loading &&
    data.conversations.length === 0 &&
    data.artifacts.length === 0 &&
    buckets.found.length === 0 &&
    buckets.needsYou.length === 0;

  function ask(question) {
    const params = new URLSearchParams({ q: question });
    if (projectId) params.set("project", projectId);
    router.push(`/insights/session?${params}`);
  }

  // Pins are optimistic: the row moves under the cursor that clicked it, and a
  // failed write puts it back rather than leaving the list lying.
  async function togglePinThread(conv) {
    const next = !conv.pinned;
    setData((d) => ({
      ...d,
      conversations: d.conversations.map((c) => (c.id === conv.id ? { ...c, pinned: next } : c)),
    }));
    try {
      await pinConversation(conv.id, next);
    } catch {
      setData((d) => ({
        ...d,
        conversations: d.conversations.map((c) => (c.id === conv.id ? { ...c, pinned: !next } : c)),
      }));
    }
  }

  async function togglePinArtifact(doc) {
    const next = !doc.pinned;
    setData((d) => ({
      ...d,
      artifacts: d.artifacts.map((a) => (a.id === doc.id ? { ...a, pinned: next } : a)),
    }));
    try {
      await pinArtifact(doc.id, next);
    } catch {
      setData((d) => ({
        ...d,
        artifacts: d.artifacts.map((a) => (a.id === doc.id ? { ...a, pinned: !next } : a)),
      }));
    }
  }

  const composer = (
    <div className="sticky bottom-0 -mx-4 mt-10 bg-gradient-to-t from-background from-70% px-4 pb-4 pt-6">
      <DeskComposer
        project={project}
        autonomy={autonomy}
        onAutonomyChange={setAutonomy}
        placeholder={
          buckets.found[0]
            ? `Ask about “${buckets.found[0].title}” — or anything else`
            : "Ask me anything about your site"
        }
      />
    </div>
  );

  if (loading) {
    return (
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-[420px] max-w-full" />
          <Skeleton className="h-4 w-[300px] max-w-full" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    );
  }

  if (isDayOne) {
    return (
      <div className="flex min-h-[calc(100svh-160px)] flex-col">
        <DeskDayOne
          hasProject={Boolean(project)}
          sourceCount={data.sourceCount}
          hasThread={data.conversations.length > 0}
          onAsk={ask}
        />
        <div className="mt-auto">{composer}</div>
      </div>
    );
  }

  return (
    // The skeleton above is a different subtree, not this one crossfading
    // with itself — Reveal just eases the swap in rather than popping.
    <Reveal className="flex min-h-[calc(100svh-160px)] flex-col">
      {/* Sized off this region's own box, not the viewport (AGENTS.md) — the
          sidebar and the Activity rail itself both eat into the window
          without moving a `lg:` breakpoint, so viewport-based collapse was
          firing far later than the space actually ran out. */}
      <div className="grid gap-x-11 gap-y-8 @3xl:grid-cols-[minmax(0,1fr)_288px]">
        {/* Its own container: once split, this column is narrower than
            `.app-main`, and DeskCards/DeskLists need to size off that, not
            the ancestor the row-vs-stacked decision above just used. */}
        <div className="@container flex min-w-0 flex-col gap-8">
          <div>
            <h1 className="text-[28px] font-bold leading-tight tracking-tight">{head.title}</h1>
            <p className="mt-2.5 max-w-[640px] text-sm leading-relaxed text-muted-foreground">
              {head.sub}
            </p>
          </div>

          <DeskCards buckets={buckets} />

          <p className="-mt-4 text-[11.5px] text-muted-foreground">
            Each item shows up in one card only — sorted by who&apos;s holding it.
          </p>

          <DeskLists
            conversations={data.conversations}
            artifacts={data.artifacts}
            onPinThread={togglePinThread}
            onPinArtifact={togglePinArtifact}
          />
        </div>

        <DeskActivity items={data.activity} />
      </div>

      <div className="mt-auto">{composer}</div>
    </Reveal>
  );
}
