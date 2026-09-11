"use client";

// What the preview route renders.
//
// One entry per state worth looking at — including the ones nobody opens by
// accident, which is where layouts actually break: a partial grant, a name
// long enough to wrap, an empty list, a failed fetch. Adding a state here is
// how it gets reviewed; a component whose only scene is the happy path is a
// component whose other states have never been seen.
//
// Scenes import the real components and pass real props. Nothing here
// reconstructs markup.
//
// Shape: `{ id, group, title, state, note, render }`. `id` is the URL handle —
// /preview/frame?scene=<id>&surface=<surface>&theme=dark — so every state is
// addressable without clicking anything. `state` says which conditions the
// scene covers, so "did anyone look at the error case" is answerable by
// reading the list.

import { useEffect, useMemo, useState } from "react";

import ContextCompressionCard from "@/components/ContextCompressionCard.jsx";
import Desk from "@/components/insights/Desk";
import DeskComposer from "@/components/insights/desk/DeskComposer";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { CornerNotice } from "@/components/ui/corner-notice";
import { FolderOpen, RefreshCw } from "lucide-react";
import { CookieConsent } from "@/components/CookieConsent";
import LoadError from "@/components/LoadError";
import DeskCards from "@/components/insights/desk/DeskCards";
import DeskActivity from "@/components/insights/desk/DeskActivity";
import { NEEDS_YOU, FOUND, IN_PROGRESS } from "@/lib/desk";
import ConnectorDialog from "@/components/connections/ConnectorDialog";
import ConnectorPermissions from "@/components/connections/ConnectorPermissions";
import ConnectorTile from "@/components/connections/ConnectorTile";
import EntityAvatar from "@/components/connections/EntityAvatar";
import ProjectEntitySelect from "@/components/connections/ProjectEntitySelect";
import StorageBadge from "@/components/connections/StorageBadge";
import ContextRing from "@/components/workspace/ContextRing";
import { Button } from "@/components/ui/button";
import {
  STORAGE_CLOUD,
  STORAGE_KEYCHAIN,
  STORAGE_LOCAL,
  STORAGE_NONE,
  STORAGE_SESSION,
} from "@/lib/credentialStorage";

const LOGO = (
  <span
    aria-hidden="true"
    style={{ width: 24, height: 24, borderRadius: 6, background: "var(--muted-foreground)", opacity: 0.35, display: "block" }}
  />
);

/** Shaped exactly like `service/connector_scopes.py::scope_rows` returns. */
const GTM_SCOPES = [
  {
    scope: "tagmanager.readonly",
    label: "Tag Manager",
    why: "Reads containers, tags, triggers and variables to see how measurement is wired.",
    access: "read",
    required: true,
    granted: true,
  },
  {
    scope: "tagmanager.edit.containers",
    label: "Tag Manager drafts",
    why: "Stages measurement fixes in a container version. Staged only — nothing reaches your site until it is published.",
    access: "write",
    required: false,
    granted: true,
  },
  {
    scope: "tagmanager.publish",
    label: "Tag Manager publishing",
    why: "Publishes a staged container version once you approve it, and is what makes a one-click rollback possible.",
    access: "write",
    required: false,
    granted: false,
  },
];

const GSC_SCOPES = [
  {
    scope: "webmasters.readonly",
    label: "Search Console",
    why: "Reads queries, pages, clicks, impressions and average position. Read-only: Duct cannot change anything in Search Console.",
    access: "read",
    required: true,
    granted: true,
  },
];

/** Shaped exactly like an adapter's `list_accounts` rows. */
const GSC_ENTITIES = [
  {
    account_id: "sc-domain:daspire.com",
    account_name: "daspire.com",
    entity_url: "https://daspire.com",
    entity_detail: "Domain property",
    entity_meta: [{ label: "Access", value: "Owner" }],
  },
  {
    account_id: "https://designsense.ai/",
    account_name: "designsense.ai",
    entity_url: "https://designsense.ai/",
    entity_detail: "URL prefix",
    entity_meta: [{ label: "Access", value: "Full access" }],
  },
  {
    account_id: "act_1234567890",
    account_name: "Acme Ads — Europe, Middle East and Africa",
    entity_detail: "Acme Holdings Business",
    entity_meta: [
      { label: "Currency", value: "EUR" },
      { label: "Timezone", value: "Europe/Dublin" },
    ],
  },
  { account_id: "properties/449182773", account_name: "Website — GA4" },
];

