"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutGrid, CalendarDays, CalendarCheck, CalendarPlus, List, PencilLine, Plus } from "lucide-react";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  VENDOR,
  connectVendorKey,
  getBrandContext,
  getPlan,
  getVendorKeyStatus,
  listLinkedAccounts,
  listPlans,
  listPosts,
} from "@/lib/contentApi";
import LoadError from "@/components/LoadError";
import { Button } from "@/components/ui/button";
import PlanKanban from "@/components/content/PlanKanban";
import PlanList from "@/components/content/PlanList";
import PlanCalendar from "@/components/content/PlanCalendar";
import PlanStrategy from "@/components/content/PlanStrategy";
import PlanDayOne from "@/components/content/PlanDayOne";
import {
  PlanState,
  dayKey,
  nextPlanStart,
  planCovering,
  planEndOf,
  planItems,
  planPeriodOptions,
  planProgress,
  planStartOf,
  planState,
} from "@/lib/contentSchedule";
import { formatDate, formatDateRange } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { PeriodName, PlanPeriodMenu } from "@/components/content/PlanPeriodPicker";

// Where a plan is made or managed: a plan_month session in the split
// workspace. Nothing linked here before #274, so a new project had no way in
// but the URL.
export const NEW_PLAN_HREF = "/content/sessions/new";

/**
 * The session for one plan: `planId` reopens that plan to revise it (with its
 * conversation, when it has one); `start` and `days` plan that period. With
 * neither, the session manages the plan covering today, or makes one for the
 * month in progress — the backend resolves the same way.
 */
export function planSessionHref({ planId, start, days } = {}) {
  const params = new URLSearchParams();
  if (planId) params.set("plan", planId);
  else if (start) {
    params.set("start", dayKey(start));
    if (days) params.set("days", String(days));
  }
  const q = params.toString();
  return q ? `${NEW_PLAN_HREF}?${q}` : NEW_PLAN_HREF;
}

function startOfToday() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

// The view a person last chose, per browser: a viewing preference, so
// localStorage, read after mount so the first render matches the server's.
const VIEW_KEY = "duct_plan_view";
export const PlanView = Object.freeze({ LIST: "list", KANBAN: "kanban", CALENDAR: "calendar" });

/**
 * The plan board: loads the project's plans and hands them to PlanBoardView.
 * Renders directly inside the Content "Plan" tab (no separate route hop). Pass
 * `initialPlanId` to preselect (e.g. from a query param). Before the first plan
 * it is `PlanDayOne`, whose "fix this" links call `onOpenTab(tab)`; a caller
 * outside Content Studio's tabs leaves it out and the links navigate there.
 * `fill` is the full-bleed /content/plan route: the board is a framed box that
 * scrolls itself; on the Content Studio page the page scrolls.
 */
