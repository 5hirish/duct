"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button } from "@/components/ui/button";
import {
  listPosts,
} from "@/lib/contentApi";
import { getActiveProjectId, getActiveProject } from "@/lib/projects";
import BrandContextForm from "@/components/content/BrandContextForm";
import DiscoverPage from "@/components/content/DiscoverPage";
import AccountsTab from "@/components/content/AccountsTab";
import AnalyticsView from "@/components/content/AnalyticsView";
import FormatLibrary from "@/components/content/FormatLibrary";
import StyleGallery from "@/components/content/StyleGallery";
import PostCard from "@/components/content/PostCard";
import PlanBoard from "@/components/content/PlanBoard";

const TABS = ["plan", "posts", "analytics", "discover", "library", "brand", "accounts"];

// The tab ids double as their labels in English; the catalogue needs a message
// per id so the other languages can say something else.
const TAB_LABELS = {
  plan: msg`plan`,
  posts: msg`posts`,
  analytics: msg`analytics`,
  discover: msg`discover`,
  library: msg`library`,
  brand: msg`brand`,
  accounts: msg`accounts`,
};

export default function ContentLandingPage() {
  const { t, i18n } = useLingui();
  const [tab,        setTab]        = useState("plan");
  const [projectId,  setProjectId]  = useState(null);
  const [projectName, setProjectName] = useState("");
  const [error,      setError]      = useState("");

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) {
      setError(t`Select a project in the sidebar to use the content agent.`);
      return;
    }
    setProjectId(id);
    const p = getActiveProject();
    setProjectName(p?.profile?.company?.name || p?.name || t`Project`);
    // `t` follows the locale; this runs once on mount on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-6 text-center">
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="max-w-2xl mx-auto py-12 px-6 text-center text-sm text-muted-foreground">
        <Trans>Loading…</Trans>
      </div>
    );
  }

  return (
    <div className="w-full">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold"><Trans>Content Studio</Trans></h1>
        <p className="text-sm text-muted-foreground">
          <Trans>Monthly plans, post drafts, formats, and analytics for {projectName}.</Trans>
        </p>
      </header>

      <nav className="border-b border-border/60 mb-6">
        <div className="flex items-center gap-1">
          {TABS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`px-3 py-2 text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {i18n._(TAB_LABELS[id])}
            </button>
          ))}
        </div>
      </nav>

      {tab === "plan"      && <PlanTab      projectId={projectId} />}
      {tab === "posts"     && <PostsTab     projectId={projectId} />}
      {tab === "analytics" && (
        <AnalyticsView projectId={projectId} onLinkAccounts={() => setTab("accounts")} />
      )}
      {tab === "discover"  && <DiscoverPage projectId={projectId} />}
      {tab === "library"   && <LibraryTab   projectId={projectId} />}
      {tab === "brand"     && <BrandTab     projectId={projectId} />}
      {tab === "accounts"  && <AccountsTab  projectId={projectId} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan tab
// ---------------------------------------------------------------------------

function PlanTab({ projectId }) {
  // This tab scrolls inside .app-main-wide, so nothing above gives the board a
  // height — it is the one caller that has to state one. svh, not vh, to match
  // the rest of the app's full-height surfaces.
  return (
    <div className="h-[calc(100svh-15rem)] min-h-[28rem]">
      <PlanBoard projectId={projectId} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Brand tab — structured form (mirrors the project-context page's pattern)
// ---------------------------------------------------------------------------

function BrandTab({ projectId }) {
  return <BrandContextForm projectId={projectId} />;
}

// ---------------------------------------------------------------------------
// Library tab — Formats (full CRUD)
// ---------------------------------------------------------------------------

const LIBRARY_SECTIONS = [
  { id: "formats", label: msg`Formats` },
  { id: "styles",  label: msg`Styles` },
];

function LibraryTab({ projectId }) {
  const { i18n } = useLingui();
  const [section, setSection] = useState("formats");
  return (
    <div className="space-y-5">
      <div className="inline-flex rounded-lg border border-border/70 bg-muted/40 p-0.5">
        {LIBRARY_SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              section === s.id
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {i18n._(s.label)}
          </button>
        ))}
      </div>
      {section === "formats" ? <FormatLibrary projectId={projectId} /> : <StyleGallery />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Posts tab — all drafted/posted posts for the project
// ---------------------------------------------------------------------------

const POST_FILTERS = ["all", "posted", "scheduled", "draft"];

// Filter ids are post statuses (API values); these are what the chips say.
const FILTER_LABELS = {
  all: msg`all`,
  posted: msg`posted`,
  scheduled: msg`scheduled`,
  draft: msg`draft`,
};

function postRank(p) {
  // Published posts first (newest), then scheduled/drafts by day index.
  if (p.posted_at) return [0, -new Date(p.posted_at).getTime()];
  return [1, p.day_index ?? 999];
}

function PostsTab({ projectId }) {
  const { i18n } = useLingui();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await listPosts(projectId);
        if (cancelled) return;
        setPosts(Array.isArray(p) ? p : []);
      } catch {/* ignore */}
      finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const counts = posts.reduce((acc, p) => {
    acc.all = (acc.all || 0) + 1;
    acc[p.status] = (acc[p.status] || 0) + 1;
    return acc;
  }, {});

  const filterLabel = i18n._(FILTER_LABELS[filter]);

  const visible = posts
    .filter((p) => filter === "all" || p.status === filter)
    .sort((a, b) => {
      const [ar, av] = postRank(a);
      const [br, bv] = postRank(b);
      return ar - br || av - bv;
    });

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 @md:grid-cols-3 @3xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="aspect-[4/5] animate-pulse rounded-xl border border-border/50 bg-muted/30" />
        ))}
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 p-10 text-center">
        <p className="mb-3 text-sm text-muted-foreground"><Trans>No posts yet. Generate a plan and draft posts from the board.</Trans></p>
        <Button asChild><Link href="/content/plan"><Trans>Open plan board →</Trans></Link></Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        {POST_FILTERS.map((f) => {
          const n = counts[f] || 0;
          if (f !== "all" && n === 0) return null;
          return (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                filter === f
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/70"
              }`}
            >
              {i18n._(FILTER_LABELS[f])} <span className="tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
          <Trans>No {filterLabel} posts.</Trans>
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4 @md:grid-cols-3 @3xl:grid-cols-4">
          {visible.map((p) => <PostCard key={p.id} post={p} />)}
        </div>
      )}
    </div>
  );
}