const stubLoader = (payload, { delayMs = 0, fail = "" } = {}) =>
  async function load() {
    if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
    if (fail) throw new Error(fail);
    return payload;
  };

const NOUNS = { entity_noun: "property", entity_noun_plural: "properties" };

/** A dialog has to be opened to be looked at; this is the trigger. */
function DialogScene({ label, ...props }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <ConnectorDialog open={open} onOpenChange={setOpen} {...props} />
    </>
  );
}

function Row({ children }) {
  return <div className="flex flex-wrap items-center gap-4">{children}</div>;
}

/** Autonomy is controlled from the parent in the real Desk — stub that here
 *  so picking an option actually round-trips back into the trigger's label. */
function DeskComposerScene(props) {
  const [autonomy, setAutonomy] = useState(AUTONOMY_ASK);
  return <DeskComposer {...props} autonomy={autonomy} onAutonomyChange={setAutonomy} />;
}

// Long titles on purpose — an agent wrote these, not someone picking a label
// short enough to fit. This is the case that revealed DeskCards had no
// line-clamp: a single item could run the card to nine lines and shove its
// siblings off the bottom.
const LONG_TITLE =
  "North-star window: Next 90 days: get net new MRR positive and keep it there. Measured 30-day position — $219.95 of new MRR against $297.86 lost to failed payments plus $209.88 sitting past-due, so the window is still net negative.";

