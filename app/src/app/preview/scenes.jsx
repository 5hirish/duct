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
import FrontDoor from "@/components/onboarding/FrontDoor";
import Desk from "@/components/insights/Desk";
import DeskComposer from "@/components/insights/desk/DeskComposer";
import ComposerDials, { TierDial } from "@/components/workspace/ComposerDials";
import ChatInput from "@/components/workspace/ChatInput";
import { DropHint } from "@/components/workspace/Attachments";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { CornerNotice } from "@/components/ui/corner-notice";
import { FolderOpen, RefreshCw } from "lucide-react";
import { CookieConsent } from "@/components/CookieConsent";
import LoadError from "@/components/LoadError";
import CloneFromUrlDialog from "@/components/content/CloneFromUrlDialog";
import CloneSourceNote from "@/components/content/CloneSourceNote";
import DeskCards from "@/components/insights/desk/DeskCards";
import DeskActivity, { activityGridClass } from "@/components/insights/desk/DeskActivity";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import { ArtifactPaneHeader, BriefPane, DataPane, DocumentFocus } from "@/components/insights/InsightsWorkspace";
import { ActivityGroup, ActivityRow } from "@/components/workspace/ActivityRow";
import { activitiesFromEvents, contextActivity, dataSourceRollup } from "@/lib/toolActivity";
import { briefFile } from "@/lib/brief";
import { saveText } from "@/lib/download";
import { ArtifactGallery } from "@/components/artifacts/ArtifactCards";
import { NEEDS_YOU, FOUND, IN_PROGRESS } from "@/lib/desk";
import ConnectorDialog from "@/components/connections/ConnectorDialog";
import ConnectorPermissions from "@/components/connections/ConnectorPermissions";
import ConnectorTile from "@/components/connections/ConnectorTile";
import ProviderCard from "@/components/connections/ProviderCard";
import { LOGOS } from "@/components/connections/logos";
import { PROVIDERS } from "@/lib/providerKeys";
import EntityAvatar from "@/components/connections/EntityAvatar";
import ProjectEntitySelect from "@/components/connections/ProjectEntitySelect";
import StorageBadge from "@/components/connections/StorageBadge";
import ContextRing from "@/components/workspace/ContextRing";
import TierSummary from "@/components/models/TierSummary";
import TierCard from "@/components/models/TierCard";
import AdvancedSettings from "@/components/models/AdvancedSettings";
import { TelemetryPanel } from "@/components/TelemetryCard";
import ChangeSetCard from "@/components/execution/ChangeSetCard";
import AuditReportV1 from "@/components/audit/AuditReportV1";
import MemoryTimeline from "@/components/memory/MemoryTimeline";
import PlanKanban from "@/components/content/PlanKanban";
import SynthesisPanel from "@/components/content/SynthesisPanel";
import { MEMORY_KINDS } from "@/lib/memoryApi";
import { ANSWERS as STORY_ANSWERS, AUDIT_REPORT as STORY_AUDIT, CHANGE_SET as STORY_CHANGE_SET, CONNECTORS as STORY_CONNECTORS, MEMORIES as STORY_MEMORIES, PLAN as STORY_PLAN, POSTS as STORY_POSTS } from "@/lib/__fixtures__/solo-story.mjs";
import { TranscriptRow, WorkingIndicator } from "@/components/workspace/AgentChat";
import StepProgress from "@/components/workspace/StepProgress";
import { Row as ChatRow } from "@/lib/agentSession";
import { StepStatus } from "@/lib/agentSteps";
import VoiceSample from "@/components/profile/VoiceSample";
import { UsageEmpty } from "@/components/models/UsagePanel";
import { TIERS } from "@/lib/modelTiers";
import { Button } from "@/components/ui/button";
import { NotificationRow } from "@/components/AppSidebar";
import { LanguageMenuItem } from "@/components/LanguageMenu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

/** The front door owns its field, so give the scene somewhere to type. The
 *  `.landing-start` wrapper is not decoration: it carries `--start-ground`, and
 *  a panel written for that ground says nothing useful on `--background`. */
function FrontDoorScene({ error = "" }) {
  const [url, setUrl] = useState("");
  return (
    <div className="landing-start">
      <FrontDoor url={url} onUrlChange={setUrl} error={error} onSubmit={(e) => e.preventDefault()} />
    </div>
  );
}

/** Autonomy is controlled from the parent in the real Desk — stub that here
 *  so picking an option actually round-trips back into the trigger's label. */
function DialsScene() {
  const [autonomy, setAutonomy] = useState(AUTONOMY_ASK);
  return <ComposerDials projectId="p1" autonomy={autonomy} onAutonomyChange={setAutonomy} deferred />;
}

function DeskActivityCollapseScene() {
  const [collapsed, setCollapsed] = useState(true);
  return (
    <div className={`grid gap-y-8 ${activityGridClass(collapsed)}`}>
      <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">
        The content column. It takes the rail&rsquo;s width back when the rail folds, which is
        the whole point of the control — so this stand-in is here to be watched, not read.
      </div>
      <DeskActivity
        items={DESK_ACTIVITY}
        collapsed={collapsed}
        onToggle={() => setCollapsed((v) => !v)}
      />
    </div>
  );
}

// The whole right pane, wired: the tabs switch, the shelf button opens the
// gallery and a card there comes back to the document. Height is fixed
// because the real pane gets its height from the split, and every question
// worth asking here — does the document fill it, does it scroll itself, does
// the header stay put — is a question about that height.
function ArtifactPaneScene({ format = "html", docCount = GALLERY_DOCS.length }) {
  const [pane, setPane] = useState("brief");
  const [shelf, setShelf] = useState(false);
  const [selected, setSelected] = useState(-1);
  const [focused, setFocused] = useState(false);
  const brief =
    format === "html"
      ? { title: "Paid ads, week of 1 Sept", version: 2, format: "html", content: GALLERY_HTML }
      : { title: "Organic growth, week of 8 Sept", version: 2, format: "markdown", content: BRIEF_MARKDOWN };
  const versions = [
    { version: 1, label: "First pass" },
    { version: 2, label: "Update 2" },
  ];
  return (
    <div className="@container flex h-[34rem] flex-col overflow-hidden rounded-xl border border-border">
      <ArtifactPaneHeader
        pane={pane}
        onPane={setPane}
        dataCount={2}
        title={shelf ? "All documents" : brief.title}
        status={shelf ? "in this thread" : ""}
        docCount={shelf ? 0 : docCount}
        onShowGallery={() => setShelf(true)}
        onDownload={shelf ? null : () => saveBrief(brief)}
        onFocus={shelf ? null : () => setFocused(true)}
        versions={shelf ? [] : versions}
        selected={selected}
        onSelect={setSelected}
      />
      <div className="min-h-0 flex-1 overflow-hidden">
        {pane === "data" ? (
          <DataPane
            fetched={[
              { label: "GA4 · landing pages · 30 d", ok: true },
              { label: "Google Ads · campaigns · 30 d", ok: true },
            ]}
          />
        ) : shelf ? (
          <div className="h-full overflow-y-auto bg-muted/30">
            <ArtifactGallery
              docs={GALLERY_DOCS}
              onOpen={() => setShelf(false)}
              loadContent={(id) =>
                id === "never" ? new Promise(() => {}) : Promise.resolve(GALLERY_CONTENT[id])
              }
            />
          </div>
        ) : (
          <BriefPane brief={brief} />
        )}
      </div>
      <DocumentFocus
        open={focused}
        onOpenChange={setFocused}
        brief={brief}
        title={brief.title}
        sub="v2"
        onDownload={() => saveBrief(brief)}
      />
    </div>
  );
}

// The real save, not a stub: a download control whose scene does nothing is a
// scene that cannot answer whether the file comes out named correctly.
function saveBrief(brief) {
  const file = briefFile(brief);
  saveText(brief.content, file.name, file.type);
}

