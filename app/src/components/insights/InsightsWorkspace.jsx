"use client";

/**
 * The insights session UI — one chat, no wizard.
 *
 * What it replaces: a six-step form (sources → Ads account → GA4 property →
 * GSC site → goal → review) that had to be completed before the agent ran at
 * all. Everything that form collected, the agent now discovers or asks for
 * mid-run, so most of what this component renders is *a pause*: a question, a
 * connect offer, or an account choice, inline in the transcript.
 *
 * The session itself — create, stream, reconnect, resume, the pause cards,
 * retry — is `useAgentSession`, the same hook the content and audit
 * workspaces run on. Opening a stored thread resumes it: the transcript is
 * rehydrated, a question the thread is still parked on comes back as its
 * card, and a run that was cut mid-turn picks up where it stopped. Nothing
 * here re-runs a prompt because the tab was reloaded.
 *
 * The right pane is the deliverable. The agent writes its brief inside
 * `<duct_artifact>`, which streams — so the pane fills in as the brief is
 * written, then settles into a stored version when the tag closes. Versions
 * accumulate within a session; the picker appears once there is a second one.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Database, Download, FileText, LayoutGrid, Maximize2, Minimize2 } from "lucide-react";
import { msg } from "@lingui/core/macro";
import { Plural, Trans, useLingui } from "@lingui/react/macro";
import { ActivityRow } from "@/components/workspace/ActivityRow";
import { CONNECTOR_NAMES, LOGOS } from "@/components/connections/logos";
import AgentChat from "@/components/workspace/AgentChat";
import EmptyState from "@/components/ui/empty-state";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { SkeletonDocument } from "@/components/ui/skeleton";
import ComposerDials, { TierDial } from "@/components/workspace/ComposerDials";
import SplitWorkspace from "@/components/workspace/SplitWorkspace";
import { AUTONOMY_ASK } from "@/lib/projectsApi";
import { getProjectById } from "@/lib/projects";
import { MarkdownView } from "@/components/artifacts/ArtifactRenderer";
import { ArtifactGallery } from "@/components/artifacts/ArtifactCards";
import { useAgentSession } from "../../hooks/useAgentSession";
import { getArtifactContent, listArtifacts, listArtifactVersions } from "../../lib/artifactsApi";
import { InsightsEvent } from "../../lib/insightsEvents";
import { briefFile, frontMatterTitle, sniffFormat, stripFrontMatter } from "../../lib/brief";
import { Row } from "../../lib/agentSession";
import { dataSourceRollup } from "../../lib/toolActivity";
import { loadPreferences } from "../../lib/userPreferences";
import { saveText } from "../../lib/download";

const AGENT_TYPE = "insights";
// `openedGroup` for the brief being written in this session, which has no
// stored group id until its first version lands.
const LIVE_GROUP = "live";

export default function InsightsWorkspace({
  projectId,
  initialPrompt = "",
  conversationId = "",
  artifactId = "",
}) {
  const { t } = useLingui();
  // The brief: every version this session produced, plus the one being written.
  const [versions, setVersions] = useState([]);
  const [selected, setSelected] = useState(-1);   // -1 = follow the latest
  const [writing, setWriting] = useState("");
  const [pane, setPane] = useState("brief");      // brief | data
  // The document alone, over the whole window.
  const [focused, setFocused] = useState(false);
  // Every document this thread has written (latest version per group), and
  // which one the pane is showing: null is the gallery, LIVE_GROUP is the
  // one being written in this session, otherwise a stored group's id.
  const [docs, setDocs] = useState([]);
  const [openedGroup, setOpenedGroup] = useState(null);
  const openedGroupRef = useRef(null);
  openedGroupRef.current = openedGroup;
  // Bumped when a version lands, so the gallery learns about the new group.
  const [docsRefresh, setDocsRefresh] = useState(0);
  // A later open supersedes an earlier one still loading.
  const openTokenRef = useRef(0);
  // What the pane is waiting on. `opening` is a document's versions on their
  // way in; `docsPending` is the thread's document list on a reopen, before
  // we know whether there is anything to show at all. Either way the pane
  // shows the shape of a brief rather than "Nothing written yet", which used
  // to flash for the half-second before the brief you came back for arrived.
  const [opening, setOpening] = useState(false);
  const [docsPending, setDocsPending] = useState(Boolean(conversationId));
  // Streamed brief text also lives in a ref: the event callback would
  // otherwise close over a stale value on every chunk.
  const briefRef = useRef("");
  // The posture this conversation runs at. Seeded from the stored project,
  // corrected by PIPELINE_STARTED (the backend may step it down for the
  // model), and changed from the composer chip — which writes the project
  // and reaches the agent at its next message.
  const [autonomy, setAutonomy] = useState(
    () => (projectId && getProjectById(projectId)?.autonomyLevel) || AUTONOMY_ASK,
  );

  const body = useMemo(
    () => ({
      project_id: projectId || null,
      prompt: initialPrompt,
      // Resuming extends the stored thread rather than opening a second one,
      // so the brief keeps versioning up from where it left off.
      ...(conversationId ? { conversation_id: conversationId, resume: true } : {}),
      // Carries the deliverable format the agent should write in, among the
      // rest of the profile.
      user_preferences: loadPreferences(),
    }),
    [projectId, initialPrompt, conversationId],
  );

  const onEvent = useCallback((event) => {
    switch (event.event) {
      case InsightsEvent.ARTIFACT_CHUNK:
        // The brief, arriving. Show it being written rather than waiting for
        // the closing tag — a long brief is a long silence otherwise.
        briefRef.current += event.text || "";
        setWriting(briefRef.current);
        setPane("brief");
        break;
      case InsightsEvent.ARTIFACT_VERSION: {
        briefRef.current = "";
        setWriting("");
        const payload = event.payload || {};
        const versionId = event.version_id;
        setVersions((prev) => [
          ...prev.filter((v) => v.version !== versionId),
          {
            version: versionId,
            // Fallback words are put on at render, where the locale is known.
            label: event.label || "",
            title: payload.title || "",
            format: payload.format || "markdown",
            content: payload.content || "",
          },
        ].sort((a, b) => a.version - b.version));
        setSelected(-1);  // a new version is what you want to be looking at
        setOpenedGroup(LIVE_GROUP);
        setDocsRefresh((n) => n + 1);
        setPane("brief");
        break;
      }
      default:
        break;
    }
  }, []);

  const agent = useAgentSession({
    agentType: AGENT_TYPE,
    notifyAs: t`Insights`,
    body,
    // A thread by its id, a fresh question by its text: a different question
    // in the same tab is a different run, and a reload of this one is this one.
    handleKey: `${AGENT_TYPE}:${projectId || ""}:${conversationId || `q:${initialPrompt}`}`,
    hydrateThreadState: true,
    onEvent,
  });

  // The Data tab is the transcript's own rows, rolled up: every source this
  // thread read, grouped by connector. It fills from the same activity rows
  // the chat shows — live and on a reopened thread alike — so the two can no
  // longer disagree about what the agent read, which is what happened while
  // one filled from step events and the other from stored tool traffic.
  const sources = useMemo(
    () => dataSourceRollup((agent.messages || []).filter((m) => m.role === Row.ACTIVITY).map((m) => m.activity)),
    [agent.messages],
  );

  useEffect(() => {
    const level = agent.started?.autonomy;
    if (level) setAutonomy(level);
  }, [agent.started?.autonomy]);

  // Put a stored document in the right pane: every version of its group,
  // newest selected. `id` is any version's id; the route resolves the group.
  const openGroup = useCallback(async (id) => {
    const token = ++openTokenRef.current;
    setOpening(true);
    try {
      const rows = await listArtifactVersions(id);
      const ordered = [...rows].sort((a, b) => a.version - b.version);
      const loaded = await Promise.all(
        ordered.map(async (row) => {
          let content = "";
          try {
            content = row.has_content ? await getArtifactContent(row.id) : "";
          } catch {
            /* a version whose bytes are gone still belongs in the picker */
          }
          return {
            version: row.version,
            label: `Version ${row.version}`,
            title: row.title || "Growth brief",
            // The stored MIME type is authoritative; sniffing is the fallback
            // for rows written before content_type was recorded.
            format: (row.content_type || "").includes("html") ? "html" : sniffFormat(content),
            content,
          };
        }),
      );
      if (token !== openTokenRef.current) return;
      setVersions(loaded);
      setSelected(-1);
      setOpenedGroup(ordered[0]?.group_id || id);
      setPane("brief");
    } catch {
      /* the thread still opens; the pane just starts empty */
    } finally {
      // Only the newest open owns the flag; a superseded one must not clear
      // it under the load that replaced it.
      if (token === openTokenRef.current) setOpening(false);
    }
  }, []);

  // From the desk, where opening a brief means opening the thread that
  // argued for it: the named document goes straight into the pane.
  useEffect(() => {
    if (artifactId) openGroup(artifactId);
  }, [artifactId, openGroup]);

  // A thread's documents are its own whether it was reopened or started in
  // this tab. Listing only the reopened ones left a live session with no way
  // to reach the gallery, however many briefs it had written by then.
  const threadId = conversationId || agent.conversationId;

  // Reopening a thread by id alone used to leave the pane empty however many
  // briefs the thread had written — only the desk's ?artifact= link loaded
  // one. Now the thread's documents are listed on open: one is shown as it
  // was, several become the gallery, and nothing needs a click to see the
  // brief you came back for.

  useEffect(() => {
    if (!threadId || !projectId) {
      setDocsPending(false);
      return undefined;
    }
    let cancelled = false;
    listArtifacts({ projectId, agentType: AGENT_TYPE, conversationId: threadId })
      .then((rows) => {
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setDocs(list);
        if (!artifactId && list.length === 1 && openedGroupRef.current === null) {
          openGroup(list[0].id);
        }
      })
      .catch(() => {
        /* the list is a convenience; the thread still opens */
      })
      .finally(() => {
        if (!cancelled) setDocsPending(false);
      });
    return () => { cancelled = true; };
  }, [threadId, projectId, artifactId, docsRefresh, openGroup]);

  // The bytes are already here, so saving one is a rename rather than a
  // fetch — which also means a version still streaming could be saved, and a
  // stored one needs no round trip.
  function downloadBrief() {
    if (!shown?.content) return;
    const file = briefFile(shown, t`Growth brief`);
    saveText(shown.content, file.name, file.type);
  }

  function showGallery() {
    openTokenRef.current += 1;  // drop a load still in flight
    setOpening(false);
    setOpenedGroup(null);
    setVersions([]);
    setSelected(-1);
    setPane("brief");
  }

  function handleRetry() {
    setWriting("");
    briefRef.current = "";
    agent.retry();
  }

  const shown = versions.length ? versions[selected < 0 ? versions.length - 1 : selected] : null;
  const hasBrief = Boolean(shown) || Boolean(writing);
  // A document on its way in, or a reopened thread whose list has not come
  // back yet: the pane keeps a brief's shape rather than declaring it empty.
  const loadingBrief = !writing && (opening || (docsPending && !hasBrief));
  // The gallery is where the thread's documents live. It opens by itself only
  // when there is a choice to make; with one document the pane shows it, and
  // the header's own button is how you get back to the shelf.
  const gallery = docs.length > 0 && openedGroup === null && !writing && !opening;
  // The document's name and state. They belong to the pane header rather than
  // to a strip of its own: the strip under the tabs restated the version the
  // picker beside it already showed, and the document paid for both.
  const liveTitle = useMemo(() => frontMatterTitle(writing), [writing]);
  const docTitle = writing
    ? liveTitle || t`Writing…`
    : shown
      ? shown.title || t`Growth brief`
      : "";

  // A connect asked for mid-run comes back to this thread, resumed — never to
  // the ?q= form of this page, which would ask the question again from scratch.
  const connectReturnTo = useMemo(() => {
    const cid = agent.conversationId || conversationId;
    if (!cid) return "";
    const qs = new URLSearchParams({ conversation: cid });
    if (projectId) qs.set("project", projectId);
    return `/insights/session?${qs}`;
  }, [agent.conversationId, conversationId, projectId]);

  const questionsCopy = useMemo(
    () => ({ hint: t`Your answer decides what Duct looks at. Skip if you'd rather it choose.` }),
    [t],
  );

  const chat = (
    <AgentChat
      title={t`Insights`}
      phase={agent.phase}
      steps={agent.steps}
      todos={agent.todos}
      messages={agent.messages}
      pending={agent.pending}
      errorMsg={agent.error}
      errorCode={agent.errorCode}
      errorRetryable={agent.errorRetryable}
      retrying={agent.retrying}
      tierStepDown={agent.tierStepDown}
      usage={agent.usage}
      compacting={agent.compacting}
      draft={agent.draft}
      isAgentTyping={agent.isAgentTyping}
      isStreaming={agent.isStreaming}
      reconnecting={agent.reconnecting}
      inputDisabled={agent.inputDisabled}
      answerDisabled={!agent.attached}
      onAnswer={agent.answer}
      // The brief format rides on every message, so a dial change reaches
      // the agent now rather than at the next session; the backend restates
      // it to the thread only when it differs from what the thread has read.
      onSendMessage={(content) =>
        agent.send(content, { artifact_format: loadPreferences().preferred_artifact_format })
      }
      onRetrySend={agent.send}
      onRetry={handleRetry}
      onStop={() => agent.stop({ keepReady: agent.opened })}
      questionsCopy={questionsCopy}
      connectReturnTo={connectReturnTo}
      composerTools={
        <ComposerDials projectId={projectId} autonomy={autonomy} onAutonomyChange={setAutonomy} deferred />
      }
      composerAside={<TierDial deferred />}
      inputPlaceholder={t`Ask about your growth data…`}
      inputAriaLabel={t`Message the insights agent`}
      startingLabel={t`Opening the session…`}
      headerExtra={<AutonomyBadge autonomy={agent.started} level={autonomy} />}
    />
  );

  const viewport = (
    <div className="flex h-full min-h-0 flex-col">
      <ArtifactPaneHeader
        pane={pane}
        onPane={setPane}
        dataCount={sources.reduce((n, g) => n + g.rows.length, 0)}
        title={gallery ? t`All documents` : docTitle}
        status={writing ? t`being written` : gallery ? t`${docs.length} in this thread` : ""}
        docCount={gallery ? 0 : docs.length}
        onShowGallery={showGallery}
        onDownload={shown?.content ? downloadBrief : null}
        onFocus={shown?.content ? () => setFocused(true) : null}
        versions={gallery ? [] : versions}
        selected={selected}
        onSelect={setSelected}
      />

      {/* Each pane scrolls itself, so a document can fill the height it is
          given instead of being capped at a guessed 74vh inside a scroller
          that then had a second scrollbar of its own. */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {pane !== "brief" ? (
          <DataPane sources={sources} />
        ) : gallery ? (
          <div className="h-full overflow-y-auto bg-muted/30">
            <ArtifactGallery docs={docs} onOpen={(doc) => openGroup(doc.id)} />
          </div>
        ) : (
          <BriefPane brief={shown} writing={writing} empty={!hasBrief} loading={loadingBrief} />
        )}
      </div>

      <DocumentFocus
        open={focused && Boolean(shown?.content)}
        onOpenChange={setFocused}
        brief={shown}
        title={docTitle}
        sub={shown ? t`v${shown.version}` : ""}
        onDownload={downloadBrief}
      />
    </div>
  );

  return (
    <SplitWorkspace
      left={chat}
      right={viewport}
      storageKey="insights_split_w"
      leftLabel={t`Chat`}
      rightLabel={t`Artifact`}
      rightStatus={writing || agent.isRunning || loadingBrief ? "busy" : hasBrief ? "ready" : "idle"}
    />
  );
}