const DESK_BUCKETS = {
  [NEEDS_YOU]: [
    { id: "n1", title: "Audit our Google Search performance please.", detail: "Pick up where you left off", tone: "attention", at: "2026-09-09T06:00:00Z" },
  ],
  [FOUND]: [
    { id: "f1", title: "Next growth milestone: 3_repeatable_growth", detail: "Checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
    { id: "f2", title: LONG_TITLE, detail: "Checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
    { id: "f3", title: "North-star metric: Net new revenue", detail: "Checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
  ],
  [IN_PROGRESS]: [
    { id: "p1", title: "Audit our Google Search performance please.", detail: "Working", tone: "running", at: "2026-09-09T06:00:00Z" },
    { id: "p2", title: "Audit our Google Search performance please.", detail: "Working", tone: "running", at: "2026-09-09T06:00:00Z" },
  ],
};
const DESK_BUCKETS_SHAPED = { needsYou: DESK_BUCKETS[NEEDS_YOU], found: DESK_BUCKETS[FOUND], inProgress: DESK_BUCKETS[IN_PROGRESS] };

const DESK_ACTIVITY = [
  { id: "a1", category: "check", action: "checked_search_console", summary: LONG_TITLE, source: "auto", created_at: "2026-09-09T05:57:00Z" },
  { id: "a2", category: "sync", action: "synced_ga4", summary: "", source: "agent", created_at: "2026-09-09T05:40:00Z" },
  { id: "a3", category: "change", action: "applied_change", summary: "Applied: pause 3 underperforming ad groups", source: "agent", created_at: "2026-09-08T18:12:00Z" },
];

// Delayed on purpose: after the first paint, dispatch `visibilitychange` in
// the frame and confirm the desk stays visible while this re-read is pending.
const PREVIEW_DESK_DATA = {
  memories: [],
  conversations: [
    {
      id: "preview-thread",
      status: "active",
      run_status: "running",
      title: "Check our Google Search performance",
      created_at: "2026-09-09T06:00:00Z",
      last_active_at: "2026-09-09T06:00:00Z",
      last_seq: 4,
    },
  ],
  artifacts: [],
  activity: DESK_ACTIVITY,
  changeSets: [],
  sourceCount: 2,
};
const loadPreviewDesk = stubLoader(PREVIEW_DESK_DATA, { delayMs: 500 });

// The same desk as it was a moment ago, which is what an overtaken load is
// carrying: a thread that has since finished, still saying "Working…".
const PREVIEW_DESK_STALE = {
  ...PREVIEW_DESK_DATA,
  activity: [],
  conversations: [
    { ...PREVIEW_DESK_DATA.conversations[0], title: "Stale answer — the desk must never show this" },
  ],
};

/** Answers out of order on purpose: slow first, fast afterwards. */
function racingLoader() {
  let asked = 0;
  return async function load() {
    asked += 1;
    const first = asked === 1;
    await new Promise((r) => setTimeout(r, first ? 1500 : 150));
    return first ? PREVIEW_DESK_STALE : PREVIEW_DESK_DATA;
  };
}

/**
 * The race, driven for you.
 *
 * The overtaking refresh has to be issued while the first load is still in
 * flight, and a second and a half is not a window anyone hits from a console —
 * so the scene fires it rather than asking for it. `useMemo` rather than module
 * scope: the loader must keep one identity for as long as the desk is mounted
 * (it is a dependency of the desk's refresh, and a new one every render would
 * restart the load forever), and must start over on the next mount, or the
 * scene works once per page load and shows a finished desk ever after.
 */
function DeskRaceScene() {
  const load = useMemo(racingLoader, []);
  useEffect(() => {
    const t = setTimeout(() => document.dispatchEvent(new Event("visibilitychange")), 300);
    return () => clearTimeout(t);
  }, []);
  return <Desk projectIdOverride="preview" loadDeskFn={load} />;
}

export const SCENES = [
  {
    id: "desk-composer",
    state: "default — a project with a favicon, no thread yet",
    group: "DeskComposer",
    title: "The insights composer",
    note: "Both Selects here use a custom chip as the trigger's content instead of SelectValue, which is why they're pinned to position=\"popper\" rather than the shadcn default (\"item-aligned\"): item-aligned aligns the selected SelectItem over the trigger by locating it through SelectValue, and silently renders off-screen with nothing to find. Check that both open in place and that picking an option updates the chip's label. Also check the send button's loading spinner and the amber \"no provider connected\" notice (type something, then use the browser's devtools to force a 401 on /api/providers/status) — the notice must not clear the draft.",
    render: () => (
      <DeskComposerScene
        project={{ id: "p1", name: "Sictec Infotech, Inc.", company: { name: "Sictec Infotech, Inc.", website_url: "https://sictec.example" } }}
        placeholder="Ask about &ldquo;Next growth milestone&rdquo; — or anything else"
      />
    ),
  },
  {
    id: "project-drafted-notice",
    state: "an audit added to a project that already existed",
    group: "AuditWorkspace",
    title: "Duct changed a project you already had",
    note: "Onboarding writes what the crawl learned into a project, and when that project is one the user already had, the write happens in the background while they read the report. This is the only thing telling them. Check that the copy leads with reassurance rather than alarm — nothing has gone wrong, and the merge rules mean nothing they typed was touched — and that a long project name still leaves the title on two lines at most.",
    render: () => (
      <CornerNotice
        icon={FolderOpen}
        title="Added to your Northwind Trading — EMEA marketing site project"
        onDismiss={() => {}}
        dismissLabel="Dismiss project update"
        actions={
          <Button size="sm" variant="outline">Review what changed</Button>
        }
      >
        <p className="mt-0.5 text-xs text-muted-foreground">
          Duct filled in what it learned from your site. Anything you had entered yourself was left
          alone, and every drafted field is marked.
        </p>
      </CornerNotice>
    ),
  },
  {
    id: "reload-notice",
    state: "new build available",
    group: "ReloadToast",
    title: "A new web build is ready",
    note: "ReloadToast mounts itself off a version poll, so it is unreachable in dev (no baked build id) — this is its body in the real primitive. Check that the copy names what a reload costs: this app holds long agent runs and unsent input, so 'refresh for the latest' would be true and would still lose someone's work. The `notification` surface positions it; here it is inline so the text can be measured.",
    render: () => (
      <CornerNotice
        icon={RefreshCw}
        title="A new version of Duct is ready"
        onDismiss={() => {}}
        actions={
          <>
            <Button size="sm">Reload</Button>
            <Button size="sm" variant="ghost">Later</Button>
          </>
        }
      >
        <p className="mt-0.5 text-xs text-muted-foreground">
          This tab is running an older build. Reloading picks up the new one — finish anything
          you have in progress first, it will not wait for you.
        </p>
      </CornerNotice>
    ),
  },
  {
    id: "context-compression",
    state: "on (default) — toggle for off",
    group: "ContextCompressionCard",
    title: "Context compression",
    note: "Both descriptions have to read as a real choice, so click the switch: off must say what the user loses, not just that a feature is off. Watch the card height across the two — the off copy is a line longer, and a card that jumps as you toggle it reads as a glitch. It is the only card in its section, so it takes the content width rather than a conn-grid track — a lone 288px card on a wide page reads as a leftover.",
    render: () => <ContextCompressionCard />,
  },
  {
    id: "cookie-consent",
    state: "asking",
    group: "CookieConsent",
    title: "The consent question",
    note: "Decline and Accept are the same control at the same size — a Decline styled as a text link is the specific thing the AEPD treats as no consent at all. Check the mobile width: the two buttons stay side by side and equal, they do not stack with Accept on top.",
    render: () => <CookieConsent onAccept={() => {}} onDecline={() => {}} />,
  },
  {
    id: "load-error",
    state: "failed",
    group: "LoadError",
    title: "A panel whose data did not arrive",
    note: "The state that used to be a red string where the empty state's invitation belongs. Retryable and not: the second has no way back because its caller reloads on its own.",
    render: () => (
      <div style={{ display: "grid", gap: 4 }}>
        <LoadError
          what="the execution queue"
          detail="User not found"
          onRetry={() => {}}
        />
        <LoadError what="your artifacts" detail="" />
      </div>
    ),
  },
  {
    id: "tile-states",
    state: "all states",
    group: "ConnectorTile",
    title: "Every state",
    note: "Connected, partial grant, session-only, not connected, and disabled. The foot is the part that breaks: state left, storage right.",
    render: () => (
      <div className="conn-grid">
        <ConnectorTile
          logo={LOGO}
          title="Google Search Console"
          description="Organic search queries, clicks, impressions, and average position data for SEO reporting."
          tone="on"
          status="Connected"
          storage={STORAGE_CLOUD}
          onClick={() => {}}
        />
        <ConnectorTile
          logo={LOGO}
          title="Google Ads"
          description="Campaign spend, conversions and search terms."
          tone="partial"
          status="Some permissions declined"
          storage={STORAGE_SESSION}
          onClick={() => {}}
        />
        <ConnectorTile
          logo={LOGO}
          title="Stripe"
          description="Settled revenue, subscriptions, refunds and payment outcomes."
          tone="off"
          status="Not connected"
          storage={STORAGE_NONE}
          onClick={() => {}}
        />
        <ConnectorTile
          logo={LOGO}
          title="Microsoft Clarity — behavioural analytics for the whole account"
          description="A description long enough to reach the two-line clamp and prove the clamp is doing something."
          tone="on"
          status="Connected — a very long account name that has to truncate somewhere"
          storage={STORAGE_LOCAL}
          onClick={() => {}}
        />
        <ConnectorTile
          logo={LOGO}
          title="Product Intelligence"
          description="Not available yet."
          tone="off"
          status="Coming soon"
          disabled
        />
      </div>
    ),
  },
  {
    id: "storage-badge",
    state: "all states",
    group: "StorageBadge",
    title: "All four answers",
    note: "Hover or focus each: the tooltip stacks label over sentence. The session one is the only one that takes a colour.",
    render: () => (
      <Row>
        {[STORAGE_CLOUD, STORAGE_LOCAL, STORAGE_KEYCHAIN, STORAGE_SESSION, STORAGE_NONE].map((s) => (
          <span key={s} className="flex items-center gap-2 text-xs text-muted-foreground">
            <StorageBadge storage={s} />
            {s}
          </span>
        ))}
      </Row>
    ),
  },
  {
    id: "permissions",
    state: "success + partial + unknown",
    group: "ConnectorPermissions",
    title: "Complete, partial, unknown",
    note: "Grouped by access, so read and write never depend on a pill to be told apart. Only the exceptions are marked.",
    render: () => (
      <div className="flex flex-col gap-6">
        <ConnectorPermissions scopes={GSC_SCOPES} scopeStatus="complete" />
        <ConnectorPermissions scopes={GTM_SCOPES} scopeStatus="partial" />
        <ConnectorPermissions scopes={GSC_SCOPES} scopeStatus="unknown" />
      </div>
    ),
  },
  {
    id: "entity-avatar",
    state: "success + fallback",
    group: "EntityAvatar",
    title: "Favicon, and what happens without one",
    note: "A real origin, an origin with no favicon (falls back to the monogram), no URL at all, and a non-web id.",
    render: () => (
      <Row>
        <EntityAvatar url="https://github.com" name="github.com" />
        <EntityAvatar url="https://example.invalid" name="example.invalid" />
        <EntityAvatar name="Acme Holdings" />
        <EntityAvatar url="sc-domain:daspire.com" name="daspire.com" />
      </Row>
    ),
  },
  {
    id: "entity-picker-populated",
    state: "success",
    group: "ProjectEntitySelect",
    title: "Populated",
    note: "Open it. Rows carry a favicon, a disambiguating line and short fact chips — the long ad-account name is there to push the truncation.",
    render: () => (
      <ProjectEntitySelect
        projectName="DesignSense AI"
        credentialId="preview"
        noun="property"
        nounPlural="properties"
        binding={{ entity_id: "https://designsense.ai/", entity_name: "designsense.ai" }}
        onChange={() => {}}
        loadEntities={stubLoader({ entities: GSC_ENTITIES, supported: true, ...NOUNS })}
      />
    ),
  },
  {
    id: "entity-picker-edges",
    state: "loading + empty + error",
    group: "ProjectEntitySelect",
    title: "Loading, empty, unsupported, failed",
    note: "The four states a live API produces and a happy-path screenshot never shows.",
    render: () => (
      <div className="flex flex-col gap-5">
        <ProjectEntitySelect
          projectName="Slow"
          credentialId="p1"
          noun="property"
          nounPlural="properties"
          onChange={() => {}}
          loadEntities={stubLoader({ entities: GSC_ENTITIES, supported: true, ...NOUNS }, { delayMs: 30000 })}
        />
        <ProjectEntitySelect
          projectName="Empty"
          credentialId="p2"
          noun="property"
          nounPlural="properties"
          onChange={() => {}}
          loadEntities={stubLoader({ entities: [], supported: true, ...NOUNS })}
        />
        <ProjectEntitySelect
          projectName="Unsupported"
          credentialId="p3"
          noun="account"
          nounPlural="accounts"
          onChange={() => {}}
          loadEntities={stubLoader({ entities: [], supported: false })}
        />
        <ProjectEntitySelect
          projectName="Failed"
          credentialId="p4"
          noun="property"
          nounPlural="properties"
          onChange={() => {}}
          loadEntities={stubLoader(null, { fail: "Failed to decrypt credentials" })}
        />
      </div>
    ),
  },
  {
    id: "dialog",
    state: "success",
    group: "ConnectorDialog",
    title: "Connected, with footer actions",
    note: "Checks the thing that was wrong: no dead space under the description, and the actions sit at the bottom with the primary rightmost.",
    render: () => (
      <DialogScene
        label="Open connected dialog"
        logo={LOGO}
        title="Google Search Console"
        description="Organic search queries, clicks, impressions, and average position data for SEO reporting."
        status={
          <span className="conn-state">
            <span className="conn-state-glyph">
              <span className="conn-dot conn-dot--on" role="img" aria-label="Connected" />
            </span>
            <StorageBadge storage={STORAGE_CLOUD} />
          </span>
        }
        footer={
          <>
            <Button size="sm" variant="destructive">
              Disconnect
            </Button>
            <Button size="sm" variant="secondary">
              Reconnect
            </Button>
          </>
        }
      >
        <ConnectorPermissions scopes={GSC_SCOPES} scopeStatus="complete" />
        <div className="conn-dialog-section">
          <h4 className="conn-dialog-heading">Use for DesignSense AI</h4>
          <ProjectEntitySelect
            projectName="DesignSense AI"
            credentialId="preview"
            noun="property"
            nounPlural="properties"
            onChange={() => {}}
            loadEntities={stubLoader({ entities: GSC_ENTITIES, supported: true, ...NOUNS })}
          />
        </div>
      </DialogScene>
    ),
  },
  {
    id: "desk-cards-long-title",
    state: "content",
    group: "Desk",
    title: "Cards, an agent-length finding title",
    note: "Drag the frame through the 448–768px band: three columns to two to one. The long title in “What I found” clamps to two lines instead of pushing its siblings out — hover or tab to it for the rest.",
    render: () => <DeskCards buckets={DESK_BUCKETS_SHAPED} />,
  },
  {
    id: "desk-background-refresh",
    state: "a working thread, then a focus refresh",
    group: "Desk",
    title: "Desk stays put while it re-reads",
    note: "Wait for the desk to load, then dispatch a visible `visibilitychange` event. The five-hundred-millisecond stub mimics the refresh: the existing desk must remain on screen rather than returning to its loading skeleton.",
    render: () => <Desk projectIdOverride="preview" loadDeskFn={loadPreviewDesk} />,
  },
  {
    id: "desk-stale-answer-dropped",
    state: "two loads in flight, the older one answering last",
    group: "Desk",
    title: "Desk drops an answer it has outrun",
    note: "Nothing to click — watch the first two seconds. The scene issues a background refresh 300ms in, while the first load is still out, and that refresh answers ten times faster: the desk paints from the newer answer, and the skeleton comes down with it even though the load that raised it is still pending. Then keep watching. The older answer lands at a second and a half carrying a desk marked stale, and must change nothing on screen. If “Stale answer” ever appears, ordering has stopped being enforced and the desk can be overwritten by whatever it was told a moment ago. React's dev double-mount replays the race, so the first paint can beat the 300ms mark — the ending is what this is for.",
    render: () => <DeskRaceScene />,
  },
  {
    id: "desk-activity-long-summary",
    state: "content",
    group: "Desk",
    title: "Activity rail, a long entry",
    note: "The right rail from the Organic Growth desk. It sizes off its own column, not the window — this scene is deliberately narrow to prove that.",
    render: () => (
      <div className="max-w-[288px]">
        <DeskActivity items={DESK_ACTIVITY} />
      </div>
    ),
  },
  {
    id: "context-ring-tones",
    state: "neutral · amber · destructive, each with usage details",
    group: "ContextRing",
    title: "Context ring, the three tones",
    note: "The gauge beside every agent workspace's status row. Tab or hover each ring for the tooltip's per-call and per-session usage — this is also where a stray local TooltipProvider used to show up as a delay that didn't match the rest of the app.",
    render: () => (
      <Row>
        {[
          { used: 0.32, tag: "neutral", cached: 41000 },
          { used: 0.79, tag: "amber", cached: 9000 },
          { used: 0.95, tag: "destructive", cached: 0 },
        ].map(({ used, tag, cached }) => (
          <ContextRing
            key={tag}
            used={used}
            details={{
              last: { window: 200000, input: Math.round(used * 200000 * 0.8), output: Math.round(used * 200000 * 0.2), cached, model: "claude-sonnet-5" },
              total: { input: 512000, output: 48000, cached: 180000, calls: 14, cost: 1.86 },
            }}
          />
        ))}
      </Row>
    ),
  },
  {
    id: "context-ring-stale",
    state: "just compacted — no live figure yet",
    group: "ContextRing",
    title: "Context ring, right after a compaction",
    note: "The last reading describes context that no longer exists. The ring reads empty and says so rather than showing a stale percentage; it fills again once the next call on the thread reports a real size.",
    render: () => (
      <Row>
        <ContextRing
          used={0.87}
          details={{ last: { window: 200000, input: 174000, output: 8200, stale: true, model: "claude-sonnet-5" }, total: { input: 512000, output: 48000, calls: 14 } }}
        />
        <span className="text-xs text-muted-foreground">No details prop — decorative only, as on a thread that hasn&rsquo;t started</span>
        <ContextRing used={0} />
      </Row>
    ),
  },
];