// Opens on mount: the scene *is* the overlay, so there is nothing to click
// first. Reopening after Escape is what the button in `artifact-pane` covers.
function DocumentFocusScene() {
  const [open, setOpen] = useState(true);
  // Built here rather than beside the other fixtures: the module's brief
  // fixtures are declared further down, and a const read above its own
  // declaration is a blank screen with a TDZ error behind it.
  const brief = { title: "Paid ads, week of 1 Sept", version: 2, format: "html", content: GALLERY_HTML };
  return (
    <div className="p-4 text-sm text-muted-foreground">
      <button type="button" className="underline" onClick={() => setOpen(true)}>
        Reopen the focus view
      </button>
      <DocumentFocus
        open={open}
        onOpenChange={setOpen}
        brief={brief}
        title={brief.title}
        sub="v2"
        onDownload={() => saveBrief(brief)}
      />
    </div>
  );
}

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
    { id: "n1", title: "Audit our Google Search performance please.", detailCode: "resume", tone: "attention", at: "2026-09-09T06:00:00Z" },
  ],
  [FOUND]: [
    { id: "f1", title: "Next growth milestone: 3_repeatable_growth", detailCode: "checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
    { id: "f2", title: LONG_TITLE, detailCode: "checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
    { id: "f3", title: "North-star metric: Net new revenue", detailCode: "checked", tone: "sure", at: "2026-09-08T09:00:00Z" },
  ],
  [IN_PROGRESS]: [
    { id: "p1", title: "Audit our Google Search performance please.", detailCode: "working", tone: "running", at: "2026-09-09T06:00:00Z" },
    { id: "p2", title: "Audit our Google Search performance please.", detailCode: "working", tone: "running", at: "2026-09-09T06:00:00Z" },
  ],
};
const DESK_BUCKETS_SHAPED = { needsYou: DESK_BUCKETS[NEEDS_YOU], found: DESK_BUCKETS[FOUND], inProgress: DESK_BUCKETS[IN_PROGRESS] };

// A brief the way the agent actually writes one: a decision up top, the
// evidence as a table, the gaps as a list. Enough element kinds to catch a
// missing typography rule.
const BRIEF_MARKDOWN = `## Cut the blog from the plan; double down on the comparison pages

Organic sessions are flat week on week, but the mix moved. The three comparison
pages now carry **41% of non-brand clicks**, up from 29%, while the blog lost
position on every query it ranked for.

### What the numbers say

| Page | Clicks | Δ vs prior week | Avg. position |
| --- | ---: | ---: | ---: |
| /compare/duct-vs-looker | 812 | +38% | 4.2 |
| /compare/duct-vs-hex | 540 | +22% | 6.1 |
| /blog/weekly-review-template | 133 | −44% | 11.8 |

### What to do this week

1. Add a \`Pricing\` section to the two comparison pages; both rank for pricing queries they do not answer.
2. Redirect the three thinnest blog posts to the comparison hub rather than rewriting them.
3. Hold the ad budget for the blog cluster until the redirect settles.

### Could not verify

- Search Console's token expired on Tuesday, so the query-level split is from the 7 days before that.
- GA4 key events were renamed mid-week; \`sign_up\` counts before Wednesday are not comparable.

> A number nobody checked should never be presented with the same confidence as one that was.
`;

const GALLERY_HTML = `<!doctype html><html><head><style>
body{font-family:system-ui;margin:0;padding:32px;color:black;background:white}h1{font-size:28px;margin:0 0 8px}
.k{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}
.k div{border:1px solid silver;border-radius:10px;padding:14px}.k b{display:block;font-size:24px}
p{line-height:1.5;max-width:60ch}.bar{height:10px;background:darkorange;border-radius:5px;width:64%;margin:6px 0 16px}
</style></head><body><h1>Paid ads, week of 1 Sept</h1><p>Spend is up 12% on flat conversions; the new broad-match campaign is where the money went.</p>
<div class="k"><div>Spend<b>€4,120</b></div><div>Conversions<b>61</b></div><div>CPA<b>€67.5</b></div></div>
<div class="bar"></div><p>Three of the four new ad groups have no negative keywords yet, and the search-terms report shows them matching on competitor names.</p></body></html>`;

// A run's tool traffic as the recorder stores it: the call, then the body the
// tool handed the model. Both the transcript's cards and the Data roll-up are
// built from this one fixture, because in the app they are built from one
// stream of events — a scene that faked either separately could show them
// agreeing when the code does not.
const use = (name, id, input) => ({ kind: "tool_use", data: { name, tool_use_id: id, input } });
const returned = (name, id, payload, isError = false) => ({
  kind: "tool_result",
  data: { name, tool_use_id: id, result: JSON.stringify(payload), is_error: isError },
});

const TOOL_TRAFFIC = [
  use("FetchData", "t1", { entity_id: "gsc_queries" }),
  returned("FetchData", "t1", {
    status: "ok", entity_id: "gsc_queries", connector_id: "gsc",
    date_from: "2026-08-20", date_to: "2026-09-17", data: { rows: new Array(500).fill(0) },
  }),
  use("FetchData", "t2", { entity_id: "ga4_landing_pages" }),
  returned("FetchData", "t2", {
    status: "ok", entity_id: "ga4_landing_pages", connector_id: "ga4",
    date_from: "2026-08-20", date_to: "2026-09-17", data: { rows: new Array(842).fill(0) },
  }),
  use("FetchData", "t3", { entity_id: "google_ads_campaigns" }),
  returned("FetchData", "t3", {
    status: "reauth_required", entity_id: "google_ads_campaigns", connector_id: "google_ads",
    message: "google_ads rejected its stored credential (expired or revoked). Nothing from this source can be fetched until the user reconnects it on the Connections page.",
  }),
  use("WebSearch", "t4", { query: "self-hosted AI gateway 2026 alternatives" }),
  returned("WebSearch", "t4", {
    status: "ok", query: "self-hosted AI gateway 2026 alternatives", grounded: true,
    sources: [
      { title: "docs.litellm.ai", url: "https://docs.litellm.ai/docs/proxy" },
      { title: "portkey.ai", url: "https://portkey.ai/docs" },
      { title: "github.com", url: "https://github.com/BerriAI/litellm" },
    ],
  }),
  use("WebFetch", "t5", { url: "https://docs.litellm.ai/docs/proxy/deploy" }),
  returned("WebFetch", "t5", { status: "ok", url: "https://docs.litellm.ai/docs/proxy/deploy", truncated: true }),
  use("task", "t6", { subagent_type: "verifier", description: "Check every number in the brief against the pulls it cites." }),
  { kind: "tool_result", data: { name: "task", tool_use_id: "t6", result: "Checked 9 figures. Two were stated without their window; both corrected.", is_error: false } },
  use("SearchMemory", "t7", { query: "pricing change" }),
  returned("SearchMemory", "t7", { count: 2, memories: [{ title: "Pricing changed on 4 Sept" }, { title: "Mobile is the growth channel" }] }),
  use("ListDataSources", "t8", {}),
  returned("ListDataSources", "t8", { status: "ok", sources: [{ id: "ga4" }, { id: "gsc" }, { id: "google_ads" }, { id: "mixpanel" }] }),
  use("GetArtifact", "t9", { artifact_id: "a1" }),
  returned("GetArtifact", "t9", { artifact_id: "a1", title: "Organic growth, week of 8 Sept", kind: "brief", version: 3 }),
  use("FetchPages", "t10", { urls: ["https://acme.io/", "https://acme.io/pricing", "https://acme.io/blog/launch"] }),
  returned("FetchPages", "t10", { pages: [{ url: "https://acme.io/" }, { url: "https://acme.io/pricing" }], errors: ["https://acme.io/blog/launch: 404"] }),
  use("publish_post", "t11", { post_id: "p1" }),
  returned("publish_post", "t11", { status: "ok", post_id: "p1", post_bridge_post_id: "pb1", status_label: "scheduled", scheduled_at: "2026-09-23T09:00:00Z" }),
];

// The run's own notice comes first: it is what the opening turn was built
// from, before any tool ran.
const ACTIVITIES = [
  contextActivity({ resume: false, blocks: { business_context: "…", user_context: "…", memory: "…", data_sources: "ga4, gsc", artifact_format: "html" } }, "context-1"),
  ...activitiesFromEvents(TOOL_TRAFFIC),
];

const GALLERY_DOCS = [
  { id: "g1", group_id: "g1", title: "Organic growth, week of 8 Sept", version: 3, version_count: 3, content_type: "text/markdown", has_content: true, created_at: new Date(Date.now() - 2 * 3600_000).toISOString() },
  { id: "g2", group_id: "g2", title: "Paid ads, week of 1 Sept", version: 1, version_count: 1, content_type: "text/html", has_content: true, created_at: new Date(Date.now() - 6 * 86400_000).toISOString() },
  { id: "never", group_id: "g3", title: "Landing-page audit, 24 Aug", version: 2, version_count: 2, content_type: "text/markdown", has_content: true, created_at: new Date(Date.now() - 20 * 86400_000).toISOString() },
  { id: "g4", group_id: "g4", title: "Signup funnel, paid search", version: 1, version_count: 1, content_type: "image/svg+xml", has_content: true, created_at: new Date(Date.now() - 3 * 86400_000).toISOString() },
];
// A figure the agent drew itself, the way every frontier model can: a funnel
// with the numbers on it. The card shows it as a picture, never as source.
// Named colours because the figure is content with its own palette, like a
// slide; the hex ratchet guards chrome, not what an agent drew.
const GALLERY_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 260" font-family="system-ui, sans-serif" font-size="14">
  <rect x="40" y="20" width="400" height="44" rx="6" fill="darkorange"/>
  <text x="240" y="48" text-anchor="middle" fill="white">Paid sessions · 2,681</text>
  <rect x="90" y="84" width="300" height="44" rx="6" fill="sandybrown"/>
  <text x="240" y="112" text-anchor="middle" fill="black">Signups · 418</text>
  <rect x="140" y="148" width="200" height="44" rx="6" fill="peachpuff"/>
  <text x="240" y="176" text-anchor="middle" fill="black">First render · 210</text>
  <rect x="190" y="212" width="100" height="36" rx="6" fill="seashell"/>
  <text x="240" y="236" text-anchor="middle" fill="black">Paid · 0</text>
</svg>`;
const GALLERY_CONTENT = { g1: BRIEF_MARKDOWN, g2: GALLERY_HTML, g4: GALLERY_SVG };

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


// ── Models & providers ────────────────────────────────────────────────────
//
// The Tiers tab is a summary plus a fold, so the state that matters is which
// of them a reader lands on and whether the summary is honest when a tier
// cannot run. Both the collapsed and blocked cases are unreachable on a
// healthy dev install, which is exactly why they are pinned here.

const MODEL_CATALOGUE = {
  models: [
    { id: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro (preview)", provider: "google_genai", engines: ["v1"] },
    { id: "gemini-3.8-flash", label: "Gemini 3.8 Flash", provider: "google_genai", engines: ["v1"] },
    { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite", provider: "google_genai", engines: ["v1"] },
    { id: "claude-opus-5", label: "Claude Opus 5", provider: "anthropic", engines: ["v1"] },
    { id: "claude-sonnet-5", label: "Claude Sonnet 5", provider: "anthropic", engines: ["v1"] },
    { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", provider: "anthropic", engines: ["v1"] },
  ],
  tiers: [
    { id: "heavy", default_model: "gemini-3.1-pro-preview", jobs: ["analysis", "audit"] },
    { id: "standard", default_model: "gemini-3.8-flash", jobs: ["verification", "synthesis", "drafting", "chat"] },
    { id: "light", default_model: "gemini-3.5-flash-lite", jobs: ["research", "memory", "recap"] },
  ],
  image_models: [
    { id: "gemini-3.1-flash-image", label: "Gemini 3.1 Flash Image", provider: "google_genai", default: true },
    { id: "gemini-3-pro-image", label: "Gemini 3 Pro Image", provider: "google_genai" },
    { id: "gpt-image-2.5-flare", label: "GPT Image 2.5 Flare", provider: "openai" },
  ],
  image_provider_order: ["google_genai", "openai", "xai"],
  provider_triples: {
    anthropic: { heavy: "claude-opus-5", standard: "claude-sonnet-5", light: "claude-haiku-4-5" },
    google_genai: { heavy: "gemini-3.1-pro-preview", standard: "gemini-3.8-flash", light: "gemini-3.5-flash-lite" },
  },
};

const MODEL_PROVIDERS = {
  google_genai: { id: "google_genai", label: "Google Gemini", source: "env", reachable: true, engines: ["v1"] },
  anthropic: { id: "anthropic", label: "Anthropic", source: "none", reachable: false, engines: ["v1"] },
  openai: { id: "openai", label: "OpenAI", source: "none", reachable: false, engines: ["v1"] },
};

// The one credential that is a live provider and no way to draw: a ChatGPT
// plan reaches the Codex backend, and the image API is a different door.
const MODEL_PROVIDERS_ON_PLAN = {
  ...MODEL_PROVIDERS,
  google_genai: { ...MODEL_PROVIDERS.google_genai, source: "none", reachable: false },
  openai: { id: "openai", label: "OpenAI", source: "subscription", reachable: true, engines: ["v1"] },
};

const MODEL_PICKS = {
  heavy: "gemini-3.1-pro-preview",
  standard: "gemini-3.8-flash",
  light: "gemini-3.5-flash-lite",
};

const MODEL_PREVIEW_OK = {
  heavy: { id: "heavy", provider: "google_genai", model: "gemini-3.1-pro-preview", runnable: true },
  standard: { id: "standard", provider: "google_genai", model: "gemini-3.8-flash", runnable: true },
  light: { id: "light", provider: "google_genai", model: "gemini-3.5-flash-lite", runnable: true },
};

// Heavy set to a provider with no key — the case the summary has to surface
// rather than hide, since the fold is closed and the cards are not on screen.
const MODEL_PREVIEW_BLOCKED = {
  ...MODEL_PREVIEW_OK,
  heavy: {
    id: "heavy",
    provider: "anthropic",
    model: "claude-opus-5",
    runnable: false,
    reason: "no_credential",
    serves: { model: "gemini-3.8-flash", engine_default: false },
  },
};

const MODEL_FILLABLE = [
  { id: "anthropic", statusId: "anthropic", label: "Anthropic" },
  { id: "gemini", statusId: "google_genai", label: "Google Gemini" },
];

function TierSummaryScene({
  picks,
  previewByTier,
  expanded = false,
  imagePick = "",
  images = { provider: "google_genai", model: "gemini-3.1-flash-image", source: "env" },
  providersById = MODEL_PROVIDERS,
}) {
  const [open, setOpen] = useState(expanded);
  const [image, setImage] = useState(imagePick);
  return (
    <TierSummary
      picks={picks}
      models={MODEL_CATALOGUE.models}
      providersById={providersById}
      previewByTier={previewByTier}
      expanded={open}
      onToggle={() => setOpen((v) => !v)}
      fillable={MODEL_FILLABLE}
      onFill={() => {}}
      configuredCount={3}
      onReset={() => {}}
      images={images}
      imageModels={MODEL_CATALOGUE.image_models}
      imagePick={image}
      onImageChange={setImage}
    />
  );
}

// Two change sets for the review card: one waiting on a person with a blocked
// row in it, one that auto-applied and can still be rolled back.
const SAMPLE_CHANGE_SET = {
  change_set_id: "cs_1",
  connector_type: "google_ads",
  account_name: "Sictec — Search",
  title: "Cut spend on three converting-nothing search terms",
  context: "Last 30 days: these three terms took 18% of spend and produced no conversions.",
  status: "proposed",
  source: "agent",
  applied_by: "",
  changes: [
    { id: "c1", op_type: "add_negative_keyword", diff: 'Add negative: "free crm template"', status: "pending" },
    { id: "c2", op_type: "pause_ad_group", diff: "Pause ad group “Brand — Exact”", status: "blocked", destructive: true,
      guardrail_violations: ["Never pause the Brand campaign — set on this account"] },
    { id: "c3", op_type: "add_negative_keyword", diff: 'Add negative: "duct tape"', status: "pending",
      warnings: ["Matches 41 historical queries, 2 of which converted"] },
  ],
};

const SAMPLE_CHANGE_SET_APPLIED = {
  ...SAMPLE_CHANGE_SET,
  change_set_id: "cs_2",
  title: "Mark checkout_complete as a key event",
  context: "",
  status: "applied",
  applied_by: "auto",
  changes: [
    { id: "c4", op_type: "mark_key_event", diff: "GA4: checkout_complete → key event", status: "applied" },
    { id: "c5", op_type: "mark_key_event", diff: "GA4: trial_start → key event", status: "rolled_back" },
  ],
};

// Approved, then someone raised the budget in Google Ads before apply ran: the
// budget row is held back rather than applied against a state nobody approved.
const SAMPLE_CHANGE_SET_DRIFTED = {
  ...SAMPLE_CHANGE_SET,
  change_set_id: "cs_3",
  title: "Shift budget from Display to Search",
  context: "",
  status: "applied",
  applied_by: "user",
  applied_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
  changes: [
    { id: "c6", op_type: "set_campaign_status", diff: "Campaign 1182 (Display — Prospecting): ENABLED → PAUSED", status: "applied" },
    { id: "c7", op_type: "set_campaign_budget", diff: "Campaign 2240 (Search — Core) daily budget: 50 → 60", status: "blocked", drifted: true },
  ],
};

// The person said no: the card keeps the proposal and says whose call it was.
const SAMPLE_CHANGE_SET_REJECTED = {
  ...SAMPLE_CHANGE_SET,
  change_set_id: "cs_4",
  status: "rejected",
  updated_at: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
};

// A Discover result set for the synthesis panel: a face-shape niche with both
// formats, tags that recur beyond the two searched for, one post with a big
// ratio on a tiny audience (it must not win a hook), and captions of every
// shape — tags first, a long opening line, no words at all.
const DISCOVER_POSTS = [
  ["d1", true, 182_000, 21_400, ["faceshape", "colorseason", "contour", "blushplacement"], "#faceshape\nStop contouring a round face like it's an oval"],
  ["d2", true, 96_000, 8_900, ["faceshape", "contour", "makeuptips"], "The blush placement that lifts a heart-shaped face in three seconds, no filler, no surgery, just where you put it"],
  ["d3", false, 410_000, 16_800, ["faceshape", "fyp", "makeuptips"], "POV: your stylist finally explains your face shape"],
  ["d4", false, 64_000, 1_900, ["colorseason", "blushplacement"], "#colorseason #fyp"],
  ["d5", true, 1_200, 700, ["faceshape", "contour"], "tiny account, huge ratio"],
  ["d6", false, 38_000, 900, ["faceshape"], "Day 4 of learning my colour season"],
].map(([id, slideshow, plays, acted, hashtags, text]) => ({
  id,
  text,
  hashtags,
  is_slideshow: slideshow,
  play_count: plays,
  digg_count: Math.round(acted * 0.7),
  comment_count: Math.round(acted * 0.05),
  share_count: Math.round(acted * 0.1),
  collect_count: Math.round(acted * 0.15),
  web_video_url: `https://www.tiktok.com/@kestrel/video/${id}`,
}));

