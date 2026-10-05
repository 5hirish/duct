"use client";

// The Plan tab before the first plan, and the first thing Content Studio
// shows anyone, because Plan is its opening tab.
//
// It replaces "No plan yet" with what Duct already knows (the DeskDayOne
// argument: information beats a picture). Three things decide how good a
// plan is — the brand's voice, its pillars, its accounts' own results — and
// most projects already have one or two of them from the audit. Showing
// those back, by name, does two jobs: it proves the plan will be about this
// brand rather than a template, and it turns "set up a content plan" into
// "you are most of the way there". Nothing here is a gate: the agent asks
// for a missing voice or pillars itself, so the button always works.
//
// The sample on the right is the real PlanList over a labelled example week,
// so what someone is promised is drawn by the component they will get.

import { useMemo } from "react";
import { CalendarPlus, Check } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { Button } from "@/components/ui/button";
import { ClampText } from "@/components/ui/clamp-text";
import { ExampleFrame } from "@/components/ui/empty-state";
import { PostStatus, PostType } from "@/lib/contentEnums";
import { cn } from "@/lib/utils";
import { PlatformGlyph, platformMeta } from "./platformGlyphs";
import PlanList from "./PlanList";

// Where each missing source is fixed: the Content Studio tab ids.
export const PlanSourceTab = Object.freeze({ BRAND: "brand", ACCOUNTS: "accounts" });

// How many pillars and accounts to name before "+N". Past this the card
// stops being a glance.
const SHOWN_PILLARS = 5;
const SHOWN_ACCOUNTS = 3;

// One week of somebody else's plan: a freelancer budgeting app, the same
// brand the product screenshots use. Two posted, one drafted, two to go, so
// the sample shows where a plan goes after today and not only its first day.
const SAMPLE_DAYS = [
  { topic: msg`What a freelancer's September actually costs`, pillar: msg`Money habits`, objective: msg`Saves`, post_type: PostType.SLIDESHOW, status: PostStatus.POSTED, platforms: ["tiktok", "instagram"] },
  { topic: msg`Late-paying client? Say this, word for word.`, pillar: msg`Invoicing`, objective: msg`Follows`, post_type: PostType.VIDEO, status: PostStatus.POSTED, platforms: ["tiktok", "youtube"] },
  { topic: msg`The 12% rule for tax money`, pillar: msg`Tax without fear`, objective: msg`Saves`, post_type: PostType.SLIDESHOW, status: PostStatus.DRAFT, platforms: ["tiktok", "instagram"] },
  { topic: msg`Net 30 is a choice, not a law`, pillar: msg`Invoicing`, objective: msg`Shares`, post_type: PostType.IMAGE, status: PostStatus.PENDING, platforms: ["instagram"] },
  { topic: msg`Why we rebuilt onboarding from scratch`, pillar: msg`Behind the app`, objective: msg`Clicks`, post_type: PostType.VIDEO, status: PostStatus.PENDING, platforms: ["tiktok", "youtube"] },
];
// The sample starts two days ago, so its posted rows sit in the past and
// its draft lands on today.
const SAMPLE_DAYS_AGO = 2;

/**
 * Props:
 *   - brand: GET /content/brand, or null when it could not be read (the
 *     checklist is left out rather than claiming nothing is set)
 *   - accounts: linked social accounts, or null when unknown
 *   - onStart(): open a plan session
 *   - onOpenTab(tab): go to the Content Studio tab that fixes a source
 */
export default function PlanDayOne({ brand, accounts, onStart, onOpenTab }) {
  const { t, i18n } = useLingui();

  const sample = useMemo(() => {
    const now = new Date();
    return {
      start_date: new Date(now.getFullYear(), now.getMonth(), now.getDate() - SAMPLE_DAYS_AGO),
      days: SAMPLE_DAYS.map((d) => ({
        ...d,
        topic: i18n._(d.topic),
        pillar: i18n._(d.pillar),
        objective: i18n._(d.objective),
      })),
    };
  }, [i18n, i18n.locale]);

  return (
    <div className="@container flex flex-col gap-8 pb-6">
      <div className="flex flex-col items-start gap-4">
        <div>
          <h2 className="text-2xl font-bold leading-tight tracking-tight">
            <Trans>Your next 30 days of posts, planned in about three minutes.</Trans>
          </h2>
          <p className="measure mt-2 text-sm leading-relaxed text-muted-foreground">
            <Trans>
              Duct reads your brand, your pillars and what has already worked, then lays out a
              month of posts with a reason for each one. You draft them one at a time, and
              nothing goes out without your yes.
            </Trans>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button size="lg" onClick={onStart}>
            <CalendarPlus aria-hidden /> <Trans>Plan the next 30 days</Trans>
          </Button>
          <span className="text-xs text-muted-foreground">
            <Trans>You can change or drop any day after.</Trans>
          </span>
        </div>
      </div>

      <div className="grid items-start gap-6 @3xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {brand && <Sources brand={brand} accounts={accounts} onOpenTab={onOpenTab} />}

        <section className="flex min-w-0 flex-col gap-3">
          <div>
            <h3 className="text-sm font-semibold"><Trans>What you get</Trans></h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              <Trans>
                Every post dated, with its pillar and what it is for. Open one and Duct drafts it
                with you.
              </Trans>
            </p>
          </div>
          <ExampleFrame label={t`Example`}>
            <div className="overflow-hidden rounded-lg border bg-background">
              <PlanList plan={sample} />
            </div>
          </ExampleFrame>
        </section>
      </div>
    </div>
  );
}

