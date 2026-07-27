"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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

export default function ContentLandingPage() {
  const [tab,        setTab]        = useState("plan");
  const [projectId,  setProjectId]  = useState(null);
  const [projectName, setProjectName] = useState("");
  const [error,      setError]      = useState("");

  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) {
      setError("Select a project in the sidebar to use the content agent.");
      return;
    }
    setProjectId(id);
    const p = getActiveProject();
    setProjectName(p?.profile?.company?.name || p?.name || "Project");
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
        Loading…
      </div>
    );
  }

  return (
    <div className="w-full">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Content Studio</h1>
        <p className="text-sm text-muted-foreground">
          Monthly plans, post drafts, formats, and analytics for {projectName}.
        </p>
      </header>

      <nav className="border-b border-border/60 mb-6">
        <div className="flex items-center gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-2 text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </nav>

      {tab === "plan"      && <PlanTab      projectId={projectId} />}
      {tab === "posts"     && <PostsTab     projectId={projectId} />}
      {tab === "analytics" && <AnalyticsView projectId={projectId} />}
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
  return <PlanBoard projectId={projectId} />;
}

// ---------------------------------------------------------------------------
// Brand tab — structured form (mirrors the project-context onboarding pattern)
// ---------------------------------------------------------------------------

function BrandTab({ projectId }) {
  return <BrandContextForm projectId={projectId} />;
}

// ---------------------------------------------------------------------------
// Library tab — Formats (full CRUD)
// ---------------------------------------------------------------------------

const LIBRARY_SECTIONS = [
  { id: "formats", label: "Formats" },
  { id: "styles",  label: "Styles" },
];

function LibraryTab({ projectId }) {
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
            {s.label}
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

function postRank(p) {
  // Published posts first (newest), then scheduled/drafts by day index.
  if (p.posted_at) return [0, -new Date(p.posted_at).getTime()];
  return [1, p.day_index ?? 999];
}

function PostsTab({ projectId }) {
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

  const visible = posts
    .filter((p) => filter === "all" || p.status === filter)
    .sort((a, b) => {
      const [ar, av] = postRank(a);
      const [br, bv] = postRank(b);
      return ar - br || av - bv;
    });

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="aspect-[4/5] animate-pulse rounded-xl border border-border/50 bg-muted/30" />
        ))}
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 p-10 text-center">
        <p className="mb-3 text-sm text-muted-foreground">No posts yet. Generate a plan and draft posts from the board.</p>
        <Button asChild><Link href="/content/plan">Open plan board →</Link></Button>
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
              {f} <span className="tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
          No {filter} posts.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {visible.map((p) => <PostCard key={p.id} post={p} />)}
        </div>
      )}
    </div>
  );
}

