"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  getBrandContext,
  listAvatars,
  listFormats,
  listPlans,
  listPosts,
  putBrandContext,
} from "@/lib/contentApi";
import { getActiveProjectId, getActiveProject } from "@/lib/projects";
import PlanKanban from "@/components/content/PlanKanban";

const TABS = ["plan", "brand", "library", "analytics"];

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
// Brand tab — simple JSON editor for MVP
// ---------------------------------------------------------------------------

function BrandTab({ projectId }) {
  const [brand,   setBrand]   = useState(null);
  const [pillars, setPillars] = useState("");
  const [audience, setAudience] = useState("");
  const [voice,   setVoice]   = useState("");
  const [valueProp, setValueProp] = useState("");
  const [goal,    setGoal]    = useState("");
  const [saving,  setSaving]  = useState(false);
  const [msg,     setMsg]     = useState("");
  const [err,     setErr]     = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const b = await getBrandContext(projectId);
        if (cancelled) return;
        setBrand(b);
        setAudience(b.content_brand?.audience || "");
        setVoice(b.content_brand?.brand_voice || "");
        setValueProp(b.content_brand?.value_prop || "");
        setGoal(b.content_brand?.content_goal || "");
        const items = Array.isArray(b.content_pillars?.items) ? b.content_pillars.items : [];
        setPillars(JSON.stringify(items, null, 2));
      } catch (e) {
        if (!cancelled) setErr(e.message || "Failed to load brand context.");
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  async function save() {
    setSaving(true); setMsg(""); setErr("");
    try {
      let parsedPillars;
      try {
        parsedPillars = pillars.trim() ? JSON.parse(pillars) : [];
      } catch {
        setErr("Pillars JSON is invalid.");
        return;
      }
      const updated = await putBrandContext(projectId, {
        content_brand: {
          audience, brand_voice: voice, value_prop: valueProp, content_goal: goal,
        },
        content_pillars: { items: parsedPillars },
      });
      setBrand(updated);
      setMsg("Saved.");
    } catch (e) {
      setErr(e.message || "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  if (!brand) return <p className="text-sm text-muted-foreground">Loading brand context…</p>;

  return (
    <div className="max-w-3xl space-y-4">
      <Field label="Audience" hint="Who is this content for?">
        <input className={INPUT} value={audience} onChange={(e) => setAudience(e.target.value)} />
      </Field>
      <Field label="Brand voice">
        <input className={INPUT} value={voice} onChange={(e) => setVoice(e.target.value)} />
      </Field>
      <Field label="Value proposition">
        <input className={INPUT} value={valueProp} onChange={(e) => setValueProp(e.target.value)} />
      </Field>
      <Field label="Content goal" hint="What does the agent optimise for?">
        <input className={INPUT} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </Field>
      <Field label="Pillars (JSON array of {id, name, description, research_hint?})" hint="Up to 5 pillars.">
        <textarea
          className={`${INPUT} font-mono text-xs`}
          rows={10}
          value={pillars}
          onChange={(e) => setPillars(e.target.value)}
        />
      </Field>

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save brand"}</Button>
        {msg && <span className="text-xs text-green-600">{msg}</span>}
        {err && <span className="text-xs text-destructive">{err}</span>}
      </div>
    </div>
  );
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

// ---------------------------------------------------------------------------
// Form helpers
// ---------------------------------------------------------------------------

const INPUT = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

function Field({ label, hint, children }) {
  return (
    <label className="block space-y-1">
      <span className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-muted-foreground/70">{hint}</span>}
    </label>
  );
}
