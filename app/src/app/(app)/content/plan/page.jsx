"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { LayoutGrid, CalendarDays } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { getPlan, listPlans } from "@/lib/contentApi";
import { getActiveProjectId } from "@/lib/projects";
import PlanKanban from "@/components/content/PlanKanban";
import PlanCalendar from "@/components/content/PlanCalendar";

export default function PlanBoardPage() {
  const searchParams = useSearchParams();
  const requestedPlanId = searchParams.get("plan");

  const [projectId, setProjectId] = useState(null);
  const [plans, setPlans] = useState([]);
  const [activeId, setActiveId] = useState(requestedPlanId || "");
  const [plan, setPlan] = useState(null); // full plan (days + posts)
  const [view, setView] = useState("kanban"); // "kanban" | "calendar"
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Load the project's plan list.
  useEffect(() => {
    const id = getActiveProjectId();
    if (!id) {
      setError("Select a project in the sidebar to view its plan.");
      setLoading(false);
      return;
    }
    setProjectId(id);
    let cancelled = false;
    (async () => {
      try {
        const list = await listPlans(id);
        if (cancelled) return;
        setPlans(list);
        setActiveId((prev) => prev || requestedPlanId || list[0]?.id || "");
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load plans.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load the full active plan (days + posts) whenever the selection changes.
  useEffect(() => {
    if (!activeId) {
      setPlan(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const full = await getPlan(activeId);
        if (!cancelled) setPlan(full);
      } catch (e) {
        if (!cancelled) setError(e.message || "Failed to load plan.");
      }
    })();
    return () => { cancelled = true; };
  }, [activeId]);

  const activeMeta = useMemo(
    () => plans.find((p) => p.id === activeId) || plan || null,
    [plans, activeId, plan]
  );

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        Loading plan…
      </div>
    );
  }

  if (plans.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No plans yet. Generate a 30-day plan to get started.
        </p>
        <Button asChild>
          <Link href="/content/sessions/new">+ Generate plan</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
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
              {activeMeta?.name || "30-day plan"}
            </span>
          )}
          {Array.isArray(plan?.days) && (
            <span className="hidden text-xs text-muted-foreground tabular-nums sm:inline">
              {plan.days.length} days
            </span>
          )}
        </div>

        <ViewToggle view={view} onChange={setView} />
      </div>

      {/* Board body */}
      {!plan ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          Loading plan…
        </div>
      ) : view === "kanban" ? (
        <PlanKanban plan={plan} />
      ) : (
        <PlanCalendar plan={plan} />
      )}
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
