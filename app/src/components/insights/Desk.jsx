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

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { buildDesk, headline } from "@/lib/desk";
import { loadDesk, pinArtifact, pinConversation } from "@/lib/deskApi";
import { getActiveProjectId, getProjectById, PROJECTS_CHANGED } from "@/lib/projects";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { Skeleton } from "@/components/ui/skeleton";
import DeskCards from "./desk/DeskCards";
import DeskLists from "./desk/DeskLists";
import DeskActivity from "./desk/DeskActivity";
import DeskComposer from "./desk/DeskComposer";
import DeskDayOne from "./desk/DeskDayOne";

const EMPTY = {
  memories: [], conversations: [], artifacts: [], activity: [], changeSets: [], sourceCount: 0,
};

export default function Desk() {
  const router = useRouter();
  const [projectId, setProjectId] = useState("");
  const [project, setProject] = useState(null);
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [autonomy, setAutonomy] = useState(AUTONOMY_ASK);

  // The active project can change from the sidebar switcher without a
  // navigation, so this listens rather than reading once.
  useEffect(() => {
    const sync = () => {
      const id = getActiveProjectId() || "";
      setProjectId(id);
      const p = id ? getProjectById(id) : null;
      setProject(p);
      setAutonomy(p?.autonomyLevel || AUTONOMY_ASK);
    };
    sync();
    window.addEventListener(PROJECTS_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PROJECTS_CHANGED, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // Asked even with no project: loadDesk answers the account-level half of the
  // question (which sources are connected) either way, and the day-one
  // checklist would otherwise tell someone with three live connectors to go
  // and connect one.
  const refresh = useCallback(async () => {
    setLoading(true);
    const next = await loadDesk({ projectId });
    setData(next);
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

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
    <div className="flex min-h-[calc(100svh-160px)] flex-col">
      <div className="grid gap-x-11 gap-y-8 lg:grid-cols-[minmax(0,1fr)_288px]">
        <div className="flex min-w-0 flex-col gap-8">
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
    </div>
  );
}
