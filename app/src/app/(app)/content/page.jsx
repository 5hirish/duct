"use client";

import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, CopyPlus, Plus } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import { msg } from "@lingui/core/macro";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  listPosts,
} from "@/lib/contentApi";
import { getProjectById } from "@/lib/projects";
import { useActiveProjectId } from "@/hooks/useActiveProjectId";
import BrandContextForm from "@/components/content/BrandContextForm";
import AccountsTab from "@/components/content/AccountsTab";
import FormatLibrary from "@/components/content/FormatLibrary";
import StyleGallery from "@/components/content/StyleGallery";
import PostCard from "@/components/content/PostCard";
import CloneFromUrlDialog from "@/components/content/CloneFromUrlDialog";
import PlanBoard from "@/components/content/PlanBoard";
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DRAFT_CHANNELS } from "@/lib/contentEnums";

// One tab shows at a time and the hub opens on the plan. Analytics brings
// Recharts and Discover is the largest tab, so neither is downloaded until
// someone opens it.
const AnalyticsView = lazy(() => import("@/components/content/AnalyticsView"));
const DiscoverPage = lazy(() => import("@/components/content/DiscoverPage"));

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
  const [tab, setTab] = useState("plan");
  const projectId = useActiveProjectId();
  const project = useMemo(() => (projectId ? getProjectById(projectId) : null), [projectId]);
  const projectName = project?.profile?.company?.name || project?.name || t`Project`;

  // A link from outside the hub (the plan board's first-run fixes) names its
  // tab; read once here rather than with useSearchParams, which would make the
  // whole hub suspend for a value only the first render needs.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");
    if (TABS.includes(wanted)) setTab(wanted);
  }, []);

  if (projectId === "") {
    return (
      <div className="max-w-2xl mx-auto py-12 px-6 text-center">
        <p className="text-sm text-muted-foreground"><Trans>Select a project in the sidebar to use the content agent.</Trans></p>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="grid grid-cols-2 gap-4 @md:grid-cols-3 @3xl:grid-cols-4 @7xl:grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]" role="status" aria-label={t`Loading`}>
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="aspect-[4/5] rounded-xl" />
        ))}
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
        {/* Seven tabs are ~500px of text: on a phone, or a tablet with the
            sidebar open, they scroll in place instead of widening the page. */}
        <div className="flex items-center gap-1 overflow-x-auto">
          {TABS.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`shrink-0 whitespace-nowrap px-3 py-2 text-sm capitalize transition-colors border-b-2 -mb-px ${
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

      {/* Keyed on the project so a switch from the sidebar remounts the tab:
          each one loads its project's data on mount, and the Posts tab's
          loading flag would otherwise never reset for the new project. */}
      <div key={projectId}>
        {tab === "plan"      && <PlanTab      projectId={projectId} onOpenTab={setTab} />}
        {tab === "posts"     && <PostsTab     projectId={projectId} />}
        <Suspense fallback={<Skeleton className="h-64 w-full rounded-xl" />}>
          {tab === "analytics" && (
            <AnalyticsView projectId={projectId} onLinkAccounts={() => setTab("accounts")} />
          )}
          {tab === "discover"  && <DiscoverPage projectId={projectId} />}
        </Suspense>
        {tab === "library"   && <LibraryTab   projectId={projectId} />}
        {tab === "brand"     && <BrandTab     projectId={projectId} />}
        {tab === "accounts"  && <AccountsTab  projectId={projectId} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan tab
// ---------------------------------------------------------------------------

function PlanTab({ projectId, onOpenTab }) {
  // This tab scrolls inside .app-main-wide, so nothing above gives the board a
  // height — it is the one caller that has to state one. svh, not vh, to match
  // the rest of the app's full-height surfaces.
  return (
    <div className="h-[calc(100svh-15rem)] min-h-[28rem]">
      <PlanBoard projectId={projectId} onOpenTab={onOpenTab} />
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

const POST_FILTERS = ["all", "posted", "scheduled", "failed", "draft"];

// Filter ids are post statuses (API values); these are what the chips say.
const FILTER_LABELS = {
  all: msg`all`,
  posted: msg`posted`,
  scheduled: msg`scheduled`,
  failed: msg`failed`,
  draft: msg`draft`,
};

function postRank(p) {
  // Published posts first (newest), then scheduled/drafts by day index.
  if (p.posted_at) return [0, -new Date(p.posted_at).getTime()];
  return [1, p.day_index ?? 999];
}

function PostsTab({ projectId }) {
  const { i18n } = useLingui();
  const router = useRouter();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [cloneOpen, setCloneOpen] = useState(false);

  // The two ways into a post no plan asked for: write one for a channel the
  // agent has a playbook for, or model one on a TikTok that already worked
  // (issue #222). The workspace does the rest.
  const newPostMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm">
          <Plus aria-hidden="true" /> <Trans>New post</Trans> <ChevronDown aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        {DRAFT_CHANNELS.map(({ id }) => (
          <DropdownMenuItem
            key={id}
            onClick={() => router.push(`/content/posts/new?${new URLSearchParams({ channel: id })}`)}
          >
            <PlatformGlyph platform={id} className="size-4" />
            <span>{platformMeta(id).label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const cloneButton = (
    <Button size="sm" variant="outline" onClick={() => setCloneOpen(true)}>
      <CopyPlus aria-hidden="true" /> <Trans>Clone a TikTok</Trans>
    </Button>
  );
  const cloneDialog = (
    <CloneFromUrlDialog
      open={cloneOpen}
      onOpenChange={setCloneOpen}
      onClone={(url) => router.push(`/content/posts/new?${new URLSearchParams({ clone_url: url })}`)}
    />
  );

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
      <div className="grid grid-cols-2 gap-4 @md:grid-cols-3 @3xl:grid-cols-4 @7xl:grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="aspect-[4/5] rounded-xl" />
        ))}
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 p-10 text-center">
        <p className="mb-3 text-sm text-muted-foreground"><Trans>No posts yet. Write one for TikTok, LinkedIn or X, draft them from a plan, or clone a TikTok that worked.</Trans></p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {newPostMenu}
          <Button asChild variant="outline" size="sm"><Link href="/content/plan"><Trans>Open plan board →</Trans></Link></Button>
          {cloneButton}
        </div>
        {cloneDialog}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {cloneDialog}
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="order-last ml-auto flex items-center gap-2">{cloneButton}{newPostMenu}</div>
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
        <div className="grid grid-cols-2 gap-4 @md:grid-cols-3 @3xl:grid-cols-4 @7xl:grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">
          {visible.map((p) => <PostCard key={p.id} post={p} />)}
        </div>
      )}
    </div>
  );
}