const AUTONOMY_LABELS = {
  ask: msg`Asks freely · nothing applies without you`,
  assisted: msg`Asks when it matters · allowlisted changes apply on their own`,
  auto: msg`Interrupts rarely · same allowlist as Assisted`,
};

/** Which mode this run is in, said before the first token.
 *
 * PIPELINE_STARTED carries `autonomy` (what the run got) and
 * `autonomy_configured` (what the project is set to). They differ when the
 * model driving it is not on the allowlist for `auto`, and saying so is the
 * difference between a considered step-down and an agent that mysteriously
 * keeps asking questions. */
function AutonomyBadge({ autonomy, level: current = "" }) {
  const { i18n } = useLingui();
  // The composer chip is the live value once the person touches it; the
  // event is what the run opened with.
  const level = current || autonomy?.autonomy || "";
  const configured = autonomy?.autonomy_configured || "";
  if (!level) return null;
  const steppedDown = configured && configured !== level && current === (autonomy?.autonomy || "");
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs">
      <span className="rounded-full bg-muted px-2 py-0.5 font-medium uppercase tracking-wide">{level}</span>
      <span className="hidden text-muted-foreground @md:inline">
        {AUTONOMY_LABELS[level] ? i18n._(AUTONOMY_LABELS[level]) : ""}
      </span>
      {steppedDown && (
        <span className="text-muted-foreground">
          <Trans>· set to <strong>{configured}</strong>, stepped down for this model</Trans>
        </span>
      )}
    </span>
  );
}

