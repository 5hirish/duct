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
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { HEADLINE_CLEAR, HEADLINE_NEEDS_YOU, buildDesk, headline } from "@/lib/desk";
import { loadDesk, pinArtifact, pinConversation } from "@/lib/deskApi";
import { getActiveProjectId, getProjectById, PROJECTS_CHANGED } from "@/lib/projects";
import { pageHidden } from "@/lib/visibility";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal } from "@/components/ui/reveal";
import { cn } from "@/lib/utils";
import { Page, PageHeader } from "@/components/ui/page";
import DeskCards, { DeskConnectFirst } from "./desk/DeskCards";
import { useGreeting } from "./desk/useGreeting";
import DeskLists from "./desk/DeskLists";
import DeskActivity, { activityGridClass } from "./desk/DeskActivity";
import DeskComposer from "./desk/DeskComposer";
import DeskDayOne from "./desk/DeskDayOne";
import { useRelativeTime } from "./desk/useRelativeTime";

// How often the desk re-reads its lists while a thread is working.
const DESK_POLL_MS = 30_000;

// Whether the Activity rail is folded away, remembered per browser. A viewing
// preference for one person on one machine, so localStorage rather than the
// profile — nothing else needs to know, and the scheduled brief has no rail.
const ACTIVITY_COLLAPSED_KEY = "duct_desk_activity_collapsed";

const EMPTY = {
  memories: [], conversations: [], artifacts: [], activity: [], changeSets: [], sourceCount: 0,
};

export default function Desk({ loadDeskFn = loadDesk, projectIdOverride = null }) {
  const { t } = useLingui();
  const relative = useRelativeTime();
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
  // Expanded on both server and first client paint, then corrected from
  // storage in an effect: reading localStorage during render is a hydration
  // mismatch, and the rail is the half of the desk it is safe to be briefly
  // wrong about.
  const [activityCollapsed, setActivityCollapsed] = useState(false);

  useEffect(() => {
    try {
      setActivityCollapsed(window.localStorage.getItem(ACTIVITY_COLLAPSED_KEY) === "1");
    } catch {
      // Private mode or blocked storage: the default stands.
    }
  }, []);

  const toggleActivity = useCallback(() => {
    setActivityCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(ACTIVITY_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        // Not worth failing a click the user can simply repeat next visit.
      }
      return next;
    });
  }, []);

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
    // The visibility listener above already refreshes on return, so a hidden
    // tick has nothing to add.
    const timer = working
      ? setInterval(() => {
          if (!pageHidden()) refresh();
        }, DESK_POLL_MS)
      : null;
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
  // Plain identifiers, so the catalogue names them ({needsYou}) rather than
  // numbering them ({0}) — AGENTS.md, "Values in a string".
  const { needsYou, sourceCount } = head;
  const lastChecked = relative(head.lastRunAt);
  const hasActivity = data.activity.length > 0;
  const greeting = useGreeting();

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

  const topFinding = buckets.found[0]?.title || "";

  // `mt-auto` belongs on the sticky element itself, not on a wrapper around it.
  // A sticky box can only travel inside its parent's content box, and a wrapper
  // sized to exactly one child gives it nowhere to go — so this read as sticky,
  // passed review as sticky, and scrolled away like any other block.
  const composer = (
    <div className="sticky bottom-0 z-10 mt-auto bg-gradient-to-t from-background from-60% pb-4 pt-8">
      <DeskComposer
        project={project}
        autonomy={autonomy}
        onAutonomyChange={setAutonomy}
        placeholder={
          topFinding
            ? t`Ask about “${topFinding}” — or anything else`
            : t`Ask me anything about your site`
        }
      />
    </div>
  );

  if (loading) {
    return (
      <Page>
        <div className="flex flex-col gap-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-10 w-[420px] max-w-full" />
          <Skeleton className="h-4 w-[300px] max-w-full" />
        </div>
        <div className="grid gap-3 @xl:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </Page>
    );
  }

  if (isDayOne) {
    return (
      <div className="flex min-h-[calc(100svh-160px)] flex-col">
        <DeskDayOne
          greeting={greeting}
          hasProject={Boolean(project)}
          sourceCount={data.sourceCount}
          hasThread={data.conversations.length > 0}
          onAsk={ask}
        />
        {composer}
      </div>
    );
  }

  return (
    // The skeleton above is a different subtree, not this one crossfading
    // with itself — Reveal just eases the swap in rather than popping.
    <Reveal className="flex min-h-[calc(100svh-160px)] flex-col">
      {/* Sized off this region's own box, not the viewport (AGENTS.md). The
          rail only exists once there is activity to show: an empty 288px
          column of "Nothing yet" was what pushed the cards into one stacked
          column at the desktop app's default width. */}
      <div className={cn("grid flex-1 gap-y-10", hasActivity && activityGridClass(activityCollapsed))}>
        {/* Its own container: once split, this column is narrower than
            `.app-main`, and the cards size off that. The composer lives in
            this column too, so it shares the content's left edge instead of
            centring under the rail. */}
        <div className="@container flex min-w-0 flex-col">
          <Page className="flex-1">
            <PageHeader
              size="hero"
              eyebrow={greeting}
              title={
                head.state === HEADLINE_NEEDS_YOU ? (
                  <Plural value={needsYou} one="# thing needs you." other="# things need you." />
                ) : head.state === HEADLINE_CLEAR ? (
                  <Trans>Nothing needs you right now.</Trans>
                ) : (
                  <Trans>Nothing to report yet.</Trans>
                )
              }
              status={
                head.hasRun ? (
                  <Trans>
                    Last checked {lastChecked} ·{" "}
                    <Plural value={sourceCount} one="# source connected" other="# sources connected" />
                  </Trans>
                ) : sourceCount ? (
                  <Plural
                    value={sourceCount}
                    one="# source connected. Ask anything below to start."
                    other="# sources connected. Ask anything below to start."
                  />
                ) : (
                  <Trans>Nothing is connected yet.</Trans>
                )
              }
            />

            {sourceCount === 0 && <DeskConnectFirst />}

            <DeskCards
              buckets={buckets}
              allClear={head.state === HEADLINE_CLEAR && head.hasRun}
              lastChecked={lastChecked}
              quiet={sourceCount === 0}
            />

            <DeskLists
              conversations={data.conversations}
              artifacts={data.artifacts}
              onPinThread={togglePinThread}
              onPinArtifact={togglePinArtifact}
            />
          </Page>
          {composer}
        </div>

        {hasActivity && (
          <DeskActivity
            items={data.activity}
            collapsed={activityCollapsed}
            onToggle={toggleActivity}
          />
        )}
      </div>
    </Reveal>
  );
}
