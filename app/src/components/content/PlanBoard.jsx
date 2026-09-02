"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutGrid, CalendarDays } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getPlan, listPlans, listPosts } from "@/lib/contentApi";
import PlanKanban from "@/components/content/PlanKanban";
import PlanCalendar from "@/components/content/PlanCalendar";

/**
 * Inline plan board — plan selector + Kanban/Calendar toggle. Renders directly
 * inside the Content "Plan" tab (no separate route hop). Pass `initialPlanId`
 * to preselect (e.g. from a query param).
 */
export default function PlanBoard({ projectId, initialPlanId = "" }) {
  const router = useRouter();
  const [plans, setPlans] = useState([]);
  const [activeId, setActiveId] = useState(initialPlanId || "");
  const [plan, setPlan] = useState(null); // full plan (days + posts)
  const [postsById, setPostsById] = useState({}); // full posts by id
  const [view, setView] = useState("kanban"); // "kanban" | "calendar"
  const [calView, setCalView] = useState("month"); // "month" | "week"
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await listPlans(projectId);
        if (cancelled) return;
        setPlans(list);
        setActiveId((prev) => prev || initialPlanId || list[0]?.id || "");
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load plans.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!activeId || !projectId) { setPlan(null); setPostsById({}); return; }
    let cancelled = false;
    (async () => {
      try {
        const [full, posts] = await Promise.all([
          getPlan(activeId),
          listPosts(projectId, { planId: activeId }).catch(() => []),
        ]);
        if (cancelled) return;
        setPlan(full);
        const map = {};
        for (const p of Array.isArray(posts) ? posts : []) map[p.id] = p;
        setPostsById(map);
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load plan.");
      }
    })();
    return () => { cancelled = true; };
  }, [activeId, projectId]);

  const activeMeta = useMemo(
    () => plans.find((p) => p.id === activeId) || plan || null,
    [plans, activeId, plan]
  );

  // Pending card → open the creation split-view, carrying the day's primary channel.
  const reviseDay = useCallback((index) => {
    const day = Array.isArray(plan?.days) ? plan.days[index] : null;
    const channel = (Array.isArray(day?.platforms) && day.platforms[0]) || "tiktok";
    const params = new URLSearchParams();
    if (activeId) params.set("plan_id", activeId);
    params.set("day", String(index));
    params.set("channel", channel);
    router.push(`/content/posts/new?${params.toString()}`);
  }, [plan, activeId, router]);

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading plan…</p>;
  }
  if (plans.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/60 p-10 text-center">
        <p className="text-sm text-muted-foreground">No plan yet for this project.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-border">
      {/* Sub-toolbar */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border/60 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          {plans.length > 1 ? (
            <Select value={activeId} onValueChange={setActiveId}>
              <SelectTrigger className="h-8 w-[220px]">
                <SelectValue placeholder="Select a plan" />
              </SelectTrigger>
              <SelectContent>
                {plans.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name || `Plan ${p.id.slice(0, 8)}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <span className="truncate text-sm font-medium">
              {activeMeta?.name || "Monthly plan"}
            </span>
          )}
          {Array.isArray(plan?.days) && (
            <span className="hidden text-xs text-muted-foreground tabular-nums @md:inline">
              {plan.days.length} posts
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {view === "calendar" && (
            <Segmented
              value={calView}
              onChange={setCalView}
              options={[{ key: "month", label: "Month" }, { key: "week", label: "Week" }]}
            />
          )}
          <ViewToggle view={view} onChange={setView} />
        </div>
      </div>

      {/* Board body */}
      {!plan ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          Loading plan…
        </div>
      ) : view === "kanban" ? (
        <PlanKanban plan={plan} postsById={postsById} onReviseDay={reviseDay} />
      ) : (
        <PlanCalendar plan={plan} postsById={postsById} view={calView} onViewChange={setCalView} onReviseDay={reviseDay} />
      )}
    </div>
  );
}

function Segmented({ value, onChange, options }) {
  return (
    <div className="flex shrink-0 items-center gap-1 rounded-lg border border-border/60 bg-muted/40 p-0.5">
      {options.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            value === key ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function ViewToggle({ view, onChange }) {
  const options = [
    { key: "kanban", label: "Kanban", Icon: LayoutGrid },
    { key: "calendar", label: "Calendar", Icon: CalendarDays },
  ];
  return (
    <div className="flex shrink-0 items-center gap-1 rounded-lg border border-border/60 bg-muted/40 p-0.5">
      {options.map(({ key, label, Icon }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            view === key
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Icon className="size-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