/**
 * The right pane's chrome, in one strip: which tab, which document, which
 * version, and the way back to the thread's shelf of documents.
 *
 * It used to be two strips — tabs, then a title line restating the version
 * the picker on the first line already named — above a document sitting in a
 * card inside a margin. Three nested surfaces for one page. Exported so
 * /preview can show the strip with the pane under it, which is the only way
 * to judge either.
 */
export function ArtifactPaneHeader({
  pane,
  onPane,
  dataCount = 0,
  title = "",
  status = "",
  docCount = 0,
  onShowGallery,
  onDownload,
  onFocus,
  versions = [],
  selected = -1,
  onSelect,
}) {
  const { t } = useLingui();
  const onBrief = pane === "brief";
  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-border/60 px-2 py-1.5">
      <PaneTab active={onBrief} onClick={() => onPane("brief")}>
        <Trans>Artifact</Trans>
      </PaneTab>
      <PaneTab active={pane === "data"} onClick={() => onPane("data")}>
        <Trans>Data</Trans>{dataCount ? ` · ${dataCount}` : ""}
      </PaneTab>

      {onBrief && (title || status) && (
        // Below a pane of ~28rem the title truncated to three letters while
        // still taking the room the controls needed, so it stands down.
        <p className="ml-1 hidden min-w-0 flex-1 items-baseline gap-1.5 border-l border-border/60 pl-2.5 @md:flex">
          <span className="truncate text-xs font-medium" title={title}>{title}</span>
          {status && <span className="shrink-0 text-2xs text-muted-foreground">{status}</span>}
        </p>
      )}

      <div className="ml-auto flex shrink-0 items-center gap-1">
        {onBrief && docCount > 0 && onShowGallery && (
          // The shelf. A thread writes several documents and the pane shows
          // one; without this the others were reachable only by reopening the
          // thread, and in a live session not at all.
          <button
            type="button"
            onClick={onShowGallery}
            aria-label={t`All documents in this thread`}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-2xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LayoutGrid className="size-3.5" aria-hidden="true" />
            <span className="hidden @md:inline"><Trans>All documents</Trans></span>
            <span className="tabular-nums">{docCount}</span>
          </button>
        )}
        {onBrief && onDownload && (
          <IconAction icon={Download} label={t`Download this document`} onClick={onDownload} />
        )}
        {onBrief && onFocus && (
          // Reading, rather than working: the document over the whole window,
          // with the chat, the rail and the rest of the app out of the way.
          <IconAction icon={Maximize2} label={t`Read full screen`} onClick={onFocus} />
        )}
        {onBrief && versions.length > 1 && (
          <select
            value={selected < 0 ? versions.length - 1 : selected}
            aria-label={t`Artifact version`}
            onChange={(e) => onSelect(Number(e.target.value))}
            // The global select reset draws its chevron 0.75rem from the
            // right edge; `px-2` put the label underneath it, which is why
            // this one read "v2 — Update⌄2".
            className="max-w-[11rem] truncate rounded-md border border-input bg-background py-1 pl-2 pr-7 text-2xs"
          >
            {versions.map((v, i) => {
              const version = v.version;
              const label = v.label || t`Version ${version}`;
              return (
                <option key={version} value={i}>
                  {t`v${version} — ${label}`}
                </option>
              );
            })}
          </select>
        )}
      </div>
    </div>
  );
}

