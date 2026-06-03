"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  listAvatars,
  listFormats,
  listPlans,
  listPosts,
} from "@/lib/contentApi";
import { getActiveProjectId, getActiveProject } from "@/lib/projects";
import BrandContextForm from "@/components/content/BrandContextForm";
import PlanKanban from "@/components/content/PlanKanban";
import DiscoverPage from "@/components/content/DiscoverPage";

const TABS = ["plan", "brand", "discover", "library", "analytics"];

export default function ContentLandingPage() {
  const router = useRouter();
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
    <div className="max-w-7xl mx-auto py-6 px-6">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Content Marketing</h1>
          <p className="text-sm text-muted-foreground">
            30-day plans, post drafts, formats, avatars, and analytics for {projectName}.
          </p>
        </div>
        <Button onClick={() => router.push("/content/sessions/new")}>
          + Generate plan
        </Button>
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
      {tab === "brand"     && <BrandTab     projectId={projectId} />}
      {tab === "discover"  && <DiscoverPage projectId={projectId} />}
      {tab === "library"   && <LibraryTab   projectId={projectId} />}
      {tab === "analytics" && <AnalyticsTab projectId={projectId} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan tab
// ---------------------------------------------------------------------------

function PlanTab({ projectId }) {
  const [loading, setLoading] = useState(true);
  const [plans,   setPlans]   = useState([]);
  const [active,  setActive]  = useState(null);
  const [err,     setErr]     = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listPlans(projectId);
        if (cancelled) return;
        setPlans(list);
        if (list.length > 0) setActive(list[0]);
      } catch (e) {
        if (!cancelled) setErr(e.message || "Failed to load plans.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading plans…</p>;
  if (err)     return <p className="text-sm text-destructive">{err}</p>;

  if (plans.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-10 text-center">
        <p className="text-sm text-muted-foreground mb-3">
          No plans yet. Generate a 30-day plan to get started.
        </p>
        <Link
          href="/content/sessions/new"
          className="inline-block rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          + Generate plan
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {plans.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          {plans.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setActive(p)}
              className={`text-xs px-2 py-1 rounded border ${
                active?.id === p.id
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              {p.name || p.id.slice(0, 8)}
            </button>
          ))}
        </div>
      )}

      {active && <PlanKanban plan={active} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Brand tab — structured form (mirrors the project-context onboarding pattern)
// ---------------------------------------------------------------------------

function BrandTab({ projectId }) {
  return <BrandContextForm projectId={projectId} />;
}

// ---------------------------------------------------------------------------
// Library tab — formats + avatars (list-only MVP)
// ---------------------------------------------------------------------------

function LibraryTab({ projectId }) {
  const [formats, setFormats] = useState([]);
  const [avatars, setAvatars] = useState([]);
  const [posts,   setPosts]   = useState([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [f, a, p] = await Promise.all([
          listFormats(projectId),
          listAvatars(projectId),
          listPosts(projectId),
        ]);
        if (cancelled) return;
        setFormats(f);
        setAvatars(a);
        setPosts(p);
      } catch {/* fall through */}
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <LibraryCard title="Formats" count={formats.length}>
        {formats.map((f) => (
          <li key={f.id} className="py-1">
            <span className="font-mono text-xs">{f.slug}</span>
            {f.name && <span className="text-muted-foreground"> — {f.name}</span>}
          </li>
        ))}
      </LibraryCard>
      <LibraryCard title="Avatars" count={avatars.length}>
        {avatars.map((a) => (
          <li key={a.id} className="py-1">{a.name}</li>
        ))}
      </LibraryCard>
      <LibraryCard title="Posts" count={posts.length}>
        {posts.slice(0, 20).map((p) => (
          <li key={p.id} className="py-1">
            <Link href={`/content/posts/${p.id}`} className="text-primary hover:underline">
              {p.topic || p.post_dir_slug}
            </Link>
            <span className="text-muted-foreground"> · {p.status}</span>
          </li>
        ))}
      </LibraryCard>
    </div>
  );
}

function LibraryCard({ title, count, children }) {
  return (
    <section className="rounded-lg border border-border bg-background">
      <header className="flex items-center justify-between px-3 py-2 border-b border-border/50">
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
      </header>
      <ul className="max-h-80 overflow-y-auto px-3 py-2 text-xs divide-y divide-border/40">
        {children}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Analytics tab — placeholder; charts land in a follow-up phase
// ---------------------------------------------------------------------------

function AnalyticsTab({ projectId }) {
  const [posts, setPosts] = useState([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await listPosts(projectId, { status: "posted" });
        if (!cancelled) setPosts(p);
      } catch {/* ignore */}
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {posts.length} posted post{posts.length === 1 ? "" : "s"}. Per-channel charts arrive in a later phase.
      </p>
      {posts.length > 0 && (
        <table className="text-xs w-full border border-border/60 rounded-md overflow-hidden">
          <thead className="bg-muted/40 text-muted-foreground">
            <tr>
              <th className="text-left px-2 py-1.5">Topic</th>
              <th className="text-left px-2 py-1.5">Pillar</th>
              <th className="text-right px-2 py-1.5">Views</th>
              <th className="text-right px-2 py-1.5">Saves</th>
              <th className="text-right px-2 py-1.5">Save rate</th>
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => (
              <tr key={p.id} className="border-t border-border/60">
                <td className="px-2 py-1.5">
                  <Link href={`/content/posts/${p.id}`} className="text-primary hover:underline">
                    {p.topic || p.post_dir_slug}
                  </Link>
                </td>
                <td className="px-2 py-1.5 text-muted-foreground">{p.pillar}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{p.perf?.view_count ?? "—"}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{p.perf?.save_count ?? "—"}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">
                  {typeof p.perf?.save_rate === "number" ? `${(p.perf.save_rate * 100).toFixed(1)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