export default function PlanBoard({ projectId, initialPlanId = "", onOpenTab, fill = false }) {
  const { t, i18n } = useLingui();
  const router = useRouter();
  const [plans, setPlans] = useState([]);
  const [activeId, setActiveId] = useState(initialPlanId || "");
  const [plan, setPlan] = useState(null); // full plan (days + posts)
  const [postsById, setPostsById] = useState({}); // full posts by id
  const [view, setViewState] = useState(PlanView.LIST);
  const [calView, setCalView] = useState("month"); // "month" | "week"
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // What the first-run screen shows back: null is "could not tell", which
  // it renders differently from "nothing set".
  const [sources, setSources] = useState({ brand: null, accounts: null, vendors: {} });
  // Bumped by the retry button. Both loads below key off it, because a
  // failure in either leaves the same empty board.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_KEY);
      if (Object.values(PlanView).includes(saved)) setViewState(saved);
    } catch {
      // Blocked storage: the agenda stands.
    }
  }, []);
  const setView = useCallback((next) => {
    setViewState(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Not worth failing a click over.
    }
  }, []);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await listPlans(projectId);
        if (cancelled) return;
        // Only a project with no plan shows its sources, so only it waits
        // for them. Either failing leaves its part of the screen out.
        if (list.length === 0) {
          const [brand, accounts, postBridge, apify] = await Promise.all([
            getBrandContext(projectId).catch(() => null),
            listLinkedAccounts(projectId).catch(() => null),
            getVendorKeyStatus(VENDOR.POSTBRIDGE, projectId).catch(() => null),
            getVendorKeyStatus(VENDOR.APIFY, projectId).catch(() => null),
          ]);
          if (cancelled) return;
          setSources({ brand, accounts, vendors: { [VENDOR.POSTBRIDGE]: postBridge, [VENDOR.APIFY]: apify } });
        }
        setPlans(list);
        // The plan for today's period first: the Plan tab manages it.
        setActiveId((prev) => prev || initialPlanId || planCovering(list, new Date())?.id || list[0]?.id || "");
      } catch (e) {
        if (!cancelled) setError(e.message || "");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, reloadKey]);

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
        if (!cancelled) setError(e.message || "");
      }
    })();
    return () => { cancelled = true; };
  }, [activeId, projectId, reloadKey]);

  const today = startOfToday();
  const startPlan = useCallback((period) => router.push(planSessionHref(period)), [router]);

  // A key pasted into the first-run checklist. The save answers with the new
  // status, so the row turns over without a second read; a refusal throws
  // and the field shows the vendor's reason.
  const connectVendor = useCallback(async (vendor, apiKey) => {
    const status = await connectVendorKey(vendor, apiKey);
    setSources((prev) => ({ ...prev, vendors: { ...prev.vendors, [vendor]: status } }));
  }, []);

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
    return (
      <LoadError
        what={t`your content plan`}
        detail={error}
        onRetry={() => { setError(""); setReloadKey((k) => k + 1); }}
      />
    );
  }
  if (loading) {
    return <p className="text-sm text-muted-foreground"><Trans>Loading plan…</Trans></p>;
  }
  if (plans.length === 0) {
    return (
      <PlanDayOne
        brand={sources.brand}
        accounts={sources.accounts}
        vendors={sources.vendors}
        onConnectVendor={connectVendor}
        onStart={startPlan}
        onOpenTab={onOpenTab || ((tab) => router.push(`/content?tab=${tab}`))}
      />
    );
  }

  return (
    <PlanBoardView
      plans={plans}
      activeId={activeId}
      onSelectPlan={setActiveId}
      plan={plan}
      postsById={postsById}
      view={view}
      onViewChange={setView}
      calView={calView}
      onCalViewChange={setCalView}
      today={today}
      onStartPlan={startPlan}
      onRevisePlan={() => router.push(planSessionHref({ planId: activeId }))}
      onReviseDay={reviseDay}
      fill={fill}
    />
  );
}

/**
 * The board itself, from data alone, so /preview can render every plan
 * situation without a backend (lib/__fixtures__/planScenarios.mjs).
 *
 * What it leads with follows the plan's dates, not the button's history: a
 * plan still running (or ahead) is revised in place, and one that has ended
 * says so and offers the next one, instead of showing a past month's posts as
 * if they were still to come.
 */
