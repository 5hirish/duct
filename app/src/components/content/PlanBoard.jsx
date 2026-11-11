"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutGrid, CalendarDays, CalendarCheck, CalendarPlus, GitBranch, List, PencilLine, Plus } from "lucide-react";
import { Trans, useLingui } from "@lingui/react/macro";
import {
  VENDOR,
  connectVendorKey,
  getBrandContext,
  getPlan,
  getVendorKeyStatus,
  listPublishers,
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
import PlanProgress from "@/components/content/PlanProgress";
import PlanPicker from "@/components/content/PlanPicker";
import { planDisplayName } from "@/lib/planStrategy";
import PlanDayOne from "@/components/content/PlanDayOne";
import FeedPlanDialog from "@/components/content/FeedPlanDialog";
import { feedSessionHref } from "@/lib/contentFeed";
import { feedScheduleBody } from "@/lib/schedules";
import { createSchedule } from "@/lib/schedulesApi";
import {
  PlanState,
  dayKey,
  nextPlanStart,
  onChannel,
  planChannels,
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
import { PlatformGlyph, platformMeta } from "@/components/content/platformGlyphs";

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

/** The board's view, remembered per browser; the list until a choice is read back. */
function usePlanView() {
  const [view, setViewState] = useState(PlanView.LIST);
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
  return [view, setView];
}

/**
 * Where drafting a day goes: the post workspace, carrying the plan, the day
 * and the day's first channel, which is the channel it was made for.
 */
export function draftDayHref(plan, index) {
  const day = Array.isArray(plan?.days) ? plan.days[index] : null;
  const channel = (Array.isArray(day?.platforms) && day.platforms[0]) || "tiktok";
  const params = new URLSearchParams();
  if (plan?.id) params.set("plan_id", plan.id);
  params.set("day", String(index));
  params.set("channel", channel);
  return `/content/posts/new?${params.toString()}`;
}

/**
 * What the first-run screen shows back for a project with no plan: its
 * brand, linked accounts, whether a scheduler is connected, and the Apify
 * key. Each read may fail on its own; null is "could not tell".
 */
async function loadFirstRunSources(projectId) {
  const [brand, accounts, publishers, apify] = await Promise.all([
    getBrandContext(projectId).catch(() => null),
    listLinkedAccounts(projectId).catch(() => null),
    listPublishers(projectId).catch(() => null),
    getVendorKeyStatus(VENDOR.APIFY, projectId).catch(() => null),
  ]);
  // Any scheduler connected is enough: which one is the Accounts tab's question.
  const scheduler = publishers ? { connected: publishers.some((p) => p.connected) } : null;
  return { brand, accounts, scheduler, vendors: { [VENDOR.APIFY]: apify } };
}

/**
 * The plan board: loads the project's plans and hands them to PlanBoardView.
 * Content Studio's Plans tab and the full-bleed /content/plan route both use
 * it. Pass `initialPlanId` to preselect (e.g. from a query param). Before the first plan
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
  const [view, setView] = usePlanView();
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
          const found = await loadFirstRunSources(projectId);
          if (cancelled) return;
          setSources(found);
        }
        setPlans(list);
        // The plan for today's period first.
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
  // A plan from shipped work (#561) starts at its setup sheet.
  const [feedOpen, setFeedOpen] = useState(false);
  const openFeed = useCallback(() => setFeedOpen(true), []);
  // The Scheduled page's empty state links here with ?from=work, so the sheet
  // that holds Repeat weekly is one click away rather than three.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("from") === "work") setFeedOpen(true);
  }, []);
  const feedDialog = feedOpen && (
    <FeedPlanDialog
      open
      onOpenChange={setFeedOpen}
      onStart={(options) => { setFeedOpen(false); router.push(feedSessionHref(options, today)); }}
      onRepeat={async (options, cadence) => {
        // Saved as a Monday 09:00 schedule in the reader's zone (#562), or one
        // that runs on each GitHub release (#563); the Scheduled page is where
        // it is paused, run or deleted.
        await createSchedule(feedScheduleBody(projectId, options, { cadence }));
        setFeedOpen(false);
        router.push("/scheduled");
      }}
    />
  );

  // A key pasted into the first-run checklist. The save answers with the new
  // status, so the row turns over without a second read; a refusal throws
  // and the field shows the vendor's reason.
  const connectVendor = useCallback(async (vendor, apiKey) => {
    const status = await connectVendorKey(vendor, apiKey);
    setSources((prev) => ({ ...prev, vendors: { ...prev.vendors, [vendor]: status } }));
  }, []);

  // Pending card → open the creation split-view, carrying the day's primary channel.
  const reviseDay = useCallback(
    (index) => router.push(draftDayHref({ ...plan, id: activeId }, index)),
    [plan, activeId, router]
  );

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
      <>
      {feedDialog}
      <PlanDayOne
        brand={sources.brand}
        accounts={sources.accounts}
        scheduler={sources.scheduler}
        vendors={sources.vendors}
        onConnectVendor={connectVendor}
        onStart={startPlan}
        onPlanFromWork={openFeed}
        onOpenTab={onOpenTab || ((tab) => router.push(`/content?tab=${tab}`))}
      />
      </>
    );
  }

  return (
    <>
    {feedDialog}
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
      onPlanFromWork={openFeed}
      fill={fill}
    />
    </>
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
  onPlanFromWork,
  fill = false,
  defaultChannel = null,
  pickerOpen = false,
}) {
  const { t, i18n } = useLingui();
  const activeMeta = plans.find((p) => p.id === activeId) || plan || null;
  // One channel at a time, or every one: the same filter drives the three
  // views and the header's count, so what the bar says is what is listed.
  const [channel, setChannel] = useState(defaultChannel);
  const allItems = useMemo(
    () => planItems(plan, postsById, { locale: i18n.locale, today }),
    [plan, postsById, i18n.locale, today]
  );
  const channels = useMemo(() => planChannels(allItems), [allItems]);
  const picked = channels.some((c) => c.channel === channel) ? channel : null;
  const items = useMemo(() => allItems.filter((it) => onChannel(it, picked)), [allItems, picked]);
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
            // The plan's name is the board's title, and the way to every other plan.
            <PlanPicker plans={plans} value={activeId} onChange={onSelectPlan} today={today} defaultOpen={pickerOpen} />
          ) : (
            <h2 className="truncate text-sm font-semibold">
              {planDisplayName(activeMeta?.name) || <Trans>Monthly plan</Trans>}
            </h2>
          )}
          {total > 0 && <PlanProgress period={periodLabel} progress={progress} ended={ended} />}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {channels.length > 1 && <ChannelFilter channels={channels} value={picked} onChange={setChannel} />}
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
              {onPlanFromWork && (
                <Button size="sm" variant="outline" className="h-8" onClick={onPlanFromWork}>
                  <GitBranch className="size-3.5" aria-hidden /> <Trans>From your work</Trans>
                </Button>
              )}
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
        <PlanStrategy strategy={plan.strategy} days={plan.days} channel={picked} variant={fill ? "strip" : "card"} />
      )}

      {!plan ? (
        <div className="flex flex-1 items-center justify-center py-10 text-sm text-muted-foreground">
          <Trans>Loading plan…</Trans>
        </div>
      ) : view === PlanView.KANBAN ? (
        <PlanKanban plan={plan} postsById={postsById} onReviseDay={onReviseDay} scroll={scroll} today={today} channel={picked} />
      ) : view === PlanView.CALENDAR ? (
        <PlanCalendar plan={plan} postsById={postsById} view={calView} onViewChange={onCalViewChange} onReviseDay={onReviseDay} channel={picked} />
      ) : (
        <PlanList plan={plan} postsById={postsById} onReviseDay={onReviseDay} scroll={scroll} today={today} channel={picked} />
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


/**
 * Every channel the plan's days are on, as glyph chips with counts, and
 * "All". A filter, so it stays neutral when chosen: the brand orange is the
 * board's one primary action. Hidden with a single channel, where it would
 * only say what every row already shows.
 */
function ChannelFilter({ channels, value, onChange }) {
  const { t } = useLingui();
  const chip = (active) =>
    cn(
      "inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-colors",
      active ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"
    );
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t`Channel`}>
      <button type="button" aria-pressed={value === null} onClick={() => onChange(null)} className={chip(value === null)}>
        <Trans>All</Trans>
      </button>
      {channels.map(({ channel, count }) => {
        const label = platformMeta(channel).label;
        const active = value === channel;
        return (
          <button
            key={channel}
            type="button"
            aria-pressed={active}
            aria-label={t`${label}, ${count} posts`}
            title={label}
            onClick={() => onChange(active ? null : channel)}
            className={chip(active)}
          >
            <PlatformGlyph platform={channel} className="size-3.5" />
            <span className="tabular-nums">{count}</span>
          </button>
        );
      })}
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
