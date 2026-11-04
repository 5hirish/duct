"use client";

// Activity — the project's audit trail. One row per lifecycle transition
// (change set proposed/approved/applied/rolled back, GTM publishes, artifact
// versions) with actor attribution. Filter by category, or scope to a single
// conversation via ?conversation_id= (linked from audit chats) to read that
// chat's proposals, auto-applies, rollbacks, and artifacts as one timeline.

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileText, History, LockKeyhole, ShieldCheck, SquareTerminal, Zap } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { getActiveProject } from "../../../lib/projects";
import { hasAuthToken, isSessionExpired } from "../../../lib/authFetch";
import LoadError from "@/components/LoadError";
import EmptyState from "@/components/ui/empty-state";
import { relativeTime } from "@/lib/format";
import { listActivity } from "../../../lib/activityApi";
import { Button } from "@/components/ui/button";
import { SkeletonList } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Page, PageHeader } from "@/components/ui/page";

const CATEGORY_TABS = [
  { value: "", label: msg`All` },
  { value: "execution", label: msg`Execution` },
  { value: "artifact", label: msg`Artifacts` },
];

const SOURCE_BADGES = {
  user: { label: msg`you`, className: "status-pill grey" },
  agent: { label: msg`agent`, className: "status-pill green" },
  auto: { label: msg`auto`, className: "status-pill yellow" },
};

function rowIcon(row) {
  if (row.category === "artifact") return FileText;
  // An outside agent drafting the project through the MCP server.
  if (row.category === "project") return SquareTerminal;
  if (row.action === "gtm.published") return Zap;
  return ShieldCheck;
}

function targetHref(row) {
  if (row.target_type === "artifact" && row.target_id) return `/artifacts/${row.target_id}`;
  if (row.target_type === "change_set") return "/execute";
  if (row.target_type === "project" && row.target_id) return `/project/${row.target_id}`;
  return null;
}

function ActivityRow({ row }) {
  const { i18n } = useLingui();
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
          <span className={badge.className} style={{ fontSize: 11 }}>{i18n._(badge.label)}</span>
          {row.connector_type && <span>{row.connector_type}</span>}
          <span>{relativeTime(row.created_at)}</span>
          {hasData && (
            <details className="inline-block">
              <summary className="cursor-pointer select-none hover:text-foreground"><Trans>details</Trans></summary>
              <pre className="mt-1 max-w-full overflow-x-auto rounded bg-muted/40 p-2 text-2xs">
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
  const { t, i18n } = useLingui();
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

  // Bumped by the error panel's retry — the load lives in an effect, so a
  // dependency is how you ask it to run again.
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((n) => n + 1), []);

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
        // A retired session is already redirecting to sign-in; anything shown
        // here would only flash past on the way out.
        if (!alive || isSessionExpired(err)) return;
        setItems([]);
        setError(err.message || "");
      });
    return () => {
      alive = false;
    };
  }, [project, signedIn, conversationId, category, reloadKey]);

  const loadMore = useCallback(() => {
    if (!nextBefore || !project?.id) return;
    setLoadingMore(true);
    listActivity({ projectId: project.id, conversationId, category, before: nextBefore })
      .then((body) => {
        setItems((prev) => [...(prev || []), ...body.items]);
        setNextBefore(body.next_before);
      })
      .catch((err) => {
        if (isSessionExpired(err)) return;
        setError(err.message || "");
      })
      .finally(() => setLoadingMore(false));
  }, [nextBefore, project, conversationId, category]);

  const projectName = project?.name || t`this project`;

  return (
    <Page>
      <PageHeader
        title={<Trans>Activity</Trans>}
        status={
          conversationId ? (
            <Trans>
              One conversation ·{" "}
              <Link href="/activity" className="underline underline-offset-2">
                show all
              </Link>
            </Trans>
          ) : (
            <Trans>What changed on {projectName}, and who did it</Trans>
          )
        }
        actions={
          <Tabs value={category} onValueChange={setCategory}>
            <TabsList>
              {CATEGORY_TABS.map((tab) => (
                <TabsTrigger key={tab.value || "all"} value={tab.value}>
                  {i18n._(tab.label)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        }
      />

      {!signedIn && (
        <div>
          <EmptyState
            icon={LockKeyhole}
            title={t`Sign in to see project activity`}
            actions={
              <Button size="sm" asChild>
                <Link href="/"><Trans>Sign in</Trans></Link>
              </Button>
            }
          >
            <Trans>
              Every entry names who did it, so the trail starts once there is an account to
              name.
            </Trans>
          </EmptyState>
        </div>
      )}

      {signedIn && items === null && (
        <SkeletonList rows={5} label={t`Loading activity`} />
      )}

      {signedIn && error && (
        <LoadError what={t`this project's activity`} detail={error} onRetry={reload} />
      )}

      {signedIn && !error && items && items.length === 0 && (
        <div>
          <EmptyState
            icon={History}
            title={t`No activity yet`}
            // One action, not two. The obvious second was "see what needs
            // approval", and on a project with no activity there is nothing
            // to approve — a button that lands on another empty page is worse
            // than no button, because it spends the reader's trust as well as
            // their click.
            actions={
              <Button size="sm" asChild>
                <Link href="/insights/organic-growth"><Trans>Ask a question</Trans></Link>
              </Button>
            }
          >
            <Trans>Proposals, approvals and rollbacks land here.</Trans>
          </EmptyState>
        </div>
      )}

      {signedIn && items && items.length > 0 && (
        <Card className="gap-0 overflow-hidden p-0">
          <ul>
            {items.map((row) => (
              <ActivityRow key={row.id} row={row} />
            ))}
          </ul>
        </Card>
      )}

      {signedIn && nextBefore && (
        <Button variant="outline" size="sm" className="self-start" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? <Trans>Loading…</Trans> : <Trans>Load older activity</Trans>}
        </Button>
      )}
    </Page>
  );
}

export default function ActivityPage() {
  const { t } = useLingui();

  // useSearchParams requires a Suspense boundary in the App Router.
  return (
    <Suspense
      fallback={
        <Page>
          <PageHeader title={<Trans>Activity</Trans>} />
          <SkeletonList rows={5} label={t`Loading activity`} />
        </Page>
      }
    >
      <ActivityFeed />
    </Suspense>
  );
}