// Every post a video, no tag on two posts, no caption with words: the panel
// must still read as a panel, not a set of holes.
const DISCOVER_POSTS_SPARSE = [
  { id: "s1", text: "#grwm", hashtags: ["grwm"], is_slideshow: false, play_count: 12_000, digg_count: 300 },
  { id: "s2", text: "", hashtags: ["outfit"], is_slideshow: false, play_count: 8_000, digg_count: 120 },
];

export const SCENES = [
  {
    id: "discover-synthesis",
    state: "mixed formats, recurring tags, three hooks",
    group: "SynthesisPanel",
    title: "What's working, above Discover's results",
    note: "Computed from the result set in the browser (lib/discoverSynthesis.js). What to check: the searched tags (faceshape, colorseason) and the generic fyp never appear under Recurring hashtags; the 1.2k-view post with a 58% ratio does not win a hook; the long caption is clipped to one opening line; the leading format's engagement is the bold one. Drag through @2xl (42rem): the two top blocks go from stacked to side by side.",
    render: () => (
      <div style={{ maxWidth: 880, padding: 24 }}>
        <SynthesisPanel posts={DISCOVER_POSTS} searchedTags={["faceshape", "colorseason"]} />
      </div>
    ),
  },
  {
    id: "discover-synthesis-sparse",
    state: "one format, nothing recurring, no hook with words",
    group: "SynthesisPanel",
    title: "What's working, from a thin result set",
    note: "Two videos from a trend feed. No leader is named when only one format is present, the hashtags block says so in a line instead of leaving a gap, and the hooks block is absent rather than empty.",
    render: () => (
      <div style={{ maxWidth: 880, padding: 24 }}>
        <SynthesisPanel posts={DISCOVER_POSTS_SPARSE} />
      </div>
    ),
  },
  {
    id: "front-door",
    state: "default — signed out, nothing typed",
    group: "FrontDoor",
    title: "The signed-out front door",
    note: "Check it in dark before anything else: this panel paints on `--start-ground`, which flips with the theme, and it previously used the fixed `--navy` brand hexes for ink — headline 1.05:1, body 2.94:1, both effectively invisible. Then drag the frame through 64rem: the mosaic should move from under the field into a second column beside it, and never sit between the headline and the button. The headline carries no accent colour on purpose — the submit button is the page's one accent.",
    render: () => <FrontDoorScene />,
  },
  {
    id: "front-door-error",
    state: "submitted empty — the field's error replaces the reassurance line",
    group: "FrontDoor",
    title: "The signed-out front door",
    note: "One line does two jobs, so check the swap does not move the layout: the hint and the error are the same element, and the error takes `role=\"alert\"` plus `aria-describedby` off the input. The reassurance it replaces (\"Free, no account, and nothing else connected\") is the page's answer to the fear that pointing Duct at a site hands over an ad account, so it must come back the moment the error clears.",
    render: () => <FrontDoorScene error="Enter your website address." />,
  },
  {
    id: "desk-composer",
    state: "default — a project with a favicon, no thread yet",
    group: "DeskComposer",
    title: "The insights composer",
    note: "Left: the posture, folded to the current choice; the other two unfold on hover, keyboard focus, or a tap of the visible one (touch has no hover), and the unfold is a width transition, not a pop. Right: the model tier as quiet text — its popover holds the tier list and, under it, thinking as a stepped slider with the stop's name beside the title, a dot per step on the track and one line saying what the stop buys — then the context ring with no label (percent, tokens and cost are on hover), then Send. Check that the folded pill's text sits centred, that the tier trigger adds the thinking rung only when one is set, that Tab walks tier choices then the slider thumb, and that the send button's loading spinner and the amber \"no provider connected\" notice (type something, then use the browser's devtools to force a 401 on /api/providers/status) do not clear the draft.",
    render: () => (
      <DeskComposerScene
        project={{ id: "p1", name: "Sictec Infotech, Inc.", company: { name: "Sictec Infotech, Inc.", website_url: "https://sictec.example" } }}
        placeholder="Ask about &ldquo;Next growth milestone&rdquo; — or anything else"
      />
    ),
  },
  {
    id: "session-composer",
    state: "inside a running session — dials deferred, ring beside Send",
    group: "DeskComposer",
    title: "The session composer",
    note: "The same card as the desk composer, in the chat shell: attach and the folded posture on the left; the tier, the context ring and Send on the right. `deferred` makes the tier panel say the choice lands at the next session and the posture tooltips say next message — check that line is there, that hovering the ring shows the token figures, and that the controls wrap under the text at phone width rather than pushing Send off the card.",
    render: () => (
      <div className="max-w-[720px]">
        <ChatInput
          onSend={() => {}}
          isStreaming
          onStop={() => {}}
          placeholder="Ask about your growth data…"
          tools={<DialsScene />}
          status={
            <>
              <TierDial deferred />
              <ContextRing
                used={0.34}
                details={{
                  last: { input: 61_000, output: 7_200, cached: 48_000, window: 200_000, cost: 0.21, model: "claude-sonnet-5" },
                  total: { input: 210_000, output: 19_000, cached: 150_000, calls: 4, cost: 0.74 },
                }}
              />
            </>
          }
        />
      </div>
    ),
  },
  {
    id: "composer-attachments",
    state: "three tiles on the card · the drop hint",
    group: "DeskComposer",
    title: "Files on the composer",
    note: "What the card looks like with things attached: an image is its own thumbnail, a PDF and a pasted block of CSV are small cards with the name and a badge. The strip scrolls sideways rather than wrapping so four screenshots never push the text box off the card; each tile's remove button sits on its corner. A large paste (over 25 lines or 3,000 characters) becomes one of these tiles rather than a wall of text in the box, named for what it looks like — pasted-1.csv here. Below it, the hint the whole card shows while a file is held over it: the card is the drop target, not the paperclip.",
    render: () => (
      <div className="max-w-[720px] space-y-6">
        <ChatInput
          onSend={() => {}}
          placeholder="Ask about your growth data…"
          initialAttachments={[
            { name: "landing-page.webp", mediaType: "image/webp", kind: "image", preview: "/art/mosaic/fons.webp" },
            { name: "Q3-board-deck-final-v2.pdf", mediaType: "application/pdf", kind: "pdf" },
            { name: "pasted-1.csv", mediaType: "text/csv", kind: "text", text: "date,sessions\n2026-09-01,120" },
            { name: "web-performance-analysis-v2.html", mediaType: "text/html", kind: "text", text: "<html/>" },
          ]}
          status={<ContextRing used={0} label="New thread" />}
        />
        <div className="relative h-24 rounded-xl border bg-card">
          <DropHint />
        </div>
      </div>
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
    note: "Connected, partial grant, not-yours, session-only, not connected, and disabled. Amber and blue are different claims: partial means degraded, info means it works but the key is Duct's or the machine's, not one the reader added. The foot is the part that breaks: state left, storage right.",
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
          title="OpenAI"
          description="GPT models, and image generation for slides and posts."
          tone="info"
          status="Duct's key"
          storage={STORAGE_CLOUD}
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
    id: "provider-key-dialog",
    state: "openai, no key",
    group: "ProviderCard",
    title: "The key dialog",
    note: "Click the tile. Check: the eye sits inside the field and the field keeps its full width; label/input are tighter than input/notes; the checkbox is a control, not small print. The ChatGPT plan section is the browser variant here \u2014 steps plus the download; in the desktop shell it is the Continue with ChatGPT button itself (with Cancel beside it while it waits), then the signed-in account row carrying Disconnect and Reconnect \u2014 the same pair, in the same variants, as every OAuth connector. Type into the field to see the prefix warning replace the storage line.",
    render: () => (
      <div className="conn-grid">
        <ProviderCard
          provider={PROVIDERS.find((p) => p.id === "openai")}
          logo={LOGO}
          status={{ id: "openai", source: "none", reachable: false, stored: false }}
        />
      </div>
    ),
  },
  {
    id: "provider-key-loading",
    state: "nothing answered yet",
    group: "ProviderCard",
    title: "Before anything is known",
    note: "The card asks three things on mount \u2014 the server's status, the keychain, and the ChatGPT sign-in \u2014 and every one of them defaults to \"nothing here\". Rendered as-is that reads \"Not set\", a verdict delivered before the question was asked. Held here with `loading`: the dot pulses, the foot says Checking, and the storage glyph is absent because where a key lives is also a claim. Open it: the key field and the plan section say the same thing rather than offering a sign-in you may already have done.",
    render: () => (
      <div className="conn-grid">
        <ProviderCard
          provider={PROVIDERS.find((p) => p.id === "openai")}
          logo={LOGO}
          status={undefined}
          loading
        />
      </div>
    ),
  },
  {
    id: "provider-key-mismatch",
    state: "stale value in the slot",
    group: "ProviderCard",
    title: "Not a key we can use",
    note: "What a leftover credential looks like — a JWT that was never an Anthropic key. The server refused it, so the dot is grey and the source reads none, not \"Your key\". Open it: the alert is in the field notes and Remove key is in the footer, which is the whole point of the state. It asks before it drops anything, and the confirm names where the key lives.",
    render: () => (
      <div className="conn-grid">
        <ProviderCard
          provider={PROVIDERS.find((p) => p.id === "anthropic")}
          logo={LOGO}
          status={{ id: "anthropic", source: "none", reachable: false, stored: false, key_mismatch: true }}
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
    id: "insights-panes-empty",
    state: "empty · empty with a CTA",
    group: "InsightsWorkspace",
    title: "Artifact and Data, with nothing in them",
    note: "Both right-pane tabs of an insights thread before anything lands. They were bare muted sentences until now, which is the shape ui/empty-state exists to replace. Only Data gets a button: its usual cause is that nothing is connected, which is fixable from here, while no artifact yet is just a young thread.",
    render: () => (
      <div className="grid gap-6 @3xl:grid-cols-2">
        <div className="h-[20rem] overflow-hidden rounded-xl border border-border">
          <BriefPane empty />
        </div>
        <div className="h-[20rem] overflow-hidden rounded-xl border border-border">
          <DataPane fetched={[]} />
        </div>
      </div>
    ),
  },
  {
    id: "data-pane-reopened",
    state: "two connectors, one expired grant",
    group: "InsightsWorkspace",
    title: "The Data tab, rolled up",
    note: "Every source the thread read, grouped by connector, built from the same activity rows the transcript shows — so the tab and the chat cannot disagree about what the agent read, which they did while one filled from step events and the other from stored tool traffic. The rows are the transcript's own control, not a second list: click the failed pull.",
    render: () => (
      <div className="h-[24rem] max-w-xl overflow-hidden rounded-xl border border-border">
        <DataPane sources={dataSourceRollup(ACTIVITIES)} />
      </div>
    ),
  },
  {
    id: "reasoning-rows",
    state: "thinking · thought for 6s · from history",
    group: "AgentChat",
    title: "The reasoning fold, with its clock",
    note: "Three states of one row. Thinking, with the seconds ticking on this client's clock from the first reasoning token; done, saying how long it took before the first word of prose (measured, not a token estimate the client would have to make up); and rebuilt from history, where there is no clock and the row just says Reasoning. The text stays behind the chevron in every state — reasoning is there to be checked, not read by default.",
    render: () => (
      <div className="max-w-xl space-y-4">
        <TranscriptRow msg={{ role: "assistant", text: "", thinking: "The window is 30 days; compare like with like before saying anything about the drop.", streaming: true, thinkingStartedAt: Date.now() - 4000 }} />
        <TranscriptRow msg={{ role: "assistant", text: "Sessions are flat; the mix moved.", thinking: "The window is 30 days; compare like with like before saying anything about the drop.", thinkingStartedAt: 1000, thinkingEndedAt: 7000 }} />
        <TranscriptRow msg={{ role: "assistant", text: "Sessions are flat; the mix moved.", thinking: "The window is 30 days; compare like with like before saying anything about the drop." }} />
      </div>
    ),
  },
  {
    id: "working-indicator",
    state: "generic · on a step · compacting",
    group: "AgentChat",
    title: "The wait, in words",
    note: "What sits at the bottom of the transcript while the agent works, in place of three bouncing dots that only ever said \"something, eventually\". With no better information the phrase rotates through a few generic verbs every couple of seconds (held still under reduced motion); when a step is running its own label takes the slot, and a compaction or a retry says so. The words are deliberately generic where the run's state is unknown — a verb naming a step the run is not on is a lie the reader can catch.",
    render: () => (
      <div className="max-w-xl space-y-3">
        <WorkingIndicator />
        <WorkingIndicator label="Collecting source data" />
        <WorkingIndicator label="Compacting context" />
      </div>
    ),
  },
  {
    id: "transcript-dividers",
    state: "compacted (unknown) · compacted (freed) · switched model · plain notice",
    group: "AgentChat",
    title: "Lines across the transcript",
    note: "A compaction and a model switch are facts about everything after them, so they are drawn as a rule across the transcript rather than a message in it. The compaction says what it freed once the next call on the thread has reported its size — before that it only says it happened. When the backend sends the summary the thread now opens with, the rule folds it behind a chevron (click the second one), set in italic so it never reads as something the agent said to the person. The model divider carries the name a person knows the model by, sent by the backend on every run start; a resumed thread that comes back on a different model gets one from its stored context rows too.",
    render: () => (
      <div className="max-w-xl">
        <TranscriptRow msg={{ role: "assistant", text: "Let me look at the last thirty days." }} />
        <TranscriptRow msg={{ role: "notice", kind: "compacted", before: 180000, after: null }} />
        <TranscriptRow msg={{ role: "notice", kind: "compacted", before: 180000, after: 42000, summary: "**Where this started.** Sessions fell 12% after the September pricing change; the drop is entirely mobile organic.\n\n**What was checked.** GA4 landing pages for the last thirty days, Search Console queries for the pricing page, and the Ads campaign that was paused on the 4th.\n\n**Open.** Whether the mobile drop is a tracking change rather than a demand change — the tag was redeployed the same week." }} />
        <TranscriptRow msg={{ role: "notice", kind: "model", label: "GPT-5.6 Terra", model: "gpt-5.6-terra" }} />
        <TranscriptRow msg={{ role: "notice", text: "Stopped here — the turn was interrupted." }} />
      </div>
    ),
  },
  {
    id: "message-rows",
    state: "a user message with files · a long one folded · a reply on the page",
    group: "AgentChat",
    title: "The two registers",
    note: "The person's message is the one bubble in the transcript: it came from outside the run and the shape says so. Files it carried sit above it as the same tiles the composer showed. A message past a screen's worth (twelve lines or 1,200 characters) folds behind Show more so a pasted page of context never buries the reply under it. The reply is prose on the page, no box — hover either row for when it was sent (the full date and time is behind it), and hover the reply for the copy button. Both are always visible where there is no hover.",
    render: () => (
      <div className="max-w-xl">
        <TranscriptRow
          msg={{
            role: "user",
            text: "These are the pages that lost traffic — does the deck explain it?",
            at: Date.now() - 5 * 60_000,
            attachments: [
              { name: "landing-page.webp", mediaType: "image/webp", kind: "image", preview: "/art/mosaic/fons.webp" },
              { name: "Q3-board-deck-final-v2.pdf", mediaType: "application/pdf", kind: "pdf" },
            ],
          }}
        />
        <TranscriptRow
          msg={{
            role: "user",
            at: Date.now() - 4 * 60_000,
            text: Array.from({ length: 22 }, (_, i) => `Line ${i + 1}: the pricing page lost ${120 - i * 3} sessions against the same week last month, all mobile.`).join("\n"),
          }}
        />
        <TranscriptRow
          msg={{
            role: "assistant",
            at: Date.now() - 3 * 60_000,
            text: "Sessions are flat; the mix moved.\n\nMobile organic to the pricing page is down **12%** since the 4th, and that is the whole of the drop. Desktop is up slightly. The tag was redeployed the same week, so before calling it demand I would check the mobile hit count in the raw events.",
          }}
        />
      </div>
    ),
  },
  {
    id: "activity-rows",
    state: "the context notice · pulls · a search · a page · a sub-agent · memory · sources · a document · a site read · a publish",
    group: "AgentChat",
    title: "What the agent did, in the transcript",
    note: "One row per tool call, where it happened. A run used to show none of this — a pull became a line in another tab, a search and an image became nothing — so the reader got ninety seconds of \"Working…\" and then a brief citing a source they never saw it open. One line each until you click: twelve sources would otherwise push the prose off the screen. Every row here is built by lib/toolActivity from recorded tool traffic, the same path a reopened thread takes.",
    render: () => (
      <div className="max-w-xl">
        <ActivityGroup activities={ACTIVITIES} />
      </div>
    ),
  },
  {
    id: "activity-rows-open",
    state: "expanded, including a failure with its way out",
    group: "AgentChat",
    title: "An activity row, opened",
    note: "What each kind has behind the chevron: the window and the row count for a pull, the sources as favicon chips for a search, the URL for a page, the brief and the answer for a sub-agent. A failed pull carries the provider's own sentence — not the model's paraphrase — and, when reconnecting is what fixes it, the link there.",
    render: () => (
      <div className="max-w-xl space-y-1">
        {ACTIVITIES.map((a) => (
          <ActivityRow key={a.id} activity={a} defaultOpen />
        ))}
      </div>
    ),
  },
  {
    id: "activity-running",
    state: "mid-call",
    group: "AgentChat",
    title: "A tool call in flight",
    note: "The running half of a card. The backend emits one event when a tool starts and another when it returns, both under the same id, and the row updates in place — so a slow pull says which source it is waiting on rather than leaving the status row to say \"Working\".",
    render: () => (
      <div className="max-w-xl">
        <ActivityGroup
          activities={[
            { id: "r1", kind: "data", status: "running", title: "ga4_landing_pages", source: "ga4", meta: { date_from: "2026-08-20", date_to: "2026-09-17" } },
            { id: "r2", kind: "web_search", status: "running", title: "duct competitors pricing 2026", meta: {} },
          ]}
        />
      </div>
    ),
  },
  {
    id: "activity-images",
    state: "two images the agent drew",
    group: "AgentChat",
    title: "An image the agent made",
    note: "The content agent draws images and renders slides; both come back through the same allowlist as a picture rather than a sentence about a picture, and clicking one opens the app's lightbox. The pictures here are the app's own mosaics, so the scene needs no backend and no generated asset in the repository.",
    render: () => (
      <div className="max-w-xl">
        <ActivityGroup
          defaultOpen
          activities={[
            { id: "i1", kind: "image", status: "success", title: "A kestrel over a harvested field, low sun", meta: { images: ["/art/mosaic/fons.webp", "/art/mosaic/otium.webp"], model: "gemini-image" } },
            { id: "i2", kind: "slide", status: "success", title: "slide-3", meta: { images: ["/art/mosaic/salve.webp"], note: "Hook slide, 1080×1920" } },
          ]}
        />
      </div>
    ),
  },
  {
    id: "brief-loading",
    state: "a document on its way in",
    group: "InsightsWorkspace",
    title: "The brief, loading",
    note: "A reopened thread while its document list or the brief's versions are still in flight. Used to flash \"Nothing written yet\" for the half-second before the brief arrived; now it holds the pane's own shape in the shimmer every wait shares (ui/skeleton, styles/skeleton.css). Reduced motion keeps the blocks and drops the sweep.",
    render: () => (
      <div className="h-[26rem] max-w-3xl overflow-hidden rounded-xl border border-border">
        <BriefPane loading />
      </div>
    ),
  },
  {
    id: "brief-markdown",
    state: "a written markdown brief",
    group: "InsightsWorkspace",
    title: "A markdown brief, typeset",
    note: "The Artifact pane with a brief the agent wrote in markdown. Twelve components asked for `prose` for months while the typography plugin was never installed, so every one of these rendered as unstyled text and looked broken. This scene is the proof the plugin is loaded: headings step down, lists get bullets, tables get rules, and dark mode inverts.",
    render: () => (
      <div className="h-[30rem] max-w-3xl overflow-hidden rounded-xl border border-border">
        <BriefPane
          brief={{
            title: "Organic growth, week of 8 Sept",
            version: 2,
            label: "Update 2",
            format: "markdown",
            content: BRIEF_MARKDOWN,
          }}
        />
      </div>
    ),
  },
  {
    id: "artifact-pane",
    state: "an HTML brief · tabs and shelf live",
    group: "InsightsWorkspace",
    title: "The artifact pane, whole",
    note: "The right pane as the thread shows it: one chrome strip, then the document, floor to ceiling. It used to be a strip of tabs, a second strip restating the version the picker already named, and the document in a card inside a 1rem margin, capped at 74vh so it scrolled inside a pane that scrolled too. Click the tabs and the shelf button — both work here.",
    render: () => <ArtifactPaneScene />,
  },
  {
    id: "artifact-pane-markdown",
    state: "a markdown brief, one document in the thread",
    group: "InsightsWorkspace",
    title: "The artifact pane, markdown",
    note: "The same pane with a markdown brief. The text sits on a page centred in the pane rather than hugging its left edge, because `card` and `background` are the same white in the light theme and the page is what tells a document from the chat beside it. Drag the frame wide to see the desk appear either side; drag it narrow and the page takes the whole width.",
    render: () => <ArtifactPaneScene format="markdown" docCount={1} />,
  },
  {
    id: "artifact-focus",
    state: "the document over the whole window",
    group: "InsightsWorkspace",
    title: "Reading a brief full screen",
    note: "What the expand control in the pane header opens: the same BriefPane on the app's dialog, so Escape closes it and focus is trapped while it is open. The strip keeps what a reader needs — what this is, a way to keep it, a way out — and drops the tabs and the version picker, which are for working with documents rather than reading one.",
    render: () => <DocumentFocusScene />,
  },
  {
    id: "artifact-gallery",
    state: "three documents · one still loading",
    group: "InsightsWorkspace",
    title: "A thread with several documents",
    note: "What the Artifact pane shows when a reopened thread has written more than one brief: portrait cards with the top of the real document drawn small inside, then title, version and age. Clicking one opens it in the pane. A thread with exactly one brief skips this and shows it directly. Reopening by thread id alone used to show nothing at all, whatever the thread had written.",
    render: () => (
      <div className="@container max-w-3xl">
        <ArtifactGallery
          docs={GALLERY_DOCS}
          onOpen={() => {}}
          loadContent={(id) =>
            id === "never" ? new Promise(() => {}) : Promise.resolve(GALLERY_CONTENT[id])
          }
        />
      </div>
    ),
  },
  {
    id: "split-workspace-collapse",
    state: "open · right pane folded",
    group: "SplitWorkspace",
    title: "Folding the viewport away",
    note: "The chevron on the divider folds the right pane so the chat takes the whole width, and it returns in the same place. Desktop only and stored per storageKey, so a thread you always read as chat stays that way. Drag this frame below 48rem and the mobile segmented control takes over instead — collapsing there would leave that control pointing at nothing, which is why it is hidden.",
    render: () => (
      <div className="h-[26rem] overflow-hidden rounded-xl border border-border">
        <SplitWorkspace
          storageKey="preview_split_collapse"
          leftLabel="Chat"
          rightLabel="Artifact"
          left={
            <div className="p-4 text-sm text-muted-foreground">
              The chat pane, which widens to the whole frame when the viewport folds away.
            </div>
          }
          right={<BriefPane empty />}
        />
      </div>
    ),
  },
  {
    id: "desk-activity-collapsed",
    state: "collapsed, with the real toggle",
    group: "Desk",
    title: "Activity rail, folded away",
    note: "Click the strip to expand and the header control to fold it back — this is the desk's own control and its own grid, imported rather than retyped. Collapsing is @3xl-only: fold it, then drag this frame below 48rem and the rail comes back whole, because a 2.75rem strip in a stacked full-width column saves nothing.",
    render: () => <DeskActivityCollapseScene />,
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
  {
    id: "notification-row",
    state: "all four permission states",
    group: "AppSidebar",
    title: "The notification row, in every state it has",
    note: "Lives in the user footer menu. Two of these are unreachable from a browser — \"System\" only happens inside the desktop shell, and \"Blocked\" needs a site permission you have to deny by hand — so this is the only place they get looked at. Clickability is the thing to check: \"Off\" asks the browser for permission and \"Notification settings\" opens the OS pane, while \"On\" and \"Blocked\" are statements and are dimmed to say so. The last row is a desktop shell too old to have `open_notification_settings`, or Linux, where there is no single page to open.",
    render: () => (
      <DropdownMenu defaultOpen modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">Open the account menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <NotificationRow permission="default" onAct={() => {}} />
          <NotificationRow permission="granted" />
          <NotificationRow permission="denied" />
          <NotificationRow permission="system" hasSettingsPage onAct={() => {}} />
          <NotificationRow permission="system" />
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
  {
    id: "language-menu-item",
    state: "sub-menu open on the current language",
    group: "AppSidebar",
    title: "The language row in the account menu",
    note: "Sits under Profile in the user footer menu. The trigger shows the current language's own name; the sub-menu lists all five as a radio group, each in its own script, so someone who landed in the wrong language can still find theirs. Picking one switches this whole preview, the same way it switches the app: cookie, profile when signed in, then a refresh in place.",
    render: () => (
      <DropdownMenu defaultOpen modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">Open the account menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <LanguageMenuItem />
        </DropdownMenuContent>
      </DropdownMenu>
    ),
  },
  {
    id: "model-setup",
    state: "collapsed, one provider, all three runnable",
    group: "TierSummary",
    title: "The setup you already have",
    note: "What the Models page opens with, and the whole answer for anyone on one key. Check that the provider is named once in the heading rather than three times as a logo per row, that Customise sits hard against the right edge at every width, and that the three model names stay on one line each — they ellipsize rather than wrap, because a two-line model name turns a three-row list into five. The note under the list is the credential answer said once for the page; the tier cards repeat it only when the three disagree.",
    render: () => <TierSummaryScene picks={MODEL_PICKS} previewByTier={MODEL_PREVIEW_OK} />,
  },
  {
    id: "model-setup-blocked",
    state: "Heavy has no key",
    group: "TierSummary",
    title: "A tier that cannot run, with the fold closed",
    note: "The state the redesign is most at risk of hiding: the cards that used to carry the warning are behind Customise now, so the summary has to say it. Heavy is struck through and the note names what serves its work instead. The card loses its tinted ground here — an amber border on a primary-tinted gradient reads as decoration rather than as a problem.",
    render: () => (
      <TierSummaryScene
        picks={{ ...MODEL_PICKS, heavy: "claude-opus-5" }}
        previewByTier={MODEL_PREVIEW_BLOCKED}
      />
    ),
  },
  {
    id: "model-tier-cards",
    state: "expanded — one runnable, one blocked",
    group: "TierCard",
    title: "The three tiers, customising",
    note: "Click a picker — the list must hang under its own trigger. It used to open at the viewport's bottom-left corner and read as a dead control, because Radix's default item-aligned positioning never resolves a selected item inside a SelectGroup and this is the app's only grouped select. The first card is the blocked case; the other two carry a credential chip because showSource is on, which only happens when the three tiers disagree about whose key pays.",
    render: () => (
      <div className="mt-tiers">
        {TIERS.map((tier, index) => (
          <TierCard
            key={tier.key}
            tier={tier}
            index={index}
            value={tier.key === "heavy" ? "claude-opus-5" : MODEL_PICKS[tier.key]}
            models={MODEL_CATALOGUE.models}
            providersById={MODEL_PROVIDERS}
            engine="v1"
            preview={MODEL_PREVIEW_BLOCKED[tier.key]}
            showSource={tier.key !== "heavy"}
            onChange={() => {}}
          />
        ))}
      </div>
    ),
  },
  {
    id: "model-advanced",
    state: "closed — open it",
    group: "AdvancedSettings",
    title: "The fold the page's second half went into",
    note: "The two switches left after the image row moved up into the setup card. Closed is the state to check first: the summary line has to say what is inside, because both are things somebody arrives looking for by name. Opening it toggles real preferences, so expect the fallback card to report itself unsaved when signed out — that is the state, not a bug.",
    render: () => (
      <AdvancedSettings ladder={TIERS.map((tier) => tier.label.message)} />
    ),
  },
  {
    id: "voice-sample",
    state: "each preset, and a language with no sample of its own",
    group: "VoiceSample",
    title: "What the writing preset actually means",
    note: "The profile page's one piece of evidence: the same finding in all three voices, so \"Practitioner\" is a thing you can read rather than a word you have to trust. Canned strings, no model call. Check the three read as genuinely different lengths and registers — if two look alike, the preset behind them is not worth offering — and that the untranslated-language notice says the preview is the limitation, not the agent.",
    render: () => (
      <div style={{ display: "grid", gap: 12, maxWidth: 640 }}>
        <VoiceSample preset="executive" />
        <VoiceSample preset="practitioner" />
        <VoiceSample preset="technical" />
        <VoiceSample preset="practitioner" language="Japanese" />
      </div>
    ),
  },
  {
    id: "change-set-card",
    state: "proposed with a blocked change · applied, auto-applied · applied with a change held for drift · rejected",
    group: "ChangeSetCard",
    title: "The human review gate",
    note: "The card an agent's proposed changes arrive inside, and the only place a change is approved, rejected or rolled back — so what it must always show is non-negotiable: the destructive flag, guardrail violations and preview errors in full, and whether a set arrived without a click. Check the status marks read as four distinct states at a glance (they were ✓ ✕ ↺ • as text until this pass) and that a long guardrail line wraps under its icon rather than beside it. The third card is an approval that went stale: the budget moved in Google Ads between approve and apply, so that row was held back and says why. The last two end on the person's own decision, \"You approved this\" or \"You rejected this\" with when, on a tinted strip: it is the one act in a thread only a human makes, so it reads as theirs, not as a badge that changed colour.",
    render: () => (
      <div style={{ display: "grid", gap: 16 }}>
        <ChangeSetCard changeSet={SAMPLE_CHANGE_SET} />
        <ChangeSetCard changeSet={SAMPLE_CHANGE_SET_APPLIED} />
        <ChangeSetCard changeSet={SAMPLE_CHANGE_SET_DRIFTED} />
        <ChangeSetCard changeSet={SAMPLE_CHANGE_SET_REJECTED} />
      </div>
    ),
  },
  {
    id: "telemetry-card",
    state: "on-by-default build · off-by-default build",
    group: "TelemetryCard",
    title: "The one data switch",
    note: "Renders `null` in every build without a DSN, which is why the panel is exported separately from the card that asks the shell — this scene passes the two answers the shell can give. What to check: the Sends / Never-sends columns stack rather than crush at phone width, the check is `text-success` and the exclusions are muted (a promise, not a warning), and that the two-line intro above them does not reflow into a third line in either state. The paragraph this replaced was seventy-two words.",
    render: () => (
      <div style={{ display: "grid", gap: 16, maxWidth: 520 }}>
        <TelemetryPanel enabled defaultOn onToggle={() => {}} />
        <TelemetryPanel enabled={false} defaultOn={false} onToggle={() => {}} />
      </div>
    ),
  },
  {
    id: "model-images",
    state: "auto · picked · picked but unreachable · nothing can draw",
    group: "TierSummary",
    title: "The Images row, in its four states",
    note: "Images is a fourth row in the setup card rather than a fold in Advanced, because it is a fourth thing Duct runs on your key. Top: nobody picked, and the option says what \"whichever key can draw\" currently resolves to — \"Auto\" alone would make the reader open another surface to find out. Second: an explicit pick, no note, because the row already says it. Third: a pick whose provider has no key — the server resolved past it, and the note has to admit that rather than show a model that will not run. Bottom: signed in with ChatGPT and nothing else. The note has to name the plan, because the OpenAI tile on the next tab is green and \"no key of yours can draw\" would read as a bug rather than as an answer.",
    render: () => (
      <div style={{ display: "grid", gap: 16 }}>
        <TierSummaryScene picks={MODEL_PICKS} previewByTier={MODEL_PREVIEW_OK} />
        <TierSummaryScene
          picks={MODEL_PICKS}
          previewByTier={MODEL_PREVIEW_OK}
          imagePick="gemini-3-pro-image"
          images={{ provider: "google_genai", model: "gemini-3-pro-image", source: "env" }}
        />
        <TierSummaryScene
          picks={MODEL_PICKS}
          previewByTier={MODEL_PREVIEW_OK}
          imagePick="gpt-image-2.5-flare"
          images={{ provider: "google_genai", model: "gemini-3.1-flash-image", source: "env" }}
        />
        <TierSummaryScene
          picks={MODEL_PICKS}
          previewByTier={MODEL_PREVIEW_OK}
          providersById={MODEL_PROVIDERS_ON_PLAN}
          images={{ provider: null, model: null, source: "none" }}
        />
      </div>
    ),
  },

  // ------------------------------------------------------------------ Shots
  // One customer's week, the same in every frame: these four scenes are what
  // scripts/shots captures for the README, from the story in
  // lib/__fixtures__/solo-story.mjs. They double as the richest examples of
  // each component, so they stay here even between screenshot runs.
  {
    id: "shot-change-set",
    state: "proposed — one destructive, one blocked by a guardrail",
    group: "ChangeSetCard",
    title: "The review card, from the story",
    note: "The change the insights agent proposes in Solo's week: a pause (destructive, so it asks), two negatives, and a budget raise the account's 25% guardrail blocks. Same object the session emits. What to check: one colour per row at most, the approve button is the plain primary even with a pause in the set, and the footer line says how many changes wait on a person.",
    render: () => (
      <div data-shot style={{ maxWidth: 680 }}>
        <ChangeSetCard changeSet={STORY_CHANGE_SET} />
      </div>
    ),
  },
  {
    id: "shot-chatgpt-card",
    state: "openai, signed in with a ChatGPT plan",
    group: "ProviderCard",
    title: "Continue with ChatGPT, signed in",
    note: "The desktop variant needs the shell: scripts/shots installs a `window.__TAURI__` stub that answers get_shell_info and chatgpt_status before the page loads. In a plain browser this renders the web variant (steps plus the download). Click the tile to open the dialog.",
    render: () => (
      <div className="conn-grid">
        <ProviderCard
          provider={PROVIDERS.find((p) => p.id === "openai")}
          logo={LOGOS.openai}
          status={{ id: "openai", source: "subscription", reachable: true, stored: false }}
        />
      </div>
    ),
  },
  {
    id: "shot-memory-timeline",
    state: "eight memories: one superseded, one pinned, one unconfirmed",
    group: "MemoryTimeline",
    title: "What Duct remembers about Solo",
    note: "The rows the insights agent recalls in the session. One goal was raised from 700 to 900, so the old value is shown superseded rather than deleted; the CPA target is pinned; the watch the agent wrote this week is still unconfirmed. Every write here is a no-op.",
    render: () => <StoryMemoryScene />,
  },
  {
    id: "shot-connectors",
    state: "five connected, four waiting",
    group: "ConnectorTile",
    title: "Solo's connections",
    note: "The stack behind the story week: the five sources the insights agent pulls, connected and saved to the account, beside four it has not needed yet. Real logos, the page's own descriptions. What to check: three tiles per row at 1040px, connected and not-connected read as different at a glance without the dot doing all the work.",
    render: () => (
      <div className="conn-grid" data-shot style={{ padding: 24 }}>
        {STORY_CONNECTORS.map((c) => (
          <ConnectorTile
            key={c.id}
            logo={LOGOS[c.id]}
            title={c.title}
            description={c.description}
            tone={c.connected ? "on" : "off"}
            status={c.connected ? "Connected" : "Not connected"}
            storage={c.connected ? STORAGE_CLOUD : STORAGE_NONE}
            onClick={() => {}}
          />
        ))}
      </div>
    ),
  },
  {
    id: "shot-plan-board",
    state: "one week: two posted, one drafted, two planned",
    group: "PlanKanban",
    title: "The story week on the board",
    note: "The plan the content agent writes in the story, with the posts it links to. Covers come from the shots mock (MEDIA_DIR); in a plain dev server the two posted cards and the draft show the no-image state instead. The empty Discarded lane is not rendered.",
    render: () => (
      <div style={{ height: 640, display: "flex" }}>
        <PlanKanban plan={STORY_PLAN} postsById={STORY_POSTS} />
      </div>
    ),
  },
  // One question, the sources read, the answer: the transcript with nothing
  // around it. Three audiences ask the story week three things; the copy
  // comes from the story so the card never says something the session does not.
  ...Object.entries(STORY_ANSWERS).map(([key, a]) => ({
    id: `shot-answer-${key}`,
    state: `${key} · ${a.sources.length} sources read`,
    group: "AgentChat",
    title: `An answer, alone: ${a.question}`,
    note: "The rows of a session with the workspace removed: the user bubble, the memories it opened with, the collected-source steps done, the assistant bubble. 600px wide so the capture lands near 3:2, the landing pages' card window; wider and the crop takes the question. What to check: the user bubble stays at 82% and right-aligned, the steps read as muted history not live progress, and bold inside the answer is one span per finding, never a whole paragraph.",
    render: () => (
      <div data-shot style={{ maxWidth: 600, padding: "20px 20px 8px" }} className="bg-card">
        <TranscriptRow msg={{ role: ChatRow.USER, text: a.question }} />
        <TranscriptRow msg={{ role: ChatRow.MEMORY_RECALL, memories: a.recalled.map((id) => { const m = STORY_MEMORIES.find((x) => x.id === id); return { id, memory_id: id, title: m.title, kind: m.kind }; }) }} />
        <div className="mb-4">
          <StepProgress steps={a.sources.map((s, i) => ({ step_id: `collect_source_data:${s.id}:${i}`, label: s.label, status: StepStatus.SUCCESS, connector_id: s.id }))} />
        </div>
        <TranscriptRow msg={{ role: ChatRow.ASSISTANT, text: a.answer }} />
      </div>
    ),
  })),
  {
    id: "audit-report-v1",
    group: "Audit",
    title: "SEO report (V1)",
    state: "A full report, so the document decision can be seen",
    note:
      "Solo's audit from the story: nine categories, every finding on a page with a value, five priorities, a three-phase plan. (The lead-magnet page shows the same audit as the document the agent hands over, AUDIT_REPORT_HTML in the story, in the briefs' language; scripts/shots captures that one straight from the HTML.) This is a printed thing rather than app chrome: it declares `color-scheme: light` and redefines the semantic tokens for its own subtree, so it looks the same in a dark app as in a light one. It used to take its ground from the theme while painting sixty fixed hexes inside it, which put the finding titles at 1.11:1 in dark. Open this scene in a DARK frame — that is the whole point of it.",
    render: () => <AuditReportV1 data={STORY_AUDIT} />,
  },
  {
    id: "clone-dialog",
    state: "empty — nothing pasted yet",
    group: "Clone a TikTok",
    title: "Paste a post that worked",
    note: "Opened from the Posts tab. What to check: the field has a visible label, the hint under it says the clone is always a carousel, and Draft a clone is the rightmost action. Nothing is fetched here; the session does the rest.",
    render: () => <CloneDialogScene />,
  },
  {
    id: "clone-dialog-share-link",
    state: "error — a share link, which carries no post id",
    group: "Clone a TikTok",
    title: "A vm.tiktok.com link, refused with what to do instead",
    note: "The server refuses the same link with a 422 (service/clone_reference.py); this says so before a session starts. The error replaces the hint rather than stacking under it, so the dialog does not grow, and the field is aria-invalid.",
    render: () => <CloneDialogScene initialValue="https://vm.tiktok.com/ZMabc123/" />,
  },
  {
    id: "clone-source",
    state: "in niche and proven — a close copy",
    group: "Clone a TikTok",
    title: "Where a cloned post came from",
    note: "Sits in the post viewport between the image bar and the caption. The author links out to the reference; the chip is the approach the server derived from the clone's fit × proof call, not something the model typed.",
    render: () => (
      <div style={{ maxWidth: 672, padding: 24 }}>
        <CloneSourceNote source={CLONE_SOURCE} />
      </div>
    ),
  },
  {
    id: "clone-source-inferred",
    state: "out of niche, the reading failed, no author",
    group: "Clone a TikTok",
    title: "A clone whose reference could only be inferred",
    note: "The diagnosis call failed, so there is no why-it-worked line, and the saved post named no author. The note still says what it was modelled on and how closely, and the link falls back to the word TikTok. An href that is not a TikTok post link is dropped, not rendered.",
    render: () => (
      <div style={{ maxWidth: 672, padding: 24 }}>
        <CloneSourceNote
          source={{
            url: "https://www.tiktok.com/@x/video/7300000000000000009",
            approach: "structure_only",
            kept: "Only the before-and-after structure: the reference was about skincare, the brand is about haircuts.",
          }}
        />
      </div>
    ),
  },
];

const CLONE_SOURCE = {
  reference_asset_id: "5c0f2a57-0000-4000-8000-000000000001",
  url: "https://www.tiktok.com/@kestrel.studio/video/7300000000000000001",
  author: "kestrel.studio",
  why_it_worked: "Slide 4 is a self-test people save: it names the viewer's face shape and the one cut that flatters it, so the post is a tool they come back to rather than a tip they scroll past.",
  fit: "in_niche",
  proof: "proven",
  approach: "close",
  kept: "The identity-call hook, one face shape per slide, and the self-test on slide 4, because at 42× the creator's following the format carried it.",
};

/** The clone dialog, open on arrival; the button brings it back after Escape. */
function CloneDialogScene({ initialValue = "" }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>Open the clone dialog</Button>
      <CloneFromUrlDialog open={open} onOpenChange={setOpen} onClone={() => setOpen(false)} initialValue={initialValue} />
    </>
  );
}


/**
 * One audit report, enough of it to judge the layout and the theming.
 * Deliberately not a trimmed stub: the rows that break are a category with no
 * failures, a finding with affected URLs, and a phase whose tasks carry an
 * effort estimate.
 */
function StoryMemoryScene() {
  const api = useMemo(() => {
    const items = STORY_MEMORIES.map((m) => ({ ...m })).sort((a, b) => (a.observed_at < b.observed_at ? 1 : -1));
    const kinds = Array.from(new Set(items.map((m) => m.kind))).sort();
    const noop = async () => ({});
    return {
      list: async ({ q = "", kind = "", includeSuperseded = true } = {}) => ({
        items: items.filter(
          (m) =>
            (includeSuperseded || m.status !== "superseded") &&
            (!kind || m.kind === kind) &&
            (!q || `${m.title} ${m.body}`.toLowerCase().includes(q.toLowerCase())),
        ),
        kinds,
        memory_paused: false,
      }),
      get: async ({ memoryId }) => items.find((m) => m.id === memoryId) || null,
      create: noop, patch: noop, remove: noop, reset: noop, setPaused: noop,
    };
  }, []);
  return (
    <div style={{ maxWidth: 880, padding: 24 }}>
      <MemoryTimeline api={api} kinds={MEMORY_KINDS} defaultKind="goal" />
    </div>
  );
}