// A square control in a strip: 1.75rem, which clears the 24px WCAG target and
// still sits quietly beside a tab. The class is shared because the focus
// view's close button is the same control wrapped in `DialogClose`.
const ICON_ACTION =
  "flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground";

/** Icon, no label; the name is the tooltip and the accessible name. */
function IconAction({ icon: Icon, label, onClick }) {
  return (
    <button type="button" onClick={onClick} title={label} aria-label={label} className={ICON_ACTION}>
      <Icon className="size-3.5" aria-hidden="true" />
    </button>
  );
}

function PaneTab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      // `shrink-0` and no wrapping: in a narrow pane beside the document
      // controls, "Data · 2" folded onto two lines and took the strip with it.
      className={`shrink-0 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

/** The deliverable. A finished version when there is one, otherwise the one
 *  being written — which is the same document a few seconds earlier.
 *
 *  The document is the pane: full height, full bleed, no card. What sat here
 *  before was a rounded card inside a 1rem margin inside a muted scroller,
 *  with an HTML brief pinned to 74vh inside that — chrome around chrome, and
 *  a second scrollbar, for a page that only ever wanted the room. */
// Exported for /preview only, the UsagePanel/UsageEmpty precedent: these two
// panes' empty states are the states a reviewer most needs to open and the
// ones no fixture-free gallery could otherwise reach.
export function BriefPane({ brief, writing, empty, loading }) {
  const { t } = useLingui();
  // While it streams there is no parsed version yet, so the front matter has
  // to come off here and the format has to be read from the bytes.
  const live = useMemo(() => stripFrontMatter(writing), [writing]);

  if (writing) {
    return (
      <DocumentPage>
        {sniffFormat(live) === "markdown" ? (
          <MarkdownView source={live} className="max-w-none px-6 py-5" />
        ) : (
          <pre className="whitespace-pre-wrap px-6 py-5 text-xs">{live}</pre>
        )}
      </DocumentPage>
    );
  }

  if (loading && !brief) {
    return (
      // The page's own anatomy, drawn in skeleton. It swaps texture for words
      // when the bytes land, and never claims the thread is empty while the
      // answer is still on its way.
      <DocumentPage>
        <SkeletonDocument className="px-6 py-5" label={t`Loading the brief`} />
      </DocumentPage>
    );
  }

  if (empty || !brief) {
    return (
      // No CTA on purpose, which is the one case ui/empty-state allows. What
      // fills this pane is the agent deciding an answer is worth keeping, and
      // the control for that is the composer already on screen beside it — a
      // button here could only say "go and type over there".
      <div className="h-full overflow-y-auto p-4">
        <EmptyState icon={FileText} title={t`Nothing written yet`}>
          <Trans>
            An answer worth keeping becomes an artifact here, and versions pile up as it is
            rewritten.
          </Trans>
        </EmptyState>
      </div>
    );
  }

  const title = brief.title || t`Growth brief`;
  if (brief.format === "html") {
    return (
      <iframe
        title={title}
        srcDoc={brief.content}
        // See ArtifactRenderer: scripts on, same-origin off.
        sandbox="allow-scripts allow-modals"
        className="h-full w-full border-0 bg-white"
      />
    );
  }
  return (
    <DocumentPage>
      <MarkdownView source={brief.content} className="max-w-none px-6 py-5" />
    </DocumentPage>
  );
}

/**
 * The document, alone, over the window.
 *
 * A brief is a thing to read, and reading it in a pane beside a transcript is
 * reading it in the corner of a working screen. This is the same `BriefPane`,
 * so there is one renderer and no second copy of the markdown and iframe
 * rules — on the app's dialog, so the portal, the focus trap, Escape and the
 * scroll lock come with it. The portal is the load-bearing part: the pane
 * declares `container-type`, and a `fixed` overlay rendered inside one is
 * positioned against the pane rather than the window.
 */
export function DocumentFocus({ open, onOpenChange, brief, title = "", sub = "", onDownload }) {
  const { t } = useLingui();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        // Pinned to all four edges, not centred-and-sized. `inset-0` alone
        // defines the box, so there is no width or height for the browser to
        // resolve and nothing to fall back to: a fixed box that is given a
        // centre and a size shrinks to fit its own header the moment one of
        // those utilities does not reach it, which is a narrow column of
        // document in the middle of the window.
        className="inset-0 h-auto max-h-none w-auto max-w-none translate-x-0 translate-y-0 overflow-hidden rounded-none border-0 bg-background p-0"
      >
        <DialogTitle className="sr-only">{title || t`Document`}</DialogTitle>
        {/* Everything the reader needs and nothing else: what this is, a way
            to keep it, a way out. No tabs, no version picker — those are for
            working with documents, and this is for reading one. */}
        <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-3 py-1.5">
          <span className="truncate text-xs font-medium">{title}</span>
          {sub && <span className="shrink-0 text-2xs text-muted-foreground">{sub}</span>}
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {onDownload && (
              <IconAction icon={Download} label={t`Download this document`} onClick={onDownload} />
            )}
            <DialogClose asChild>
              <button
                type="button"
                title={t`Leave full screen`}
                aria-label={t`Leave full screen`}
                className={ICON_ACTION}
              >
                <Minimize2 className="size-3.5" aria-hidden="true" />
              </button>
            </DialogClose>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <BriefPane brief={brief} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** The page a written brief sits on. One surface, floor to ceiling, centred
 *  on a muted desk when the pane is wider than a column of text is worth —
 *  which is the whole distinction from the chat beside it, since `card` and
 *  `background` are the same white in the light theme. */
function DocumentPage({ children }) {
  return (
    <div className="h-full overflow-y-auto bg-muted/30">
      <div className="mx-auto min-h-full w-full max-w-3xl bg-card">{children}</div>
    </div>
  );
}

/**
 * Every source this thread read, grouped by connector.
 *
 * The transcript says what the agent did and when; this says what it has, in
 * one place, which is the question you ask after forty turns rather than
 * during them. Both are the same rows — `dataSourceRollup` over the
 * transcript's activity cards — so the pane cannot claim a pull the chat
 * never showed.
 */
export function DataPane({ sources }) {
  const { i18n, t } = useLingui();
  if (!sources?.length) {
    return (
      // This one does get a CTA, because its most common cause is actionable:
      // the pane stays empty for a whole thread when nothing is connected, and
      // that is the state the agent spends the conversation apologising for.
      <div className="h-full overflow-y-auto p-4">
        <EmptyState
          icon={Database}
          title={t`No sources pulled yet`}
          actions={
            <Button size="sm" variant="outline" asChild>
              <Link href="/connections"><Trans>Check connections</Trans></Link>
            </Button>
          }
        >
          <Trans>
            Each source Duct reads shows up here with the period it covers, and the provider’s
            own words when a pull fails.
          </Trans>
        </EmptyState>
      </div>
    );
  }
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      {sources.map((group) => {
        const name = CONNECTOR_NAMES[group.source]
          ? i18n._(CONNECTOR_NAMES[group.source])
          : String(group.source || "").replace(/_/g, " ");
        return (
          // A heading and its rows, not a card: the connector is named once,
          // at the top, and each pull under it is the transcript's own row
          // with the name left off — one vocabulary, two places to meet it.
          <section key={group.source}>
            <header className="flex items-center gap-2 px-1 pb-1">
              <span className="flex size-4 items-center justify-center [&_img]:size-4 [&_svg]:size-4">
                {LOGOS[group.source] || <Database className="size-3.5" aria-hidden="true" />}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs font-medium">{name}</span>
              <span className="shrink-0 text-2xs text-muted-foreground">
                {group.failed > 0 ? (
                  <Trans>{group.ok} read · {group.failed} failed</Trans>
                ) : (
                  <Plural value={group.ok} one="# pull" other="# pulls" />
                )}
              </span>
            </header>
            <div className="border-l border-border/60 pl-2">
              {group.rows.map((row) => (
                <ActivityRow key={row.id} activity={row} named={false} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
