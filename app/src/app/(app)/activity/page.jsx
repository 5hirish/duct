"use client";

// Activity — the project's audit trail. One row per lifecycle transition
// (change set proposed/approved/applied/rolled back, GTM publishes, artifact
// versions) with actor attribution. Filter by category, or scope to a single
// conversation via ?conversation_id= (linked from audit chats) to read that
// chat's proposals, auto-applies, rollbacks, and artifacts as one timeline.

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileText, History, ShieldCheck, Zap } from "lucide-react";
import { getActiveProject } from "../../../lib/projects";
import { hasAuthToken } from "../../../lib/authFetch";
import { relativeTime } from "@/lib/format";
import { listActivity } from "../../../lib/activityApi";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const CATEGORY_TABS = [
  { value: "", label: "All" },
  { value: "execution", label: "Execution" },
  { value: "artifact", label: "Artifacts" },
];

const SOURCE_BADGES = {
  user: { label: "you", className: "status-pill grey" },
  agent: { label: "agent", className: "status-pill green" },
  auto: { label: "auto", className: "status-pill yellow" },
};

function rowIcon(row) {
  if (row.category === "artifact") return FileText;
  if (row.action === "gtm.published") return Zap;
  return ShieldCheck;
}

function targetHref(row) {
  if (row.target_type === "artifact" && row.target_id) return `/artifacts/${row.target_id}`;
  if (row.target_type === "change_set") return "/execute";
  return null;
}

function ActivityRow({ row }) {
  const Icon = rowIcon(row);
  const badge = SOURCE_BADGES[row.source] || SOURCE_BADGES.user;
  const href = targetHref(row);
  const hasData = row.data && Object.keys(row.data).length > 0;

  return (
    <li className="flex items-start gap-3 px-3 py-2.5 border-b border-border/40 last:border-b-0">
      <span className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden="true">
        <Icon size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug">
          {href ? (
            <Link href={href} className="hover:underline underline-offset-2">
              {row.summary || row.action}
            </Link>
          ) : (
            row.summary || row.action
          )}
        </p>
        <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span className={badge.className} style={{ fontSize: 11 }}>{badge.label}</span>
          {row.connector_type && <span>{row.connector_type}</span>}
          <span>{relativeTime(row.created_at)}</span>
          {hasData && (
            <details className="inline-block">
              <summary className="cursor-pointer select-none hover:text-foreground">details</summary>
              <pre className="mt-1 max-w-full overflow-x-auto rounded bg-muted/40 p-2 text-[11px]">
                {JSON.stringify(row.data, null, 2)}
              </pre>
            </details>
          )}
        </p>
      </div>
    </li>
  );
}

function ActivityFeed() {
  const searchParams = useSearchParams();
  const conversationId = searchParams.get("conversation_id") || "";

  const [project, setProject] = useState(null);
  const [signedIn, setSignedIn] = useState(true);
  const [category, setCategory] = useState("");
  const [items, setItems] = useState(null); // null = loading
  const [nextBefore, setNextBefore] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setProject(getActiveProject());
    setSignedIn(hasAuthToken());
  }, []);

  useEffect(() => {
    if (!project?.id || !signedIn) {
      if (project !== null) setItems([]);
      return;
    }
    let alive = true;
    setItems(null);
    setError("");
    listActivity({ projectId: project.id, conversationId, category })
      .then((body) => {
        if (!alive) return;
        setItems(body.items);
        setNextBefore(body.next_before);
      })
      .catch((err) => {
        if (!alive) return;
        setItems([]);
        setError(err.message || "Failed to load activity.");
      });
    return () => {
      alive = false;
    };
  }, [project, signedIn, conversationId, category]);

  const loadMore = useCallback(() => {
    if (!nextBefore || !project?.id) return;
    setLoadingMore(true);
    listActivity({ projectId: project.id, conversationId, category, before: nextBefore })
      .then((body) => {
        setItems((prev) => [...(prev || []), ...body.items]);
        setNextBefore(body.next_before);
      })
      .catch((err) => setError(err.message || "Failed to load more."))
      .finally(() => setLoadingMore(false));
  }, [nextBefore, project, conversationId, category]);

  return (
    <section>
      <div className="page-toolbar-back">
        <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">Activity</h1>
      </div>

      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 14 }}>
        Everything that changed on <strong>{project?.name || "this project"}</strong> — who
        proposed it, who approved it, what was applied or rolled back.
      </p>

      {conversationId && (
        <p style={{ marginBottom: 12 }}>
          <span className="status-pill grey">
            Filtered to one conversation ·{" "}
            <Link href="/activity" className="underline underline-offset-2">
              show all
            </Link>
          </span>
        </p>
      )}

      <Tabs value={category} onValueChange={setCategory}>
        <TabsList>
          {CATEGORY_TABS.map((tab) => (
            <TabsTrigger key={tab.value || "all"} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {!signedIn && (
        <p className="app-subtle" style={{ marginTop: 18 }}>Sign in to see project activity.</p>
      )}

      {signedIn && items === null && (
        <p className="app-subtle" style={{ marginTop: 18 }}>Loading…</p>
      )}

      {signedIn && items && items.length === 0 && (
        <div style={{ marginTop: 18 }}>
          <p className="app-subtle">
            {error ||
              "No activity yet. When an agent proposes changes or writes artifacts for this project, every transition lands here."}
          </p>
        </div>
      )}

      {signedIn && items && items.length > 0 && (
        <div className="rounded-lg border border-border/60" style={{ marginTop: 18 }}>
          <ul>
            {items.map((row) => (
              <ActivityRow key={row.id} row={row} />
            ))}
          </ul>
        </div>
      )}

      {signedIn && nextBefore && (
        <div style={{ marginTop: 12 }}>
          <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load older activity"}
          </Button>
        </div>
      )}
    </section>
  );
}

export default function ActivityPage() {
  // useSearchParams requires a Suspense boundary in the App Router.
  return (
    <Suspense
      fallback={
        <section>
          <div className="page-toolbar-back">
            <h1 className="page-toolbar-title text-2xl font-semibold tracking-tight">
              <History size={20} className="inline-block mr-2 align-[-3px]" aria-hidden="true" />
              Activity
            </h1>
          </div>
          <p className="app-subtle">Loading…</p>
        </section>
      }
    >
      <ActivityFeed />
    </Suspense>
  );
}