export function PlanBoardView({
  plans,
  activeId,
  onSelectPlan,
  plan,
  postsById = {},
  view = PlanView.LIST,
  onViewChange,
  calView = "month",
  onCalViewChange,
  today,
  onStartPlan,
  onRevisePlan,
  onReviseDay,
  fill = false,
}) {
  const { t, i18n } = useLingui();
  const activeMeta = plans.find((p) => p.id === activeId) || plan || null;
  const items = useMemo(
    () => planItems(plan, postsById, { locale: i18n.locale, today }),
    [plan, postsById, i18n.locale, today]
  );
  const progress = planProgress(items);
  const state = planState(activeMeta, today);
  const ended = state === PlanState.ENDED;
  const current = planCovering(plans, today);
  const newOptions = current ? [] : planPeriodOptions(today, plans);
  const aheadFrom = nextPlanStart(plans, today);
  const aheadOptions = aheadFrom ? planPeriodOptions(aheadFrom, plans) : [];
  const selectedEnd = planEndOf(activeMeta);
  const periodLabel = formatDateRange(planStartOf(activeMeta), selectedEnd, { locale: i18n.locale });
  const scroll = fill ? "self" : "page";
  const { total, posted, missed } = progress;

  return (
    <div
      className={cn(
        "@container flex min-w-0 flex-col",
        fill ? "h-full min-h-[28rem] overflow-hidden rounded-2xl border border-border" : "gap-5"
      )}
    >
      <div className={cn("flex shrink-0 flex-wrap items-center justify-between gap-3", fill && "border-b border-border/60 px-4 py-2.5")}>
        <div className="flex min-w-0 flex-col gap-0.5">
          {plans.length > 1 ? (
            <Select value={activeId} onValueChange={onSelectPlan}>
              <SelectTrigger className="h-8 w-[220px]">
                <SelectValue placeholder={t`Select a plan`} />
              </SelectTrigger>
              <SelectContent>
                {plans.map((p) => {
                  const shortId = p.id.slice(0, 8);
                  return (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name || t`Plan ${shortId}`}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          ) : (
            <h2 className="truncate text-sm font-semibold">
              {activeMeta?.name || <Trans>Monthly plan</Trans>}
            </h2>
          )}
          {total > 0 && (
            <p className="text-xs tabular-nums text-muted-foreground">
              {periodLabel && <>{periodLabel} · </>}
              <Trans>{posted} of {total} posted</Trans>
              {missed > 0 && (
                <>
                  {" · "}
                  <span className="text-warning"><Plural value={missed} one="# missed" other="# missed" /></span>
                </>
              )}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view === PlanView.CALENDAR && (
            <Segmented
              value={calView}
              onChange={onCalViewChange}
              options={[{ key: "month", label: t`Month` }, { key: "week", label: t`Week` }]}
            />
          )}
          <ViewToggle view={view} onChange={onViewChange} />
          {!ended && (
            <>
              {/* Nothing covers today while a later plan is open: the gap
                  can still be planned. An ended plan offers it in its card. */}
              <PlanPeriodMenu options={newOptions} onPick={onStartPlan} icon={Plus} variant="outline">
                <Trans>New plan</Trans>
              </PlanPeriodMenu>
              <PlanPeriodMenu options={aheadOptions} onPick={onStartPlan} icon={CalendarPlus} variant="outline">
                <Trans>Plan ahead</Trans>
              </PlanPeriodMenu>
              <Button size="sm" className="h-8" onClick={onRevisePlan}>
                <PencilLine className="size-3.5" aria-hidden /> <Trans>Revise plan</Trans>
              </Button>
            </>
          )}
        </div>
      </div>

      {ended && (
        <PlanEnded
          end={selectedEnd}
          posted={posted}
          total={total}
          next={newOptions[0] || null}
          others={newOptions.slice(1)}
          current={current}
          onStartPlan={onStartPlan}
          onOpenCurrent={() => current && onSelectPlan(current.id)}
          className={fill ? "m-4 mb-0" : undefined}
        />
      )}

      {plan && (
        <PlanStrategy
          strategy={plan.strategy}
          days={plan.days}
          className={fill ? "border-b border-border/60 px-4 py-3" : ""}
        />
      )}

      {!plan ? (
        <div className="flex flex-1 items-center justify-center py-10 text-sm text-muted-foreground">
          <Trans>Loading plan…</Trans>
        </div>
      ) : view === PlanView.KANBAN ? (
        <PlanKanban plan={plan} postsById={postsById} onReviseDay={onReviseDay} scroll={scroll} today={today} />
      ) : view === PlanView.CALENDAR ? (
        <PlanCalendar plan={plan} postsById={postsById} view={calView} onViewChange={onCalViewChange} onReviseDay={onReviseDay} />
      ) : (
        <PlanList plan={plan} postsById={postsById} onReviseDay={onReviseDay} scroll={scroll} today={today} />
      )}
    </div>
  );
}

/**
 * A plan whose dates are behind us. It says so, counts what went out, and
 * leads with the next plan; when one already covers today, with that one.
 */
function PlanEnded({ end, posted, total, next, others, current, onStartPlan, onOpenCurrent, className }) {
  const { i18n } = useLingui();
  const ended = formatDate(end, { withYear: false, locale: i18n.locale });
  return (
    <Card variant="hero" className={cn("gap-4 @2xl:flex-row @2xl:items-center", className)}>
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-brand" aria-hidden>
        <CalendarCheck className="size-5" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-sm font-semibold">
          <Trans>This plan ended on {ended}.</Trans>
        </p>
        <p className="text-sm text-muted-foreground">
          {posted === 0 ? (
            <Trans>None of its {total} posts went out. The ideas are still below if you want them.</Trans>
          ) : (
            <Trans>{posted} of its {total} posts went out. The next plan learns from them.</Trans>
          )}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {current ? (
          <Button size="sm" onClick={onOpenCurrent}>
            <Trans>Open the current plan</Trans>
          </Button>
        ) : (
          next && (
            <>
              <Button size="sm" onClick={() => onStartPlan(next)}>
                <Plus className="size-3.5" aria-hidden /> <Trans>New plan · <PeriodName option={next} /></Trans>
              </Button>
              <PlanPeriodMenu options={others} onPick={onStartPlan} icon={CalendarPlus} variant="outline">
                <Trans>Another length</Trans>
              </PlanPeriodMenu>
            </>
          )
        )}
      </div>
    </Card>
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
  const { t } = useLingui();
  const options = [
    { key: PlanView.LIST, label: t`List`, Icon: List },
    { key: PlanView.KANBAN, label: t`Kanban`, Icon: LayoutGrid },
    { key: PlanView.CALENDAR, label: t`Calendar`, Icon: CalendarDays },
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
