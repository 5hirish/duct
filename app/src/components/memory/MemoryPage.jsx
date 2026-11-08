"use client";

// Memory — one page, two scopes, switched by a tab.
//
//   Project   what Duct knows about the account. Shared with every member,
//             read by every agent that works on it.
//   Only you  how you like to work. Private: no teammate, owner or admin
//             sees it, and agents use it only when they work for you.
//
// They used to be two pages that looked alike and said different things, so
// nobody could tell which memory they were in. The switch puts the difference
// in the one place it can be seen, with the privacy line under it. The rows,
// filters and verbs are MemoryTimeline's; this file only binds each scope to
// its API and its words.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Building2, Lock, Users } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { Page, PageHeader } from "@/components/ui/page";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MemoryTimeline from "@/components/memory/MemoryTimeline";
import { hasAuthToken } from "@/lib/authFetch";
import { getProjectById } from "@/lib/projects";
import {
  PROJECT_KIND_GROUPS,
  USER_KIND_GROUPS,
  createMemory,
  createUserMemory,
  deleteMemory,
  deleteUserMemory,
  getMemory,
  listMemory,
  listUserMemory,
  moveUserMemory,
  resetMemory,
  resetUserMemory,
  setMemoryPaused,
  setUserMemoryPaused,
  updateMemory,
  updateUserMemory,
} from "@/lib/memoryApi";

export const SCOPE_PROJECT = "project";
export const SCOPE_YOU = "you";

/**
 * @param projectId     The project whose shared memory the Project tab shows.
 *                      Without one, the page is your memory alone.
 * @param initialScope  Which tab opens. `?view=you|project` overrides it.
 * @param focusId       A deep-linked project memory id (?m=).
 * @param back          PageHeader's back link, for the project route.
 */
export default function MemoryPage({ projectId = "", initialScope = SCOPE_PROJECT, focusId = "", back }) {
  const { t } = useLingui();
  const [scope, setScope] = useState(projectId ? initialScope : SCOPE_YOU);
  const [projectName, setProjectName] = useState("");
  const [signedIn, setSignedIn] = useState(true);

  // Browser state is read after mount (LocalBackendGate: the first render has
  // to match the server's).
  useEffect(() => {
    setSignedIn(hasAuthToken());
    setProjectName(projectId ? getProjectById(projectId)?.name || "" : "");
    const view = new URLSearchParams(window.location.search).get("view");
    if (view === SCOPE_YOU || (view === SCOPE_PROJECT && projectId)) setScope(view);
  }, [projectId]);

  const choose = (next) => {
    setScope(next);
    // Linkable, without a navigation that would refetch the page.
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(window.history.state, "", url);
  };

  const projectApi = useMemo(
    () => ({
      list: (opts) => listMemory({ projectId, ...opts }),
      get: ({ memoryId }) => getMemory({ projectId, memoryId }),
      create: (entry) => createMemory({ projectId, ...entry }),
      patch: (patch) => updateMemory({ projectId, ...patch }),
      remove: ({ memoryId }) => deleteMemory({ projectId, memoryId }),
      setPaused: ({ paused }) => setMemoryPaused({ projectId, paused }),
      reset: () => resetMemory({ projectId }),
    }),
    [projectId]
  );

  const userApi = useMemo(
    () => ({
      list: (opts) => listUserMemory({ ...opts, projectId }),
      create: (entry) => createUserMemory(entry),
      patch: (patch) => updateUserMemory(patch),
      move: projectId ? ({ memoryId, bound }) => moveUserMemory({ memoryId, projectId: bound ? projectId : "" }) : undefined,
      remove: ({ memoryId }) => deleteUserMemory({ memoryId }),
      setPaused: ({ paused }) => setUserMemoryPaused({ paused }),
      reset: () => resetUserMemory(),
    }),
    [projectId]
  );

  const onProject = scope === SCOPE_PROJECT && Boolean(projectId);
  const name = projectName || t`this project`;

  return (
    <Page width="reading">
      <PageHeader
        title={<Trans>Memory</Trans>}
        status={
          onProject ? (
            <Trans>Shared with everyone on {name}.</Trans>
          ) : (
            <Trans>Private to you. Agents use it only when they work for you.</Trans>
          )
        }
        back={back}
        actions={
          onProject ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/project/${projectId}/members`}>
                <Users className="size-4" /> <Trans>Members</Trans>
              </Link>
            </Button>
          ) : null
        }
      />

      {projectId && (
        <Tabs value={scope} onValueChange={choose} className="mb-4">
          <TabsList>
            <TabsTrigger value={SCOPE_PROJECT}>
              <Building2 aria-hidden="true" />
              <span className="max-w-[12rem] truncate">{projectName || <Trans>Project</Trans>}</span>
            </TabsTrigger>
            <TabsTrigger value={SCOPE_YOU}>
              <Lock aria-hidden="true" /> <Trans>Only you</Trans>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      )}

      {onProject ? (
        <MemoryTimeline
          key={`project:${projectId}`}
          api={projectApi}
          groups={PROJECT_KIND_GROUPS}
          signedIn={signedIn}
          focusId={focusId}
          errorSubject={t`this project's memory`}
          addPlaceholder={t`e.g. We never bid on competitor brand terms`}
          resetPrompt={t`Delete every memory for this project, for every member? This cannot be undone.`}
          emptyHint={t`Nothing yet. Fill in project settings, run an audit or ask the agent a question: what it learns lands here for you to keep or dismiss.`}
        />
      ) : (
        <MemoryTimeline
          key="you"
          api={userApi}
          groups={USER_KIND_GROUPS}
          binding={projectId ? { projectId, projectName: name } : null}
          signedIn={signedIn}
          errorSubject={t`your memory`}
          addPlaceholder={t`e.g. Always compare to the same week last year`}
          resetPrompt={t`Delete everything Duct has learned about how you work? This cannot be undone.`}
          emptyHint={t`Nothing yet. Tell Duct how you like answers, like "give me the number first, then the why".`}
        />
      )}
    </Page>
  );
}