function Sources({ brand, accounts, onOpenTab }) {
  const cb = brand.content_brand || {};
  const voice = [cb.tone, cb.value_prop, brand.description].find((v) => typeof v === "string" && v.trim()) || "";
  const pillars = (Array.isArray(brand.content_pillars?.items) ? brand.content_pillars.items : [])
    .map((p) => (p?.name || "").trim())
    .filter(Boolean);
  const pillarCount = pillars.length;
  const linked = Array.isArray(accounts) ? accounts : [];
  const ready = [Boolean(voice), pillars.length > 0, linked.length > 0].filter(Boolean).length;
  const total = 3;

  return (
    <section className="flex flex-col rounded-xl border bg-card p-5">
      <header className="mb-4 flex items-baseline gap-2">
        <h3 className="text-sm font-semibold"><Trans>What Duct plans from</Trans></h3>
        {/* A count is encouragement only once it has started: "0 of 3"
            reads as a to-do list in front of a button that needs none of it. */}
        {ready > 0 && (
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">
            <Trans>{ready} of {total} ready</Trans>
          </span>
        )}
      </header>

      <ul className="flex flex-col gap-4">
        <Source done={Boolean(voice)} title={<Trans>Brand voice</Trans>}>
          {voice ? (
            <ClampText text={voice} lines={2} className="text-xs text-muted-foreground" />
          ) : (
            <Missing
              text={<Trans>Not set. Duct asks you a question or two before it plans.</Trans>}
              action={<Trans>Describe your brand</Trans>}
              onClick={() => onOpenTab?.(PlanSourceTab.BRAND)}
            />
          )}
        </Source>

        <Source
          done={pillars.length > 0}
          title={pillars.length > 0
            ? <Plural value={pillarCount} one="# content pillar" other="# content pillars" />
            : <Trans>Content pillars</Trans>}
        >
          {pillars.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {pillars.slice(0, SHOWN_PILLARS).map((name) => (
                <span key={name} className="rounded-full bg-primary/10 px-2 py-0.5 text-2xs font-medium text-primary">
                  {name}
                </span>
              ))}
              {pillars.length > SHOWN_PILLARS && (
                <span className="px-1 py-0.5 text-2xs text-muted-foreground">+{pillars.length - SHOWN_PILLARS}</span>
              )}
            </div>
          ) : (
            <Missing
              text={<Trans>None yet. Duct asks what you want to be known for.</Trans>}
              action={<Trans>Add pillars</Trans>}
              onClick={() => onOpenTab?.(PlanSourceTab.BRAND)}
            />
          )}
        </Source>

        <Source done={linked.length > 0} title={<Trans>Your accounts</Trans>}>
          {linked.length > 0 ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              {linked.slice(0, SHOWN_ACCOUNTS).map((a) => {
                const meta = platformMeta(a.platform);
                return (
                  <span key={`${a.platform}:${a.account_id}`} className="inline-flex min-w-0 items-center gap-1.5 text-xs">
                    <span
                      title={meta.label}
                      className="flex size-4.5 shrink-0 items-center justify-center rounded-md text-white"
                      style={{ backgroundColor: meta.color }}
                    >
                      <PlatformGlyph platform={a.platform} className="size-2.5" />
                    </span>
                    <span className="truncate">@{a.username}</span>
                  </span>
                );
              })}
              {linked.length > SHOWN_ACCOUNTS && (
                <span className="text-2xs text-muted-foreground">+{linked.length - SHOWN_ACCOUNTS}</span>
              )}
            </div>
          ) : (
            <Missing
              text={<Trans>Optional. Link one and the plan learns from your own results and posting times.</Trans>}
              action={<Trans>Link an account</Trans>}
              onClick={() => onOpenTab?.(PlanSourceTab.ACCOUNTS)}
            />
          )}
        </Source>
      </ul>
    </section>
  );
}

function Source({ done, title, children }) {
  return (
    <li className="grid grid-cols-[1.125rem_minmax(0,1fr)] items-start gap-3">
      <span
        className={cn(
          "mt-px flex size-4.5 items-center justify-center rounded-full",
          done ? "bg-success/20" : "border-[1.5px] border-dashed border-border"
        )}
      >
        {done && <Check className="size-2.5 text-success" strokeWidth={3.5} aria-hidden />}
        <span className="sr-only">{done ? <Trans>Ready</Trans> : <Trans>Not set</Trans>}</span>
      </span>
      <div className="min-w-0 space-y-1.5">
        <p className="text-sm font-medium leading-snug">{title}</p>
        {children}
      </div>
    </li>
  );
}

function Missing({ text, action, onClick }) {
  return (
    <div className="space-y-2">
      <p className="text-xs leading-relaxed text-muted-foreground">{text}</p>
      <Button size="xs" variant="outline" onClick={onClick}>{action}</Button>
    </div>
  );
}
