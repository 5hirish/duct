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

import { useState } from "react";

import ContextCompressionCard from "@/components/ContextCompressionCard.jsx";
import { CornerNotice } from "@/components/ui/corner-notice";
import { FolderOpen, RefreshCw } from "lucide-react";
import { CookieConsent } from "@/components/CookieConsent";
import LoadError from "@/components/LoadError";
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

export const SCENES = [
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
